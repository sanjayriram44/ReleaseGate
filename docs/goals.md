# Phase 4 goals

**Status: confirmed** (CLAUDE.md §0.2 draft; measurement method added below). `scripts/metrics.py`
measures each goal and writes the current values to `docs/metrics.md`. A goal that can't be
measured yet is shown as "not measurable yet", not as a failure.

| Goal | Measure | Target | How `scripts/metrics.py` measures it |
|---|---|---|---|
| G1 Correct Phase 4 behavior | AC-04 to AC-07 pass in CI **and** via the tester against our live URL | 100% | In-process tester run: required checks per AC. Live result: latest `docs/test-reports/*-deploy.md` from a `--full` post-deploy run (never run by this script, because it resets live data) |
| G2 No regressions | AC-01 to AC-03, `tests/contract/test_openapi_contract.py` (no missing or extra codes), all Phase 3 tests | 100% | In-process tester run for AC-01..AC-03; `pytest` result, including the OpenAPI contract test (checks extra codes only after carry-over item 7) |
| G3 Interoperability (graded) | Team 2's suite against our service; our tester against Team 2's | ≥ 95% of in-scope (Phase 1–4) tests pass; every failure has an issue with an owner | Latest `docs/test-reports/YYYY-MM-DD-cross-team-<direction>.md` per direction, read from its `Result: X/Y passed (in scope)` line |
| G4 Timeliness | CVE query latency (AC-04); error latency (AC-05) | ≤ 10 s; ≤ 15 s | Slowest AC-04 / AC-05 request in the container-smoke stage and the latest live `--full` run. The in-process time is reported only as a lower bound |
| G5 Test strength | Line coverage of `app/` (`pytest --cov=app`) | ≥ 85%, never below the stored baseline | `pytest --cov=app` total, compared with `.coverage-baseline` (Phase 4 starting value: 97.95%), which is updated when coverage rises |
| G6 Healthy deployment | Live commit equals the commit deployed; post-deploy checks (§16) pass | Every deploy | `commit` from live `GET /health` (read-only) vs the SHA in the latest `docs/test-reports/*-deploy.md`, plus that report's `Result:` line. Not measurable until §16.1 adds `commit` to `/health` |

Test-report convention: `docs/test-reports/YYYY-MM-DD-<cross-team-ours-to-team2 | cross-team-team2-to-ours | deploy>.md`,
each with a `Result: X/Y passed` line (and `(in scope)` for cross-team runs), the commit SHA, and the main problem with its owner.

Confirmed by: Daksh Agarwal, 2026-10-30
