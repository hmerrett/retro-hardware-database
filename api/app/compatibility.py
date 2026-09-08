"""Evidence-backed component compatibility and substitution facts.

The source part is the part expected by a design; the target part is the
candidate proposed in its place. Only exact equivalence is symmetric when
queried. Sharing a BomComponent never creates a relationship implicitly.
"""
from __future__ import annotations

from sqlalchemy import and_, or_

from .models import (BomHousePartOption, BomHousePartOptionEvidence, BomPartNumber,
                     BomPosition, BomSource,
                     ComponentCompatibility, ComponentCompatibilityEvidence,
                     ComponentProductionUse, ComponentProductionUseEvidence,
                     InventoryItem, InventoryLot, ReferenceBom)

RELATIONSHIP_TYPES = {
    "exact-equivalent", "manufacturer-alternate", "electrical-substitute",
    "pin-compatible-substitute", "functional-substitute",
    "documented-service-substitute", "production-alternate",
    "conditional-substitute", "incompatible",
}
SYMMETRIC_TYPES = {"exact-equivalent"}
STATUSES = {"draft", "evidenced", "verified", "disputed", "deprecated"}
PROMOTED_STATUSES = {"evidenced", "verified"}
EVIDENCE_REQUIRED_STATUSES = {"evidenced", "verified", "disputed", "deprecated"}
DIMENSION_VALUES = {"compatible", "conditional", "incompatible"}
DIMENSION_FIELDS = {
    "function_compatible", "pinout_compatible", "package_compatible",
    "voltage_compatible", "logic_level_compatible", "timing_compatible",
    "frequency_compatible", "thermal_current_compatible", "analogue_compatible",
    "firmware_content_compatible", "region_standard_compatible",
}
SOURCE_AUTHORITY = {
    "manufacturer datasheet": 4,
    "manufacturer service manual": 4,
    "official service bulletin": 4,
    "engineering document": 4,
    "official parts list": 4,
    "schematic": 3,
    "board/physical corroboration": 2,
    "reputable secondary technical source": 2,
    "user observation/test result": 1,
}
USABLE_RELATIONSHIPS = RELATIONSHIP_TYPES - {"incompatible"}


def _normalised(value):
    return value if value != "" else None


def _validate_scope(db, reference_bom_id, position_id):
    if position_id is None:
        return
    if reference_bom_id is None:
        raise ValueError("a position scope requires a reference BOM")
    position = db.get(BomPosition, position_id)
    if position is None or position.reference_bom_id != reference_bom_id:
        raise ValueError("position scope does not belong to the reference BOM")


def _duplicate_query(db, fields, *, excluding_id=None):
    query = db.query(ComponentCompatibility).filter_by(
        source_part_number_id=fields["source_part_number_id"],
        target_part_number_id=fields["target_part_number_id"],
        relationship_type=fields["relationship_type"],
        scope_reference_bom_id=fields.get("scope_reference_bom_id"),
        scope_position_id=fields.get("scope_position_id"),
        platform=fields.get("platform"), manufacturer=fields.get("manufacturer"),
        required_package=fields.get("required_package"),
        region=fields.get("region"), video_standard=fields.get("video_standard"),
    )
    if fields["relationship_type"] in SYMMETRIC_TYPES:
        query = db.query(ComponentCompatibility).filter(
            ComponentCompatibility.relationship_type == fields["relationship_type"],
            or_(
                and_(ComponentCompatibility.source_part_number_id ==
                     fields["source_part_number_id"],
                     ComponentCompatibility.target_part_number_id ==
                     fields["target_part_number_id"]),
                and_(ComponentCompatibility.source_part_number_id ==
                     fields["target_part_number_id"],
                     ComponentCompatibility.target_part_number_id ==
                     fields["source_part_number_id"]),
            ),
            ComponentCompatibility.scope_reference_bom_id ==
            fields.get("scope_reference_bom_id"),
            ComponentCompatibility.scope_position_id == fields.get("scope_position_id"),
            ComponentCompatibility.platform == fields.get("platform"),
            ComponentCompatibility.manufacturer == fields.get("manufacturer"),
            ComponentCompatibility.required_package == fields.get("required_package"),
            ComponentCompatibility.region == fields.get("region"),
            ComponentCompatibility.video_standard == fields.get("video_standard"),
        )
    if excluding_id is not None:
        query = query.filter(ComponentCompatibility.id != excluding_id)
    return query


def _validate_fields(db, fields, *, excluding_id=None):
    relationship = fields.get("relationship_type")
    if relationship not in RELATIONSHIP_TYPES:
        raise ValueError("unknown compatibility relationship type")
    source_id = fields.get("source_part_number_id")
    target_id = fields.get("target_part_number_id")
    if source_id == target_id:
        raise ValueError("a compatibility relationship cannot refer to itself")
    if db.get(BomPartNumber, source_id) is None or db.get(BomPartNumber, target_id) is None:
        raise ValueError("compatibility endpoints must be manufacturer part numbers")
    _validate_scope(db, fields.get("scope_reference_bom_id"),
                    fields.get("scope_position_id"))
    for name in DIMENSION_FIELDS:
        if fields.get(name) is not None and fields[name] not in DIMENSION_VALUES:
            raise ValueError(f"invalid {name.replace('_', ' ')} value")
    if relationship == "exact-equivalent" and any(
            fields.get(name) == "incompatible" for name in DIMENSION_FIELDS):
        raise ValueError("exact equivalence cannot contain an incompatible dimension")
    if relationship == "conditional-substitute" and not fields.get("caveat"):
        raise ValueError("a conditional substitute requires a caveat")
    if _duplicate_query(db, fields, excluding_id=excluding_id).first() is not None:
        raise ValueError("an identical compatibility relationship already exists")


def create_draft(db, source_part_number_id: int, target_part_number_id: int,
                 relationship_type: str, **fields) -> ComponentCompatibility:
    """Create an unverified fact; no relationship is inferred from component family."""
    fields = {key: _normalised(value) for key, value in fields.items()}
    values = {"source_part_number_id": source_part_number_id,
              "target_part_number_id": target_part_number_id,
              "relationship_type": relationship_type, **fields}
    _validate_fields(db, values)
    row = ComponentCompatibility(status="draft", **values)
    db.add(row)
    db.flush()
    return row


def update_draft(db, relationship: ComponentCompatibility, **fields):
    if relationship.status != "draft":
        raise ValueError("only draft compatibility relationships can be edited")
    values = {name: getattr(relationship, name) for name in
              {"source_part_number_id", "target_part_number_id", "relationship_type",
               "scope_reference_bom_id", "scope_position_id", "region", "video_standard",
               "platform", "manufacturer", "required_package",
               "caveat", *DIMENSION_FIELDS}}
    values.update({key: _normalised(value) for key, value in fields.items()})
    _validate_fields(db, values, excluding_id=relationship.id)
    for key, value in fields.items():
        setattr(relationship, key, _normalised(value))
    return relationship


def attach_evidence(db, relationship: ComponentCompatibility, source_id: int,
                    *, locator="", directly_states_claim=False, notes=None):
    if db.get(BomSource, source_id) is None:
        raise ValueError("evidence source does not exist")
    evidence = ComponentCompatibilityEvidence(
        compatibility_id=relationship.id, source_id=source_id,
        locator=locator or "", directly_states_claim=directly_states_claim, notes=notes)
    db.add(evidence)
    db.flush()
    return evidence


def evidence_facts(db, relationship_id: int):
    rows = (db.query(ComponentCompatibilityEvidence, BomSource)
            .join(BomSource, BomSource.id == ComponentCompatibilityEvidence.source_id)
            .filter(ComponentCompatibilityEvidence.compatibility_id == relationship_id)
            .order_by(ComponentCompatibilityEvidence.id).all())
    return [{"evidence": link, "source": source,
             "authority": SOURCE_AUTHORITY.get(source.source_type.lower(), 0)}
            for link, source in rows]


def set_status(db, relationship: ComponentCompatibility, status: str):
    if status not in STATUSES:
        raise ValueError("unknown compatibility status")
    facts = evidence_facts(db, relationship.id)
    if status in EVIDENCE_REQUIRED_STATUSES and not facts:
        raise ValueError("a non-draft compatibility status requires evidence")
    if status == "verified" and not any(
            fact["evidence"].directly_states_claim or fact["authority"] >= 3
            for fact in facts):
        raise ValueError("verified compatibility requires direct or authoritative evidence")
    relationship.status = status
    db.flush()
    return relationship


def detach_evidence(db, evidence: ComponentCompatibilityEvidence):
    relationship = db.get(ComponentCompatibility, evidence.compatibility_id)
    remaining = (db.query(ComponentCompatibilityEvidence)
                 .filter(ComponentCompatibilityEvidence.compatibility_id == evidence.compatibility_id,
                         ComponentCompatibilityEvidence.id != evidence.id).count())
    if (relationship and relationship.status in EVIDENCE_REQUIRED_STATUSES
            and remaining == 0):
        raise ValueError("cannot remove the last evidence from a promoted relationship")
    if relationship and relationship.status == "verified":
        remaining_facts = [fact for fact in evidence_facts(db, relationship.id)
                           if fact["evidence"].id != evidence.id]
        if not any(fact["evidence"].directly_states_claim or fact["authority"] >= 3
                   for fact in remaining_facts):
            raise ValueError("cannot remove evidence supporting verified status")
    db.delete(evidence)


def attach_house_mapping_evidence(db, option: BomHousePartOption, source_id: int,
                                  *, locator="", directly_states_mapping=False,
                                  notes=None):
    if db.get(BomSource, source_id) is None:
        raise ValueError("evidence source does not exist")
    row = BomHousePartOptionEvidence(
        option_id=option.id, source_id=source_id, locator=locator or "",
        directly_states_mapping=directly_states_mapping, notes=notes)
    db.add(row)
    db.flush()
    return row


def set_house_mapping_status(db, option: BomHousePartOption, status: str):
    allowed = {"draft", "confirmed", "production-supplier", "probable",
               "disputed", "unknown"}
    if status not in allowed:
        raise ValueError("unknown house-number mapping status")
    evidence_count = db.query(BomHousePartOptionEvidence).filter_by(
        option_id=option.id).count()
    if status not in {"draft", "unknown"} and evidence_count == 0:
        raise ValueError("a promoted house-number mapping requires evidence")
    option.mapping_status = status
    db.flush()
    return option


def create_production_use(db, part_number_id: int, reference_bom_id: int,
                          *, position_id=None, notes=None):
    _validate_scope(db, reference_bom_id, position_id)
    if db.get(BomPartNumber, part_number_id) is None:
        raise ValueError("production use requires a manufacturer part number")
    row = ComponentProductionUse(
        part_number_id=part_number_id, reference_bom_id=reference_bom_id,
        position_id=position_id, status="draft", notes=notes)
    db.add(row)
    db.flush()
    return row


def attach_production_evidence(db, production_use: ComponentProductionUse,
                               source_id: int, *, locator="", notes=None):
    if db.get(BomSource, source_id) is None:
        raise ValueError("evidence source does not exist")
    row = ComponentProductionUseEvidence(
        production_use_id=production_use.id, source_id=source_id,
        locator=locator or "", notes=notes)
    db.add(row)
    db.flush()
    return row


def set_production_use_status(db, production_use: ComponentProductionUse, status: str):
    if status not in STATUSES:
        raise ValueError("unknown production-use status")
    evidence_count = db.query(ComponentProductionUseEvidence).filter_by(
        production_use_id=production_use.id).count()
    if status in EVIDENCE_REQUIRED_STATUSES and evidence_count == 0:
        raise ValueError("a non-draft production-use status requires evidence")
    production_use.status = status
    db.flush()
    return production_use


def _applies(row, reference: ReferenceBom | None, position: BomPosition | None):
    if (row.scope_reference_bom_id is not None
            and (reference is None or row.scope_reference_bom_id != reference.id)):
        return False
    if (row.scope_position_id is not None
            and (position is None or row.scope_position_id != position.id)):
        return False
    if row.region is not None and (reference is None or row.region != reference.region):
        return False
    if row.platform is not None and (reference is None or row.platform != reference.platform):
        return False
    if (row.manufacturer is not None
            and (reference is None or row.manufacturer != reference.manufacturer)):
        return False
    if (row.required_package is not None
            and (position is None or row.required_package != position.package)):
        return False
    return not (row.video_standard is not None
                and (reference is None
                     or row.video_standard != reference.video_standard))


def direct_substitutes(db, part_number_id: int, *, reference=None, position=None,
                       include_drafts=False):
    """Return explicit facts with directionality and evidence kept visible."""
    query = db.query(ComponentCompatibility).filter(or_(
        ComponentCompatibility.source_part_number_id == part_number_id,
        and_(ComponentCompatibility.relationship_type.in_(SYMMETRIC_TYPES),
             ComponentCompatibility.target_part_number_id == part_number_id),
    ))
    if not include_drafts:
        query = query.filter(ComponentCompatibility.status != "draft")
    result = []
    for row in query.order_by(ComponentCompatibility.id):
        if not _applies(row, reference, position):
            continue
        candidate_id = (row.source_part_number_id
                        if row.target_part_number_id == part_number_id
                        else row.target_part_number_id)
        result.append({"relationship": row,
                       "candidate": db.get(BomPartNumber, candidate_id),
                       "evidence": evidence_facts(db, row.id)})
    return result


def candidates_for_position(db, position: BomPosition):
    """Return owned stock justified by exact identity or an explicit assertion."""
    reference = db.get(ReferenceBom, position.reference_bom_id)
    identities = {}
    expected_part_ids = []
    if position.part_number_id is not None:
        expected_part_ids.append(position.part_number_id)
        identities[position.part_number_id] = {
            "classification": "exact", "fact": None, "reason": "exact expected part"}
    if position.house_part_id is not None:
        mappings = (db.query(BomHousePartOption)
                    .filter(BomHousePartOption.house_part_id == position.house_part_id,
                            BomHousePartOption.mapping_status.in_({
                                "confirmed", "production-supplier", "probable"}))
                    .all())
        for mapping in mappings:
            expected_part_ids.append(mapping.part_number_id)
            classification = ("conditional" if mapping.mapping_status == "probable"
                              else "manufacturer-alternate")
            identities.setdefault(mapping.part_number_id, {
                "classification": classification, "fact": None,
                "reason": f"house-number mapping: {mapping.mapping_status}"})
    for expected_part_id in expected_part_ids:
        for fact in direct_substitutes(db, expected_part_id,
                                       reference=reference, position=position):
            relation = fact["relationship"]
            if relation.status not in PROMOTED_STATUSES or relation.relationship_type == "incompatible":
                continue
            classification = ("conditional" if relation.relationship_type ==
                              "conditional-substitute" else "substitute")
            if relation.relationship_type in {
                    "exact-equivalent", "manufacturer-alternate", "production-alternate"}:
                classification = "manufacturer-alternate"
            identities.setdefault(fact["candidate"].id, {
                "classification": classification, "fact": fact,
                "reason": relation.relationship_type})
    if not identities:
        return []
    lots = (db.query(InventoryLot)
            .filter(InventoryLot.part_number_id.in_(identities),
                    InventoryLot.active.is_(True), InventoryLot.quantity > 0).all())
    result = []
    for lot in lots:
        if (lot.test_status or "").lower() in {"failed", "intermittent"}:
            continue
        unavailable = (db.query(InventoryItem)
                       .filter(InventoryItem.lot_id == lot.id,
                               or_(InventoryItem.lifecycle_status != "inventory",
                                   InventoryItem.active.is_(False))).count())
        usable = max(0, lot.quantity - unavailable)
        if usable:
            result.append({"lot": lot, "part_number": db.get(BomPartNumber, lot.part_number_id),
                           "usable_quantity": usable, **identities[lot.part_number_id]})
    return result
