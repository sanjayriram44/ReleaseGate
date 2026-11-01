# Phase 4 progress: handoff to the next session

Written 2026-10-30 at the end of the first Phase 4 session, so a teammate's Claude Code session can
pick up here. **Read `CLAUDE.md` (the Phase 4 handoff) first**, then this file, `docs/issues.md`
(the task list) and `docs/metrics.md` (current values against `docs/goals.md`).

## Where things stand

- `main` is at `136c05a` plus this handoff commit. CI is green on every commit, and the work went
  straight to main in small commits, each with a regression test.
- **Deployed:** `136c05a` is live on the GCE VM (system `:8080`, tester `:8081`), checked
  non-destructively (`docs/test-reports/2026-10-30-deploy.md`). **The live data is empty**: the
  demo release (ExampleGateway 1.0.0 with `fixtures/sbom_25_components.json`) has not been
  re-seeded. The session's permission settings blocked that write, so a human should do it.
- Tests: 139 passed. Coverage of `app/` is 98.29%; `.coverage-baseline` holds that value.

### Done (CLAUDE.md §14.1)

| Step | State |
|---|---|
| 1 Goal audit | Done. `docs/goals.md` was confirmed by Daksh Agarwal on 2026-10-30. `scripts/metrics.py` writes `docs/metrics.md`. Tasks are in `docs/issues.md` (`gh` isn't authenticated). |
| 2 CI stages A–E | Done. Jobs `static` → `unit` → (`acceptance` (C), `tester` (D)) → `coverage`, plus `docker-build` (E) after `static`. Each suite job saves its coverage data; `coverage` combines them and fails below 85%, so G5 is still the whole suite. `tests/unit/test_ci_split.py` checks every test file runs in exactly one job, so put new test files under an existing directory or add them to a job. Stage F waits for the incident endpoints. |
| 3 §4 carry-over 1–8 | All done, one commit each: threadpool SBOM upload, nested-component flattening, offset/fraction timestamps, short duplicate error, blank names → 400, Content-Type message, no 422 in the generated OpenAPI (the contract test now fails on extra codes), smoke test in `tmp_path`. `scripts/smoke.sh` was updated for offsets too. |
| 4 Shared time parsing and formatting | Done as part of §4 item 3: `parse_utc(value, field)` and `format_utc` in `app/clock.py`. Use them for `awareness_at`, `fix_available_at` and `submitted_at`. |
| 5–11 | Done in session 3; see below. |
| Unblocked extras (session 2, 2026-10-30) | `/health` reports the built commit (`GIT_SHA` build arg → `Settings.commit`, `unknown` when unset; §16.1). CI stage E `docker-build` builds both images tagged with the SHA and checks the commit inside the system image; shown to fail on a throwaway branch without `ENV GIT_SHA` (deleted). The live VM still runs `136c05a`, so G6 stays unmeasurable until a redeploy with `deploy/gcp.sh update`, which now passes `GIT_SHA`. |
| Unblocked extras, continued | Structured JSON request logs (§8) in `app/request_log.py`: one line per request to stdout with request ID (echoed in `X-Request-Id`), user, method, path, status, latency, clock on arrival and whether it's overridden, plus error code/message on 4xx/5xx; uvicorn's access log is off. Still to add when those features exist: source error detail on 503 lines, overdue-deadline counts. |
| Post-deploy checks (§16) | `scripts/post_deploy_check.sh <base_url> <sha>` runs the five non-destructive checks of §16.2; the CVE check skips until the query is built. `deploy/gcp.sh update [ref]` now checks out an exact commit (detached) instead of pulling, `rollback <tag>` builds a tag, and both run the checks and print PASS/FAIL. The not-yet-built list moved to `app/contract_status.py`, shared by the contract test and the checks; remove operations there as they're built. Against the live URL: all pass except `health` (no commit until a redeploy). `--full` isn't built. |
| Nightly backup (§8) | `app/backup.py` (in the image) makes an online SQLite backup, checks its integrity, saves `releasegate-<UTC stamp>.db` and keeps the newest 7. `deploy/backup.sh`, run at 03:30 UTC by `deploy/releasegate-backup.cron`, runs it in the api container into `/backups`, bind-mounted from `/opt/releasegate/backups`. `gcp.sh update` and the startup script install the cron entry (and `cron` if missing). Not yet exercised on the VM: no Docker here, and the deploy is the teammate's. |

### Human tasks still open

1. Tag the commit that was deployed for Phase 3 and push the tag:
   `git tag phase3 9c0b191 && git push origin phase3`.
2. Ask Team 2 to rerun their suite against the live system, now that it has the timestamp fix.
   Coordinate first: their run resets our data.
3. Re-seed the demo release on the live system (see above).

## Session 3 (2026-11-01): Phase 4 features built and deployed

The proposed answers in `docs/pod-questions-phase4.md` were adopted as Team 6's decisions (rows in
`docs/decisions.md`, each "awaiting Team 2"). Two of them changed the contract: 400 for a
malformed CVE ID, and 409 for a duplicate submission. §14.1 steps 5–11 are done, one commit each
with CI green, and `68011ca` is deployed (`docs/test-reports/2026-11-01-deploy.md`):

- `app/services/deadlines.py`: pure deadline functions. The commit is marked
  **needs-human-review**: a team member still has to review the logic and `tests/unit/test_deadlines.py`.
- Incidents: `POST /incidents`, `GET`/`PATCH /incidents/{id}`, `POST /incidents/{id}/submissions`,
  with audit entries (AC-06, AC-07).
- `PUT /test/vulnerability-source`, `FixtureSource` and the CVE query (AC-05). `VULN_SOURCE=fixture`
  is the only source built.
- The AC-04 fixtures are **drafts**: `fixtures/README.md` has the checklist for the two checkers (Q7).
- The tester and both `/test/run` endpoints run AC-01..AC-07 (`tester/phase4.py`); checks that
  depend on unconfirmed answers are informational.
- CI stage F `container-smoke` (compose up, tester, restart persistence), plus log signals
  (source error details, overdue counts).

### Still open

1. ~~Live full run~~ **Done 2026-11-01** (`docs/test-reports/2026-11-01-deploy-full.md`): tester
   52/52 against the live URL, both `/test/run` harnesses pass, smoke.sh and restart persistence
   pass, demo data re-seeded. G1, G2, G4, G5 and G6 are met (`docs/metrics.md`). The answers are
   accepted for the submission (`docs/decisions.md`). `phase3` and `phase4` (now `e864340`) are tagged.
2. **Cross-team runs both ways** (G3), each with its own report. Team 2 first needs the contract
   commit `c249e2c` and the decisions.
3. **Human checks:** review the deadline code; verify the AC-04 fixtures (one reviewer per team,
   before the submission); instructor sign-off for Q8's OSV source. Team 2 agreed Q1–Q7 and "no
   push alerts" on 2026-11-01, and is open to the OSV switch.
4. ~~Tags~~ done: `phase3` → `9c0b191`, `phase4` → `e864340` (moved from `68011ca` after the calendar-limit fix). If a later fix is deployed, move
   `phase4` only with the team's agreement.
5. `post_deploy_check.sh --full` is still not built; the live tester run is done by hand.

## How the work was done (keep doing it this way)

- **Inner loop per step (§0.3):** write the test first and see it fail for the expected reason,
  make the smallest change, then run the full gate:
  `.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy && .venv/bin/pytest`.
  Commit one step at a time, push, and wait for CI to go green before the next step. Tick the
  box in `docs/issues.md` in the same commit. Commit messages end with the Co-Authored-By line.
- **CI status without `gh`:** the repo is public, so query
  `https://api.github.com/repos/sanjayriram44/ReleaseGate/actions/runs?head_sha=<sha>` and then
  `.../actions/runs/<id>/jobs`.
- **Metrics:** run `.venv/bin/python scripts/metrics.py` after each task. It runs pytest with
  coverage and raises `.coverage-baseline` when coverage rises; commit both files.
  `--offline` skips the GitHub and live `/health` reads, but then writes "skipped" into
  `metrics.md`, so don't commit an offline run.
- **Test reports:** use `docs/test-reports/YYYY-MM-DD-<cross-team-ours-to-team2 |
  cross-team-team2-to-ours | deploy>.md`, each with a `Result: X/Y passed` line (add `(in scope)`
  for cross-team runs), the commit SHA, and the main problem with its owner. `metrics.py` parses
  these.
- **Tooling:** `uv` isn't on PATH. For dependency changes, install it into a scratch venv
  (`python3 -m venv <dir> && <dir>/bin/pip install uv`), run `uv lock`, then
  `UV_PROJECT_ENVIRONMENT=.venv <dir>/bin/uv sync --locked`. Ruff formats Python inside Markdown,
  so `CLAUDE.md` and `docs/PHASE3_HANDOFF.md` are excluded in `pyproject.toml`. pytest collects
  any `test*` helper, so name helpers `make_*`. The shell is zsh. Run local servers on
  `PORT=18080` / `TESTER_PORT=18081`, because old Dependency-Track containers may hold 8080/8081.
- **Deploy** (now `update [ref]` / `rollback <tag>`, both followed by the post-deploy checks): run
  `PATH="$HOME/google-cloud-sdk/bin:$PATH" PROJECT=project-13c0e17b-3f88-45f0-be0 bash deploy/gcp.sh update`
  (`status` checks health). It pulls main on the VM, rebuilds and keeps the data volume. Ask
  before every deploy and before anything that writes to or resets the live system. A tester or
  harness run (`/test/setup`, `/test/run`) resets the data, so re-seed the demo release afterwards.

- **On Windows** (the second session ran there): the venv is `.venv/Scripts/`, not `.venv/bin/`; pytest's default temp dir may be unwritable, so pass `--basetemp=<scratch dir>` (for `metrics.py`, set `PYTEST_ADDOPTS=--basetemp=...`); run Python file edits with `PYTHONUTF8=1` so `§` stays UTF-8; and there is no local Docker, so the image is checked by CI stage E. Shell scripts are committed with LF even though `core.autocrlf` is on.

## Things to watch in the next steps

- **Contract test allowlist:** `tests/contract/test_openapi_contract.py` keeps `NOT_YET_IMPLEMENTED`.
  Remove each operation from it as you build it; the test fails if you forget. The generated
  OpenAPI must list exactly the contract's response codes, no more and no fewer, so declare
  `responses=` to match `docs/openapi.yaml`.
- **Timestamps:** `format_utc` gives six-digit microseconds whenever there's a fraction, so audit
  timestamps from the real clock now carry microseconds. Times set through the test clock in
  whole seconds stay whole seconds.
- **Error messages:** messages from our own validators (`ValueError` in `AfterValidator` or
  `BeforeValidator`) render as `"<field> <reason>"`, e.g. `product must not be blank`. Reuse that
  for `rationale` (non-blank) and `classification`.
- **Stale behaviour in scripts:** `scripts/smoke.sh` and `tester/checks.py` encode current
  behaviour. Update them whenever behaviour changes; a stale offset check in `smoke.sh` was missed
  once.
- **Harness descriptions:** the harness text in `docs/openapi.yaml` (and `tester/harness.py`) still
  says `now` is "UTC, trailing Z". That's still accepted, so it was left alone; changing that text
  is a contract edit.
- **Stage F:** `container-smoke` needs the incident endpoints for its restart/persistence check,
  so build it after step 6, as §14.1 orders.
