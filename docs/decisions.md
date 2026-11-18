# Decisions

Agreed answers and outstanding proposals are recorded below. Proposed details still need pod (Team 2) confirmation. Team 2's answers to the Phase 4 questions (`docs/pod-questions-phase4.md`) arrived on 2026-11-01.

| Topic | Answer | Status |
|---|---|---|
| Missing `X-User-Id` | Endpoints requiring the header return 400 with `INVALID_REQUEST` when it is missing. Test-control endpoints are exempt. | agreed |
| CycloneDX versions | Accept valid CycloneDX JSON with `specVersion` 1.4, 1.5, or 1.6. Reject unsupported versions with 400 and an explanatory message. | agreed |
| Component without `version` | Reject the entire SBOM with 400 if an inventory component, including a nested component, is missing a required version. | agreed |
| Error-code assertions | Check exact error codes for explicitly agreed cases, alongside HTTP statuses and meaningful nonempty messages. For other cases, check the status and error envelope until specific code values are agreed. | recommended |
| Nested components | Recursively flatten nested inventory components and include every component at every depth in storage and `component_count`. Proposed details: exclude metadata and tool components, and retain repeated occurrences unless agreed otherwise. Implementation: document order, each parent before its children; a missing version at any depth rejects the SBOM with the component's path. | recursive flattening agreed; exclusions and repeated occurrences proposed |
| Unregistered release + SBOM | Check release existence before validating the SBOM body. Unknown release IDs return 404. | agreed |
| SBOM schema strictness | Official CycloneDX schemas bundled with `cyclonedx-python-lib` (non-vendored); unknown properties that the official schema forbids are rejected | implementation choice |
| Shared fixtures | `fixtures/` (25-component SBOM and releases fixture) reviewed by Team 6 and used unchanged by both teams | agreed with Team 2 (2026-10-17) |
| Timestamp format (§10 Q1) | Inputs may end in `Z` or a numeric offset (`+02:00`, `-00:00`, up to ±23:59) and are converted to UTC; a timestamp with no zone is 400. Fractional seconds are kept (truncated beyond microseconds). Outputs always end in `Z`: whole seconds without a fraction, otherwise six digits (`2026-11-01T23:59:59.100000Z`). One parser and formatter in `app/clock.py`. | agreed with Team 2 (2026-11-01) |
| Deadline statuses (Q2) | A stage submitted at or before its deadline is `met`. Unsubmitted, it is `pending` while now ≤ deadline and `overdue` from one second later. A late submission stays `overdue` with `submitted_at` set (no `late` status). Voluntary cases, and the final report before `fix_available_at`, are `not_applicable` with `deadline_at: null`. | agreed with Team 2 (2026-11-01) |
| Submission errors (Q2) | A second submission for the same stage is 409 `SUBMISSION_EXISTS` (added to the contract); a submission for a `not_applicable` stage is 400. | agreed with Team 2 (2026-11-01); contract addition in c249e2c, which Team 2 applies to their copy |
| Incident timestamps (Q3) | `submitted_at` or `fix_available_at` earlier than `awareness_at` is 400. Times later than the clock's now are accepted. A second `fix_available_at` overwrites the first and is audited again. On a voluntary incident it is stored, but every deadline stays `not_applicable`. | agreed with Team 2 (2026-11-01) |
| Malformed CVE ID; incident `cve_id` (Q4) | A CVE ID that doesn't match `^CVE-[0-9]{4}-[0-9]+$` is 400 `INVALID_REQUEST` on the CVE query (added to the contract) and on incident creation. An incident's `cve_id` needs only that format; it needn't be known to the source. | agreed with Team 2 (2026-11-01); contract addition in c249e2c, which Team 2 applies to their copy |
| Purl matching (Q5) | A component matches when its purl equals an affected purl after both have their qualifiers (`?…`) and subpath (`#…`) removed. `affected_purls` list exact versions only. A component without a purl never matches. | agreed with Team 2 (2026-11-01) |
| Vulnerability source after reset (Q6) | `POST /test/reset` leaves the source `available` with zero records, so every CVE is unknown. `PUT /test/vulnerability-source` replaces all records (and the mode). | agreed with Team 2 (2026-11-01) |
| AC-04 fixtures and ordering (Q7) | One person per team checks the expected values before the Phase 4 milestone. Cross-team tests compare affected releases and matched components as sets, not by order. Until both teams' checkers sign off, `fixtures/ground_truth.json` is a draft and AC-04 is not authoritative. | agreed with Team 2 (2026-11-01): one reviewer per team verifies the values before the Phase 4 submission; reviewers not yet named, so the fixtures stay drafts |
| Production vulnerability source; alerts (Q8) | Proposed: switch from Dependency-Track to a local OSV snapshot (needs instructor sign-off, so not built yet; every graded test uses the fixture source, `VULN_SOURCE=fixture`). No push alerts in Phase 4: deadline status is shown on every read. | no push alerts: agreed with Team 2 (2026-11-01). OSV snapshot instead of Dependency-Track: Team 2 open to it (2026-11-01); instructor sign-off pending, not built |

## Phase 5

Questions and proposed answers: `docs/pod-questions-phase5.md` (P5-Q1..Q11). Nothing below is agreed until Team 2 answers; built behavior is marked "awaiting Team 2".

| Topic | Answer | Status |
|---|---|---|
| Trailing whitespace (P5-Q9) | A timestamp, date or CVE ID with a trailing `\n`, `\r\n` or space is 400 `INVALID_REQUEST`, and nothing is stored. Every Python validation regex uses `fullmatch`. | built in `ce44401`; awaiting Team 2 (their 2026-11-02 run expected this) |
| Lowercase `t` and `z` (P5-Q9) | Accepted in every timestamp (RFC 3339 §5.6), e.g. `2026-11-01t23:59:59z`; output is always `…T…Z`. A timestamp with no zone is still 400. Amends the Phase 4 timestamp-format answer above. | built in `50928bd`; awaiting Team 2 (their 2026-11-02 run expected this) |
| SBOM media type (P5-Q9) | The SBOM upload accepts `application/json` and `application/vnd.cyclonedx+json` (parameters such as `charset` allowed, case-insensitive); anything else is 400 `INVALID_REQUEST` `Content-Type must be application/json`, checked after the 404 for an unknown release. | built in `416c069`; awaiting Team 2 |
| SBOM with no `Content-Type` (P5-Q9) | Proposed: 400, like any other non-JSON type. Until Team 2 answers, it is still accepted (`ALLOW_MISSING_CONTENT_TYPE` in `app/routers/sbom.py`). | open |
| Invalid-UTF-8 SBOM body (P5-Q9) | 400 `INVALID_JSON` with the message `request body is not valid JSON: not UTF-8 text`. | built in `43d3e33`; awaiting Team 2 |
