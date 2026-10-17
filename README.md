# ReleaseGate

Release/SBOM registry and (later) CRA deadline tracker. Implements the shared contract in
`docs/openapi.yaml`. Phase 3 scope: releases, CycloneDX SBOM ingestion, audit log, test
endpoints. See `CLAUDE.md` (the Phase 3 handoff) for rules and open questions.

## Run locally

```bash
uv sync
ENABLE_TEST_ENDPOINTS=true DB_PATH=./data/releasegate.db \
  uv run uvicorn app.main:create_app --factory --port 8080
```

## Test

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

`tests/contract/` compares the generated OpenAPI with `docs/openapi.yaml`; `tests/acceptance/`
drives AC-01 to AC-03 over HTTP using the pod fixtures in `fixtures/` (agreed with Team 2).

## Docker

```bash
ENABLE_TEST_ENDPOINTS=true docker compose up --build   # API on :8080, data in a named volume
```

| Variable | Meaning |
|---|---|
| `DB_PATH` | SQLite file (`/data/releasegate.db` in the container, on the volume) |
| `ENABLE_TEST_ENDPOINTS` | `true` mounts `/api/v1/test/*`; evaluation deployment only |
| `PORT` | Port (default 8080) |

Run a single instance: SQLite and the in-memory test clock assume one process.

## Tester

`tester/` is a separate service (port 8081 in compose) that runs the shared AC-01, AC-02 and
AC-03 checks over HTTP against **any** system implementing `docs/openapi.yaml`: ours or another
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
- *Required* checks come from the shared contract and AC-01..AC-03 and decide pass/fail.
  *Informational* checks cover our provisional pod decisions (`docs/decisions.md`) and never fail
  a run.
- Error messages for rejected input appear in the report for the human inspection AC-03 asks for.

## Models (as delivered in Phase 3)

The Phase 2 report (`docs/phase2_report.pdf`, Section 3.2) has the full information and
behavior models. Where its diagrams show an external timer service, that design was dropped:
deadlines (Phase 4) will be computed on read from stored timestamps.

**Data.** `releases` (product, version, support_end_date; product+version unique) has many
`components` (name, version, purl) from its current SBOM. `audit_log` holds one entry per
change (timestamp, user, action, entity); SQLite triggers reject any UPDATE or DELETE on it.
Support status is never stored: a release is `supported` while the clock's UTC date is on or
before `support_end_date`.

**SBOM upload** (`PUT /api/v1/releases/{releaseId}/sbom`): unknown release → 404; body not JSON
→ 400; missing `bomFormat`/`specVersion`, a specVersion other than 1.4–1.6, a schema violation
or a component without a version → 400 naming the problem. Only a fully valid SBOM is stored,
replacing the release's previous components and writing its audit entry in one transaction.

## Known limitations

- **Phase 3 scope only.** CVE queries, incidents, deadlines, report generation and
  `/api/v1/test/vulnerability-source` (REQ-03 to REQ-07) are not built yet; those contract paths
  return 404. Dependency-Track is not integrated into the app; see `spikes/dependency_track/`.
- **Nested components are not stored.** Only top-level `components[]` entries are kept.
- **Large SBOMs are slow.** CycloneDX schema validation grows roughly with the square of the
  component count (about 10 s at 5,000 components) and blocks other requests while it runs.
- **Single instance.** SQLite and the in-memory test clock assume one process; the test clock
  returns to real time when the container restarts.
- **No authentication.** `X-User-Id` only attributes changes in the audit log. The test
  endpoints are unauthenticated, and `POST /api/v1/test/reset` (also called by every tester run)
  wipes all data, so the evaluation deployment holds synthetic data only.
- **Provisional behavior.** Except for the shared fixtures, the rows in `docs/decisions.md`
  still await pod confirmation and may change.

## Deployment (Google Compute Engine)

| | URL |
|---|---|
| System base URL | `http://136.116.160.182:8080` (test endpoints on, synthetic data only) |
| Tester base URL | `http://136.116.160.182:8081` |
| Intra-pod specification | `docs/openapi.yaml` |

One `e2-medium` Debian 12 VM in `us-central1-a` (static IP) runs the compose stack above;
`deploy/gcp-startup.sh` installs Docker and starts it on every boot.

```bash
PROJECT=<gcp-project-id> bash deploy/gcp.sh update   # pull latest main on the VM and rebuild
PROJECT=<gcp-project-id> bash deploy/gcp.sh status   # VM state, /health of system and tester
```

`create` built the VM, static IP and the firewall rules that open only TCP 8080 and 8081; it is a
one-time step.
