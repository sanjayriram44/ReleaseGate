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

## Deployment (Google Compute Engine)

Evaluation deployment: `http://136.116.160.182:8080` (static IP, test endpoints on, synthetic
data only). One `e2-medium` Debian 12 VM in `us-central1-a` runs the compose stack above;
`deploy/gcp-startup.sh` installs Docker and starts it on every boot.

```bash
PROJECT=<gcp-project-id> bash deploy/gcp.sh update   # pull latest main on the VM and rebuild
PROJECT=<gcp-project-id> bash deploy/gcp.sh status   # VM state, base URL, /health
```

`create` built the VM, static IP and the firewall rule that opens only TCP 8080; it is a
one-time step.
