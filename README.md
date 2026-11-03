# ReleaseGate

Release/SBOM registry, CVE impact query and CRA deadline tracker. Implements the shared
contract in `docs/openapi.yaml`. Phase 4 scope: releases, CycloneDX SBOM ingestion, the CVE
affected-releases query with a test vulnerability source, incidents with computed 24 h / 72 h /
14-day deadlines, audit log, test endpoints. Report generation (REQ-07) is Phase 5. See
`CLAUDE.md` (the Phase 4 handoff; Phase 3's is `docs/PHASE3_HANDOFF.md`) for rules, and
`docs/PHASE4_PROGRESS.md` for where the work stands.

## Run locally

```bash
uv sync
ENABLE_TEST_ENDPOINTS=true DB_PATH=./data/releasegate.db \
  uv run uvicorn app.main:create_app --factory --port 8080 --no-access-log
```

## Test

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

`tests/contract/` compares the generated OpenAPI with `docs/openapi.yaml`; `tests/acceptance/`
drives AC-01 to AC-07 over HTTP using the pod fixtures in `fixtures/` (the Phase 4 CVE fixtures
are still drafts; see `fixtures/README.md`). `tests/unit/test_deadlines.py` covers the deadline
math at every boundary.

## Docker

```bash
ENABLE_TEST_ENDPOINTS=true docker compose up --build   # API on :8080, data in a named volume
```

| Variable | Meaning |
|---|---|
| `DB_PATH` | SQLite file (`/data/releasegate.db` in the container, on the volume) |
| `ENABLE_TEST_ENDPOINTS` | `true` mounts `/api/v1/test/*`; evaluation deployment only |
| `PORT` | Port (default 8080) |
| `VULN_SOURCE` | Vulnerability source; only `fixture` (filled by `PUT /api/v1/test/vulnerability-source`) is built |

Run a single instance: SQLite and the in-memory test clock assume one process.

## Tester

`tester/` is a separate service (port 8081 in compose) that runs the shared AC-01 to AC-07
checks over HTTP against **any** system implementing `docs/openapi.yaml`: ours or another
team's. Open its page and enter a system base URL, or call the API:

```bash
curl -X POST http://<tester-host>:8081/api/v1/runs \
  -H 'Content-Type: application/json' -d '{"target_base_url": "http://<system-host>:8080"}'
```

- The response is a report: `result` (`pass` / `fail` / `error`), a summary, and each check with
  expected vs actual and the response excerpt. `GET /api/v1/runs/{run_id}` fetches it again
  (the last 50 runs are kept in memory).
- **A run calls the target's `POST /api/v1/test/reset` at the start and the end, so it wipes the
  target's data.** The target needs its test endpoints enabled.
- *Required* checks come from the shared contract and AC-01..AC-07 and decide pass/fail.
  *Informational* checks cover our provisional pod decisions (`docs/decisions.md`) and never fail
  a run.
- Error messages for rejected input appear in the report for the human inspection AC-03 asks for.

## Autograder endpoints (`/test`)

Both base URLs (system `:8080`, tester `:8081`) serve the course autograder harness, documented
in `docs/openapi.yaml` under "autograder harness". No authentication.

| Call | System | Tester |
|---|---|---|
| `GET /test` | describes the service | describes the service |
| `POST /test/setup` (201) | resets all data; optional `{"now": "…Z"}` sets the clock | optional `{"target_url": "…"}` (or `target_base_url`); default is our system's public URL. Also calls the system's `/test/setup` with the same `session_id` |
| `POST /test/run` | runs AC-01..AC-07 against itself | runs AC-01..AC-07 against the target over HTTP, then the system's own `/test/run` for the session |
| `GET /test/report?session_id=…` | result and every check | result and every check; on both, an unseen id (or no session yet) is a new, not-yet-run session, never 404 |

`setup` returns a `session_id`; `run` and `report` take it (in the JSON body or query string;
without it they use the latest session). `run` is synchronous and finishes in a few seconds.
`run` and `report` carry `target_url`, `results` (every check) and `coverage` in percent:
`code` is `app/` line coverage from our test suite (`.coverage-baseline`, published by the
system; null for a target that doesn't publish one), `component` the share of contract API
operations the run called, and `system` the share of AC-01..AC-07 it exercised.
The system's `/test` endpoints exist only when `ENABLE_TEST_ENDPOINTS=true`.

## Models (as delivered in Phase 4)

The Phase 2 report (`docs/phase2_report.pdf`, Section 3.2) has the full information and
behavior models. Where its diagrams show an external timer service, deadline alerts or
`Waiting`/`Late` states, that design was dropped: deadlines are computed on every read from
stored timestamps, and the statuses are `pending`, `met`, `overdue` and `not_applicable`.

**Data.** `releases` (product, version, support_end_date; product+version unique) has many
`components` (name, version, purl) from its current SBOM, with nested components flattened in
document order (`metadata.component` and `metadata.tools` are not stored). `audit_log` holds one
entry per change (timestamp, user, action, entity); SQLite triggers reject any UPDATE or DELETE on it.
Support status is never stored: a release is `supported` while the clock's UTC date is on or
before `support_end_date`. `incidents` (cve_id, awareness_at, created_by, classification,
rationale, fix_available_at) have at most one `submissions` row per stage; `deadline_at` and
`status` are never stored. `vulnerability_records` / `vulnerability_purls` and a mode flag hold the
test vulnerability source.

**CVE query** (`GET /api/v1/vulnerabilities/{cveId}/affected-releases`): malformed ID → 400;
source unreachable → 503 (checked before anything else, so an outage never looks like "unknown"
or "nothing affected"); unknown CVE → 404; otherwise 200 with affected releases grouped by
support status. A component matches when its purl equals an affected purl with qualifiers and
subpath removed; components without a purl never match. Read-only.

**Deadlines** (`app/services/deadlines.py`, pure functions): for mandatory incidents, early
warning at `awareness_at` + 24 h, notification at + 72 h, final report at `fix_available_at` +
14 days. Submitted at or before the deadline is `met`; a late submission stays `overdue`;
unsubmitted is `pending` until the deadline and `overdue` after it. Voluntary incidents, and the
final report before a fix, are `not_applicable`. Timestamps may carry a UTC offset and are
returned in UTC ending in `Z`.

**SBOM upload** (`PUT /api/v1/releases/{releaseId}/sbom`): unknown release → 404; body not JSON
→ 400; missing `bomFormat`/`specVersion`, a specVersion other than 1.4–1.6, a schema violation
or a component without a version → 400 naming the problem. Only a fully valid SBOM is stored,
replacing the release's previous components and writing its audit entry in one transaction.

## Known limitations

- **No production vulnerability data.** The only source is the test fixture source, so with
  test endpoints off every CVE is unknown (404). The proposed production source, a local OSV
  snapshot replacing Dependency-Track, waits for instructor sign-off (`docs/decisions.md`, Q8);
  see `spikes/dependency_track/`.
- **Draft CVE ground truth.** `fixtures/ground_truth.json` (AC-04) hasn't been verified by the
  two teams' checkers yet, so AC-04 passing shows agreement with the draft only.
- **No reports or alerts yet.** Report data and generation (REQ-07) are Phase 5. There are no
  push alerts: overdue status is visible on every `GET /api/v1/incidents/{incidentId}`.
- **Deadline logic awaits human review** (CLAUDE.md §14.2).
- **Large SBOMs are slow.** CycloneDX schema validation grows roughly with the square of the
  component count (about 10 s at 5,000 components). It runs in a worker thread, so other
  requests are still answered meanwhile.
- **Single instance.** SQLite and the in-memory test clock assume one process; the test clock
  returns to real time when the container restarts.
- **No authentication.** `X-User-Id` only attributes changes in the audit log. The test
  endpoints are unauthenticated, and `POST /api/v1/test/reset` (also called by every tester run)
  wipes all data, so the evaluation deployment holds synthetic data only.
- **Pod decisions.** Team 2 agreed the Phase 4 answers on 2026-11-01 (`docs/decisions.md`),
  including the 400 for a malformed CVE ID and the 409 for a duplicate submission, both added to
  the contract. A few Phase 3 SBOM details (metadata components, repeated nested components)
  are still proposals.

## Deployment (Google Compute Engine)

| | URL |
|---|---|
| System base URL | `http://136.116.160.182:8080` (test endpoints on, synthetic data only) |
| Tester base URL | `http://136.116.160.182:8081` |
| Intra-pod specification | `docs/openapi.yaml` |

One `e2-medium` Debian 12 VM in `us-central1-a` (static IP) runs the compose stack above;
`deploy/gcp-startup.sh` installs Docker and starts it on every boot.

```bash
PROJECT=<gcp-project-id> bash deploy/gcp.sh update [ref]    # build ref (default origin/main), then check
PROJECT=<gcp-project-id> bash deploy/gcp.sh rollback <tag>  # build an earlier tag, then check
PROJECT=<gcp-project-id> bash deploy/gcp.sh status          # VM state, /health of system and tester
```

`create` built the VM, static IP and the firewall rules that open only TCP 8080 and 8081; it is a
one-time step.

`update` and `rollback` check out an exact commit on the VM (so `/health` reports it), rebuild,
and then run the non-destructive post-deploy checks, printing `PASS` or `FAIL` with a rollback
hint. To run the checks by hand from a checkout of the deployed commit:
`bash scripts/post_deploy_check.sh <base_url> <commit> [--test-endpoints on|off]`.

**Backups.** `update` installs `deploy/releasegate-backup.cron`, which runs `deploy/backup.sh`
at 03:30 UTC: an online SQLite backup (`app/backup.py`) into `/opt/releasegate/backups`, outside
the data volume, keeping the newest 7 (log: `/var/log/releasegate-backup.log`). Each copy is one
self-contained file that passed `PRAGMA integrity_check`. To restore one on the VM:

```bash
cd /opt/releasegate && sudo docker compose stop api
sudo docker compose run --rm --no-deps -u 0 api sh -c 'cp /backups/releasegate-<stamp>.db /data/releasegate.db && rm -f /data/releasegate.db-wal /data/releasegate.db-shm && chown 10001 /data/releasegate.db'
sudo docker compose start api
```

## Contributors

ECE 30861, Team 6:

- Daksh Agarwal
- Sanjay Sriram
- Sathvik Valluri
- Donovan Baran
