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
drives AC-01 to AC-03 over HTTP using the pod fixtures in `fixtures/` (draft, pending sign-off).

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
