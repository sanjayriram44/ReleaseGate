# Issues

GitHub issues aren't used (`gh` isn't authenticated), so tasks are tracked here, as CLAUDE.md
§0.1 allows. One checkbox per task, with the test or check that proves it. **blocked** names the
open question (CLAUDE.md §9, `docs/pod-questions-phase5.md`) or missing material (§5.2) that must
be answered first; a blocked
task gets a question, not a guess. `scripts/metrics.py` lists the blocked items in
`docs/metrics.md`.

## Goal audit and CI

- [x] Confirm `docs/goals.md` with a team member — proof: "Confirmed by" filled in
- [x] CI stage A `static` job — proof: job green, and fails on a deliberate lint error
- [x] CI stage B `unit` job with coverage gate — proof: job green, and fails below the G5 threshold
- [x] CI stage E `docker-build` (both images, tagged with the SHA; the system image reports it) — proof: job green, and fails on a throwaway branch without `ENV GIT_SHA`
- [x] CI stages C `acceptance` and D `tester`, with the G5 gate in a `coverage` job that combines all three suites' data — proof: jobs green; throwaway branches failed only in `acceptance`, only in `tester`, and in `coverage` at `--fail-under=100`; `tests/unit/test_ci_split.py` fails if a test file runs in no job or two
- [x] CI stage F `container-smoke` — proof: job green on `c509ef6`; `tests/unit/test_container_smoke.py` shows the restart check notices a change

## Phase 3 carry-over (`docs/PHASE4_HANDOFF.md` §4)

- [x] 1 Non-blocking SBOM upload — proof: regression test that `/health` answers during a slow upload
- [x] 2 Flatten nested components — proof: tests for nested storage, `component_count`, path-named version error
- [x] 3 Timestamp parsing with offsets and fractions, moved to `app/clock.py` — proof: unit tests with Team 2's inputs
- [x] 4 Short duplicate-component error — proof: test on the fixture with a duplicated component
- [x] 5 Blank product/version → 400 `must not be blank` — proof: acceptance test
- [x] 6 Non-JSON `Content-Type` → `Content-Type must be application/json` — proof: acceptance test
- [x] 7 No stray 422 in generated OpenAPI; contract test fails on extra codes — proof: contract test
- [x] 8 Smoke test uses `tmp_path` — proof: `tests/unit/test_smoke.py`
- [x] Tag `phase3` (`9c0b191`, tagged 2026-11-01)
- [ ] Ask Team 2 to rerun (redeployed `136c05a` on 2026-10-30) — proof: human runs the tag; Team 2's report in `docs/test-reports/`

## Phase 4 features (`docs/PHASE4_HANDOFF.md` §6)

- [x] `deadlines.py` pure functions — proof: `tests/unit/test_deadlines.py` (boundaries, rollover, fractions, offsets, voluntary); human review. (needs-human-review)
- [x] `POST /api/v1/incidents` + audit `INCIDENT_CREATED` — proof: AC-06
- [x] `GET /api/v1/incidents/{incidentId}` — proof: AC-06, AC-07
- [x] `PATCH /api/v1/incidents/{incidentId}` + audit `FIX_AVAILABLE_RECORDED` — proof: AC-07
- [x] `POST /api/v1/incidents/{incidentId}/submissions` + audit `SUBMISSION_RECORDED` — proof: AC-07
- [x] `PUT /api/v1/test/vulnerability-source` + `FixtureSource` — proof: acceptance tests
- [x] `GET /api/v1/vulnerabilities/{cveId}/affected-releases` — proof: AC-05, then AC-04
- [x] AC-04 fixtures drafted (`sbom_patched.json`, `vulnerabilities.json`, `cve_dataset.json`, `ground_truth.json`) — proof: `tests/acceptance/test_ac04_fixture.py`
- [ ] AC-04 fixtures verified by one checker per team — proof: names and date in `docs/decisions.md` and `fixtures/README.md`. **blocked: one checker per team (Q7) must verify the draft values**
- [ ] Production vulnerability source — proof: decision in `docs/decisions.md`. **blocked: instructor sign-off for the OSV snapshot (Q8)**
- [x] `/health` reports the built commit (`GIT_SHA` build arg; `unknown` when unset) — proof: `tests/acceptance/test_test_support.py::test_health_reports_the_built_commit`
- [x] Reset clears incidents, submissions and vulnerability records; `/health` reports source mode — proof: acceptance tests
- [x] Tester checks and harness `/test/run` for AC-04..AC-07 — proof: `tests/tester`, `tests/test_harness.py`
- [x] Structured JSON request logs (§8): one line per request, request ID echoed in `X-Request-Id`, error code/message on 4xx/5xx, uvicorn access log off — proof: `tests/unit/test_request_log.py`
- [x] Log signals for the source and deadlines (§8): source error detail on 503 lines, overdue-deadline counts — proof: tests with the CVE query and incidents.
- [x] Nightly SQLite backup, 7 copies (§8): `app/backup.py` (online backup API, integrity check, prune), `deploy/backup.sh` + `deploy/releasegate-backup.cron` installed by `gcp.sh update` — proof: `tests/unit/test_backup.py`; 5 backups taken during 319 concurrent writes, each consistent
- [ ] Confirm the backup on the VM: `/etc/cron.d/releasegate-backup` installed and nightly copies written (confirmed 2026-11-18: copies on 11-16, 11-17, 11-18 at 03:30 UTC); **still open:** try the README restore steps once — proof: note in a deploy report
- [x] `scripts/post_deploy_check.sh` (non-destructive), `deploy/gcp.sh update [ref]` from an exact commit and `rollback <tag>`, both running the checks (§16) — proof: `tests/unit/test_post_deploy_check.py`; dry run with a stub `gcloud`; run against the live URL on 2026-10-30 (all pass except the commit check: `136c05a` predates `GIT_SHA`)
- [x] `post_deploy_check.sh --full` (destructive: tester run, smoke test, restart persistence; §16.2 items 6–8) — built in Phase 5 (see below); the live run is the Phase 5 "Final deploy, full live run" task
- [x] Deploy Phase 4 (`68011ca`, 2026-11-01) — proof: `docs/test-reports/2026-11-01-deploy.md`
- [x] Live full run: tester 52/52, both harnesses, smoke.sh, restart persistence; demo re-seeded — proof: `docs/test-reports/2026-11-01-deploy-full.md`
- [x] Tag `phase4` on the deployed commit `e864340` (first `68011ca`) — proof: `git ls-remote --tags origin`
- [ ] Cross-team runs both ways in `docs/test-reports/` (G3) — proof: `YYYY-MM-DD-cross-team-<direction>.md` with `Result:`
  - [x] Team 2 → ours, 2026-11-02: 341/353 (`2026-11-02-cross-team-team2-to-ours.md`)
  - [ ] Ours → Team 2 (the 48/50 run was recorded in `86ded5e` and reverted in `07eadf7`; redone in Phase 5, below)
- [ ] A team member reviews the deadline logic (`0f2e32e`, needs-human-review) and its tests

## Phase 5 goal audit (CLAUDE.md §0.1, §13 step 1)

- [x] Confirm the Phase 5 `docs/goals.md` with a team member — proof: "Confirmed by" filled in
- [x] `scripts/metrics.py` measures the Phase 5 goals (G1 AC-08..AC-10, G2 AC-01..AC-07, G3 Phase 5 runs only, G6 `phase5` tag, G7) — proof: `tests/unit/test_metrics.py`
- [x] Check the live `/health` commit (§2.3) — 2026-11-18: live reports `bee2b44` (= `main`), so `68b4261`, `2d7a905`, `820a730` and `2591c73` are live. No deploy report records `bee2b44` (newest is `2026-11-01-deploy.md`, `e864340`), and origin's `phase4` tag (annotated) now points at `bee2b44`, not `e864340`
- [ ] Record who deployed `bee2b44`, when, and why `phase4` was moved; write the missing deploy report or note it in `docs/PHASE4_PROGRESS.md` — proof: G6 row in `docs/metrics.md`. **blocked: a team member must say who deployed it and moved the tag**
- [ ] Phase 4 grade and grader feedback recorded; each piece of feedback becomes an issue here — **blocked: a team member must supply the Phase 4 grade (CLAUDE.md §2.3)**

## Phase 5 carry-over (CLAUDE.md §4)

- [x] 1 Reject a trailing newline (`\n`, `\r\n`) or trailing space in `now`, `awareness_at`, `fix_available_at`, `submitted_at`, `support_end_date`, `cve_id` (fullmatch / `\Z`; Team 2 run, 5 failures) — proof: `tests/unit/test_clock.py` (incl. a guard against `re.compile(r"^…$")` in `app/` and `tester/`) and `tests/acceptance/test_trailing_whitespace.py` → 400, nothing stored
- [x] 2 Accept lowercase `t`/`z` in timestamps, output `…T…Z` (RFC 3339 §5.6; Team 2 run, 4 failures) — proof: `tests/unit/test_clock.py` + `tests/acceptance/test_lowercase_t_z.py` (now, awareness_at, fix_available_at, submitted_at; no zone still 400)
- [x] 3a SBOM upload: 400 `Content-Type must be application/json` for a non-JSON media type; accepted set is one constant, `SBOM_MEDIA_TYPES` in `app/routers/sbom.py` (`application/json`, `application/vnd.cyclonedx+json`, with parameters) (Team 2 run, 1 failure) — proof: `tests/acceptance/test_sbom_media_type.py`; `tester/checks.py`, `scripts/smoke.sh`, `scripts/container_smoke.py` already send `application/json`
- [ ] 3b SBOM upload with **no** `Content-Type` header: still accepted; flip `ALLOW_MISSING_CONTENT_TYPE` in `app/routers/sbom.py` if Team 2 agrees to 400 — proof: `test_missing_content_type_*` in `tests/acceptance/test_sbom_media_type.py`. **blocked: P5-Q9 (missing header case)**
- [x] 4 Invalid-UTF-8 SBOM message: `request body is not valid JSON: not UTF-8 text`, still 400 `INVALID_JSON` (Team 2 run, 2 failures) — proof: `tests/unit/test_sbom_validation.py::test_non_utf8`, `tests/acceptance/test_sbom.py::test_non_utf8_body_is_400_invalid_json_and_keeps_the_inventory`
- [x] 5 Gate `Database.reset()` (the only audit-deleting path) on test endpoints being enabled — proof: `tests/unit/test_db.py::test_reset_refuses_unless_allowed_and_leaves_the_audit_log`, `tests/unit/test_reset_gate.py`; first section of `docs/audit-immutability.md`
- [x] Record items 1, 2, 3a and 4 in `docs/decisions.md` as "awaiting Team 2" (P5-Q9), and the open missing-header case — proof: "Phase 5" table in `docs/decisions.md`
- [x] 6 Re-seed the live demo data and return the live clock to real time — done by the 2026-11-18 full live run (`docs/test-reports/2026-11-18-deploy-full-c188b54.md`, "Live data afterwards"), now with report data
- [x] 7 Deploy items 1–5 (`deploy/gcp.sh update origin/phase5`, `c188b54`), post-deploy checks 5/5, deploy report — proof: `docs/test-reports/2026-11-18-deploy-c188b54.md`
- [ ] Team 2 reruns their Phase 4 suite against the fixes — proof: new `docs/test-reports/YYYY-MM-DD-cross-team-team2-to-ours.md`, none of the 12 failures left

## Phase 5 features (CLAUDE.md §6)

- [x] `app/services/reports.py` pure functions: `STAGE_FIELDS`, `validate_report_data()`, `missing_fields()`, `build_report()` (needs-human-review) — proof: `tests/unit/test_reports.py` written first, incl. `STAGE_FIELDS` == fixture `stage_fields`. Mapping provisional (P5-Q1)
- [ ] A team member reviews the report logic (`app/services/reports.py`, needs-human-review) and its tests
- [x] `report_data` table (§6.5), `Database.reset()` clears it before incidents — proof: `tests/unit/test_db.py` (one row per incident and stage, foreign key, reset, existing database)
- [x] `PUT /api/v1/incidents/{incidentId}/report-data/{stage}` + audit `REPORT_DATA_STORED`, removed from `NOT_YET_IMPLEMENTED` — proof: `tests/acceptance/test_reports.py` (404, 400 stage/field/type/JSON/Content-Type, replace, nothing stored on error, audit details). Provisional: P5-Q1, Q3, Q4, Q5
- [x] `GET /api/v1/incidents/{incidentId}/reports/{stage}`, removed from `NOT_YET_IMPLEMENTED` — proof: `tests/acceptance/test_reports.py` (read-only, `generated_at` = clock, survives a restart). Provisional: P5-Q1, Q2, Q5, Q6
- [x] Contract commit (`0b3432d`): PUT 200 body (P5-Q3), GET 400 invalid stage (P5-Q5), `x-fields-by-stage` on `ReportData` (Phase 2 grader 5.1) — proof: contract test; `tests/unit/test_reports.py::test_contract_fields_by_stage_match_the_table`
- [ ] Team 2 agrees the contract commit and applies it to their copy — **blocked: Team 2's answers to P5-Q1, P5-Q3, P5-Q5**
- [x] AC-08 acceptance test from `fixtures/report_cases.json` — proof: `tests/acceptance/test_reports.py::test_ac08_reports_from_the_fixture`. The fixture is still a DRAFT
- [ ] `fixtures/report_cases.json` verified by one checker per team — proof: names and date in `docs/decisions.md` and `fixtures/README.md`. **blocked: P5-Q11 checkers**
- [x] AC-09 acceptance test (four events in order, clock timestamps, rejected request adds nothing, PATCH/DELETE 405 leave the log unchanged) — proof: `tests/acceptance/test_ac09_audit.py`. Action names provisional (P5-Q7)
- [x] `docs/audit-immutability.md`: write-route inventory, triggers, INSERT-only `audit.py`, 405 routes, gated `reset()`, known limits — proof: each claim names its test
- [ ] A team member reviews `docs/audit-immutability.md` (AC-09 code-inspection evidence)
- [x] G7: `tests/unit/test_audit_immutability.py` (static scan of `app/` + triggers raise `IntegrityError`) — proof: test green; G7 row in `docs/metrics.md`. Found that `INSERT OR REPLACE` could overwrite an entry; fixed with the `audit_no_replace` trigger
- [x] Route-audit coverage test: every POST/PUT/PATCH/DELETE outside `/api/v1/test` and `/test` has an expected audit action and writes exactly one entry — proof: `tests/acceptance/test_audit_coverage.py` (fails when an operation is missing from the inventory)
- [x] AC-10: `scripts/container_smoke.py` seed/verify covers Phase 5 state (SBOM replace, CVE records + query, incident with fix and submission, report data + three reports, full audit log), exact JSON compare under the same test clock — proof: `tests/tester/test_ac10.py`, `tests/unit/test_container_smoke.py`; CI stage F; a real uvicorn restart locally on 2026-11-18 (AC-10 PASS)
- [x] AC-10 cross-team: `python -m tester.ac10 snapshot|verify <url> <file>` in `tester/ac10.py`, the one implementation `container_smoke.py` also runs — proof: `tests/tester/test_ac10.py`. Provisional: P5-Q8
- [x] README: the two-step AC-10 procedure for Team 2 ("AC-10 across teams")
- [x] `tester/phase5.py` (AC-08, AC-09; required vs informational), `tester/coverage.py` `ACCEPTANCE_CRITERIA` (AC-01..AC-09) — proof: `tests/tester/test_phase5.py` (our system passes all; faulty targets fail the right checks); local HTTP run 89/89 required, 22/22 informational
- [x] Both `/test/run` harnesses run AC-08/AC-09 (they call `tester.checks.run`); `system` coverage is AC-01..AC-09 and stays 100%, so CI stage F's assertion holds — proof: `tests/test_harness.py`
- [ ] Decide how AC-10 counts in the harness `system` coverage (the harness descriptions now say AC-01..AC-09; AC-10 is the two-step snapshot/verify run) — **blocked: Phase 5 assignment text in `docs/phase5_assignment.md` (§5.2) and a team member's decision on AC-10 coverage**
- [x] `post_deploy_check.sh --full --confirm-reset [--restart-cmd] [--report]` (tester AC-01..AC-09, smoke.sh, AC-10 snapshot → restart → verify, re-seed at real time; PASS/FAIL per step; report with `Result`, `**AC-10:**`, `Latency`) and `deploy/gcp.sh full`; the report operations are in the non-destructive checks via `app/contract_status.py` — proof: `tests/unit/test_post_deploy_full.py`; local end-to-end run with a real restart and a stub-gcloud dry run of `gcp.sh full` (2026-11-18)
- [x] README (Phase 5 scope, report and audit models, known limitations, full live run), `docs/decisions.md`, `fixtures/README.md` Phase 5 section — proof: the files; a team member's review is still welcome
- [x] Full live run (AC-01..AC-10) on `c188b54`: 97/97, AC-10 PASS across `docker compose restart api` — proof: `docs/test-reports/2026-11-18-deploy-full-c188b54.md`; rerun on `271da8e` (main): `docs/test-reports/2026-11-18-deploy-full.md`
- [ ] Final cross-team run, ours → Team 2 (AC-01..AC-09, AC-10 two-step if they cooperate) — proof: `docs/test-reports/YYYY-MM-DD-cross-team-ours-to-team2.md` with `Result: X/Y passed (in scope)`. **blocked: Team 2's final URL and run window (P5-Q10)**
- [ ] Final cross-team run, Team 2 → ours — proof: `docs/test-reports/YYYY-MM-DD-cross-team-team2-to-ours.md`. **blocked: P5-Q10**
- [x] Tag `phase5` on the deployed commit (human, 2026-11-18): `phase5` → `c188b54` — proof: `git ls-remote --tags origin`; G6 row met. Move it if a later code change is redeployed
- [x] Bring live up to `main`: deployed `271da8e` and reran `gcp.sh full` (97/97, AC-10 PASS; both `/test` pages say AC-01..AC-09) — proof: `docs/test-reports/2026-11-18-deploy.md`, `2026-11-18-deploy-full.md`
- [ ] Move the `phase5` tag from `c188b54` to the live `271da8e` (human) — proof: `git ls-remote --tags origin`; G6 row met

## Human tasks (CLAUDE.md §9, §10, §8)

Status summary with evidence: `docs/PHASE5_PROGRESS.md`.


- [ ] Send `docs/pod-questions-phase5.md` to Team 2 and record the answers in `docs/decisions.md` (P5-Q1..Q11)
- [ ] Save the Phase 5 assignment text as `docs/phase5_assignment.md` (§5.2)
- [ ] One checker per team verifies `fixtures/report_cases.json` (P5-Q11); names and date in `docs/decisions.md` and `fixtures/README.md`
- [ ] Team 2's final live URL and an agreed run window (P5-Q10)
- [ ] A team member reviews the timestamp formatter change (`2591c73`, needs-human-review) and, once built, the report logic

- [x] Team 2 confirms the answers in `docs/decisions.md` (Q1–Q8), including the two contract additions — 2026-11-01
- [ ] Update the shared diagrams for "no push alerts" and the deadline status names (CLAUDE.md §10)
- [ ] Name Team 6's AC-04 fixture reviewer (decision Q7) and get Team 2's reviewer to check the same values before the Phase 4 submission
- [ ] Spec housekeeping list in CLAUDE.md §10 (Phase 2 grader points 5.1, 3.2, 7.1, 3.1, 2.3, 9.1, 10, and the report text fixes)
- [ ] Uptime monitor on `/health`
- [x] Re-seed the live demo release (ExampleGateway 1.0.0 + `fixtures/sbom_25_components.json`, CVE records, one incident) — 2026-11-01
