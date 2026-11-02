# Issues

GitHub issues aren't used (`gh` isn't authenticated), so tasks are tracked here, as CLAUDE.md
§0.1 allows. One checkbox per task, with the test or check that proves it. **blocked** names the
open question (CLAUDE.md §10) or missing material (§5.2) that must be answered first; a blocked
task gets a question, not a guess. `scripts/metrics.py` lists the blocked items in
`docs/metrics.md`.

## Goal audit and CI

- [x] Confirm `docs/goals.md` with a team member — proof: "Confirmed by" filled in
- [x] CI stage A `static` job — proof: job green, and fails on a deliberate lint error
- [x] CI stage B `unit` job with coverage gate — proof: job green, and fails below the G5 threshold
- [x] CI stage E `docker-build` (both images, tagged with the SHA; the system image reports it) — proof: job green, and fails on a throwaway branch without `ENV GIT_SHA`
- [x] CI stages C `acceptance` and D `tester`, with the G5 gate in a `coverage` job that combines all three suites' data — proof: jobs green; throwaway branches failed only in `acceptance`, only in `tester`, and in `coverage` at `--fail-under=100`; `tests/unit/test_ci_split.py` fails if a test file runs in no job or two
- [x] CI stage F `container-smoke` — proof: job green on `c509ef6`; `tests/unit/test_container_smoke.py` shows the restart check notices a change

## Phase 3 carry-over (CLAUDE.md §4)

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

## Phase 4 features (CLAUDE.md §6)

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
- [ ] Confirm the backup on the VM after the next deploy: `/etc/cron.d/releasegate-backup` installed, one manual `sudo /opt/releasegate/deploy/backup.sh` writes a copy, and the README restore steps work — proof: note in the deploy report
- [x] `scripts/post_deploy_check.sh` (non-destructive), `deploy/gcp.sh update [ref]` from an exact commit and `rollback <tag>`, both running the checks (§16) — proof: `tests/unit/test_post_deploy_check.py`; dry run with a stub `gcloud`; run against the live URL on 2026-10-30 (all pass except the commit check: `136c05a` predates `GIT_SHA`)
- [ ] `post_deploy_check.sh --full` (destructive: tester run, smoke test, restart persistence; §16.2 items 6–8) — proof: run on the evaluation deployment after warning Team 2
- [x] Deploy Phase 4 (`68011ca`, 2026-11-01) — proof: `docs/test-reports/2026-11-01-deploy.md`
- [x] Live full run: tester 52/52, both harnesses, smoke.sh, restart persistence; demo re-seeded — proof: `docs/test-reports/2026-11-01-deploy-full.md`
- [x] Tag `phase4` on the deployed commit `e864340` (first `68011ca`) — proof: `git ls-remote --tags origin`
- [ ] Cross-team runs both ways in `docs/test-reports/` (G3) — proof: `YYYY-MM-DD-cross-team-<direction>.md` with `Result:`
  - [x] Team 2 → ours, 2026-11-02: 341/353 (`2026-11-02-cross-team-team2-to-ours.md`)
  - [ ] Ours → Team 2
- [ ] Reject a trailing newline in timestamps and `cve_id` (`$` → `\Z` / fullmatch; Team 2 run, 5 failures) — proof: regression tests with `\n` inputs
- [ ] Accept lowercase `t`/`z` in timestamps (RFC 3339 §5.6; Team 2 run, 4 failures) — proof: unit + acceptance tests
- [ ] SBOM upload: 400 for a non-JSON `Content-Type` (contract lists only `application/json`; Team 2 run, 1 failure) — proof: acceptance test
- [ ] Optional: invalid-UTF-8 SBOM message mentions JSON (Team 2's test checks the wording; 2 failures) — proof: acceptance test
- [ ] Re-seed the live demo data after Team 2's 2026-11-02 run (it reset the data and froze the clock at 2026-11-01T23:59:59Z)
- [ ] A team member reviews the deadline logic (`0f2e32e`, needs-human-review) and its tests

## Human tasks (CLAUDE.md §11, §8)

- [x] Team 2 confirms the answers in `docs/decisions.md` (Q1–Q8), including the two contract additions — 2026-11-01
- [ ] Update the shared diagrams for "no push alerts" and the deadline status names (CLAUDE.md §11)
- [ ] Name Team 6's AC-04 fixture reviewer (decision Q7) and get Team 2's reviewer to check the same values before the Phase 4 submission
- [ ] Spec housekeeping list in CLAUDE.md §11
- [ ] Uptime monitor on `/health`
- [x] Re-seed the live demo release (ExampleGateway 1.0.0 + `fixtures/sbom_25_components.json`, CVE records, one incident) — 2026-11-01
