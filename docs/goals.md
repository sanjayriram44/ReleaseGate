# Phase 5 goals

**Status: DRAFT, awaiting a team member's confirmation** (CLAUDE.md §0.2, with the measurement
method below). No feature code is written until a team member fills in "Confirmed by".
`scripts/metrics.py` measures each goal and writes the current values to `docs/metrics.md`. A goal
that can't be measured yet is shown as "not measurable yet", not as a failure. The Phase 4 goals
are in git history (`bee2b44:docs/goals.md`).

| Goal | Measure | Target | How `scripts/metrics.py` measures it |
|---|---|---|---|
| G1 Correct Phase 5 behavior | AC-08, AC-09, AC-10 pass in CI **and** against our live URL (AC-10 live = restart on the VM) | 100% | AC-08 and AC-09: in-process tester run, required checks per AC. AC-10 needs a restart, so in CI it is stage F `container-smoke` (part of G2's pytest/CI result), and live it is the `**AC-10:** PASS` line of the latest Phase 5 `Mode: full` deploy report. Live AC-08/AC-09: that report's `Result:` line. This script never runs anything against the live URL, because a full run resets its data |
| G2 No regressions | AC-01..AC-07, the contract test (no missing or extra codes), every existing test | 100% | In-process tester run for AC-01..AC-07 and the contract; full `pytest` result |
| G3 Interoperability (graded) | Final cross-team runs, both directions, Phases 3–5 in scope | ≥ 95% each way; every failure has an issue with an owner; none of Team 2's 12 Phase 4 failures remain | Latest `docs/test-reports/YYYY-MM-DD-cross-team-<direction>.md` per direction dated 2026-11-18 or later, from its `Result: X/Y passed (in scope)` line. Phase 4 reports are shown for context but don't count. Failure owners and the 12 Phase 4 cases are checked by reading the report (each report lists them) |
| G4 Timeliness | AC-04 query latency; AC-05 error latency | ≤ 10 s; ≤ 15 s (unchanged) | Slowest AC-04 / AC-05 request from the latest `Mode: full` deploy report's `Latency:` line |
| G5 Test strength | Line coverage of `app/` (`pytest --cov=app`) | ≥ 85% and never below `.coverage-baseline` (99.07% at `bee2b44`) | `pytest --cov=app` total vs `.coverage-baseline`, which rises with coverage |
| G6 Healthy deployment | Live `/health` commit equals the deployed commit; post-deploy checks pass; `phase5` tag on it | Every deploy | `commit` from live `GET /health` (read-only) vs the SHA and `Result:` line of the latest `docs/test-reports/*-deploy.md`, and the commit the `phase5` tag points at on origin (`git ls-remote`, read-only) |
| G7 Audit integrity | No code path changes or removes an audit row except the gated test reset; triggers reject UPDATE/DELETE | Always | Runs `tests/unit/test_audit_immutability.py` (CLAUDE.md §6.6): a static scan of `app/` for `UPDATE`/`DELETE`/`DROP`/`REPLACE` on `audit_log` outside `Database.reset`, and raw UPDATE/DELETE raising `IntegrityError`. Not measurable until that test exists |

Test-report convention (unchanged): `docs/test-reports/YYYY-MM-DD-<cross-team-ours-to-team2 |
cross-team-team2-to-ours | deploy>.md`, each with a `Result: X/Y passed` line (and `(in scope)` for
cross-team runs), the commit SHA, and every failure with its owner. New for Phase 5: a `Mode: full`
deploy report also has an `**AC-10:** PASS` or `**AC-10:** FAIL` line for the restart check.

Confirmed by: _(name, date)_
