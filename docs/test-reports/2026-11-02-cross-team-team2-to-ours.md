# Cross-team run: Team 2's tests against our service, 2026-11-02

**Commit:** `e8643407b5aed0fa69ff671d98a9e78ec7854225` (tag `phase4`; `/health` reported it before
and after the run)
**Target:** `http://136.116.160.182:8080` (the URL in the pod sheet)
**Runner:** Team 2's Phase 3 + Phase 4 pytest suite (`cra-service/test_api.py`, 157 tests;
`cra-service/test_phase4_api.py`, 196 tests), session `61081f53-4457-47ee-8fee-fce407dfcf30`,
2026-11-02T00:35:03Z to 00:35:32Z (UTC). Full report:
<https://team6-cross---cra-phase3-tester-2sn7vmtx4a-uc.a.run.app/test/report?session_id=61081f53-4457-47ee-8fee-fce407dfcf30>
**Result:** 341/353 passed (12 failed, 0 errors, 0 skipped; 96.6%)

The common interface works: the report came back complete and well formed (`result`, `summary`,
one check per test with AC, request, response and duration). Per AC: AC-01 61/63, AC-02 5/5,
AC-03 86/89, AC-04 10/10, AC-05 11/11, AC-06 59/62, AC-07 109/113.

## The 12 failures

| # | Tests | What happened | Contract | Owner |
|---|---|---|---|---|
| 1 | 5: `test_invalid_clock_preserves_reference`, `test_ac06_invalid_awareness_timestamp`, `test_ac07_invalid_mutation_timestamp` (patch, submission), `test_ac06_malformed_incident_cve_is_invalid_request`, all with a trailing `\n` | A timestamp or `cve_id` ending in a newline is accepted (200/201) instead of 400; the CVE ID is even stored with the `\n`. Python's `$` matches before a final newline in `app/clock.py` `_TIMESTAMP` and `app/models.py` `CVE_ID` (also `_DATE_RE`, though `date.fromisoformat` catches dates). | Bug: the value is not a valid timestamp or CVE ID | Us (Team 6) |
| 2 | 4: `test_clock_aware_input_uses_utc_date`, `test_ac06_aware_timestamp_normalized_to_utc`, `test_ac07_aware_mutation_times_normalize_microseconds` (patch, submission), input `2026-11-01t23:59:59z` | Lowercase `t` and `z` are rejected with 400; Team 2 expects them accepted and normalised to `…T…Z`. | `format: date-time` is RFC 3339, whose §5.6 note allows lowercase `t` and `z` | Us |
| 3 | 1: `test_sbom_requires_json_media_type` | A valid SBOM sent with `Content-Type: text/plain` is stored (200); Team 2 expects 400. Our JSON endpoints already reject a non-JSON media type; the SBOM upload reads the raw body and never checks it. | The SBOM request body lists only `application/json` | Us |
| 4 | 2: `test_ac03_invalid_sbom_never_changes_inventory[…invalid_encoding]` (empty, preserve-existing) | Status and code match (400 `INVALID_JSON`) and the inventory is unchanged; the test also wants the message to contain "JSON", and ours says "request body is not valid UTF-8 text". | Message wording is not in the contract | Team 2's test over-specifies; we can reword cheaply |

Unresolved at the time of writing: all four. None affects AC-04/AC-05 matching or the deadline
calculations; every deadline and status assertion passed.

## Coverage

- **Code:** not measurable from this run (black-box HTTP against the deployed container). Our own
  suite covers `app/` at the level in `docs/metrics.md`.
- **Component:** releases, SBOM upload, components, CVE query (including the unreachable source),
  incidents, fix time, submissions, plus the test reset, clock and vulnerability source. Gap: no
  test calls `GET /api/v1/audit-logs`, so REQ-07 audit output is untested by Team 2.
- **System model:** all seven acceptance criteria, AC-01 to AC-07, including the
  support boundary, invalid-SBOM atomicity, every deadline stage and status, and duplicate
  submissions.

## Side effect

The run reset the live data and left the test clock at `2026-11-01T23:59:59Z`. The demo data must
be re-seeded and the clock returned to real time (`POST /api/v1/test/reset` does both).
