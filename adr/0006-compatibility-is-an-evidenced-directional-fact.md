# 0006: Compatibility is an evidenced, directional fact

Date: 2026-09-08

## Status

Accepted for the component-compatibility foundation.

## Context

A generic component family, a manufacturer orderable part, a house number and
the literal marking observed on a device answer different questions. Treating a
shared family as proof of interchangeability would hide package, voltage,
pinout, timing, firmware and board-specific limitations. Historical production
use is also not proof that a part is the only technically suitable replacement.

## Decision

`BomComponent` remains the generic function or family. `BomPartNumber` remains a
manufacturer-specific implementation. `BomHousePart` and its options describe
organisation-specific stock-number mappings. Physical markings remain observed
state and never create canonical identities automatically.

Compatibility assertions run from the part expected by a design to the proposed
replacement. Exact equivalence is the sole symmetric relationship and is
queried in either direction; every other relationship is directional. Technical
dimensions are nullable so missing information remains unknown. Scope may be
global or limited by the existing Reference BOM, position, platform,
manufacturer, package, region or video-standard concepts.

Draft assertions may be incomplete. Evidenced, verified, disputed and deprecated
assertions retain evidence. Verified status additionally requires either a
source that directly states the claim or an authoritative technical source.
Evidence source deletion is restricted. Historical production use has its own
table and evidence rather than being encoded as technical compatibility.

MariaDB enforces valid lookup values, non-self relationships, canonical foreign
keys, position-to-BOM scope, evidence-source retention and the representable
unique scope. Service validation handles evidence-count promotion rules,
authority rules, symmetric reverse duplicates and duplicate global scopes where
SQL NULL uniqueness cannot express the intended rule cleanly.

Inventory candidate queries use exact manufacturer identity, evidence-promoted
house-number mappings, or explicit promoted compatibility assertions. They do
not infer candidates merely because two part numbers share a generic component.

## Consequences

Conflicting and conditional claims remain queryable instead of overwriting one
another. Candidate results can explain why stock was returned without allocating
or installing it. Curated compatibility and production data can be added later
without changing inventory quantity or donor-provenance semantics.
