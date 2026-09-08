"""Read helpers for the BOM workbench foundation.

The physical register keeps owning physical things. This module reads the new
reference BOM layer beside it: which reference BOM a motherboard is linked to,
the expected positions in that reference, the evidence behind them, and the
sparse state overlay for one physical board.
"""
from __future__ import annotations

from .models import (BomComponent, BomHousePart, BomPartNumber, BomPosition,
                     BomPositionEvidence, BomSource, PartBom, ReferenceBom,
                     PartBomPositionState)

REFERENCE_STATUSES = ["draft", "verified"]
VERIFYING_STATUSES = {"verified", "trusted"}
BASELINE_STATES = ["unknown", "expected-populated", "empty"]
INSPECTION_STATUSES = ["uninspected", "partial", "complete"]
POSITION_STATES = [
    "present",
    "missing",
    "damaged",
    "untested",
    "tested-good",
    "tested-bad",
    "substituted",
    "removed",
    "unknown",
]


def link_for_part(db, part_id):
    return db.get(PartBom, part_id)


def component_label(component: BomComponent | None,
                    part_number: BomPartNumber | None,
                    house_part: BomHousePart | None = None,
                    expected: str | None = "") -> str:
    """Best available expected-component label without inventing missing facts."""
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
    if expected:
        bits.append(expected)
    return " / ".join(bits)


def inherited_state_label(link: PartBom) -> str:
    """Board-level baseline text for a position with no explicit state row."""
    baseline = link.baseline_state or "unknown"
    inspected = link.inspection_status or "uninspected"
    if baseline == "expected-populated":
        state = "inherits expected-populated baseline"
    elif baseline == "empty":
        state = "inherits empty baseline"
    else:
        state = "unknown baseline"
    if inspected != "complete":
        return f"{state}; not position-verified"
    return f"{state}; full-board inspection recorded"


def unsupported_position_count(db, reference_bom_id: int) -> int:
    """How many expected positions lack row-level evidence."""
    position_ids = [pid for (pid,) in db.query(BomPosition.id)
                    .filter(BomPosition.reference_bom_id == reference_bom_id)]
    if not position_ids:
        return 0
    supported = {pid for (pid,) in
                 db.query(BomPositionEvidence.position_id)
                 .filter(BomPositionEvidence.position_id.in_(position_ids))
                 .distinct()}
    return len([pid for pid in position_ids if pid not in supported])


def validate_reference_status(db, reference: ReferenceBom,
                              status: str | None = None) -> None:
    """Drafts may be incomplete; verified/trusted BOMs need evidence per row."""
    next_status = status or reference.status
    if next_status in VERIFYING_STATUSES:
        missing = unsupported_position_count(db, reference.id)
        if missing:
            raise ValueError(
                f"reference BOM has {missing} unsupported position assertion(s)")


def set_reference_status(db, reference: ReferenceBom, status: str) -> None:
    validate_reference_status(db, reference, status)
    reference.status = status


def add_position_state(db, part_id: str, position_id: int, state: str,
                       **fields) -> PartBomPositionState:
    """Create a physical-state overlay only for the Part's linked reference BOM."""
    db.flush()
    link = link_for_part(db, part_id)
    if link is None:
        raise ValueError("part is not linked to a reference BOM")
    pos = db.get(BomPosition, position_id)
    if pos is None or pos.reference_bom_id != link.reference_bom_id:
        raise ValueError("position does not belong to the part's reference BOM")
    row = PartBomPositionState(part_id=part_id, reference_bom_id=link.reference_bom_id,
                               position_id=position_id, state=state, **fields)
    db.add(row)
    return row


def workbench(db, part):
    """Context for a physical board's BOM workbench, or None when none is linked."""
    link = link_for_part(db, part.asset_id)
    if link is None:
        return None
    ref = db.get(ReferenceBom, link.reference_bom_id)
    if ref is None:
        return None
    positions = (db.query(BomPosition)
                 .filter(BomPosition.reference_bom_id == ref.id)
                 .order_by(BomPosition.refdes, BomPosition.id).all())
    comp_ids = {p.component_id for p in positions if p.component_id}
    pn_ids = {p.part_number_id for p in positions if p.part_number_id}
    house_ids = {p.house_part_id for p in positions if p.house_part_id}
    components = {c.id: c for c in db.query(BomComponent)
                  .filter(BomComponent.id.in_(comp_ids)).all()} if comp_ids else {}
    part_numbers = {pn.id: pn for pn in db.query(BomPartNumber)
                    .filter(BomPartNumber.id.in_(pn_ids)).all()} if pn_ids else {}
    house_parts = {hp.id: hp for hp in db.query(BomHousePart)
                   .filter(BomHousePart.id.in_(house_ids)).all()} if house_ids else {}
    evidence_rows = (db.query(BomPositionEvidence, BomSource)
                     .join(BomSource, BomSource.id == BomPositionEvidence.source_id)
                     .filter(BomPositionEvidence.position_id.in_([p.id for p in positions]))
                     .order_by(BomPositionEvidence.id).all()) if positions else []
    evidence = {}
    for pe, source in evidence_rows:
        evidence.setdefault(pe.position_id, []).append({"link": pe, "source": source})
    states = {s.position_id: s for s in
              db.query(PartBomPositionState)
              .filter(PartBomPositionState.part_id == part.asset_id).all()}
    return {
        "link": link,
        "reference": ref,
        "rows": [{
            "position": pos,
            "component": components.get(pos.component_id),
            "part_number": part_numbers.get(pos.part_number_id),
            "house_part": house_parts.get(pos.house_part_id),
            "expected": component_label(components.get(pos.component_id),
                                        part_numbers.get(pos.part_number_id),
                                        house_parts.get(pos.house_part_id),
                                        pos.expected),
            "evidence": evidence.get(pos.id, []),
            "state": states.get(pos.id),
            "baseline_state": inherited_state_label(link),
        } for pos in positions],
    }
