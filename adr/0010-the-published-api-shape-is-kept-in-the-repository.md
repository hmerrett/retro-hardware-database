# 0010 — The published API shape is kept in the repository

**Status:** Accepted
**Date:** 2026-09-11

## Context

FastAPI writes the OpenAPI document from the code, every time the app starts. It
is therefore incapable of disagreeing with the code: rename a field and the
document renames it too, and `/docs` goes on looking perfectly correct. Nothing
was kept between one version and the next, so there was not even a copy to hold
this month's against last month's.

The practical effect is that no caller-visible change to the API could fail
anything. `asset_id` could become `id` and the whole of CI would stay green,
while every QR label printed against this register, `tools/rhdb.py` and anything
anyone wrote against the API later would break. The suite would not object
either: its tests were written after the code by observing it, so they report the
shape rather than require it — a rename makes them red in the way that reads
"update the test", not "you have broken something".

This was raised in review as the first of a set of related criticisms: that the
specification is a product of the code rather than a definition it is built to,
and that the tests verify the implementation rather than the intent. The full
remedy — authoring the document first and making the code conform — belongs to a
project that means to be extensible, and this one has settled on configurable
(README). The half that is worth having regardless is the part that turns a
silent change into a visible one.

## Decision

**The document is committed to `api/openapi.json`, and a test compares it with
the one the running app produces.** A change to any route or model that callers
can see fails that test, and the failure names what moved rather than printing a
diff of a 76KB file. Recording an intended change is deliberate and separate:

    RHDB_UPDATE_OPENAPI=1 pytest api/tests/test_openapi_contract.py

which rewrites the file, so the change arrives in a pull request as a diff of the
published shape — a thing a reviewer can read and agree to.

**The document stays generated.** This is a ratchet, not an authored contract.
It does not make the document the definition, and it cannot catch a design that
was wrong from the first commit; it catches the shape changing under callers who
were promised the old one.

## Consequences

- The file covers the `/api` surface only — 26 operations across 15 paths. The
  HTML pages are `include_in_schema=False` and are not callers' business.
- An upgrade to FastAPI or Pydantic that renders the document differently will
  fail this test too. That is correct and is the point: the published document
  did change, and whether callers can live with it is a question worth being
  asked once per upgrade rather than never.
- Eight of the 26 operations still declare no response model, so the contract is
  thin exactly where the deletes and `/api/machines`, `/api/items/{aid}/log` and
  `/api/files` are. Pinning the document does not fix that; it does stop it
  getting worse quietly.
- If the document is ever to become the definition rather than the report, the
  direction of the arrow has to reverse — the file authored, the code made to
  conform, and this test inverted into a conformance check. Nothing here blocks
  that; it is the same file.
