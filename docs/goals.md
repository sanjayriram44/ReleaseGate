# Phase 4 goals

**Status: confirmed** (the CLAUDE.md §0.2 draft, unchanged). `scripts/metrics.py` measures each
goal and writes the current values to `docs/metrics.md`.

| Goal | Measure | Target | How `scripts/metrics.py` measures it |
|---|---|---|---|
| G1 Correct Phase 4 behavior | AC-04 to AC-07 pass in CI **and** via the tester against our live URL | 100% | Runs the tester's checks in-process and counts required checks per AC; the live run is recorded in `docs/test-reports/` (it resets the live data, so it is never run by this script) |
| G2 No regressions | AC-01 to AC-03, contract test (no missing or extra codes), all Phase 3 tests | 100% | Same in-process tester run for AC-01..AC-03 and contract checks; `pytest` result |
| G3 Interoperability (graded) | Team 2's suite against our service; our tester against Team 2's | ≥ 95% pass; every failure has an issue with an owner | Latest `docs/test-reports/*cross-team*.md` per direction |
| G4 Timeliness | CVE query latency (AC-04); error latency (AC-05) | ≤ 10 s; ≤ 15 s | Slowest AC-04 / AC-05 request in the in-process tester run (once those checks exist) |
| G5 Test strength | Line coverage of `app/` (`pytest --cov`) | ≥ 85% (Phase 3 baseline 88%), never decreasing | `pytest --cov=app` total |
| G6 Healthy deployment | Deployed commit equals the tagged commit; post-deploy checks (§16) pass | Every deploy | `commit` in the live `GET /health` vs the latest `phase*` tag (read-only) |

Confirmed by: Daksh Agarwal, 2026-10-30
