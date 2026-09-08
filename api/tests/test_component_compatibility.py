"""Compatibility facts stay explicit, directional, scoped and evidenced."""
import pytest
from sqlalchemy.exc import DBAPIError

from app import compatibility
from app.models import (BomComponent, BomHousePart, BomHousePartOption,
                        BomPartNumber, BomPosition, BomSource,
                        ComponentCompatibility, ComponentProductionUse,
                        InventoryItem, InventoryLot, PartBom, ReferenceBom)


def _identity(db, number, *, generic=None, manufacturer="Example", package="DIP"):
    component = generic or BomComponent(generic_name=number.removeprefix("SN"))
    if component.id is None:
        db.add(component)
        db.flush()
    part = BomPartNumber(component_id=component.id, manufacturer=manufacturer,
                         part_number=number, package=package)
    db.add(part)
    db.flush()
    return component, part


def _source(db, source_type="manufacturer datasheet"):
    source = BomSource(source_type=source_type, title="Compatibility evidence")
    db.add(source)
    db.flush()
    return source


def _board(db, expected_part, *, region="UK", video="PAL", refdes="U13",
           platform=None, manufacturer=None, package=None):
    reference = ReferenceBom(name="Board", region=region, video_standard=video,
                             platform=platform, manufacturer=manufacturer)
    db.add(reference)
    db.flush()
    position = BomPosition(reference_bom_id=reference.id, refdes=refdes,
                           component_id=expected_part.component_id,
                           part_number_id=expected_part.id, package=package)
    db.add(position)
    db.flush()
    return reference, position


def _promoted(db, expected, candidate, relationship="electrical-substitute", **fields):
    row = compatibility.create_draft(
        db, expected.id, candidate.id, relationship, **fields)
    compatibility.attach_evidence(db, row, _source(db).id,
                                  directly_states_claim=True)
    compatibility.set_status(db, row, "verified")
    return row


class TestIdentity:
    def test_generic_and_manufacturer_parts_remain_distinct(self, db):
        generic, first = _identity(db, "SN74LS257N")
        _same, second = _identity(db, "74LS257PC", generic=generic,
                                  manufacturer="Motorola")

        assert first.component_id == second.component_id == generic.id
        assert first.id != second.id
        assert compatibility.direct_substitutes(db, first.id) == []

    def test_house_number_can_map_to_multiple_manufacturer_parts(self, db):
        generic, first = _identity(db, "SN74LS257N")
        _same, second = _identity(db, "74LS257PC", generic=generic)
        house = BomHousePart(component_id=generic.id, organization="Commodore",
                             house_number="901521-57")
        db.add(house)
        db.flush()
        db.add_all([BomHousePartOption(house_part_id=house.id, part_number_id=first.id),
                    BomHousePartOption(house_part_id=house.id, part_number_id=second.id)])
        db.commit()

        assert {row.part_number_id for row in db.query(BomHousePartOption)} == {
            first.id, second.id}

    def test_house_number_mapping_promotion_requires_evidence(self, db):
        generic, part_number = _identity(db, "SN74LS257N")
        house = BomHousePart(component_id=generic.id, organization="Commodore",
                             house_number="901521-57")
        db.add(house)
        db.flush()
        option = BomHousePartOption(house_part_id=house.id,
                                    part_number_id=part_number.id)
        db.add(option)
        db.flush()
        with pytest.raises(ValueError, match="requires evidence"):
            compatibility.set_house_mapping_status(db, option, "confirmed")
        compatibility.attach_house_mapping_evidence(db, option, _source(db).id,
                                                      directly_states_mapping=True)
        compatibility.set_house_mapping_status(db, option, "confirmed")
        assert option.mapping_status == "confirmed"

    def test_observed_text_does_not_create_canonical_identity(self, db, part):
        _generic, expected = _identity(db, "SN74LS257N")
        _reference, position = _board(db, expected)
        board = part(type="motherboard")
        from app.models import PartBom, PartBomPositionState
        db.add(PartBom(part_id=board["asset_id"],
                       reference_bom_id=position.reference_bom_id))
        db.add(PartBomPositionState(
            part_id=board["asset_id"], reference_bom_id=position.reference_bom_id,
            position_id=position.id, state="present", observed="mystery 257 marking"))
        db.commit()

        assert db.query(BomPartNumber).count() == 1


class TestRelationships:
    def test_directional_substitute_has_no_implicit_reverse(self, db):
        _generic, expected = _identity(db, "EXPECTED")
        _generic2, candidate = _identity(db, "CANDIDATE")
        _promoted(db, expected, candidate)

        assert compatibility.direct_substitutes(db, expected.id)[0]["candidate"].id == candidate.id
        assert compatibility.direct_substitutes(db, candidate.id) == []

    def test_exact_equivalence_queries_symmetrically(self, db):
        generic, first = _identity(db, "FIRST")
        _same, second = _identity(db, "SECOND", generic=generic)
        _promoted(db, first, second, "exact-equivalent")

        assert compatibility.direct_substitutes(db, second.id)[0]["candidate"].id == first.id

    def test_self_reference_and_duplicate_are_rejected(self, db):
        _generic, first = _identity(db, "FIRST")
        _generic2, second = _identity(db, "SECOND")
        with pytest.raises(ValueError, match="itself"):
            compatibility.create_draft(db, first.id, first.id, "exact-equivalent")
        compatibility.create_draft(db, first.id, second.id, "electrical-substitute")
        with pytest.raises(ValueError, match="already exists"):
            compatibility.create_draft(db, first.id, second.id, "electrical-substitute")

    def test_reverse_duplicate_equivalence_is_rejected(self, db):
        _generic, first = _identity(db, "FIRST")
        _generic2, second = _identity(db, "SECOND")
        compatibility.create_draft(db, first.id, second.id, "exact-equivalent")
        with pytest.raises(ValueError, match="already exists"):
            compatibility.create_draft(db, second.id, first.id, "exact-equivalent")

    @pytest.mark.parametrize("dimension", sorted(compatibility.DIMENSION_FIELDS))
    def test_exact_equivalence_rejects_explicit_contradictions(self, db, dimension):
        _generic, first = _identity(db, "FIRST")
        _generic2, second = _identity(db, "SECOND")
        with pytest.raises(ValueError, match="incompatible dimension"):
            compatibility.create_draft(
                db, first.id, second.id, "exact-equivalent",
                **{dimension: "incompatible"})

    def test_database_rejects_self_reference(self, db):
        _generic, first = _identity(db, "FIRST")
        db.add(ComponentCompatibility(
            source_part_number_id=first.id, target_part_number_id=first.id,
            relationship_type="exact-equivalent", status="draft"))
        with pytest.raises(DBAPIError):
            db.commit()
        db.rollback()

    @pytest.mark.parametrize(("field", "value"), [
        ("relationship_type", "magic"),
        ("status", "certain-ish"),
        ("timing_compatible", "maybe"),
    ])
    def test_database_rejects_invalid_compatibility_enums(self, db, field, value):
        _generic, first = _identity(db, "FIRST")
        _generic2, second = _identity(db, "SECOND")
        values = {"source_part_number_id": first.id,
                  "target_part_number_id": second.id,
                  "relationship_type": "electrical-substitute", "status": "draft"}
        values[field] = value
        db.add(ComponentCompatibility(**values))
        with pytest.raises(DBAPIError):
            db.commit()
        db.rollback()

    def test_database_requires_canonical_manufacturer_part_endpoints(self, db):
        db.add(ComponentCompatibility(
            source_part_number_id=999998, target_part_number_id=999999,
            relationship_type="electrical-substitute", status="draft"))
        with pytest.raises(DBAPIError):
            db.commit()
        db.rollback()

    def test_conditional_caveat_and_explicit_incompatibility_remain_visible(self, db):
        _generic, expected = _identity(db, "EXPECTED")
        _generic2, candidate = _identity(db, "CANDIDATE")
        conditional = compatibility.create_draft(
            db, expected.id, candidate.id, "conditional-substitute",
            caveat="PAL boards only", timing_compatible="conditional")
        incompatible = compatibility.create_draft(
            db, expected.id, candidate.id, "incompatible")
        for row in (conditional, incompatible):
            compatibility.attach_evidence(db, row, _source(db).id,
                                          directly_states_claim=True)
            compatibility.set_status(db, row, "evidenced")
        db.commit()

        rows = compatibility.direct_substitutes(db, expected.id)
        assert {row["relationship"].relationship_type for row in rows} == {
            "conditional-substitute", "incompatible"}
        assert conditional.caveat == "PAL boards only"


class TestEvidence:
    def test_draft_needs_no_evidence_but_promotion_does(self, db):
        _generic, expected = _identity(db, "EXPECTED")
        _generic2, candidate = _identity(db, "CANDIDATE")
        row = compatibility.create_draft(db, expected.id, candidate.id,
                                         "functional-substitute")
        with pytest.raises(ValueError, match="requires evidence"):
            compatibility.set_status(db, row, "evidenced")
        compatibility.attach_evidence(db, row, _source(db).id)
        compatibility.set_status(db, row, "evidenced")
        assert row.status == "evidenced"

    def test_verified_requires_direct_or_authoritative_evidence(self, db):
        _generic, expected = _identity(db, "EXPECTED")
        _generic2, candidate = _identity(db, "CANDIDATE")
        row = compatibility.create_draft(db, expected.id, candidate.id,
                                         "functional-substitute")
        compatibility.attach_evidence(
            db, row, _source(db, "user observation/test result").id)
        with pytest.raises(ValueError, match="authoritative"):
            compatibility.set_status(db, row, "verified")

    def test_disputed_fact_remains_queryable(self, db):
        _generic, expected = _identity(db, "EXPECTED")
        _generic2, candidate = _identity(db, "CANDIDATE")
        row = compatibility.create_draft(db, expected.id, candidate.id,
                                         "electrical-substitute")
        compatibility.attach_evidence(db, row, _source(db).id)
        compatibility.set_status(db, row, "disputed")
        assert compatibility.direct_substitutes(db, expected.id)[0]["relationship"] is row

    def test_last_evidence_cannot_be_detached_from_promoted_fact(self, db):
        _generic, expected = _identity(db, "EXPECTED")
        _generic2, candidate = _identity(db, "CANDIDATE")
        row = _promoted(db, expected, candidate)
        evidence = compatibility.evidence_facts(db, row.id)[0]["evidence"]
        with pytest.raises(ValueError, match="last evidence"):
            compatibility.detach_evidence(db, evidence)

    def test_database_prevents_deleting_an_evidence_source_in_use(self, db):
        _generic, expected = _identity(db, "EXPECTED")
        _generic2, candidate = _identity(db, "CANDIDATE")
        row = compatibility.create_draft(db, expected.id, candidate.id,
                                         "electrical-substitute")
        source = _source(db)
        compatibility.attach_evidence(db, row, source.id)
        db.commit()
        db.delete(source)
        with pytest.raises(DBAPIError):
            db.commit()
        db.rollback()


class TestApplicabilityAndInventory:
    def test_global_board_position_and_video_scopes_are_distinct(self, db):
        _generic, expected = _identity(db, "EXPECTED")
        candidates = [_identity(db, name)[1] for name in ("GLOBAL", "BOARD", "POSITION", "NTSC")]
        pal_ref, pal_position = _board(db, expected)
        other_ref, other_position = _board(db, expected, region="US", video="NTSC")
        _promoted(db, expected, candidates[0])
        _promoted(db, expected, candidates[1], scope_reference_bom_id=pal_ref.id)
        _promoted(db, expected, candidates[2], scope_reference_bom_id=pal_ref.id,
                  scope_position_id=pal_position.id)
        _promoted(db, expected, candidates[3], video_standard="NTSC")

        pal = {row["candidate"].part_number for row in compatibility.direct_substitutes(
            db, expected.id, reference=pal_ref, position=pal_position)}
        ntsc = {row["candidate"].part_number for row in compatibility.direct_substitutes(
            db, expected.id, reference=other_ref, position=other_position)}
        assert pal == {"GLOBAL", "BOARD", "POSITION"}
        assert ntsc == {"GLOBAL", "NTSC"}

    def test_wrong_bom_position_scope_is_rejected(self, db):
        _generic, expected = _identity(db, "EXPECTED")
        _generic2, candidate = _identity(db, "CANDIDATE")
        first_ref, _first_position = _board(db, expected)
        _other_ref, other_position = _board(db, expected, refdes="U14")
        with pytest.raises(ValueError, match="does not belong"):
            compatibility.create_draft(
                db, expected.id, candidate.id, "electrical-substitute",
                scope_reference_bom_id=first_ref.id,
                scope_position_id=other_position.id)

    def test_database_rejects_cross_bom_position_scope(self, db):
        _generic, expected = _identity(db, "EXPECTED")
        _generic2, candidate = _identity(db, "CANDIDATE")
        first_ref, _first_position = _board(db, expected)
        _other_ref, other_position = _board(db, expected, refdes="U14")
        db.add(ComponentCompatibility(
            source_part_number_id=expected.id, target_part_number_id=candidate.id,
            relationship_type="electrical-substitute", status="draft",
            scope_reference_bom_id=first_ref.id,
            scope_position_id=other_position.id))
        with pytest.raises(DBAPIError):
            db.commit()
        db.rollback()

    def test_database_rejects_duplicate_position_scoped_relationship(self, db):
        _generic, expected = _identity(db, "EXPECTED")
        _generic2, candidate = _identity(db, "CANDIDATE")
        reference, position = _board(db, expected)
        values = {
            "source_part_number_id": expected.id,
            "target_part_number_id": candidate.id,
            "relationship_type": "electrical-substitute", "status": "draft",
            "scope_reference_bom_id": reference.id,
            "scope_position_id": position.id,
        }
        db.add_all([ComponentCompatibility(**values), ComponentCompatibility(**values)])
        with pytest.raises(DBAPIError):
            db.commit()
        db.rollback()

    def test_platform_manufacturer_package_region_and_video_scope(self, db):
        _generic, expected = _identity(db, "EXPECTED")
        _generic2, candidate = _identity(db, "CANDIDATE")
        reference, position = _board(
            db, expected, platform="C64", manufacturer="Commodore", package="DIP",
            region="UK", video="PAL")
        _promoted(db, expected, candidate, platform="C64", manufacturer="Commodore",
                  required_package="DIP", region="UK", video_standard="PAL")

        assert compatibility.direct_substitutes(
            db, expected.id, reference=reference, position=position)
        reference.video_standard = "NTSC"
        assert compatibility.direct_substitutes(
            db, expected.id, reference=reference, position=position) == []

    def test_global_and_narrower_incompatible_claims_remain_queryable(self, db):
        _generic, expected = _identity(db, "EXPECTED")
        _generic2, candidate = _identity(db, "CANDIDATE")
        reference, position = _board(db, expected)
        _promoted(db, expected, candidate, "documented-service-substitute")
        _promoted(db, expected, candidate, "incompatible",
                  scope_reference_bom_id=reference.id)

        relationships = {fact["relationship"].relationship_type
                         for fact in compatibility.direct_substitutes(
                             db, expected.id, reference=reference, position=position)}
        assert relationships == {"documented-service-substitute", "incompatible"}

    def test_inventory_candidates_require_explicit_identity_or_relationship(self, db):
        generic, expected = _identity(db, "EXPECTED")
        _same, looks_related = _identity(db, "LOOKS-RELATED", generic=generic)
        _other, substitute = _identity(db, "SUBSTITUTE")
        _other2, conditional = _identity(db, "CONDITIONAL")
        _ref, position = _board(db, expected)
        _promoted(db, expected, substitute)
        _promoted(db, expected, conditional, "conditional-substitute",
                  caveat="socket adapter required")
        for part_number, status in ((expected, "passed"), (looks_related, "passed"),
                                    (substitute, "passed"), (conditional, "passed")):
            db.add(InventoryLot(component_id=part_number.component_id,
                                part_number_id=part_number.id, quantity=1,
                                test_status=status))
        db.commit()

        rows = compatibility.candidates_for_position(db, position)
        by_number = {row["part_number"].part_number: row for row in rows}
        assert set(by_number) == {"EXPECTED", "SUBSTITUTE", "CONDITIONAL"}
        assert by_number["EXPECTED"]["classification"] == "exact"
        assert by_number["CONDITIONAL"]["classification"] == "conditional"
        assert by_number["CONDITIONAL"]["fact"]["relationship"].caveat

    def test_generic_only_position_does_not_infer_manufacturer_candidates(self, db):
        generic, arbitrary_part = _identity(db, "ARBITRARY")
        reference = ReferenceBom(name="Generic-only board")
        db.add(reference)
        db.flush()
        position = BomPosition(reference_bom_id=reference.id, refdes="U13",
                               component_id=generic.id)
        db.add_all([position, InventoryLot(
            component_id=generic.id, part_number_id=arbitrary_part.id,
            quantity=5, test_status="passed")])
        db.commit()

        assert compatibility.candidates_for_position(db, position) == []

    def test_evidenced_house_mapping_can_supply_inventory_candidate(self, db):
        generic = BomComponent(generic_name="74LS257")
        db.add(generic)
        db.flush()
        _same, manufacturer_part = _identity(db, "SN74LS257N", generic=generic)
        house = BomHousePart(component_id=generic.id, organization="Commodore",
                             house_number="901521-57")
        reference = ReferenceBom(name="House-number board")
        db.add_all([house, reference])
        db.flush()
        position = BomPosition(reference_bom_id=reference.id, refdes="U13",
                               component_id=generic.id, house_part_id=house.id)
        option = BomHousePartOption(house_part_id=house.id,
                                    part_number_id=manufacturer_part.id)
        db.add_all([position, option])
        db.flush()
        compatibility.attach_house_mapping_evidence(db, option, _source(db).id)
        compatibility.set_house_mapping_status(db, option, "confirmed")
        db.add(InventoryLot(component_id=generic.id,
                            part_number_id=manufacturer_part.id, quantity=1,
                            test_status="passed"))
        db.commit()

        candidate = compatibility.candidates_for_position(db, position)[0]
        assert candidate["part_number"].id == manufacturer_part.id
        assert candidate["classification"] == "manufacturer-alternate"
        assert candidate["reason"] == "house-number mapping: confirmed"

    def test_failed_or_unavailable_stock_is_excluded(self, db):
        _generic, expected = _identity(db, "EXPECTED")
        _ref, position = _board(db, expected)
        failed = InventoryLot(part_number_id=expected.id, quantity=1, test_status="failed")
        unavailable = InventoryLot(part_number_id=expected.id, quantity=1,
                                   test_status="passed")
        intermittent = InventoryLot(part_number_id=expected.id, quantity=1,
                                    test_status="intermittent")
        inactive = InventoryLot(part_number_id=expected.id, quantity=1,
                                test_status="passed", active=False)
        db.add_all([failed, unavailable, intermittent, inactive])
        db.flush()
        db.add(InventoryItem(lot_id=unavailable.id, lifecycle_status="installed"))
        db.commit()

        assert compatibility.candidates_for_position(db, position) == []


class TestHistoricalProductionUse:
    def test_production_use_is_separate_from_technical_compatibility(self, db):
        _generic, fitted = _identity(db, "ORIGINAL")
        reference, position = _board(db, fitted)
        use = compatibility.create_production_use(
            db, fitted.id, reference.id, position_id=position.id)
        with pytest.raises(ValueError, match="requires evidence"):
            compatibility.set_production_use_status(db, use, "verified")
        compatibility.attach_production_evidence(db, use, _source(db).id,
                                                  locator="parts list p. 4")
        compatibility.set_production_use_status(db, use, "verified")
        db.commit()

        assert db.query(ComponentProductionUse).one().status == "verified"
        assert compatibility.direct_substitutes(db, fitted.id) == []

    def test_database_rejects_invalid_production_use_status(self, db):
        _generic, fitted = _identity(db, "ORIGINAL")
        reference, _position = _board(db, fitted)
        db.add(ComponentProductionUse(
            part_number_id=fitted.id, reference_bom_id=reference.id,
            status="legend"))
        with pytest.raises(DBAPIError):
            db.commit()
        db.rollback()

    def test_database_rejects_invalid_house_mapping_status(self, db):
        generic, part_number = _identity(db, "ORIGINAL")
        house = BomHousePart(component_id=generic.id, organization="Commodore",
                             house_number="901521-57")
        db.add(house)
        db.flush()
        db.add(BomHousePartOption(
            house_part_id=house.id, part_number_id=part_number.id,
            mapping_status="folklore"))
        with pytest.raises(DBAPIError):
            db.commit()
        db.rollback()


class TestCompatibilityPresentation:
    def test_workbench_exposes_status_evidence_and_caveat(self, client, db, part):
        _generic, expected = _identity(db, "EXPECTED")
        _generic2, candidate = _identity(db, "CANDIDATE")
        reference, position = _board(db, expected)
        board = part(type="motherboard")
        db.add(PartBom(part_id=board["asset_id"], reference_bom_id=reference.id))
        _promoted(db, expected, candidate, "conditional-substitute",
                  caveat="requires a socket adapter",
                  scope_reference_bom_id=reference.id,
                  scope_position_id=position.id)
        db.commit()

        page = client.get(f"/parts/{board['asset_id']}/bom").text

        assert "CANDIDATE" in page
        assert "conditional-substitute" in page
        assert "verified" in page
        assert "requires a socket adapter" in page
