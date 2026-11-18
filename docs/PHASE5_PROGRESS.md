# Phase 5 progress

**As of 2026-11-18**, branch `phase5` (PR [#1](https://github.com/sanjayriram44/ReleaseGate/pull/1) into `main`, all CI checks green).
Live: `c188b54` on `http://136.116.160.182:8080`, tester on `:8081`. Handoff: `CLAUDE.md`. Tasks: `docs/issues.md`.
Goals: `docs/goals.md` (confirmed by Daksh Agarwal, 2026-11-18); current values: `docs/metrics.md`.

## Where it stands

All of the Phase 5 feature work in the handoff (§13 steps 1, 3–11) is built, tested and deployed. **It rests on our proposed answers to the pod questions** (`docs/pod-questions-phase5.md`, P5-Q1..Q8; `docs/decisions.md`), because Team 2 hasn't answered yet. What's left is mostly people: Team 2's answers and checkers, the assignment text, the final cross-team runs, reviews, and the `phase5` tag.

| Goal | Status | Evidence |
|---|---|---|
| G1 AC-08..AC-10 in CI and live | **met** | In-process AC-08 30/30, AC-09 7/7; live full run 97/97 with AC-10 PASS across `docker compose restart api` (`docs/test-reports/2026-11-18-deploy-full.md`) |
| G2 No regressions | **met** | AC-01..AC-07 and the contract all pass; 495 tests pass |
| G3 Interoperability | **not measurable yet** | Needs the final cross-team runs both ways |
| G4 Timeliness | **met** | Live: slowest AC-04 0.03 s, AC-05 0.03 s |
| G5 Coverage of `app/` | **met** | 99.20% (≥ 85%, ≥ baseline) |
| G6 Healthy deployment | **no**, only the tag is missing | Live commit = deployed commit, checks 12/12; no `phase5` tag yet |
| G7 Audit integrity | **met** | `tests/unit/test_audit_immutability.py` passes (static scan + triggers) |

## Verification run on 2026-11-18

- **Gate:** ruff, ruff format and mypy clean; `pytest` 495 passed (286 on `main`). Coverage: `app/` 99.20%; `app/` + `tester/` 97%.
- **CI** on PR #1: all 7 jobs pass (static, unit, acceptance, tester, coverage, docker-build, container-smoke with the AC-10 restart).
- **Autograder harness, local** (system and tester as separate services, driven like the grader: `GET /test`, `POST /test/setup` → 201, `POST /test/run`, `GET /test/report`, and an unseen `session_id`): every response valid against the `/test` schemas in `docs/openapi.yaml`. Both runs `pass`, 89/89 required and 22/22 informational checks, AC-01..AC-09 exercised; coverage `code` 99.2, `component` 100, `system` 100. The tester's report carries `target_url`.
- **Autograder harness, live, read-only:** `GET /test` and `GET /test/report` for an unseen session on both `:8080` and `:8081` → 200, schema-valid. A live `/test/setup` + `/test/run` was **not** run: it resets the live data. The same checks ran live through `deploy/gcp.sh full` (tester 89/89).
- **Live deploy** of `c188b54`: post-deploy checks 5/5, probes 12/12 (`docs/test-reports/2026-11-18-deploy.md`). The live database has the three audit triggers.
- **Live full run:** 97/97, AC-10 PASS, the container restart confirmed, demo data re-seeded at real time with report data.
- **Backups on the VM:** the cron is installed, and nightly backups were written on 2026-11-16, -17 and -18 at 03:30 UTC (`/var/log/releasegate-backup.log`). A restore hasn't been tried.
- **`scripts/smoke.sh`** now covers the Phase 5 behavior (11 new checks) and passes locally.

## Handoff compliance, section by section

| Handoff | Status |
|---|---|
| §0.1 Goal audit, review, freshness | Done: goals confirmed, `metrics.py` measures G1–G7, `docs/issues.md` has every §4/§6 task, metrics refreshed after each step |
| §0.3 Inner loop | Tests first, watched fail; full gate per step; one step per commit; pushed with green CI. Mutation checks on AC-09, the audit inventory and the GET handler |
| §0.4 Skills | Documentation skill used for the README; deploy confirmed with the user |
| §2.3 Unknown state | Live `/health` checked (was `bee2b44`, now `c188b54`); live data re-seeded and clock real. **Open:** Phase 4 grade and feedback; who deployed `bee2b44` and moved `phase4` |
| §3 Decisions | Kept: reports computed on read, one row per stage, no legal judgment, fixture source only |
| §4 items 1–5 | Done (`ce44401`, `50928bd`, `416c069`, `43d3e33`, `6d73206`). Item 3's missing-header case is open (P5-Q9). Item 6 done by the full run. Item 7: deployed; **Team 2's rerun of their Phase 4 suite not yet requested** |
| §5.2 Required materials | **Missing:** Team 2's answers; fixture checkers; `docs/phase5_assignment.md`; Team 2's final URL and run window |
| §6.1–6.5 Report endpoints, table | Done on the proposals; contract change `0b3432d` pending Team 2 |
| §6.6 Audit log | Done: inventory, G7 test, route-audit test, `docs/audit-immutability.md`. Found and fixed an `INSERT OR REPLACE` hole |
| §6.7 AC-10 | Done: `tester/ac10.py`, CI stage F, live on the VM, README procedure |
| §6.8 AC automation | Done in tests, tester and both harnesses. **Open:** harness description strings still say AC-01..AC-07, and how AC-10 counts in `system` coverage; both wait for the assignment text |
| §6.9 Final cross-team runs | **Not done** (needs Team 2) |
| §6.10 Demonstration | Ready on the live system: the demo incident's notification report shows `missing_fields: ["user_mitigations"]`; the audit log has the entries; PATCH gives 405; `gcp.sh full` shows the restart |
| §7 Rules | Followed; unagreed behavior is informational in the tester (rule 4); ground truth still a draft (rule 5) |
| §8 Operations | `post_deploy_check.sh --full` and `deploy/gcp.sh full` built and run live. **Open:** uptime monitor on `/health`; a backup restore test |
| §9 Open questions | All 11 still unanswered by Team 2 |
| §10 Spec housekeeping | 5.1 addressed in our contract copy (`x-fields-by-stage`). **Open:** the diagrams (3.2, 7.1), 3.1, 2.3, 9.1, 10, and the report text fixes |
| §12 Self-review | Done, including `smoke.sh` and stale comment references |
| §13.1 Definition of done | Not yet: cross-team reports, Team 2 answers, verified fixtures and the `phase5` tag are missing |

## What we are missing (owner: people, not code)

1. **Team 2's answers** to P5-Q1..Q11, and their agreement to apply contract commit `0b3432d`. If an answer differs, the stage table, the fixture and some checks change.
2. **The Phase 5 assignment text** in `docs/phase5_assignment.md`. Then fix the harness description strings (`app/harness.py`, `tester/harness.py`, `tester/main.py`, the `/test` section of `docs/openapi.yaml`) and decide how AC-10 counts in `system` coverage. Phase 3 lost 55 points on harness format, so this is the biggest grading risk.
3. **Fixture checkers**, one per team, for `fixtures/report_cases.json` (AC-08) and `fixtures/ground_truth.json` (AC-04). Both are still DRAFT.
4. **Final cross-team runs**, both directions, in an agreed window (P5-Q10): ours → Team 2 (that report has been missing since Phase 4) and Team 2 → ours. Also ask Team 2 to rerun their Phase 4 suite against the live fixes. Each run resets the target; re-seed afterwards with `deploy/gcp.sh full`.
5. **Merge PR #1** and tag `phase5` on the final deployed commit (`git tag phase5 <sha> && git push origin phase5`). If the merge creates a new commit, deploy `main` and rerun `gcp.sh full` before tagging.
6. **Human reviews:** `app/services/reports.py` and its tests (needs-human-review), the deadline logic (`0f2e32e`), the timestamp formatter (`2591c73`), `docs/audit-immutability.md`.
7. **Phase 4 grade and feedback** (each piece becomes an issue), and who deployed `bee2b44` and moved the `phase4` tag.
8. **Spec housekeeping** for the Phase 2 grader points (§10): diagrams, security requirements, estimates, risk owners, reference order, report text.
9. **Ops:** an uptime monitor on `/health`; try one backup restore.
10. **P5-Q9:** the SBOM upload with no `Content-Type` (still accepted; one flag flips it).

## How to continue

- Gate: `.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy && .venv/bin/pytest` (or `uv run …`). Without `uv`, a Python 3.12 venv with the versions from `uv.lock` works.
- Metrics: `.venv/bin/python scripts/metrics.py` → `docs/metrics.md`.
- Deploy: `PROJECT=project-13c0e17b-3f88-45f0-be0 bash deploy/gcp.sh update <ref>` (non-destructive checks), then `… gcp.sh full` (destructive full run; warn Team 2 first).
- AC-10 with Team 2: `python -m tester.ac10 snapshot <url> ac10.json`, they restart, then `python -m tester.ac10 verify <url> ac10.json`.
