# ReleaseGate

Release/SBOM registry, CVE impact query, CRA deadline tracker and CRA report-data preparation.
Implements the shared contract in `docs/openapi.yaml`. Phase 5 scope: releases, CycloneDX SBOM
ingestion, the CVE affected-releases query with a test vulnerability source, incidents with
computed 24 h / 72 h / 14-day deadlines, **report data and generated reports for the three CRA
stages (REQ-07, AC-08)**, an append-only audit log with code-inspection evidence (REQ-08, AC-09),
persistence across restarts (AC-10), and test endpoints. The system prepares report data for a
person to submit; it never submits anything or decides what is reportable.

See `CLAUDE.md` (the Phase 5 handoff; earlier ones are `docs/PHASE4_HANDOFF.md` and
`docs/PHASE3_HANDOFF.md`) for rules, `docs/goals.md` and `docs/metrics.md` for goals and current
values, `docs/issues.md` for tasks, and `docs/decisions.md` for pod answers.

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
drives AC-01 to AC-09 over HTTP using the pod fixtures in `fixtures/` (the CVE and report fixtures
are still drafts; see `fixtures/README.md`). `tests/unit/test_deadlines.py` covers the deadline
math at every boundary, `tests/unit/test_reports.py` the report rules, and
`tests/unit/test_audit_immutability.py` the audit log (goal G7). `tests/tester/test_ac10.py` and
`tests/unit/test_container_smoke.py` cover AC-10; CI stage F runs it across a real
`docker compose restart api`.

Without `uv`, a virtualenv works too: `python3.12 -m venv .venv`, then install the versions pinned
in `uv.lock` (`pip install --group dev` and the runtime dependencies from `pyproject.toml`), and
use `.venv/bin/ruff`, `.venv/bin/mypy` and `.venv/bin/pytest`.

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

`tester/` is a separate service (port 8081 in compose) that runs the shared AC-01 to AC-09
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
- *Required* checks come from the shared contract and AC-01..AC-09 and decide pass/fail.
  *Informational* checks cover pod decisions that weren't agreed when the check was written
  (`docs/decisions.md`; for Phase 5, every check that rests on an answer in
  `docs/pod-questions-phase5.md`, which Team 2 has since agreed) and never fail a run.
- Error messages for rejected input appear in the report for the human inspection AC-03 asks for.

### AC-10 across teams (two steps)

A tester can't restart another team's server over HTTP, so AC-10 (state survives a restart with
0 s timestamp drift) runs in two steps (P5-Q8, agreed with Team 2). From a checkout or the tester image:

```bash
python -m tester.ac10 snapshot http://<system-host>:8080 ac10.json   # RESETS the target, seeds, saves
# the system's owner restarts the service (for us: docker compose restart api), then:
python -m tester.ac10 verify   http://<system-host>:8080 ac10.json   # AC-10 PASS or FAIL
```

`snapshot` stores a release whose SBOM was replaced, vulnerability records and one CVE query
result, a mandatory incident with a fix and a submission, report data for all three stages, and
saves every response, the three reports and the full audit log. `verify` sets the same test
clock (it is held in memory, so a restart clears it) and compares every response exactly. It
uses only the contract and the test-control endpoints.

## Autograder endpoints (`/test`)

Both base URLs (system `:8080`, tester `:8081`) serve the course autograder harness, documented
in `docs/openapi.yaml` under "autograder harness". No authentication.

| Call | System | Tester |
|---|---|---|
| `GET /test` | describes the service | describes the service |
| `POST /test/setup` (201) | resets all data; optional `{"now": "…Z"}` sets the clock | optional `{"target_url": "…"}` (or `target_base_url`); default is our system's public URL. Also calls the system's `/test/setup` with the same `session_id` |
| `POST /test/run` | runs AC-01..AC-09 against itself | runs AC-01..AC-09 against the target over HTTP, then the system's own `/test/run` for the session |
| `GET /test/report?session_id=…` | result and every check | result and every check; on both, an unseen id (or no session yet) is a new, not-yet-run session, never 404 |

`setup` returns a `session_id`; `run` and `report` take it (in the JSON body or query string;
without it they use the latest session). `run` is synchronous and finishes in a few seconds.
`run` and `report` carry `target_url`, `results` (every check) and `coverage` in percent:
`code` is `app/` line coverage from our test suite (`.coverage-baseline`, published by the
system; null for a target that doesn't publish one), `component` the share of contract API
operations the run called, and `system` the share of AC-01..AC-09 it exercised (AC-10 needs a
restart, so a single run can't exercise it; how it should count is still to be decided against the
Phase 5 assignment text).
The system's `/test` endpoints exist only when `ENABLE_TEST_ENDPOINTS=true`.

## Models (as delivered in Phase 5)

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
`status` are never stored. `report_data` holds one JSON object per incident and stage, exactly
as supplied; reports are never stored. `vulnerability_records` / `vulnerability_purls` and a mode
flag hold the test vulnerability source.

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

**Report data and reports** (`app/services/reports.py`, pure functions; built on the answers to
P5-Q1..Q6, which Team 2 agreed, `docs/decisions.md`). Each `ReportData` field belongs to one stage (CRA
Art. 14(2); `x-fields-by-stage` in the contract):

| Stage | Required (listed in `missing_fields` when missing) | Optional |
|---|---|---|
| `early_warning` | `member_states` | — |
| `vulnerability_notification` | `product_information`, `exploit_nature`, `vulnerability_nature`, `corrective_measures_taken`, `user_mitigations` | `sensitivity` |
| `final_report` | `vulnerability_description`, `severity`, `impact`, `corrective_measure_details` | `malicious_actor_information` |

`PUT /api/v1/incidents/{incidentId}/report-data/{stage}` checks the incident (404), then the
stage (400), then the body: another stage's field, an unknown field or a wrong type is 400 naming
the field. It replaces the stage's data as a whole, audits `REPORT_DATA_STORED` (field names
only, never the text) and returns the stage's report. `GET .../reports/{stage}` builds the
report on every read: `data` holds the stage's supplied fields exactly as sent, `missing_fields`
the required ones that are absent, null, blank or an empty array, and `generated_at` the clock's
time. Generating a report stores and audits nothing.

**Audit log.** Every successful state change writes one entry in the same transaction; failed
requests, reads and test endpoints write none. Three SQLite triggers reject UPDATE, DELETE and
an INSERT OR REPLACE over an existing entry, and the only delete path is the test reset, which
refuses unless test endpoints are enabled. `docs/audit-immutability.md` is the AC-09
code-inspection evidence, with the write-route inventory and the test behind each claim.

**SBOM upload** (`PUT /api/v1/releases/{releaseId}/sbom`): unknown release → 404; a Content-Type
other than `application/json` or `application/vnd.cyclonedx+json` → 400 (a missing header is
still accepted, although Team 2 agreed it should be 400; see Known limitations); body not JSON → 400; missing `bomFormat`/`specVersion`, a specVersion other than 1.4–1.6, a schema violation
or a component without a version → 400 naming the problem. Only a fully valid SBOM is stored,
replacing the release's previous components and writing its audit entry in one transaction.

## Known limitations

- **No production vulnerability data.** The only source is the test fixture source, so with
  test endpoints off every CVE is unknown (404). The proposed production source, a local OSV
  snapshot replacing Dependency-Track, waits for instructor sign-off (`docs/decisions.md`, Q8);
  see `spikes/dependency_track/`.
- **Draft CVE ground truth.** `fixtures/ground_truth.json` (AC-04) hasn't been verified by the
  two teams' checkers yet, so AC-04 passing shows agreement with the draft only.
- **Phase 5 pod answers are agreed, but not every check reflects that yet.** Team 2 agreed to
  every Phase 5 answer (`docs/decisions.md`): the stage-field table, the PUT's response body, the
  GET's 400 for an invalid stage, the audit action names, the AC-10 procedure and the P5-Q9 input
  rules. They apply the contract change (`0b3432d`) to their copy. The tester checks that rest on
  these answers are still informational, and Team 2's fixture checkers, final URL and run window
  are still to come.
- **An SBOM upload with no `Content-Type` is still accepted.** Team 2 agreed it should be 400
  (P5-Q9); the switch is `ALLOW_MISSING_CONTENT_TYPE` in `app/routers/sbom.py`, to be flipped and
  deployed before the final cross-team run.
- **Draft report ground truth.** `fixtures/report_cases.json` (AC-08) was drafted by Claude from
  CRA Art. 14(2) and hasn't been verified by a checker per team, so AC-08 passing shows agreement
  with the draft only.
- **No alerts and no submission.** There are no push alerts (overdue status is visible on every
  `GET /api/v1/incidents/{incidentId}`), and reports are prepared for a person to submit; nothing
  is sent to ENISA or a CSIRT. Reports are JSON only.
- **Human review owed** for the deadline logic, the timestamp formatter (`2591c73`) and the report
  logic (`app/services/reports.py`), all marked `needs-human-review`.
- **Audit immutability has limits.** On the evaluation deployment the test reset clears the audit
  log (by design, for the testers), and anyone with write access to the SQLite file can drop the
  triggers; backups are the mitigation (`docs/audit-immutability.md`).
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
PROJECT=<gcp-project-id> bash deploy/gcp.sh full            # DESTRUCTIVE full live run (warn Team 2 first)
```

`create` built the VM, static IP and the firewall rules that open only TCP 8080 and 8081; it is a
one-time step.

`update` and `rollback` check out an exact commit on the VM (so `/health` reports it), rebuild,
and then run the non-destructive post-deploy checks, printing `PASS` or `FAIL` with a rollback
hint. To run the checks by hand from a checkout of the deployed commit:
`bash scripts/post_deploy_check.sh <base_url> <commit> [--test-endpoints on|off]`.

**Full live run.** `full` resets the live system, so run it only on the evaluation deployment and
only after warning Team 2. It reads the deployed commit on the VM and runs the checks above with
`--full --confirm-reset`: the whole tester (AC-01..AC-09), `scripts/smoke.sh`, AC-10 across
`docker compose restart api`, then a re-seed of the demo data at real time (ExampleGateway
1.0.0 with the 25-component SBOM, the fixture CVE records, one mandatory incident for
CVE-2023-25577 with early-warning and notification report data, one field left out). Each step
prints PASS/FAIL/SKIP, and it writes `docs/test-reports/<date>-deploy-full.md`, which
`scripts/metrics.py` reads for goals G1 and G4. By hand:
`bash scripts/post_deploy_check.sh <base_url> <commit> --full --confirm-reset --restart-cmd '<cmd>' --report <file>`.

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
