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
| 2 CI stages A–B | Done. Jobs `static` → `unit` → `test`. The 85% coverage gate runs on the full suite in `test`, because unit tests alone cover 72%; move it once stages C–D split the suites. |
| 3 §4 carry-over 1–8 | All done, one commit each: threadpool SBOM upload, nested-component flattening, offset/fraction timestamps, short duplicate error, blank names → 400, Content-Type message, no 422 in the generated OpenAPI (the contract test now fails on extra codes), smoke test in `tmp_path`. `scripts/smoke.sh` was updated for offsets too. |
| 4 Shared time parsing and formatting | Done as part of §4 item 3: `parse_utc(value, field)` and `format_utc` in `app/clock.py`. Use them for `awareness_at`, `fix_available_at` and `submitted_at`. |
| 5 onwards | **Not started; blocked on the human answers below.** |
| Unblocked extras (session 2, 2026-10-30) | `/health` reports the built commit (`GIT_SHA` build arg → `Settings.commit`, `unknown` when unset; §16.1). CI stage E `docker-build` builds both images tagged with the SHA and checks the commit inside the system image; shown to fail on a throwaway branch without `ENV GIT_SHA` (deleted). The live VM still runs `136c05a`, so G6 stays unmeasurable until a redeploy with `deploy/gcp.sh update`, which now passes `GIT_SHA`. |
| Unblocked extras, continued | Structured JSON request logs (§8) in `app/request_log.py`: one line per request to stdout with request ID (echoed in `X-Request-Id`), user, method, path, status, latency, clock on arrival and whether it's overridden, plus error code/message on 4xx/5xx; uvicorn's access log is off. Still to add when those features exist: source error detail on 503 lines, overdue-deadline counts. |
| Post-deploy checks (§16) | `scripts/post_deploy_check.sh <base_url> <sha>` runs the five non-destructive checks of §16.2; the CVE check skips until the query is built. `deploy/gcp.sh update [ref]` now checks out an exact commit (detached) instead of pulling, `rollback <tag>` builds a tag, and both run the checks and print PASS/FAIL. The not-yet-built list moved to `app/contract_status.py`, shared by the contract test and the checks; remove operations there as they're built. Against the live URL: all pass except `health` (no commit until a redeploy). `--full` isn't built. |

### Human tasks still open

1. Tag the commit that was deployed for Phase 3 and push the tag:
   `git tag phase3 9c0b191 && git push origin phase3`.
2. Ask Team 2 to rerun their suite against the live system, now that it has the timestamp fix.
   Coordinate first: their run resets our data.
3. Re-seed the demo release on the live system (see above).

## Blocked: questions to settle before step 5

The proposals come from CLAUDE.md §10. Settle each with Team 2, record it in `docs/decisions.md`,
and only then build on it. Don't guess.

| Q | Question | Proposal | Blocks |
|---|---|---|---|
| Q1 | Timestamp amendment | Accept `Z` or offsets, always return UTC `Z` with microseconds. **Already built**; recorded as proposed in `decisions.md` | pod sign-off only |
| Q2 | Submission after its deadline | Stays `overdue`, with `submitted_at` set | `deadlines.py` |
| Q3 | Duplicate submission for a stage; submission for a `not_applicable` stage | 409 (needs a contract change, otherwise 400); 400 | submissions endpoint |
| Q4 | Timestamps before `awareness_at`; times after the clock's now | 400; allowed | PATCH, submissions |
| Q5 | PATCH `fix_available_at` twice, or on a voluntary case | Overwrite (audited); store it but keep deadlines `not_applicable` | PATCH |
| Q6 | Malformed CVE ID | 400 `INVALID_REQUEST` (adds 400 to the contract) | CVE query |
| Q7 | Matching key | Exact purl after stripping qualifiers and subpath; no purl → no match | CVE query |
| Q8 | State after reset | Source `available` with zero records | vulnerability-source, reset |
| Q9 | Incident `cve_id` | Format check only | create incident |
| Q10 | Production vulnerability source | Local OSV snapshot (spike recommendation) or Dependency-Track (needs an 8 GB VM, which costs money, and instructor sign-off) | production source only; the graded `FixtureSource` doesn't depend on it |
| Q11 | Push alerts | None in Phase 4; status is shown on read | diagrams only |
| §5.2 | AC-04 fixtures | Claude may draft the structure and the spike's candidate values, marked unverified; a team member verifies and Team 2 signs off, with the date in `decisions.md` | AC-04 |

When you have answers, continue §14.1 from step 5: `app/services/deadlines.py` as pure functions,
unit tests first. Mark the deadline commits `needs-human-review` (§14.2), and have a team member
review them before anything depends on them.

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
- **Coverage gate:** when stages C–D split the suites (§15), coverage has to be combined across
  jobs, or kept on one full-suite job, because G5 is measured on the whole suite.
- **Stage F:** `container-smoke` needs the incident endpoints for its restart/persistence check,
  so build it after step 6, as §14.1 orders.
