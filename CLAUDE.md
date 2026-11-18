# ReleaseGate — Phase 5 Handoff for Claude Code

> **How to use this file:** move the Phase 4 handoff (the old `CLAUDE.md`) to `docs/PHASE4_HANDOFF.md`, then save this file as `CLAUDE.md` in the repository root. Claude Code reads it automatically. Read Section 0 and Sections 1–5 before writing any code, then follow the order in §13. Comments in the code that cite "CLAUDE.md §n" were written against the Phase 4 handoff; they now mean `docs/PHASE4_HANDOFF.md §n`. Update a comment when you touch its file.

> Written 2026-11-18 from `main` at `bee2b44`, the Phase 2 report (`docs/phase2_report.pdf`, graded 26.25/28), `docs/PHASE4_PROGRESS.md`, `docs/issues.md` and the test reports in `docs/test-reports/`.

---

## 0. Working method: read this before anything else

The Phase 4 method still applies in full (`docs/PHASE4_HANDOFF.md` §0). The short version:

### 0.1 Outer loop (Imprint): goal → review → work → freshness

1. **Goal audit.** `docs/goals.md` must describe Phase 5. Today it describes Phase 4. **Stop, draft the Phase 5 goals from §0.2 into `docs/goals.md`, and ask a team member to confirm them before writing feature code.** Update `scripts/metrics.py` to measure them.
2. **Review.** Read `docs/metrics.md` and `docs/issues.md` (GitHub issues aren't used; `gh` isn't authenticated). Add one checkbox per task in §4 and §6, each with the test that proves it.
3. **Work.** Take one unblocked task: its pod questions (§9) are answered and its fixtures exist. A task blocked on §9 gets a question, not a guess.
4. **Freshness.** After each task, rerun `scripts/metrics.py` and check `docs/goals.md` is still true. A pod decision or grader feedback that makes it stale sends you back to step 1.

### 0.2 Phase 5 goals and measures (draft for `docs/goals.md`; a human must confirm)

| Goal | Measure | Target |
|---|---|---|
| G1 Correct Phase 5 behavior | AC-08, AC-09, AC-10 pass in CI **and** against our live URL (AC-10 live = restart on the VM) | 100% |
| G2 No regressions | AC-01..AC-07, the contract test (no missing or extra codes), every existing test | 100% |
| G3 Interoperability (graded) | Final cross-team runs, both directions, Phases 3–5 in scope | ≥ 95% each way; every failure has an issue with an owner; none of Team 2's 12 Phase 4 failures remain |
| G4 Timeliness | AC-04 query latency; AC-05 error latency | ≤ 10 s; ≤ 15 s (unchanged) |
| G5 Test strength | Line coverage of `app/` | ≥ 85% and never below `.coverage-baseline` (99.07% at `bee2b44`) |
| G6 Healthy deployment | Live `/health` commit equals the deployed commit; post-deploy checks pass; `phase5` tag on it | Every deploy |
| G7 Audit integrity | No code path changes or removes an audit row except the gated test reset (static test, §6.6); triggers reject UPDATE/DELETE (unit test) | Always |

`scripts/metrics.py` changes: add `PHASE5_ACS = ["AC-08", "AC-09", "AC-10"]` and a G1 row for them, move AC-04..AC-07 into G2, add G7, and read the final cross-team reports for G3.

### 0.3 Inner loop: for every small step

1. State the step's goal in one line and name the test that proves it.
2. Read the spec for it: `docs/openapi.yaml`, `docs/decisions.md`, the AC text in the report (§4.1), and the fixture.
3. Write the test first and watch it **fail for the expected reason**.
4. Make the smallest change that passes it.
5. Run the full gate: `.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy && .venv/bin/pytest` (or `uv run …`).
6. **Line-up check:** compare real output with the expected output field by field, and the generated OpenAPI with `docs/openapi.yaml`. A difference is a failure even when tests are green.
7. Self-review the diff against §12.
8. Debug loop on failure: reproduce with a failing test → isolate → hypothesis → fix → full gate. Keep the reproduction as a regression test. **After three failed attempts, or if the fix would change the contract, a fixture or a §9 answer, stop and ask.**
9. One step per commit. Push, wait for green CI, then start the next step. Tick the box in `docs/issues.md` in the same commit. Commit messages end with the Co-Authored-By line.

### 0.4 Skills

Check the installed skills before each kind of task and use the relevant one (testing-strategy for new endpoints, debug in the debug loop, code-review for step 7, deploy-checklist before deploys, documentation for README/decisions). This file and the contract win any conflict; mention the conflict to a team member.

---

## 1. What we are building

ReleaseGate tracks which software releases contain which components, tells a manufacturer which supported releases a CVE affects, and, for actively exploited vulnerabilities, tracks the EU Cyber Resilience Act's 24-hour, 72-hour and 14-day reporting deadlines and **prepares the report data for a person to submit**. It never submits anything to an authority and never decides whether something is reportable.

**Course context:** ECE 30861, Team 6 (Daksh Agarwal, Sanjay Sriram, Sathvik Valluri, Donovan Baran), in a pod with Team 2. Both teams implement the same shared specification independently and test each other through the common HTTP interface. Cross-team results are graded. Matching the shared interface exactly matters more than anything else.

**Phase 5 in one line (report §6.3):** CRA compliance report generation, immutable audit logging, and cross-team test execution: REQ-07 and REQ-08, proven by AC-08, AC-09 and AC-10, plus a final run of the whole suite against Team 2's live URL.

| Report §6.3 field | Phase 5 commitment |
|---|---|
| Capability | CRA report generation, immutable audit logging, cross-team test execution |
| Artifacts | `/incidents/{incidentId}/reports/{stage}` (and the report-data PUT it needs), `/audit-logs`, final cross-team testing scripts |
| Uncertainty to reduce | Audit-log immutability; complete persistence across process restarts |
| Demonstration | Retrieve a formatted JSON stage report; run the automated suite against Team 2's live URL |
| Automated validation | AC-08 (REQ-07), AC-09 and AC-10 (REQ-08) |

---

## 2. Where we are after Phase 4

### 2.1 What exists and works (on `main`, `bee2b44`)

| Area | State |
|---|---|
| Releases, SBOMs, components | Done (AC-01..AC-03). CycloneDX 1.4–1.6, nested components flattened, atomic replace, 400 for SBOMs nested too deeply (`820a730`) |
| CVE query + fixture source | Done (AC-04, AC-05). `VULN_SOURCE=fixture` is the only source built |
| Incidents and deadlines | Done (AC-06, AC-07). Computed on read in `app/services/deadlines.py` |
| Audit log | `GET /api/v1/audit-logs`, PATCH/DELETE → 405, triggers block UPDATE/DELETE, entries written in the same transaction as releases, SBOMs, incidents, fixes and submissions |
| Not built | `PUT /api/v1/incidents/{incidentId}/report-data/{stage}`, `GET /api/v1/incidents/{incidentId}/reports/{stage}` (both listed in `app/contract_status.py` `NOT_YET_IMPLEMENTED`) |
| Tester + harness | `tester/` runs AC-01..AC-07 against any URL; `/test`, `/test/setup`, `/test/run`, `/test/report` on both services, in the autograder format (`68b4261`, `2d7a905`) |
| CI | Stages A–F (static, unit, acceptance, tester, coverage ≥ 85%, docker-build, container-smoke with a restart check). 99.07% coverage |
| Ops | GCE `e2-medium`, system `http://136.116.160.182:8080`, tester `:8081`; `deploy/gcp.sh update/rollback/status`; nightly backup cron; JSON request logs |
| Tags | `phase3` → `9c0b191`, `phase4` → `e864340` |

### 2.2 Grading and cross-team history

| Item | Result | Lesson |
|---|---|---|
| Phase 2 report | 26.25/28 | Deductions still open in the shared spec: §10 |
| Phase 3 | 45/100; every lost point was the `/test` harness format | Fixed in `68b4261` and `2d7a905`. **Before Phase 5 grading, confirm the harness format against the Phase 5 assignment text** (§5.2) |
| Team 2 → us, 2026-11-02 | 341/353 (96.6%) | 12 failures, all ours to fix: §4 items 1–4 |
| Us → Team 2, 2026-11-02 | 48/50 recorded in `86ded5e`, then **reverted** in `07eadf7` with no reason given | No ours-to-Team-2 report exists, so G3 was never measurable. Redo it in Phase 5 (§6.9) |

### 2.3 Unknown state to check first

- **What's deployed.** The last recorded deploy is `e864340` (2026-11-01). The harness fixes (`68b4261`, `2d7a905`), the deep-nesting 400 (`820a730`) and the year-padding fix (`2591c73`) may not be live. Read `GET http://136.116.160.182:8080/health` (`commit`) and record what you find. Don't deploy without asking.
- **Live data.** Team 2's 2026-11-02 run reset the live data and froze the clock at `2026-11-01T23:59:59Z`. `docs/issues.md` still lists the re-seed as open.
- **Phase 4 grade and feedback.** Not in the repo. Ask a team member; any Phase 4 feedback becomes an issue.

---

## 3. Decisions already made (do not revisit without asking)

Everything in `docs/PHASE4_HANDOFF.md` §3 still holds: FastAPI + SQLite (WAL, `BEGIN IMMEDIATE`) on a named volume; deadlines computed on read with no timer service, scheduler or push alerts; `awareness_at` supplied by a person; one injectable clock; audit rows in the same transaction as the change, with triggers blocking edits; shared fixtures used unchanged; no scope cuts without both teams and the instructor. All Phase 3 and Phase 4 answers in `docs/decisions.md` stand.

New for Phase 5:

| Area | Decision | Why |
|---|---|---|
| Reports are computed on read | `GET .../reports/{stage}` builds the report from stored report data and the clock every time. No stored report snapshots | Same reasoning as deadlines: deterministic under the test clock and nothing to drift after a restart |
| Report data storage | One row per (incident, stage) holding the stage's fields as JSON, replaced as a whole on PUT (pending P5-Q3) | Matches PUT semantics; one write and one audit entry per PUT |
| No legal judgment | The system never fills in report text, decides a field is "not applicable", or submits a report | Report §2.2 exclusions; REQ-07 only lists what is missing |
| Production vulnerability source | Unchanged: fixture source only until the instructor signs off the OSV snapshot (decision Q8) | Shared-scope change |

**Outdated material warning (still true):** the Phase 2 diagrams show a timer service, deadline alerts, `Waiting`/`Late` states, `timer_id`, routes such as `/cases` and `GET /releases/{id}/sbom`, and the report text says `awareness_time`. Follow `docs/openapi.yaml`, `docs/decisions.md` and this file.

---

## 4. Problems to fix first (carry-over, in this order)

Each item is one commit with its own regression test. Items 1–4 are Team 2's 12 failures (`docs/test-reports/2026-11-02-cross-team-team2-to-ours.md`); their expected behavior is pod question P5-Q9, but items 1, 2 and 4 only make us stricter or more lenient in the direction RFC 3339 and the contract already point, so build them now and record them in `docs/decisions.md` as "awaiting Team 2".

1. **Trailing newline accepted (5 failures).** Python's `$` matches before a final `\n`, so `2026-11-01T12:00:00Z\n` and `CVE-2023-25577\n` pass and the CVE ID is even stored with the newline. Use `fullmatch` (or `\Z`) in `app/clock.py` `_TIMESTAMP`, `app/models.py` `CVE_ID` and `_DATE_RE`, and grep `app/` and `tester/` for any other `re.compile(r"^…$")` or `.match(` used for validation. Tests: `\n`, `\r\n` and a trailing space on `now`, `awareness_at`, `fix_available_at`, `submitted_at`, `support_end_date`, `cve_id` (incident and CVE query path) → 400, nothing stored.
2. **Lowercase `t` and `z` rejected (4 failures).** RFC 3339 §5.6 allows them, and the contract's `format: date-time` is RFC 3339. Accept `2026-11-01t23:59:59z` and `…t…+02:00`; output stays `…T…Z` through `format_utc`. Keep rejecting a missing zone. Tests: unit tests in `tests/unit/test_clock.py` plus one acceptance test per timestamp field.
3. **SBOM upload ignores `Content-Type` (1 failure).** `put_sbom` reads the raw body and never checks the media type; the contract's request body lists only `application/json`. Return 400 `Content-Type must be application/json` for any other type. Proposed accepted set (P5-Q9): `application/json` and `application/vnd.cyclonedx+json`, with parameters such as `charset`. A **missing** header is the open part of P5-Q9: build the check so the accepted set is one constant, and ask before deciding the missing-header case. Check that `tester/checks.py`, `scripts/smoke.sh`, `scripts/container_smoke.py` and the acceptance tests all send `application/json` before you flip it.
4. **Invalid-UTF-8 message (2 failures).** `app/services/sbom_validation.py` says "request body is not valid UTF-8 text". Say `request body is not valid JSON: not UTF-8 text`, keeping 400 `INVALID_JSON`.
5. **Gate the only audit-deleting path.** `Database.reset()` drops the triggers and deletes `audit_log`. It's reachable only through `/api/v1/test/reset` and the system's `/test/setup`, both mounted only when `ENABLE_TEST_ENDPOINTS=true`. AC-09 asks for code inspection that "no update or delete paths exist", so make that obvious: `reset()` takes the settings (or a flag) and raises unless test endpoints are enabled, and a test proves a production-configured app has no route that reaches it. Document it in `docs/audit-immutability.md` (§6.6).
6. **Re-seed the live demo data and return the live clock to real time** (human or with permission): `POST /api/v1/test/reset`, then the seed in `docs/test-reports/2026-11-01-deploy-full.md` ("Live data afterwards").
7. After 1–5: ask before deploying with `deploy/gcp.sh update`, run the post-deploy checks, then ask Team 2 to rerun their Phase 4 suite. Record it as a new `docs/test-reports/YYYY-MM-DD-cross-team-team2-to-ours.md`.

---

## 5. Materials

### 5.1 Already in the repo

| File | Use |
|---|---|
| `docs/openapi.yaml` | **Single source of truth.** Phase 5 sections: `/incidents/{incidentId}/report-data/{stage}`, `/incidents/{incidentId}/reports/{stage}`, `/audit-logs`, schemas `ReportData`, `GeneratedReport`, `AuditEvent`, `ReportStage` |
| `docs/phase2_report.pdf` | §3.1 REQ-07/REQ-08, §3.2 information model (report invariant: "that stage's Section 5 fields as JSON, plus a missing_fields list naming every empty one"), §4.1 AC-08..AC-10, §4.3 how others evaluate AC-09/AC-10, §5.2 example 8 (report data), §6.3 Phase 5 milestone |
| `docs/decisions.md` | Every pod answer. Add Phase 5 answers here |
| `docs/pod-questions-phase5.md` | **New.** The eleven Phase 5 questions with proposed answers, ready to send to Team 2 |
| `fixtures/report_cases.json` | **New, DRAFT.** AC-08 cases: two mandatory incidents with report data for all three stages and expected `missing_fields`, plus informational edge cases |
| `docs/PHASE4_HANDOFF.md`, `docs/PHASE4_PROGRESS.md` | Phase 4 rules, CI stages, deploy checklist, how the work was done (tooling notes for `uv`, Windows, ports 18080/18081) |
| `scripts/container_smoke.py` | Seed → restart → verify; the base for AC-10 |

### 5.2 Needed before the matching work can be called done (**REQUIRED**)

| Item | Why | Who |
|---|---|---|
| Team 2's answers to `docs/pod-questions-phase5.md`, at least P5-Q1..Q7 | The report endpoints and AC-08/AC-09 checks depend on them | A team member sends them; record answers in `docs/decisions.md` |
| `fixtures/report_cases.json` verified by one checker per team | Ground truth is human-verified (report Q4.2, Q8.2) | Names and date in `docs/decisions.md` and `fixtures/README.md` |
| The Phase 5 assignment text, saved as `docs/phase5_assignment.md` | Phase 3 lost 55 points on harness format alone; the Phase 5 deliverables, report questions and harness expectations must be checked against the real text | A team member. **If it's missing, ask before changing anything in `app/harness.py` or `tester/harness.py`** |
| Team 2's final live URL and a run window | Final cross-team runs (§6.9) | A team member |

> **Rule (unchanged):** Claude Code may write test code and draft fixture *structure*, but **never decides expected results**. `fixtures/report_cases.json` was drafted by Claude from CRA Art. 14(2) and the contract; its expected values become authoritative only after the human checks above. If a decision changes the stage-to-field mapping, a person updates the fixture.

---

## 6. Phase 5 scope: what to build

### 6.1 Endpoints (exact paths from `openapi.yaml`)

| Method & path | Purpose | Reqs |
|---|---|---|
| `PUT /api/v1/incidents/{incidentId}/report-data/{stage}` | Store the stage's report data → `200`; `400` invalid stage, field or type; `404` unknown incident. `X-User-Id` required. Audit `REPORT_DATA_STORED` | REQ-07, REQ-08 |
| `GET /api/v1/incidents/{incidentId}/reports/{stage}` | `200 GeneratedReport`; `404` unknown incident; `400` invalid stage **only if P5-Q5 adds it to the contract** | REQ-07 |
| `GET /api/v1/audit-logs`, `PATCH`/`DELETE /api/v1/audit-logs/{eventId}` | Already built; AC-09 verifies them | REQ-08 |

Remove both report operations from `app/contract_status.py` as you build them (the contract test fails if you forget), and declare `responses=` that match `docs/openapi.yaml` exactly. Contract changes from P5-Q3 (PUT 200 body) and P5-Q5 (GET 400) go into one commit agreed with Team 2, as `c249e2c` did in Phase 4.

### 6.2 Which fields belong to which stage (proposal P5-Q1, from CRA Art. 14(2))

| Stage | Article | Required (listed in `missing_fields` when missing) | Optional (in `data` when supplied, never "missing") |
|---|---|---|---|
| `early_warning` | 14(2)(a) | `member_states` | — |
| `vulnerability_notification` | 14(2)(b) | `product_information`, `exploit_nature`, `vulnerability_nature`, `corrective_measures_taken`, `user_mitigations` | `sensitivity` ("where applicable") |
| `final_report` | 14(2)(c)(i)–(iii) | `vulnerability_description`, `severity`, `impact`, `corrective_measure_details` | `malicious_actor_information` ("where available") |

This agrees with the report's §5.2 example 8, where a notification without `sensitivity` returns `missing_fields: []`. Put the mapping in one place (`app/services/reports.py` `STAGE_FIELDS`), ordered as in the `ReportData` schema, and drive validation, `missing_fields` and the tester from it. **Don't build the endpoints on this mapping until Team 2 has answered P5-Q1**; the pure functions and their tests can be written now.

### 6.3 Report-data behavior (REQ-07, REQ-08; proposals P5-Q2..Q5)

1. Check the incident exists (404 `INCIDENT_NOT_FOUND`) and the stage is one of the three (400 `INVALID_REQUEST`), in that order, before reading the body.
2. Body must be a JSON object. Each key must be a field of **this stage** (another stage's field or an unknown key → 400 naming the field). `member_states` must be an array of strings; every other field a string. Wrong type → 400 naming the field. Use the shared error shape and the `"<field> <reason>"` message style.
3. Store values exactly as sent (no trimming), replacing the stage's previous data in one transaction with the audit entry `REPORT_DATA_STORED`, `entity_type: incident`, `entity_id: <incidentId>`, `details: {"stage": …, "fields": [sorted keys supplied]}`. Don't copy the text into the audit details.
4. Voluntary incidents and a final report before `fix_available_at` are allowed (P5-Q5).
5. 200 response: the `GeneratedReport` for the stage (P5-Q3). Until P5-Q3 is answered, return it anyway: a body on a 200 the contract leaves empty doesn't break a client, but tell Team 2.
6. An invalid request stores nothing and writes no audit entry.

### 6.4 Report generation (REQ-07)

`GET .../reports/{stage}` returns:

```json
{
  "incident_id": "inc-…",
  "stage": "vulnerability_notification",
  "generated_at": "<clock now, format_utc>",
  "data": { "<only the stage's supplied fields>": "…" },
  "missing_fields": ["<required fields of the stage that are missing, in schema order>"]
}
```

- A required field is missing when it's absent, `null`, an empty or whitespace-only string, or an empty `member_states` array (P5-Q2). A stage with nothing stored returns `data: {}` and every required field in `missing_fields`.
- `data` never contains nulls, fields from other stages, or anything the system made up (P5-Q6).
- Read-only: no audit entry, nothing stored.
- Keep the logic in pure functions (`missing_fields(stage, data) -> list[str]`, `build_report(...)`) with unit tests written first, the way `deadlines.py` was done. Mark the commit `needs-human-review`.

### 6.5 Data model additions

```
report_data(incident_id FK → incidents ON DELETE CASCADE, stage, data TEXT /* JSON object */,
            updated_by, updated_at, PRIMARY KEY (incident_id, stage))
```

`CREATE TABLE IF NOT EXISTS` covers existing databases (no column changes, so no `_migrate` step). Add `DELETE FROM report_data` to `Database.reset()` before `DELETE FROM incidents`.

### 6.6 Audit log (REQ-08, AC-09)

The audit log exists; Phase 5 proves it.

- **Inventory.** List every state-changing route and the action it writes in `docs/audit-immutability.md`: `RELEASE_REGISTERED`, `SBOM_STORED`/`SBOM_REPLACED` (entity `release`), `INCIDENT_CREATED`, `FIX_AVAILABLE_RECORDED`, `SUBMISSION_RECORDED`, `REPORT_DATA_STORED` (entity `incident`). Test endpoints write none (P5-Q7). Add a test that walks the generated OpenAPI and fails if a POST/PUT/PATCH route outside `/api/v1/test` and `/test` has no audit test.
- **Timestamps** come from the injected clock (they already do), so with the test clock set they equal the clock exactly.
- **Immutability evidence** for the code-inspection half of AC-09, in `docs/audit-immutability.md`: the two triggers, `app/services/audit.py` (INSERT only), the routes that return 405, and the gated `reset()` from §4 item 5. Back it with:
  - `tests/unit/test_audit_immutability.py`: scans every `.py` under `app/` for SQL that names `audit_log` and fails on any `UPDATE`, `DELETE`, `DROP` or `REPLACE` outside `Database.reset`; and checks a raw `UPDATE`/`DELETE` on `audit_log` raises `sqlite3.IntegrityError` ("audit log is append-only"). That's G7.
  - The known limit, stated plainly: anyone with write access to the SQLite file can drop the triggers (report Q8.1 already says this). Backups are the mitigation.

### 6.7 Persistence across restarts (REQ-08, AC-10)

- Extend `scripts/container_smoke.py` `seed`/`verify` to cover everything AC-10 names plus Phase 5 state: release, components, an SBOM **replace**, the vulnerability records and one CVE query result, a mandatory incident with a fix and a submission (computed deadlines), report data for all three stages and the three generated reports, and the full audit log. Compare JSON exactly after re-setting the same test clock; that is the "0-second timestamp drift".
- Run it in CI stage F (already wired) and live on the VM (§8).
- For cross-team AC-10 (P5-Q8, proposed two-step): add `tester ac10-snapshot <url> <file>` and `tester ac10-verify <url> <file>` commands (reuse `container_smoke.py`'s logic so there is one implementation), and document the procedure in the README. Don't add a restart endpoint unless Team 2 chooses that option.

### 6.8 Acceptance criteria to automate

- **AC-08 (REQ-07):** load `fixtures/report_cases.json`; create both incidents, record each fix, PUT each stage's data, set the clock to `reference_clock`, GET all six reports. Pass if every response is a valid `GeneratedReport`, `generated_at` equals the clock, `data` equals what was PUT, the complete case has `missing_fields: []` for every stage, and the incomplete case lists exactly `exploit_nature` and `user_mitigations` for `vulnerability_notification` (as a set) and nothing for the other two. Edge cases are informational until their pod questions are answered (`required: false` in the fixture), except `unknown_incident` (404 is in the contract).
- **AC-09 (REQ-08):** reset; with the test clock set and moved forward one minute before each step, and a different `X-User-Id` each time, register a release, upload `sbom_25_components.json`, open a mandatory incident, record an early-warning submission. Pass if the log has exactly four events in that order, each with the right `action`, `user_id`, `entity_type`, `entity_id` and a `timestamp` equal to the clock at that step (±2 s; exact for us), if a rejected request in between (for example an incident without `rationale`) adds no event, and if PATCH and DELETE on every event return 405 and leave the log unchanged. The code-inspection half is `docs/audit-immutability.md` plus G7's test. Action-name checks are informational until P5-Q7 is agreed.
- **AC-10 (REQ-01, 02, 05, 06, 08):** §6.7. Pass if the state after restart equals the snapshot exactly.

Add AC-08 and AC-09 to the tester as `tester/phase5.py` (same style as `tester/phase4.py`: required checks from the contract and AC text, informational checks for pod proposals), to both `/test/run` harnesses, and to `tests/acceptance/`. Update `tester/coverage.py` `ACCEPTANCE_CRITERIA` and the harness descriptions ("AC-01..AC-07" appears in `app/harness.py`, `tester/harness.py` and `docs/openapi.yaml`). A single `/test/run` can't restart the target, so decide with a team member how AC-10 counts in the harness's `system` coverage (for example, report it as exercised only by the two-step run) and **check that decision against the Phase 5 assignment text**; CI stage F currently asserts `system == 100.0`.

### 6.9 Final cross-team testing (graded)

- Agree a window with Team 2 (P5-Q10). Every run resets the target.
- **Ours → Team 2:** our deployed tester against Team 2's URL with AC-01..AC-09 (and AC-10 two-step if they cooperate). Write `docs/test-reports/YYYY-MM-DD-cross-team-ours-to-team2.md` with a `Result: X/Y passed (in scope)` line, the tester commit, every failure with its owner, and coverage (component, system model; code is unmeasurable black-box). This report is the one that went missing in Phase 4.
- **Team 2 → us:** after the §4 fixes are deployed. Same report format, `…-cross-team-team2-to-ours.md`.
- A failure that's ours becomes an issue and a fix through the inner loop; a failure that's Team 2's, or a spec ambiguity, goes to them in writing and into the report.

### 6.10 Demonstration of completion (report §6.3)

On the live system: open a mandatory incident, PUT report data for each stage with one required field left out, GET the three reports and show the JSON with `missing_fields`; show the audit log for those actions and a 405 on PATCH; restart the API container and show the same state; show the final cross-team run reports. AC-08..AC-10 green in CI and against the live URL.

### 6.11 Out of scope

Submitting reports to ENISA, CSIRTs or anyone else; deciding reportability or inferring awareness; the one-month severe-incident final report (Art. 14(4)(c)); push alerts; authentication; the production vulnerability source until the instructor signs off; any report format other than the contract's JSON (no PDF or ENISA template).

---

## 7. Rules the implementation must follow

All Phase 3 and 4 rules still apply: the contract is law; error shape `{"error": {"code", "message"}}`; invalid input is 400, never 422; one clock and one timestamp parser/formatter; nothing derived is stored (support status, deadlines, statuses, and now reports); `X-User-Id` required on POST/PUT/PATCH outside the test endpoints; validate fully before writing; every state change audited in the same transaction; test endpoints gated; no secrets in the repo. New for Phase 5:

1. **Report text is stored and returned exactly as sent.** No trimming, rewording, translation or auto-filling.
2. **`missing_fields` comes from one stage-field table** shared by the app, the tests and the tester.
3. **The audit log has exactly one INSERT path and one gated delete path** (`reset()` under test endpoints). Anything else is a G7 failure.
4. **No AC checks on unagreed behavior as required checks.** Anything resting on a P5 proposal is informational until Team 2 agrees.
5. **Ground truth is human-verified**, including `fixtures/report_cases.json`.

---

## 8. Operations and deployment

Unchanged from `docs/PHASE4_HANDOFF.md` §8 and §16 (deploy checklist, post-deploy checks, rollback, backups), plus:

- **Build `post_deploy_check.sh --full`** (still missing; report §6.3 lists "final cross-team testing scripts" as a Phase 5 artifact). It resets the target, so it runs only on the evaluation deployment after warning Team 2: the tester (AC-01..AC-09), `scripts/smoke.sh`, then the AC-10 snapshot → `docker compose restart api` on the VM → verify, then re-seed the demo data. Print PASS/FAIL per step.
- Add the two report operations to the non-destructive checks' expected OpenAPI paths (they come from `app/contract_status.py`).
- **Ask before every deploy and before anything that writes to or resets the live system.** Deploy command and tooling notes: `docs/PHASE4_PROGRESS.md` "How the work was done".
- After the final deploy: tag `phase5` (a human runs `git tag phase5 <sha> && git push origin phase5`), record the deploy and the full live run in `docs/test-reports/`, and re-seed the demo data including one incident with report data.
- Still open from Phase 4: confirm the backup cron on the VM (one manual `sudo /opt/releasegate/deploy/backup.sh`), and an uptime monitor on `/health` (human).

---

## 9. Open questions: ask before deciding

The full list, with proposed answers, is `docs/pod-questions-phase5.md`, ready to send to Team 2. In short:

| # | Question | Blocks |
|---|---|---|
| P5-Q1 | Fields per stage; required vs optional | Report endpoints, AC-08 |
| P5-Q2 | What counts as missing | `missing_fields`, AC-08 edge cases |
| P5-Q3 | PUT replace vs merge; 200 body | Report-data PUT, contract |
| P5-Q4 | Other-stage, unknown and wrongly typed fields | Report-data validation |
| P5-Q5 | Invalid stage (400 on GET is a contract addition); voluntary; final report before fix | Both endpoints, contract |
| P5-Q6 | Content of `data` and `generated_at`; generation is read-only | Report generation |
| P5-Q7 | Audit action vocabulary, what's logged, timestamps, ordering | AC-09 required checks |
| P5-Q8 | How AC-10 runs cross-team | AC-10 tester commands |
| P5-Q9 | Trailing newline, lowercase `t`/`z`, SBOM media types, missing Content-Type | §4 items 1–4 (build now; the missing header waits) |
| P5-Q10 | Final cross-team run window | §6.9 |
| P5-Q11 | Fixture checkers for AC-04 and AC-08 | Authoritative AC-04/AC-08 |

Record every answer in `docs/decisions.md`. Contract changes go into one commit both teams apply.

---

## 10. Spec housekeeping (human tasks; the Phase 2 grader's points are still open)

The pod must keep the common specification current. These came from the Phase 2 grading (26.25/28) and the Phase 3/4 handoffs and are **still not done** (`docs/issues.md`, "Human tasks"):

- **5.1 (−0.25): state which report fields are required for each stage.** P5-Q1 answers it; put the table from §6.2 into the shared spec and `docs/openapi.yaml` (for example an `x-required-by-stage` extension or a description on `ReportData`).
- **3.2 (−0.25): deadline status names differ between diagrams and API.** Diagrams must use `pending`/`met`/`overdue`/`not_applicable`; drop `Waiting`/`Late`.
- **7.1 (−0.25): the diagram shows a timer service and routes that don't match.** Remove the timer service from 2.1, 3.1 and 7.1; align routes with the contract; remove deadline alerts (decision: no push alerts); remove or justify "return the stored SBOM" (the contract has no `GET …/sbom` and we don't keep the raw document).
- **3.1 (−0.25): security and quality requirements need detail, including what is left out and why.** Add them (no authentication, test endpoints open on the evaluation server, audit immutability limited by file access, single instance).
- **2.3 (−0.25): hour estimates as ranges, per team.** **9.1 (−0.25): name an owner for each risk.** **10 (−0.25): number references in order of first use.**
- Report text fixes: `awareness_time` → `awareness_at` (§1.3); AC-05 uses `PUT /test/vulnerability-source` with `mode: unreachable`, not stopping a service (§4.3); replace the §6.4 scope-cut sentence with "any scope change needs both teams and instructor sign-off"; if the OSV switch is approved, update §2.2 limits and the 2.1 diagram.
- Human reviews still owed: the deadline logic (`0f2e32e`) and the timestamp formatter change (`2591c73`), both `needs-human-review`; the new report logic once built.

---

## 11. Risks for Phase 5

| Risk | Effect | Mitigation |
|---|---|---|
| Team 2 answers P5-Q1/Q2 differently or late | AC-08 checks disagree; graded cross-team failures that aren't bugs | Send `docs/pod-questions-phase5.md` first; build pure functions and tests while waiting; keep unagreed checks informational |
| Harness format or Phase 5 deliverables differ from what we assume | Repeat of Phase 3's 55-point loss | Get the Phase 5 assignment text into `docs/phase5_assignment.md` before touching the harness; test `/test/*` against it |
| AC-10 can't be automated cross-team | AC-10 unevaluated by Team 2 | Two-step snapshot/verify (P5-Q8); our own CI and live run cover it regardless |
| Audit delete path found on inspection | AC-09 inspection fails | §4 item 5 and G7's static test |
| A final run wipes the other team's data mid-test | Flaky graded results | Agreed window (P5-Q10); announce each run |
| Live deployment behind `main` | We're graded on old behavior | Check `/health` commit first (§2.3); deploy and tag `phase5` after the final fixes |
| AC-04 ground truth still unverified | AC-04 never authoritative | Name checkers now (P5-Q11) |

---

## 12. Self-review checklist (step 7 of the inner loop)

Everything in `docs/PHASE4_HANDOFF.md` §14.3, plus:

- No regex validation that can match before a trailing newline (`fullmatch` or `\Z`).
- Report data stored exactly as sent; reports computed on read; `data` has no nulls and no other stage's fields.
- `missing_fields` and validation use the one stage-field table.
- The new write path audits `REPORT_DATA_STORED` in the same transaction; failed requests audit nothing; reads audit nothing.
- No new SQL touches `audit_log` except the INSERT in `app/services/audit.py`.
- `app/contract_status.py` and the contract test reflect what's built; generated OpenAPI has exactly the contract's codes.
- Tester, harness descriptions, `scripts/smoke.sh` and `scripts/container_smoke.py` updated for any behavior change.

---

## 13. Order of work

Each line is one or more inner-loop steps with green CI in between.

1. **Goal audit:** Phase 5 goals into `docs/goals.md` (human confirms), `scripts/metrics.py` updated, `docs/issues.md` updated with every §4 and §6 task. Check the live `/health` commit (§2.3).
2. **Send `docs/pod-questions-phase5.md` to Team 2** (human). Ask for the Phase 5 assignment text.
3. §4 items 1–5, one commit each.
4. Deploy (with permission), Team 2 reruns their Phase 4 suite; record the report.
5. `app/services/reports.py` pure functions (stage-field table, `missing_fields`, `build_report`) with unit tests first; `needs-human-review`.
6. `report_data` table, reset, then `PUT …/report-data/{stage}` with audit → `GET …/reports/{stage}` → AC-08 acceptance tests (once P5-Q1..Q6 are answered and the fixture is checked).
7. AC-09 acceptance test, `docs/audit-immutability.md`, G7's static test, the route-audit coverage test.
8. AC-10: extend `container_smoke.py`, add the tester's two-step commands.
9. `tester/phase5.py`, both harnesses, coverage constants, CI stage F assertions.
10. `post_deploy_check.sh --full`.
11. README (Phase 5 scope, models, known limitations), `docs/decisions.md`, `fixtures/README.md` (Phase 5 section).
12. Deploy → full live run → final cross-team runs both ways → human tags `phase5`.

### 13.1 Definition of done for Phase 5

- AC-08, AC-09 and AC-10 green in CI and against the live URL; AC-01..AC-07 still green.
- All goals in `docs/goals.md` met or explained in `docs/metrics.md`.
- Final cross-team reports in both directions in `docs/test-reports/`, each failure with an owner.
- `docs/decisions.md` has Team 2's Phase 5 answers; `fixtures/report_cases.json` and the AC-04 fixtures verified by a named checker per team, or the README says plainly that they aren't.
- `docs/audit-immutability.md` written; G7 test green.
- README "Known limitations" current; the deployed commit tagged `phase5` and verified by the post-deploy checks.

---

## 14. Repository layout additions

```
app/
├── routers/reports.py           # PUT …/report-data/{stage}, GET …/reports/{stage}
├── services/reports.py          # STAGE_FIELDS, missing_fields(), build_report(): pure; store/load
└── db.py                        # + report_data table; reset() gated and clears it
fixtures/report_cases.json       # AC-08 (DRAFT until verified)
tester/phase5.py                 # AC-08, AC-09 checks; AC-10 snapshot/verify
tests/
├── unit/test_reports.py         # stage table, missing rules, build_report
├── unit/test_audit_immutability.py   # G7
├── acceptance/test_reports.py   # AC-08 + validation/404/400 cases
└── acceptance/test_ac09_audit.py
scripts/post_deploy_check.py     # + --full
docs/
├── goals.md, metrics.md         # Phase 5 versions
├── pod-questions-phase5.md
├── audit-immutability.md        # AC-09 code-inspection evidence
├── phase5_assignment.md         # from a team member
├── PHASE4_HANDOFF.md            # the previous CLAUDE.md
└── test-reports/                # final cross-team runs, deploys
```
