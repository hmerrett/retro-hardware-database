"""Physical donor-board movement and provenance behaviour."""
from datetime import datetime

import pytest
from sqlalchemy.exc import DBAPIError

from app import donor, inventory
from app.models import (BomComponent, BomPosition, ComponentEvent, InventoryItem,
                        InventoryLot, Part, PartBom, PartBomPositionState,
                        ReferenceBom, StorageLocation)


def _board(db, part, *, refdes="U2", model="Board", component=None):
    component = component or BomComponent(generic_name="6526 CIA")
    reference = ReferenceBom(name=f"{model} reference", status="draft")
    db.add(reference)
    if component.id is None:
        db.add(component)
    db.flush()
    position = BomPosition(reference_bom_id=reference.id, refdes=refdes,
                           component_id=component.id, expected="6526 CIA")
    db.add(position)
    saved = part(type="motherboard", model=model)
    db.add(PartBom(part_id=saved["asset_id"], reference_bom_id=reference.id))
    db.commit()
    return db.get(Part, saved["asset_id"]), reference, position, component


class TestDonorSetup:
    @pytest.mark.parametrize(("baseline", "effective"), [
        ("expected-populated", "present"),
        ("empty", "missing"),
    ])
    def test_setup_uses_the_board_baseline_without_position_rows(
            self, db, part, baseline, effective):
        board, reference, position, _component = _board(db, part)

        link = donor.setup_board(db, board.asset_id, baseline)
        db.commit()

        assert board.board_role == "donor"
        assert link.baseline_state == baseline
        assert donor.effective_position_state(link, None) == effective
        assert db.query(PartBomPositionState).count() == 0
        assert reference.status == "draft"
        assert db.get(BomPosition, position.id).expected == "6526 CIA"

    def test_database_rejects_an_unknown_board_role(self, db, part):
        board, _reference, _position, _component = _board(db, part)
        board.board_role = "parts-bin"

        with pytest.raises(DBAPIError):
            db.commit()
        db.rollback()

    def test_sparse_exception_does_not_change_the_reference_bom(self, db, part):
        board, reference, position, _component = _board(db, part)
        donor.setup_board(db, board.asset_id, "expected-populated")

        state = donor.set_position_state(
            db, board.asset_id, position.id, "damaged", notes="leg missing")
        db.commit()

        assert state.state == "damaged"
        assert db.query(PartBomPositionState).count() == 1
        assert db.get(ReferenceBom, reference.id).status == "draft"
        assert db.get(BomPosition, position.id).expected == "6526 CIA"


class TestHarvest:
    def test_harvest_creates_traceable_stock_and_provenance(self, db, part):
        board, _reference, position, component = _board(db, part)
        drawer = StorageLocation(name="IC Drawer 4")
        db.add(drawer)
        db.flush()
        donor.setup_board(db, board.asset_id, "expected-populated")

        item = donor.harvest_position(
            db, board.asset_id, position.id, storage_location_id=drawer.id,
            item_code="CIA-001")
        db.commit()

        state = db.query(PartBomPositionState).one()
        event = db.query(ComponentEvent).filter_by(event_type="harvested").one()
        lot = db.get(InventoryLot, item.lot_id)
        assert state.state == "removed"
        assert item.lifecycle_status == "inventory"
        assert lot.quantity == 1
        assert db.query(InventoryItem).filter_by(lot_id=lot.id).count() == 1
        assert inventory.usable_quantity_for_component(db, component.id) == 1
        assert (event.source_part_id, event.source_position_id) == (
            board.asset_id, position.id)
        assert event.inventory_item_id == item.id
        assert event.destination_storage_location_id == drawer.id

    def test_second_harvest_is_rejected_without_partial_rows(self, db, part):
        board, _reference, position, _component = _board(db, part)
        donor.setup_board(db, board.asset_id, "expected-populated")
        donor.harvest_position(db, board.asset_id, position.id, item_code="ONE")
        db.commit()
        counts = (db.query(InventoryLot).count(), db.query(InventoryItem).count(),
                  db.query(ComponentEvent).count())

        with pytest.raises(ValueError, match="no component"):
            donor.harvest_position(db, board.asset_id, position.id, item_code="TWO")

        assert counts == (db.query(InventoryLot).count(),
                          db.query(InventoryItem).count(),
                          db.query(ComponentEvent).count())

    def test_exact_existing_lot_receives_the_harvested_unit(self, db, part):
        board, _reference, position, component = _board(db, part)
        lot = InventoryLot(component_id=component.id, quantity=2,
                           condition="pulled", test_status="untested")
        db.add(lot)
        donor.setup_board(db, board.asset_id, "expected-populated")
        db.commit()

        item = donor.harvest_position(
            db, board.asset_id, position.id, lot_id=lot.id, item_code="EXACT")
        db.commit()

        assert item.lot_id == lot.id
        assert lot.quantity == 3

    def test_unlike_existing_lot_is_rejected(self, db, part):
        board, _reference, position, _component = _board(db, part)
        other = BomComponent(generic_name="Different component")
        db.add(other)
        db.flush()
        lot = InventoryLot(component_id=other.id, quantity=2, condition="pulled")
        db.add(lot)
        donor.setup_board(db, board.asset_id, "expected-populated")
        db.commit()

        with pytest.raises(ValueError, match="exact identity"):
            donor.harvest_position(db, board.asset_id, position.id, lot_id=lot.id)

        assert lot.quantity == 2
        assert db.query(InventoryItem).count() == 0

    def test_database_failure_rolls_back_the_whole_harvest(self, db, part):
        board, _reference, position, _component = _board(db, part)
        existing_lot = InventoryLot(quantity=1)
        db.add(existing_lot)
        db.flush()
        inventory.add_inventory_item(db, existing_lot.id, item_code="DUPLICATE")
        donor.setup_board(db, board.asset_id, "expected-populated")
        db.commit()
        before = (db.query(InventoryLot).count(), db.query(InventoryItem).count(),
                  db.query(ComponentEvent).count())

        with pytest.raises(DBAPIError):
            donor.harvest_position(
                db, board.asset_id, position.id, item_code="DUPLICATE")

        assert before == (db.query(InventoryLot).count(),
                          db.query(InventoryItem).count(),
                          db.query(ComponentEvent).count())
        assert db.query(PartBomPositionState).count() == 0

    def test_wrong_bom_source_is_rejected_atomically(self, db, part):
        board, _reference, _position, _component = _board(db, part)
        other = ReferenceBom(name="Other reference", status="draft")
        db.add(other)
        db.flush()
        wrong = BomPosition(reference_bom_id=other.id, refdes="U99")
        db.add(wrong)
        db.flush()
        donor.setup_board(db, board.asset_id, "expected-populated")

        with pytest.raises(ValueError, match="does not belong"):
            donor.harvest_position(db, board.asset_id, wrong.id)

        assert db.query(InventoryLot).count() == 0
        assert db.query(InventoryItem).count() == 0
        assert db.query(ComponentEvent).count() == 0


class TestInstallation:
    def _harvested_item(self, db, part):
        source, _ref, source_position, component = _board(
            db, part, model="Donor")
        donor.setup_board(db, source.asset_id, "expected-populated")
        item = donor.harvest_position(
            db, source.asset_id, source_position.id, item_code="MOVE-001")
        db.commit()
        return source, source_position, component, item

    def test_available_item_installs_and_keeps_donor_provenance(self, db, part):
        source, source_position, component, item = self._harvested_item(db, part)
        target, _ref, target_position, _unused = _board(
            db, part, model="Repair target", component=component)
        donor.setup_board(db, target.asset_id, "empty", role="repair")

        state = donor.install_item(db, item.id, target.asset_id, target_position.id)
        db.commit()

        events = donor.provenance_events(db, item.id)
        assert state.inventory_item_id == item.id
        assert state.state == "present"
        assert item.lifecycle_status == "installed"
        assert [(e.event_type, e.source_part_id, e.source_position_id)
                for e in events[:1]] == [
                    ("harvested", source.asset_id, source_position.id)]
        assert events[-1].event_type == "installed"
        assert events[-1].destination_part_id == target.asset_id
        assert inventory.usable_quantity_for_component(db, component.id) == 0

    def test_installed_item_cannot_be_installed_or_moved_again(self, db, part):
        _source, _source_position, _component, item = self._harvested_item(db, part)
        first, _ref, first_position, _unused = _board(db, part, model="First target")
        donor.setup_board(db, first.asset_id, "empty", role="repair")
        donor.install_item(db, item.id, first.asset_id, first_position.id)
        db.commit()
        second, _ref2, second_position, _unused2 = _board(
            db, part, model="Second target")
        donor.setup_board(db, second.asset_id, "empty", role="repair")

        with pytest.raises(ValueError, match="not available"):
            donor.install_item(db, item.id, second.asset_id, second_position.id)
        with pytest.raises(ValueError, match="loose inventory"):
            inventory.move_inventory_item(db, item, item.lot_id)

    def test_harvesting_an_installed_item_reuses_its_identity(self, db, part):
        source, source_position, _component, item = self._harvested_item(db, part)
        target, _ref, target_position, _unused = _board(db, part, model="Target")
        donor.setup_board(db, target.asset_id, "empty", role="repair")
        donor.install_item(db, item.id, target.asset_id, target_position.id)
        db.commit()
        original_lot_id = item.lot_id
        original_quantity = db.get(InventoryLot, original_lot_id).quantity

        returned = donor.harvest_position(db, target.asset_id, target_position.id)
        db.commit()

        assert returned.id == item.id
        assert returned.lifecycle_status == "inventory"
        assert db.query(InventoryItem).count() == 1
        assert db.get(InventoryLot, original_lot_id).quantity == original_quantity
        events = donor.provenance_events(db, item.id)
        assert events[0].source_part_id == source.asset_id
        assert events[0].source_position_id == source_position.id

    def test_install_does_not_overwrite_an_observed_component(self, db, part):
        _source, _source_position, _component, item = self._harvested_item(db, part)
        target, _ref, target_position, _unused = _board(db, part, model="Occupied")
        donor.setup_board(db, target.asset_id, "expected-populated", role="repair")
        before = db.query(ComponentEvent).count()

        with pytest.raises(ValueError, match="already occupied"):
            donor.install_item(db, item.id, target.asset_id, target_position.id)

        assert item.lifecycle_status == "inventory"
        assert db.query(ComponentEvent).count() == before

    def test_fitted_item_cannot_be_marked_removed_without_removal_event(
            self, db, part):
        _source, _source_position, _component, item = self._harvested_item(db, part)
        target, _ref, target_position, _unused = _board(db, part, model="Target")
        donor.setup_board(db, target.asset_id, "empty", role="repair")
        donor.install_item(db, item.id, target.asset_id, target_position.id)
        db.commit()
        before = db.query(ComponentEvent).count()

        with pytest.raises(ValueError, match="removal workflow"):
            donor.set_position_state(db, target.asset_id, target_position.id, "removed")

        assert item.lifecycle_status == "installed"
        assert db.query(ComponentEvent).count() == before

    def test_database_prevents_one_item_occupying_two_positions(self, db, part):
        _source, _source_position, _component, item = self._harvested_item(db, part)
        first, first_ref, first_position, _unused = _board(db, part, model="One")
        second, second_ref, second_position, _unused2 = _board(db, part, model="Two")
        db.add_all([
            PartBomPositionState(
                part_id=first.asset_id, reference_bom_id=first_ref.id,
                position_id=first_position.id, state="present",
                inventory_item_id=item.id),
            PartBomPositionState(
                part_id=second.asset_id, reference_bom_id=second_ref.id,
                position_id=second_position.id, state="present",
                inventory_item_id=item.id),
        ])

        with pytest.raises(DBAPIError):
            db.commit()
        db.rollback()

    def test_wrong_bom_destination_leaves_item_available(self, db, part):
        _source, _source_position, _component, item = self._harvested_item(db, part)
        target, _target_ref, _target_position, _unused = _board(
            db, part, model="Target")
        other = ReferenceBom(name="Wrong destination", status="draft")
        db.add(other)
        db.flush()
        wrong = BomPosition(reference_bom_id=other.id, refdes="U88")
        db.add(wrong)
        db.commit()
        before = db.query(ComponentEvent).count()

        with pytest.raises(ValueError, match="does not belong"):
            donor.install_item(db, item.id, target.asset_id, wrong.id)

        assert item.lifecycle_status == "inventory"
        assert db.query(ComponentEvent).count() == before
        assert db.query(PartBomPositionState).filter_by(
            part_id=target.asset_id).count() == 0


class TestDonorDatabaseIntegrity:
    def test_database_rejects_an_unknown_item_lifecycle(self, db):
        lot = InventoryLot(quantity=1)
        db.add(lot)
        db.flush()
        db.add(InventoryItem(lot_id=lot.id, lifecycle_status="teleported"))

        with pytest.raises(DBAPIError):
            db.commit()
        db.rollback()

    def test_database_rejects_an_unknown_event_type(self, db):
        db.add(ComponentEvent(event_type="rewritten", created_at=datetime.now()))

        with pytest.raises(DBAPIError):
            db.commit()
        db.rollback()

    @pytest.mark.parametrize("end", ["source", "destination"])
    def test_database_rejects_cross_bom_event_positions(self, db, part, end):
        board, reference, _position, _component = _board(db, part)
        other = ReferenceBom(name="Other event reference", status="draft")
        db.add(other)
        db.flush()
        wrong = BomPosition(reference_bom_id=other.id, refdes="U99")
        db.add(wrong)
        db.flush()
        fields = {
            f"{end}_part_id": board.asset_id,
            f"{end}_reference_bom_id": reference.id,
            f"{end}_position_id": wrong.id,
        }
        db.add(ComponentEvent(event_type="tested", created_at=datetime.now(),
                              **fields))

        with pytest.raises(DBAPIError):
            db.commit()
        db.rollback()

    def test_current_position_requires_a_real_inventory_item(self, db, part):
        board, reference, position, _component = _board(db, part)
        db.add(PartBomPositionState(
            part_id=board.asset_id, reference_bom_id=reference.id,
            position_id=position.id, state="present", inventory_item_id=999999))

        with pytest.raises(DBAPIError):
            db.commit()
        db.rollback()

    def test_deleting_source_link_preserves_event_and_clears_its_asset_link(
            self, db, part):
        board, _reference, position, _component = _board(db, part)
        donor.setup_board(db, board.asset_id, "expected-populated")
        item = donor.harvest_position(db, board.asset_id, position.id)
        db.commit()
        event_id = donor.provenance_events(db, item.id)[0].id

        db.delete(db.get(PartBom, board.asset_id))
        db.commit()

        event = db.get(ComponentEvent, event_id)
        assert event is not None
        assert event.source_part_id is None
        assert event.source_reference_bom_id is None
        assert event.source_position_id == position.id


class TestDonorPresentation:
    def test_workbench_shows_sparse_state_and_bench_controls(self, client, db, part):
        board, _reference, position, _component = _board(db, part)
        donor.setup_board(db, board.asset_id, "expected-populated")
        donor.set_position_state(db, board.asset_id, position.id, "damaged")
        db.commit()

        page = client.get(f"/parts/{board.asset_id}/bom").text

        assert "donor board" in page
        assert "explicit: damaged" in page
        assert "/harvest" in page
        assert "default:" not in page

    def test_inventory_shows_original_donor_provenance(self, client, db, part):
        board, _reference, position, _component = _board(db, part)
        donor.setup_board(db, board.asset_id, "expected-populated")
        donor.harvest_position(db, board.asset_id, position.id, item_code="TRACE-UI")
        db.commit()

        page = client.get("/inventory").text

        assert "TRACE-UI" in page
        assert f"{board.asset_id} / {position.refdes}" in page
