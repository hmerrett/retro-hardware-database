"""The first BOM layer: reference assertions beside physical board state."""
import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError

from app import bom as bomlogic
from app import inventory
from app.models import (BomComponent, BomHousePart, BomHousePartOption,
                        BomPartMarking, BomPartNumber, BomPosition,
                        BomPositionEvidence, BomSource, InventoryItem,
                        InventoryLot, PartBom, PartBomPositionState,
                        ReferenceBom, StorageLocation)


def _tiny_bom(db):
    bom = ReferenceBom(
        name="Test board reference BOM",
        status="draft",
        manufacturer="Example Maker",
        platform="Example Test System",
        board_identifier="TEST-ASSY-1",
        pcb_revision="Rev T",
        population_variant="test fixture only",
        region="test",
        video_standard="test video",
        notes="Small fixture, not production hardware data.",
    )
    component = BomComponent(generic_name="74LS257", category="logic",
                             specification="quad 2-input multiplexer")
    part_number = BomPartNumber(component_id=None, manufacturer="Example Logic",
                                part_number="EX74LS257N", package="DIP-16")
    house = BomHousePart(component_id=None, organization="Example House",
                         house_number="EH-257")
    source = BomSource(source_type="secondary source",
                       title="Tiny BOM test fixture",
                       locator="table 1",
                       notes="Not a real C64 BOM.")
    db.add_all([bom, component, part_number, house, source])
    db.flush()
    part_number.component_id = component.id
    house.component_id = component.id
    positions = [
        BomPosition(reference_bom_id=bom.id, refdes="U7",
                    component_id=component.id, part_number_id=part_number.id,
                    house_part_id=house.id, expected="test multiplexer", package="DIP-16",
                    side="top", x_norm=0.25, y_norm=0.4, region="logic"),
        BomPosition(reference_bom_id=bom.id, refdes="U13",
                    component_id=component.id, expected="test logic IC",
                    package="DIP-16"),
        BomPosition(reference_bom_id=bom.id, refdes="U18"),
        BomPosition(reference_bom_id=bom.id, refdes="R1",
                    expected="test resistor"),
        BomPosition(reference_bom_id=bom.id, refdes="C1",
                    expected="test capacitor"),
    ]
    db.add_all(positions)
    db.flush()
    db.add(BomPositionEvidence(position_id=positions[0].id, source_id=source.id,
                               locator="U7 row"))
    db.commit()
    return bom, positions


class TestExistingRegisterStillWorks:
    def test_computers_and_parts_are_still_plain_assets(self, client):
        comp = client.post("/api/computers", json={
            "manufacturer": "Acme", "model": "Bench PC"}).json()
        part = client.post("/api/parts", json={
            "type": "motherboard", "computer_id": comp["asset_id"],
            "manufacturer": "Acme", "model": "Board"}).json()

        page = client.get(f"/parts/{part['asset_id']}").text

        assert "Installed in" in page
        assert "BOM Workbench" not in page


class TestReferenceBom:
    def test_it_exists_without_a_physical_part(self, db):
        bom, positions = _tiny_bom(db)

        assert db.get(ReferenceBom, bom.id).name == "Test board reference BOM"
        assert not db.query(PartBom).filter(
            PartBom.reference_bom_id == bom.id).count()
        assert [p.refdes for p in positions] == ["U7", "U13", "U18", "R1", "C1"]

    def test_a_part_links_to_a_reference_bom(self, db, part):
        bom, _positions = _tiny_bom(db)
        board = part(type="motherboard", model="Fixture board")
        db.add(PartBom(part_id=board["asset_id"], reference_bom_id=bom.id))
        db.commit()

        assert db.get(PartBom, board["asset_id"]).reference_bom_id == bom.id

    def test_a_position_carries_evidence(self, db):
        _bom, positions = _tiny_bom(db)

        links = db.query(BomPositionEvidence).filter(
            BomPositionEvidence.position_id == positions[0].id).all()

        assert len(links) == 1
        assert db.get(BomSource, links[0].source_id).title == "Tiny BOM test fixture"

    def test_physical_state_does_not_change_the_reference_bom(self, db, part):
        bom, positions = _tiny_bom(db)
        board = part(type="motherboard", model="Fixture board")
        db.add(PartBom(part_id=board["asset_id"], reference_bom_id=bom.id))
        bomlogic.add_position_state(db, board["asset_id"], positions[1].id,
                                    "missing",
                                    notes="socket empty on this board")
        db.commit()

        assert db.get(BomPosition, positions[1].id).expected == "test logic IC"
        assert db.query(PartBomPositionState).filter_by(
            part_id=board["asset_id"]).one().state == "missing"

    def test_unknown_remains_unknown(self, db):
        _bom, positions = _tiny_bom(db)
        unknown = db.get(BomPosition, positions[2].id)

        assert unknown.expected is None
        assert unknown.component_id is None
        assert unknown.part_number_id is None
        assert unknown.house_part_id is None

    @pytest.mark.parametrize(("field", "value"), [
        ("x_norm", -0.01),
        ("x_norm", 1.01),
        ("y_norm", -0.01),
        ("y_norm", 1.01),
    ])
    def test_normalised_coordinates_outside_the_board_are_rejected(
            self, db, field, value):
        bom, _positions = _tiny_bom(db)
        db.add(BomPosition(reference_bom_id=bom.id, refdes="BAD",
                           **{field: value}))

        with pytest.raises(DBAPIError):
            db.commit()
        db.rollback()

    def test_null_normalised_coordinates_remain_valid(self, db):
        bom, _positions = _tiny_bom(db)
        position = BomPosition(reference_bom_id=bom.id, refdes="NC",
                               x_norm=None, y_norm=None)
        db.add(position)
        db.commit()

        assert position.x_norm is None
        assert position.y_norm is None

    def test_duplicate_refdes_is_rejected_within_one_reference_bom(self, db):
        bom, _positions = _tiny_bom(db)
        db.add(BomPosition(reference_bom_id=bom.id, refdes="U7"))

        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_the_same_refdes_can_exist_in_different_reference_boms(self, db):
        first, _positions = _tiny_bom(db)
        second = ReferenceBom(name="Second test BOM")
        db.add(second)
        db.flush()
        db.add(BomPosition(reference_bom_id=second.id, refdes="U7"))
        db.commit()

        assert db.query(BomPosition).filter(BomPosition.refdes == "U7").count() == 2
        assert first.id != second.id

    def test_draft_rows_may_exist_without_evidence(self, db):
        bom, positions = _tiny_bom(db)

        assert bom.status == "draft"
        assert bomlogic.unsupported_position_count(db, bom.id) == len(positions) - 1

    def test_verified_status_requires_position_evidence(self, db):
        bom, _positions = _tiny_bom(db)

        with pytest.raises(ValueError, match="unsupported position"):
            bomlogic.set_reference_status(db, bom, "verified")

        assert bom.status == "draft"

    def test_component_identity_separates_generic_vendor_house_and_markings(self, db):
        component = BomComponent(generic_name="74LS257")
        ti = BomPartNumber(component_id=None, manufacturer="Texas Instruments",
                           part_number="SN74LS257N", package="DIP-16")
        commodore = BomHousePart(component_id=None, organization="Commodore",
                                 house_number="901521-57")
        db.add_all([component, ti, commodore])
        db.flush()
        ti.component_id = component.id
        commodore.component_id = component.id
        db.add(BomPartMarking(part_number_id=ti.id, marking="SN74LS257N"))
        db.add(BomPartMarking(part_number_id=ti.id, marking="74LS257N"))
        db.add(BomHousePartOption(house_part_id=commodore.id, part_number_id=ti.id))
        db.commit()

        assert db.get(BomPartNumber, ti.id).component_id == component.id
        assert db.get(BomHousePart, commodore.id).component_id == component.id
        assert db.query(BomPartMarking).filter_by(part_number_id=ti.id).count() == 2
        assert db.query(BomHousePartOption).filter_by(
            house_part_id=commodore.id).one().part_number_id == ti.id

    def test_position_state_from_the_correct_reference_bom_is_accepted(self, db, part):
        bom, positions = _tiny_bom(db)
        board = part(type="motherboard", model="Correct BOM state")
        db.add(PartBom(part_id=board["asset_id"], reference_bom_id=bom.id))
        bomlogic.add_position_state(db, board["asset_id"], positions[0].id,
                                    "present")
        db.commit()

        state = db.query(PartBomPositionState).filter_by(
            part_id=board["asset_id"]).one()
        assert state.reference_bom_id == bom.id

    def test_position_state_from_another_reference_bom_is_rejected(self, db, part):
        first, _positions = _tiny_bom(db)
        second = ReferenceBom(name="Other BOM")
        db.add(second)
        db.flush()
        other_position = BomPosition(reference_bom_id=second.id, refdes="U99")
        db.add(other_position)
        db.flush()
        board = part(type="motherboard", model="Wrong BOM state")
        db.add(PartBom(part_id=board["asset_id"], reference_bom_id=first.id))

        with pytest.raises(ValueError, match="does not belong"):
            bomlogic.add_position_state(db, board["asset_id"], other_position.id,
                                        "missing")

    def test_cross_bom_position_state_is_rejected_by_database(self, db, part):
        first, _positions = _tiny_bom(db)
        second = ReferenceBom(name="Other BOM")
        db.add(second)
        db.flush()
        other_position = BomPosition(reference_bom_id=second.id, refdes="U99")
        db.add(other_position)
        db.flush()
        board = part(type="motherboard", model="Wrong BOM state")
        db.add(PartBom(part_id=board["asset_id"], reference_bom_id=first.id))
        db.add(PartBomPositionState(part_id=board["asset_id"],
                                    reference_bom_id=first.id,
                                    position_id=other_position.id,
                                    state="missing"))

        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


class TestBomWorkbench:
    def test_a_part_without_a_bom_has_no_workbench_link(self, client, part):
        board = part(type="motherboard", model="No BOM board")

        page = client.get(f"/parts/{board['asset_id']}").text

        assert "BOM Workbench" not in page

    def test_a_part_with_a_bom_has_a_workbench_link(self, client, db, part):
        bom, _positions = _tiny_bom(db)
        board = part(type="motherboard", model="Linked BOM board")
        db.add(PartBom(part_id=board["asset_id"], reference_bom_id=bom.id))
        db.commit()

        page = client.get(f"/parts/{board['asset_id']}").text

        assert f'href="/parts/{board["asset_id"]}/bom"' in page
        assert "BOM Workbench" in page

    def test_the_workbench_renders_positions_evidence_and_exceptions(
            self, client, db, part):
        bom, positions = _tiny_bom(db)
        board = part(type="motherboard", model="Linked BOM board")
        db.add(PartBom(part_id=board["asset_id"], reference_bom_id=bom.id))
        bomlogic.add_position_state(db, board["asset_id"], positions[1].id,
                                    "missing",
                                    notes="not fitted on this physical board")
        db.commit()

        page = client.get(f"/parts/{board['asset_id']}/bom").text

        assert "Test board reference BOM" in page
        assert "U7" in page and "test multiplexer" in page
        assert "secondary source: Tiny BOM test fixture" in page
        assert "U13" in page and "missing" in page
        assert "U18" in page and "unknown" in page
        assert db.get(BomPosition, positions[1].id).expected == "test logic IC"

    def test_a_physical_board_can_record_only_exceptions(self, db, part):
        bom, positions = _tiny_bom(db)
        board = part(type="motherboard", model="Sparse board state")
        db.add(PartBom(part_id=board["asset_id"], reference_bom_id=bom.id))
        bomlogic.add_position_state(db, board["asset_id"], positions[3].id,
                                    "damaged")
        db.commit()

        assert db.query(BomPosition).filter(
            BomPosition.reference_bom_id == bom.id).count() == 5
        assert db.query(PartBomPositionState).filter_by(
            part_id=board["asset_id"]).count() == 1

    def test_absent_override_inherits_baseline_without_claiming_inspection(self, db, part):
        bom, positions = _tiny_bom(db)
        board = part(type="motherboard", model="Baseline board")
        db.add(PartBom(part_id=board["asset_id"], reference_bom_id=bom.id,
                       baseline_state="expected-populated",
                       inspection_status="partial"))
        db.commit()

        ctx = bomlogic.workbench(db, type("P", (), {"asset_id": board["asset_id"]})())
        row = next(r for r in ctx["rows"] if r["position"].id == positions[0].id)

        assert row["state"] is None
        assert row["baseline_state"] == (
            "inherits expected-populated baseline; not position-verified")

    def test_workbench_visibility_comes_from_the_bom_relationship(
            self, client, db, part):
        bom, _positions = _tiny_bom(db)
        board = part(type="other", model="Relationship-linked board")
        db.add(PartBom(part_id=board["asset_id"], reference_bom_id=bom.id))
        db.commit()

        page = client.get(f"/parts/{board['asset_id']}").text
        workbench = client.get(f"/parts/{board['asset_id']}/bom")

        assert "BOM Workbench" in page
        assert workbench.status_code == 200


class TestStorageLocations:
    def test_root_storage_location_works(self, db):
        root = StorageLocation(name="Workshop", kind="site")
        db.add(root)
        db.commit()

        assert inventory.location_path(db, root) == "Workshop"

    def test_nested_storage_location_path_is_derived(self, db):
        home = StorageLocation(name="Home", kind="site")
        garage = StorageLocation(name="Garage", kind="room")
        cabinet = StorageLocation(name="Electronics Cabinet", kind="cabinet")
        drawer = StorageLocation(name="Drawer 14", kind="drawer")
        bin_b = StorageLocation(name="Bin B", kind="bin")
        db.add_all([home, garage, cabinet, drawer, bin_b])
        db.flush()
        garage.parent_id = home.id
        cabinet.parent_id = garage.id
        drawer.parent_id = cabinet.id
        bin_b.parent_id = drawer.id
        db.commit()

        assert inventory.location_path(db, bin_b) == (
            "Home > Garage > Electronics Cabinet > Drawer 14 > Bin B")
        assert not hasattr(bin_b, "path")

    def test_location_cannot_parent_itself(self, db):
        loc = StorageLocation(name="Loop")
        db.add(loc)
        db.flush()

        with pytest.raises(ValueError, match="own parent"):
            inventory.set_location_parent(db, loc, loc.id)

    def test_database_rejects_direct_self_parenting(self, db):
        loc = StorageLocation(name="Direct loop")
        db.add(loc)
        db.flush()
        loc.parent_id = loc.id

        with pytest.raises(DBAPIError, match="cannot be its own parent"):
            db.commit()
        db.rollback()

    def test_path_updates_when_a_location_moves(self, db):
        first = StorageLocation(name="First workshop")
        second = StorageLocation(name="Second workshop")
        shelf = StorageLocation(name="Shelf")
        db.add_all([first, second, shelf])
        db.flush()
        inventory.set_location_parent(db, shelf, first.id)
        db.commit()
        assert inventory.location_path(db, shelf) == "First workshop > Shelf"

        inventory.set_location_parent(db, shelf, second.id)
        db.commit()

        assert inventory.location_path(db, shelf) == "Second workshop > Shelf"

    def test_deleting_a_parent_promotes_its_child_to_a_root(self, db):
        cabinet = StorageLocation(name="Cabinet")
        drawer = StorageLocation(name="Drawer")
        db.add_all([cabinet, drawer])
        db.flush()
        inventory.set_location_parent(db, drawer, cabinet.id)
        db.commit()

        db.delete(cabinet)
        db.commit()
        db.refresh(drawer)

        assert drawer.parent_id is None
        assert inventory.location_path(db, drawer) == "Drawer"

    def test_location_cannot_be_moved_below_its_descendant(self, db):
        root = StorageLocation(name="Root")
        child = StorageLocation(name="Child")
        grandchild = StorageLocation(name="Grandchild")
        db.add_all([root, child, grandchild])
        db.flush()
        inventory.set_location_parent(db, child, root.id)
        inventory.set_location_parent(db, grandchild, child.id)
        db.commit()

        with pytest.raises(ValueError, match="cycle"):
            inventory.set_location_parent(db, root, grandchild.id)

    def test_derived_path_rejects_an_already_corrupt_cycle(self, db):
        first = StorageLocation(name="First")
        second = StorageLocation(name="Second")
        db.add_all([first, second])
        db.flush()
        # Direct ORM assignment bypasses the supported tree write helper. Reading
        # such corrupt legacy data must fail loudly rather than present a partial path.
        first.parent_id = second.id
        second.parent_id = first.id
        db.commit()

        with pytest.raises(ValueError, match="cycle"):
            inventory.location_path(db, first)


class TestInventoryLots:
    def test_bulk_component_inventory_lot_can_be_created(self, db):
        component = BomComponent(generic_name="10k resistor")
        db.add(component)
        db.flush()
        lot = InventoryLot(component_id=component.id, quantity=100,
                           condition="new", test_status=None)
        db.add(lot)
        db.commit()

        assert db.get(InventoryLot, lot.id).quantity == 100
        assert db.query(InventoryItem).filter_by(lot_id=lot.id).count() == 0

    def test_manufacturer_lot_can_reference_the_same_generic_component(self, db):
        component = BomComponent(generic_name="74LS257")
        ti = BomPartNumber(manufacturer="Texas Instruments",
                           part_number="SN74LS257N")
        db.add_all([component, ti])
        db.flush()
        ti.component_id = component.id
        lot = InventoryLot(component_id=component.id, part_number_id=ti.id,
                           quantity=8, condition="NOS", test_status="passed")
        db.add(lot)
        db.commit()

        assert db.get(InventoryLot, lot.id).component_id == component.id
        assert db.get(InventoryLot, lot.id).part_number_id == ti.id

    def test_unknown_manufacturer_and_test_values_remain_unknown(self, db):
        component = BomComponent(generic_name="74LS257")
        db.add(component)
        db.flush()
        lot = InventoryLot(component_id=component.id, quantity=2)
        db.add(lot)
        db.commit()

        saved = db.get(InventoryLot, lot.id)
        assert saved.part_number_id is None
        assert saved.test_status is None

    def test_quantity_cannot_be_negative(self, db):
        db.add(InventoryLot(quantity=-1))

        with pytest.raises(DBAPIError):
            db.commit()
        db.rollback()

    def test_failed_stock_is_distinguishable_from_usable_stock(self, db):
        component = BomComponent(generic_name="74LS257")
        db.add(component)
        db.flush()
        db.add_all([
            InventoryLot(component_id=component.id, quantity=4,
                         test_status="passed"),
            InventoryLot(component_id=component.id, quantity=3,
                         test_status="failed"),
        ])
        db.commit()

        assert inventory.usable_quantity_for_component(db, component.id) == 4

    def test_multiple_lots_for_the_same_component_in_different_locations(self, db):
        component = BomComponent(generic_name="74LS257")
        workshop = StorageLocation(name="Workshop")
        shelf = StorageLocation(name="Shelf 3")
        db.add_all([component, workshop, shelf])
        db.flush()
        db.add_all([
            InventoryLot(component_id=component.id, quantity=2,
                         storage_location_id=workshop.id),
            InventoryLot(component_id=component.id, quantity=5,
                         storage_location_id=shelf.id),
        ])
        db.commit()

        lots = db.query(InventoryLot).filter_by(component_id=component.id).all()
        assert len(lots) == 2
        assert {lot.storage_location_id for lot in lots} == {workshop.id, shelf.id}

    def test_inventory_pages_render_lots_and_storage_paths(self, client, db):
        component = BomComponent(generic_name="74LS257")
        workshop = StorageLocation(name="Workshop", kind="site")
        shelf = StorageLocation(name="Shelf 3", kind="shelf")
        db.add_all([component, workshop, shelf])
        db.flush()
        shelf.parent_id = workshop.id
        db.add(InventoryLot(component_id=component.id, quantity=6,
                            condition="pulled", test_status="untested",
                            storage_location_id=shelf.id))
        db.commit()

        inv = client.get("/inventory").text
        storage = client.get("/storage-locations").text

        assert "74LS257" in inv
        assert "pulled" in inv and "untested" in inv
        assert "Workshop &gt; Shelf 3" in inv
        assert "Workshop &gt; Shelf 3" in storage


class TestInventoryItems:
    def test_traceable_item_can_belong_to_a_lot(self, db):
        lot = InventoryLot(quantity=1)
        db.add(lot)
        db.flush()

        item = inventory.add_inventory_item(db, lot.id, item_code="TRACE-1")
        db.commit()

        assert item.lot_id == lot.id
        assert db.get(InventoryItem, item.id).item_code == "TRACE-1"

    def test_traceable_items_do_not_increase_usable_stock(self, db):
        component = BomComponent(generic_name="traceable test component")
        lot = InventoryLot(component_id=None, quantity=4, test_status="passed")
        db.add_all([component, lot])
        db.flush()
        lot.component_id = component.id
        for n in range(3):
            inventory.add_inventory_item(db, lot.id, item_code=f"TRACE-{n}")
        db.commit()

        assert inventory.usable_quantity_for_component(db, component.id) == 4

    def test_every_unit_in_a_lot_may_be_individually_tracked(self, db):
        lot = InventoryLot(quantity=4)
        db.add(lot)
        db.flush()

        for n in range(4):
            inventory.add_inventory_item(db, lot.id, item_code=f"ALL-{n}")
        db.commit()

        assert db.query(InventoryItem).filter_by(lot_id=lot.id).count() == 4

    def test_more_traceable_items_than_lot_quantity_are_rejected(self, db):
        lot = InventoryLot(quantity=4)
        db.add(lot)
        db.flush()
        for n in range(4):
            inventory.add_inventory_item(db, lot.id, item_code=f"FULL-{n}")
        db.flush()

        with pytest.raises(ValueError, match="quantity"):
            inventory.add_inventory_item(db, lot.id, item_code="TOO-MANY")

    def test_quantity_cannot_be_reduced_below_traceable_item_count(self, db):
        lot = InventoryLot(quantity=4)
        db.add(lot)
        db.flush()
        for n in range(3):
            inventory.add_inventory_item(db, lot.id, item_code=f"REDUCE-{n}")
        db.flush()

        with pytest.raises(ValueError, match="traceable"):
            inventory.set_lot_quantity(db, lot, 2)

        assert lot.quantity == 4

    def test_traceable_item_cannot_move_into_a_full_lot(self, db):
        source = InventoryLot(quantity=1)
        full = InventoryLot(quantity=1)
        db.add_all([source, full])
        db.flush()
        item = inventory.add_inventory_item(db, source.id, item_code="MOVE-ME")
        inventory.add_inventory_item(db, full.id, item_code="ALREADY-FULL")
        db.flush()

        with pytest.raises(ValueError, match="quantity"):
            inventory.move_inventory_item(db, item, full.id)

        assert item.lot_id == source.id
