"""Helpers for the physical replacement-part inventory layer."""
from __future__ import annotations

from sqlalchemy import or_

from .models import (BomComponent, BomHousePart, BomPartNumber, BomPosition,
                     ComponentEvent, InventoryItem, InventoryLot, Part,
                     PartBomPositionState, StorageLocation)

CONDITIONS = ["new", "NOS", "used", "pulled", "refurbished", "unknown"]
TEST_STATUSES = ["untested", "passed", "failed", "intermittent", "unknown"]
UNUSABLE_TEST_STATUSES = {"failed"}


def location_path(db, location: StorageLocation | None) -> str:
    """Derived display path for a storage node; the tree is the canonical data."""
    if location is None:
        return ""
    seen = set()
    parts = []
    cur = location
    while cur is not None:
        if cur.id in seen:
            raise ValueError("storage location hierarchy contains a cycle")
        seen.add(cur.id)
        parts.append(cur.name)
        cur = db.get(StorageLocation, cur.parent_id) if cur.parent_id else None
    return " > ".join(reversed(parts))


def validate_location_parent(db, location: StorageLocation,
                             parent_id: int | None) -> None:
    """Reject a parent assignment which would stop the storage tree being a tree."""
    if parent_id is None:
        return
    if location.id is not None and parent_id == location.id:
        raise ValueError("a storage location cannot be its own parent")
    seen = set()
    parent = db.get(StorageLocation, parent_id)
    while parent is not None:
        if parent.id in seen:
            raise ValueError("storage location hierarchy contains a cycle")
        if location.id is not None and parent.id == location.id:
            raise ValueError("storage location move would create a cycle")
        seen.add(parent.id)
        parent = db.get(StorageLocation, parent.parent_id) if parent.parent_id else None


def set_location_parent(db, location: StorageLocation,
                        parent_id: int | None) -> None:
    """The supported write path for moving a location within the storage tree."""
    validate_location_parent(db, location, parent_id)
    location.parent_id = parent_id


def traceable_item_count(db, lot_id: int) -> int:
    return db.query(InventoryItem).filter(InventoryItem.lot_id == lot_id).count()


def _locked_lot(db, lot_id: int) -> InventoryLot:
    """Serialise supported count-changing writes through their parent lot row."""
    lot = (db.query(InventoryLot)
           .filter(InventoryLot.id == lot_id)
           .with_for_update().one_or_none())
    if lot is None:
        raise ValueError("inventory lot does not exist")
    return lot


def add_inventory_item(db, lot_id: int, **fields) -> InventoryItem:
    """Identify one member of a lot without increasing that lot's total stock."""
    if fields.get("lifecycle_status", "inventory") != "inventory":
        raise ValueError("new traceable items must enter as loose inventory")
    db.flush()
    lot = _locked_lot(db, lot_id)
    if traceable_item_count(db, lot_id) >= lot.quantity:
        raise ValueError("traceable item count cannot exceed lot quantity")
    item = InventoryItem(lot_id=lot_id, **fields)
    db.add(item)
    return item


def move_inventory_item(db, item: InventoryItem, lot_id: int) -> None:
    """Move a tracked unit without letting the destination overstate identities."""
    if item.lifecycle_status != "inventory":
        raise ValueError("only a loose inventory item can move between lots")
    if item.lot_id == lot_id:
        return
    db.flush()
    lot = _locked_lot(db, lot_id)
    if traceable_item_count(db, lot_id) >= lot.quantity:
        raise ValueError("traceable item count cannot exceed lot quantity")
    item.lot_id = lot_id


def set_lot_quantity(db, lot: InventoryLot, quantity: int) -> None:
    """Change total stock without orphaning identities for tracked members."""
    if quantity < 0:
        raise ValueError("inventory lot quantity cannot be negative")
    db.flush()
    locked = _locked_lot(db, lot.id)
    tracked = traceable_item_count(db, locked.id)
    if quantity < tracked:
        raise ValueError(
            f"lot quantity cannot be below its {tracked} traceable item(s)")
    locked.quantity = quantity


def lot_label(component: BomComponent | None,
              part_number: BomPartNumber | None,
              house_part: BomHousePart | None) -> str:
    bits = []
    if component and component.generic_name:
        bits.append(component.generic_name)
    if part_number:
        label = " ".join(x for x in (part_number.manufacturer,
                                     part_number.part_number) if x)
        if label:
            bits.append(label)
    if house_part and house_part.house_number:
        label = " ".join(x for x in (house_part.organization,
                                     house_part.house_number) if x)
        bits.append(label)
    return " / ".join(bits) or "unknown component"


def inventory_rows(db):
    lots = db.query(InventoryLot).order_by(InventoryLot.id).all()
    component_ids = {lot.component_id for lot in lots if lot.component_id}
    part_number_ids = {lot.part_number_id for lot in lots if lot.part_number_id}
    house_part_ids = {lot.house_part_id for lot in lots if lot.house_part_id}
    location_ids = {lot.storage_location_id for lot in lots if lot.storage_location_id}
    components = {c.id: c for c in db.query(BomComponent)
                  .filter(BomComponent.id.in_(component_ids)).all()} if component_ids else {}
    part_numbers = {pn.id: pn for pn in db.query(BomPartNumber)
                    .filter(BomPartNumber.id.in_(part_number_ids)).all()} if part_number_ids else {}
    house_parts = {hp.id: hp for hp in db.query(BomHousePart)
                   .filter(BomHousePart.id.in_(house_part_ids)).all()} if house_part_ids else {}
    locations = {loc.id: loc for loc in db.query(StorageLocation)
                 .filter(StorageLocation.id.in_(location_ids)).all()} if location_ids else {}
    rows = []
    for lot in lots:
        item_rows = []
        for item in db.query(InventoryItem).filter_by(lot_id=lot.id).order_by(
                InventoryItem.id):
            fitted = db.query(PartBomPositionState).filter_by(
                inventory_item_id=item.id).one_or_none()
            installed_part = db.get(Part, fitted.part_id) if fitted else None
            installed_position = db.get(BomPosition, fitted.position_id) if fitted else None
            origin = (db.query(ComponentEvent)
                      .filter_by(inventory_item_id=item.id, event_type="harvested")
                      .order_by(ComponentEvent.created_at, ComponentEvent.id)
                      .first())
            source_part = db.get(Part, origin.source_part_id) if origin else None
            source_position = db.get(BomPosition, origin.source_position_id) if origin else None
            item_rows.append({
                "item": item,
                "status": "installed" if fitted else item.lifecycle_status,
                "installed_part": installed_part,
                "installed_position": installed_position,
                "source_part": source_part,
                "source_position": source_position,
            })
        rows.append({
            "lot": lot,
            "label": lot_label(components.get(lot.component_id),
                               part_numbers.get(lot.part_number_id),
                               house_parts.get(lot.house_part_id)),
            "location_path": location_path(db, locations.get(lot.storage_location_id)),
            "tracked_items": item_rows,
        })
    return rows


def storage_rows(db):
    locations = db.query(StorageLocation).order_by(
        StorageLocation.parent_id, StorageLocation.display_order,
        StorageLocation.name, StorageLocation.id).all()
    return [{"location": loc, "path": location_path(db, loc)} for loc in locations]


def usable_quantity_for_component(db, component_id: int) -> int:
    lots = (db.query(InventoryLot)
            .filter(InventoryLot.component_id == component_id,
                    InventoryLot.active.is_(True),
                    InventoryLot.quantity > 0)
            .all())
    total = 0
    for lot in lots:
        if (lot.test_status or "").lower() in UNUSABLE_TEST_STATUSES:
            continue
        unavailable = (db.query(InventoryItem)
                       .filter(InventoryItem.lot_id == lot.id,
                               or_(InventoryItem.lifecycle_status != "inventory",
                                   InventoryItem.active.is_(False)))
                       .count())
        total += max(0, lot.quantity - unavailable)
    return total
