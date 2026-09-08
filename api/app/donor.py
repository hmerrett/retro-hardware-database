"""Transactional donor-board and traceable-component workflows.

``ComponentEvent`` rows are append-only through this module: supported workflows
only create events and never update or delete them. Current lifecycle and fitted
position live on ``InventoryItem`` and ``PartBomPositionState`` respectively;
events remain the historical provenance after either current state changes.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

from . import inventory
from .models import (BomPosition, ComponentEvent, InventoryItem, InventoryLot,
                     LogEntry, Part, PartBom, PartBomPositionState)

BOARD_ROLES = ["normal", "donor", "repair"]
EVENT_TYPES = [
    "acquired", "harvested", "added-to-inventory", "moved", "installed",
    "removed", "tested", "marked-failed", "discarded",
]


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _append_event(db, **fields) -> ComponentEvent:
    """Append immutable history; no supported workflow mutates an existing row."""
    event = ComponentEvent(created_at=_now(), **fields)
    db.add(event)
    return event


def _part_and_position(db, part_id: str, position_id: int, *, lock=False):
    part = db.get(Part, part_id)
    if part is None:
        raise ValueError("physical part does not exist")
    query = db.query(PartBom).filter(PartBom.part_id == part_id)
    if lock:
        query = query.with_for_update()
    link = query.one_or_none()
    position = db.get(BomPosition, position_id)
    if link is None:
        raise ValueError("part is not linked to a reference BOM")
    if position is None or position.reference_bom_id != link.reference_bom_id:
        raise ValueError("position does not belong to the part's reference BOM")
    return part, link, position


def _position_state(db, part_id: str, position_id: int):
    return (db.query(PartBomPositionState)
            .filter_by(part_id=part_id, position_id=position_id)
            .one_or_none())


def effective_position_state(link: PartBom,
                             state: PartBomPositionState | None) -> str:
    if state is not None:
        return state.state
    if link.baseline_state == "expected-populated":
        return "present"
    if link.baseline_state == "empty":
        return "missing"
    return "unknown"


def setup_board(db, part_id: str, baseline_state: str, *, role="donor",
                inspection_status="uninspected", notes=None) -> PartBom:
    """Set a physical board's role and sparse population baseline."""
    if role not in BOARD_ROLES:
        raise ValueError("unknown physical board role")
    if baseline_state not in {"expected-populated", "empty"}:
        raise ValueError("donor baseline must be expected-populated or empty")
    with db.begin_nested():
        part = db.get(Part, part_id)
        link = db.get(PartBom, part_id)
        if part is None or link is None:
            raise ValueError("physical part must be linked to a reference BOM")
        if part.type != "motherboard":
            raise ValueError("donor workflow requires a physical motherboard part")
        part.board_role = role
        link.baseline_state = baseline_state
        link.inspection_status = inspection_status
        if notes is not None:
            link.notes = notes
        db.add(LogEntry(
            asset_id=part_id, created_at=_now(), kind="change",
            message=f"set up as {role} board from {baseline_state} baseline"))
    return link


def set_position_state(db, part_id: str, position_id: int, state: str,
                       **fields) -> PartBomPositionState:
    """Create or update one explicit observation without expanding the baseline."""
    if state not in {
        "present", "missing", "damaged", "untested", "tested-good",
        "tested-bad", "substituted", "removed", "unknown",
    }:
        raise ValueError("unknown physical position state")
    with db.begin_nested():
        _part, link, _position = _part_and_position(
            db, part_id, position_id, lock=True)
        row = _position_state(db, part_id, position_id)
        if row is None:
            row = PartBomPositionState(
                part_id=part_id, reference_bom_id=link.reference_bom_id,
                position_id=position_id, state=state)
            db.add(row)
        else:
            if row.inventory_item_id is not None and state in {"missing", "removed"}:
                raise ValueError(
                    "a fitted traceable item must use the removal workflow")
            row.state = state
        for name in ("observed_part_number_id", "observed_house_part_id",
                     "observed", "notes"):
            if name in fields:
                setattr(row, name, fields[name])
    return row


def _identity(position: BomPosition, state: PartBomPositionState | None):
    return (
        position.component_id,
        (state.observed_part_number_id if state and state.observed_part_number_id
         else position.part_number_id),
        (state.observed_house_part_id if state and state.observed_house_part_id
         else position.house_part_id),
    )


def _lot_matches(lot: InventoryLot, identity, condition: str | None) -> bool:
    return ((lot.component_id, lot.part_number_id, lot.house_part_id) == identity
            and lot.condition == condition)


def harvest_position(db, part_id: str, position_id: int, *, lot_id=None,
                     storage_location_id=None, item_code=None, condition="pulled",
                     event_date: date | None = None, notes=None) -> InventoryItem:
    """Atomically remove one component, inventory it, and preserve its origin."""
    with db.begin_nested():
        part, link, position = _part_and_position(db, part_id, position_id, lock=True)
        if part.board_role not in {"donor", "repair"}:
            raise ValueError("board is not marked for donor or repair work")
        state = _position_state(db, part_id, position_id)
        if effective_position_state(link, state) in {"missing", "removed", "unknown"}:
            raise ValueError("position has no component available to harvest")
        identity = _identity(position, state)
        fitted_item = None
        if state and state.inventory_item_id is not None:
            fitted_item = (db.query(InventoryItem)
                           .filter(InventoryItem.id == state.inventory_item_id)
                           .with_for_update().one_or_none())
            if fitted_item is None or fitted_item.lifecycle_status != "installed":
                raise ValueError("position traceable-item state is inconsistent")
        if fitted_item is not None:
            item = fitted_item
            lot = db.get(InventoryLot, item.lot_id)
            if lot_id is not None and lot_id != lot.id:
                raise ValueError("installed item must return to its existing lot")
            item.lifecycle_status = "inventory"
        elif lot_id is None:
            lot = InventoryLot(
                component_id=identity[0], part_number_id=identity[1],
                house_part_id=identity[2], storage_location_id=storage_location_id,
                quantity=1, condition=condition, test_status="untested")
            db.add(lot)
            db.flush()
        else:
            lot = (db.query(InventoryLot).filter(InventoryLot.id == lot_id)
                   .with_for_update().one_or_none())
            if lot is None or not _lot_matches(lot, identity, condition):
                raise ValueError("inventory lot is not an exact identity and condition match")
            inventory.set_lot_quantity(db, lot, lot.quantity + 1)
        if fitted_item is None:
            item = inventory.add_inventory_item(
                db, lot.id, item_code=item_code, condition=condition,
                test_status="untested", lifecycle_status="inventory")
        if state is None:
            state = PartBomPositionState(
                part_id=part_id, reference_bom_id=link.reference_bom_id,
                position_id=position_id, state="removed")
            db.add(state)
        else:
            state.state = "removed"
            state.inventory_item_id = None
        db.flush()
        _append_event(
            db, event_type="harvested", event_date=event_date,
            source_part_id=part_id, source_reference_bom_id=link.reference_bom_id,
            source_position_id=position.id, inventory_lot_id=lot.id,
            inventory_item_id=item.id,
            destination_storage_location_id=lot.storage_location_id, notes=notes)
        db.add(LogEntry(
            asset_id=part_id, created_at=_now(), kind="change",
            message=f"{position.refdes} harvested to inventory"))
    return item


def install_item(db, item_id: int, part_id: str, position_id: int, *,
                 event_date: date | None = None, notes=None) -> PartBomPositionState:
    """Atomically fit one available traceable item into one physical position."""
    with db.begin_nested():
        item = (db.query(InventoryItem).filter(InventoryItem.id == item_id)
                .with_for_update().one_or_none())
        if item is None or item.lifecycle_status != "inventory" or not item.active:
            raise ValueError("inventory item is not available for installation")
        _part, link, position = _part_and_position(db, part_id, position_id, lock=True)
        occupied = _position_state(db, part_id, position_id)
        if occupied and occupied.inventory_item_id is not None:
            raise ValueError("destination position already contains a traceable item")
        if effective_position_state(link, occupied) not in {
                "missing", "removed", "unknown"}:
            raise ValueError("destination position is already occupied")
        if db.query(PartBomPositionState).filter_by(inventory_item_id=item.id).first():
            raise ValueError("inventory item is already installed")
        lot = db.get(InventoryLot, item.lot_id)
        actual = (lot.component_id, lot.part_number_id, lot.house_part_id)
        expected = (position.component_id, position.part_number_id,
                    position.house_part_id)
        new_state = "present" if actual == expected else "substituted"
        if occupied is None:
            occupied = PartBomPositionState(
                part_id=part_id, reference_bom_id=link.reference_bom_id,
                position_id=position.id, state=new_state)
            db.add(occupied)
        occupied.state = new_state
        occupied.inventory_item_id = item.id
        occupied.observed_part_number_id = lot.part_number_id
        occupied.observed_house_part_id = lot.house_part_id
        item.lifecycle_status = "installed"
        db.flush()
        _append_event(
            db, event_type="installed", event_date=event_date,
            destination_part_id=part_id,
            destination_reference_bom_id=link.reference_bom_id,
            destination_position_id=position.id, inventory_lot_id=lot.id,
            inventory_item_id=item.id,
            source_storage_location_id=lot.storage_location_id, notes=notes)
        db.add(LogEntry(
            asset_id=part_id, created_at=_now(), kind="change",
            message=f"{position.refdes} installed from traceable inventory"))
    return occupied


def provenance_events(db, item_id: int):
    return (db.query(ComponentEvent).filter(ComponentEvent.inventory_item_id == item_id)
            .order_by(ComponentEvent.created_at, ComponentEvent.id).all())
