# Issues

GitHub issues aren't used (`gh` isn't authenticated), so tasks are tracked here, as CLAUDE.md
§0.1 allows. One checkbox per task, with the test or check that proves it. **blocked** names the
open question (CLAUDE.md §10) or missing material (§5.2) that must be answered first; a blocked
task gets a question, not a guess. `scripts/metrics.py` lists the blocked items in
`docs/metrics.md`.

## Goal audit and CI

- [x] Confirm `docs/goals.md` with a team member — proof: "Confirmed by" filled in
- [ ] CI stage A `static` job — proof: job green, and fails on a deliberate lint error
- [ ] CI stage B `unit` job with coverage gate — proof: job green, and fails below the G5 threshold
- [ ] CI stages C–F (acceptance, tester, docker-build, container-smoke) — proof: each job green and shown to fail

## Phase 3 carry-over (CLAUDE.md §4)

- [ ] 1 Non-blocking SBOM upload — proof: regression test that `/health` answers during a slow upload
- [ ] 2 Flatten nested components — proof: tests for nested storage, `component_count`, path-named version error
- [ ] 3 Timestamp parsing with offsets and fractions, moved to `app/clock.py` — proof: unit tests with Team 2's inputs
- [ ] 4 Short duplicate-component error — proof: test on the fixture with a duplicated component
- [ ] 5 Blank product/version → 400 `must not be blank` — proof: acceptance test
- [ ] 6 Non-JSON `Content-Type` → `Content-Type must be application/json` — proof: acceptance test
- [ ] 7 No stray 422 in generated OpenAPI; contract test fails on extra codes — proof: contract test
- [ ] 8 Smoke test uses `tmp_path` — proof: `tests/unit/test_smoke.py`
- [ ] Tag `phase3`, redeploy, ask Team 2 to rerun — proof: human runs the tag; Team 2's report in `docs/test-reports/`

## Phase 4 features (CLAUDE.md §6)

- [ ] `deadlines.py` pure functions — proof: `tests/unit/test_deadlines.py` (boundaries, rollover, fractions, offsets, voluntary); human review. **blocked: §10 Q2**
- [ ] `POST /api/v1/incidents` + audit `INCIDENT_CREATED` — proof: AC-06. **blocked: §10 Q9**
- [ ] `GET /api/v1/incidents/{incidentId}` — proof: AC-06, AC-07
- [ ] `PATCH /api/v1/incidents/{incidentId}` + audit `FIX_AVAILABLE_RECORDED` — proof: AC-07. **blocked: §10 Q4, Q5**
- [ ] `POST /api/v1/incidents/{incidentId}/submissions` + audit `SUBMISSION_RECORDED` — proof: AC-07. **blocked: §10 Q2, Q3, Q4**
- [ ] `PUT /api/v1/test/vulnerability-source` + `FixtureSource` — proof: acceptance tests. **blocked: §10 Q8**
- [ ] `GET /api/v1/vulnerabilities/{cveId}/affected-releases` — proof: AC-05, then AC-04. **blocked: §10 Q6, Q7**
- [ ] AC-04 fixtures (`sbom_patched.json`, `vulnerabilities.json`, `cve_dataset.json`, `ground_truth.json`) human-verified and signed off by Team 2 — proof: date in `docs/decisions.md`. **blocked: §5.2 human verification**
- [ ] Production vulnerability source — proof: decision in `docs/decisions.md`. **blocked: §10 Q10**
- [ ] Reset clears incidents, submissions and vulnerability records; `/health` reports source mode and commit — proof: acceptance tests
- [ ] Tester checks and harness `/test/run` for AC-04..AC-07 — proof: `tests/tester`, `tests/test_harness.py`
- [ ] Structured JSON request logs and signals (§8) — proof: unit test on the log line
- [ ] Nightly SQLite backup cron, 7 copies (§8) — proof: script test
- [ ] `scripts/post_deploy_check.sh`, `deploy/gcp.sh` build-from-tag and `rollback` (§16) — proof: run against the live URL (non-destructive mode)
- [ ] Deploy, cross-team runs both ways in `docs/test-reports/`, tag `phase4` — proof: §14.4

## Human tasks (CLAUDE.md §11, §8)

- [ ] Confirm "no push alerts in Phase 4" with the pod and update diagrams. **blocked: §10 Q11**
- [ ] Settle §10 Q1 (timestamp amendment) with Team 2. **blocked: §10 Q1**
- [ ] Spec housekeeping list in CLAUDE.md §11
- [ ] Uptime monitor on `/health`
