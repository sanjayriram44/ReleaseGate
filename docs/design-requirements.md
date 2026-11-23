# Phase 5 design requirements and the tests that check them

**Status: DRAFT (2026-11-22), for the team to review.** Drawn by Claude from the Phase 5 models
(architecture, behavior and information schema, Q5.1) and `docs/decisions.md`.

This is the mapping the course's spec v2 asks for in the tester's **model coverage**
(`coverage.model`). The tester reports it only when it tests our own system.
- `total` is the number of design requirements below (14).
- `covered` is how many of them the suite evaluated in that session. A requirement counts once
  one of its mapped checks ran, whether or not the check passed.

The machine copy is `tester/model.py`, and `tests/unit/test_model_coverage.py` fails if the two
differ, or if a mapped check no longer exists.

| ID | Design requirement | Model | Tester checks |
|---|---|---|---|
| DR-01 | A release's support status is computed on every read from the injectable clock and is never stored. | Information schema; architecture (clock) | `ac01.*` |
| DR-02 | A release is unique per product and version, and an unknown release is 404. | Information schema | `contract.duplicate`, `contract.unknown_release` |
| DR-03 | The components of a valid CycloneDX SBOM, nested ones flattened, are stored for its release and listed back. | Behavior (SBOM upload); information schema | `ac02.*` |
| DR-04 | An SBOM upload checks the release first (404), then the JSON and the CycloneDX schema; a rejection states its reason and stores nothing. | Behavior (SBOM upload) | `ac03.*` |
| DR-05 | A new valid SBOM replaces the release's components in one transaction; an invalid one leaves them unchanged. | Behavior (SBOM upload) | `contract.replace`, `contract.invalid_keeps_existing` |
| DR-06 | The CVE query asks the vulnerability source first (503 when it is unreachable), then answers 404 for an unknown CVE. | Behavior (CVE query); architecture | `ac05.*` |
| DR-07 | Affected releases come from purl matching against stored components and are grouped by support status at the clock's time. | Behavior (CVE query) | `ac04.*` |
| DR-08 | An incident stores the human-supplied awareness_at, classification and rationale; invalid input is 400 and stores nothing. | Information schema | `ac06.*` |
| DR-09 | Deadlines (awareness + 24 h, + 72 h, fix + 14 days) and their status are computed on every read from stored timestamps and the clock, with no timer. | Behavior (deadline statechart) | `ac07.*` |
| DR-10 | Report data is checked against one stage-field table, and each stage's report is built on read from the stored data, with missing_fields. | Behavior (report data, Panel D); information schema (REPORT_DATA) | `ac08.*` |
| DR-11 | Every successful state change writes exactly one audit entry in the same transaction, with the user and the clock's time; a rejected request writes none. | Information schema (AUDIT_LOG) | `ac09.steps`, `ac09.rejected_adds_nothing`, `ac09.four_events`, `ac09.order`, `ac09.timestamps`, `contract.audit_list` |
| DR-12 | Audit entries cannot be changed or deleted through the API (405). | Information schema (AUDIT_LOG triggers); architecture | `ac09.immutable`, `contract.audit_patch`, `contract.audit_delete` |
| DR-13 | The gated test endpoints reset all state, including the audit log, and set the injectable clock. | Architecture (test endpoints) | `setup.*`, `teardown.*`, `ac09.reset` |
| DR-14 | All stored data survives a process restart with no timestamp drift (AC-10). | Architecture (SQLite on a named volume) | None in a single run: the two-step `python -m tester.ac10 snapshot` / `verify` procedure evaluates it |

A tester run against our own system evaluates DR-01 to DR-13, so it reports `covered: 13`,
`total: 14`.
