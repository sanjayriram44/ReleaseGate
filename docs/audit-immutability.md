# Audit-log immutability (AC-09 code-inspection evidence)

This file is the code-inspection half of AC-09 (REQ-08): every state change is recorded, and "no
update or delete paths exist" for audit entries. Each claim names the code and the test that
proves it. Goal G7 in `docs/goals.md` is measured by `tests/unit/test_audit_immutability.py`.

## 1. What is recorded

Every successful state change through the application interface writes exactly one entry, in the
same SQLite transaction as the change (so a change and its entry commit or roll back together).
Failed requests, reads and the test-control endpoints (`/api/v1/test/*`, `/test*`) write none.
Action names follow the vocabulary in P5-Q7, which Team 2 agreed (recorded 2026-11-22); events with the same timestamp keep the order they were recorded in.

| Operation | `action` | `entity_type` / `entity_id` | Written by |
|---|---|---|---|
| `POST /api/v1/releases` | `RELEASE_REGISTERED` | `release` / release ID | `app/services/releases.py` |
| `PUT /api/v1/releases/{releaseId}/sbom` | `SBOM_STORED` (first), `SBOM_REPLACED` (later) | `release` / release ID | `app/services/sbom.py` |
| `POST /api/v1/incidents` | `INCIDENT_CREATED` | `incident` / incident ID | `app/services/incidents.py` |
| `PATCH /api/v1/incidents/{incidentId}` | `FIX_AVAILABLE_RECORDED` | `incident` / incident ID | `app/services/incidents.py` |
| `POST /api/v1/incidents/{incidentId}/submissions` | `SUBMISSION_RECORDED` | `incident` / incident ID | `app/services/incidents.py` |
| `PUT /api/v1/incidents/{incidentId}/report-data/{stage}` | `REPORT_DATA_STORED`, details `{stage, fields}` (names only, never the text) | `incident` / incident ID | `app/services/report_store.py` |

Each entry has `event_id`, `timestamp` (the injected clock's time, so exactly the test clock when
it is set), `user_id` (from `X-User-Id`, required on every write), `action`, `entity_type`,
`entity_id` and optional `details`. `GET /api/v1/audit-logs` returns entries oldest first, ordered
by an autoincrement sequence number.

Proof:

- `tests/acceptance/test_audit_coverage.py`: walks the generated OpenAPI; fails if a write
  operation outside the test endpoints isn't in the table above, and checks each one writes exactly
  one matching entry.
- `tests/acceptance/test_ac09_audit.py` (AC-09): four changes by four users one minute apart give
  exactly four entries in order with the right action, user, entity and clock timestamp; a rejected
  request in between adds nothing; reads and test endpoints add nothing.
- `tests/acceptance/test_audit.py`: failed requests write no entries.

## 2. Nothing changes or removes an entry

**One INSERT path.** `app/services/audit.py` `record()` is the only code that writes to
`audit_log`, and it only inserts.

**No update or delete routes.** `PATCH` and `DELETE /api/v1/audit-logs/{eventId}` exist only to
return `405 AUDIT_IMMUTABLE` (`app/routers/audit.py`); there is no other route on the audit log.
`tests/acceptance/test_ac09_audit.py::test_ac09_events_cannot_be_changed_or_deleted` sends both to
every entry and checks the log is unchanged.

**Database triggers** (`app/db.py` `AUDIT_TRIGGERS`), created on every start with `CREATE TRIGGER
IF NOT EXISTS`, so existing databases get them too:

- `audit_no_update`: `BEFORE UPDATE ON audit_log` → abort "audit log is append-only".
- `audit_no_delete`: `BEFORE DELETE ON audit_log` → abort.
- `audit_no_replace`: `BEFORE INSERT ON audit_log` when the `event_id` or sequence number already
  exists → abort. Added in Phase 5: `INSERT OR REPLACE` removes the conflicting row without firing
  DELETE triggers, so without it an entry could be overwritten. The G7 test found this.

**Static scan** (`tests/unit/test_audit_immutability.py`, G7): parses every `.py` under `app/` and
fails if any SQL string that updates, deletes, replaces, drops or alters `audit_log` or its
triggers appears anywhere except `Database.reset`, or if any `INSERT INTO audit_log` appears outside
`audit.record`. The same file checks that raw `UPDATE`, `DELETE`, `REPLACE` and `INSERT OR REPLACE`
on `audit_log` raise `sqlite3.IntegrityError` and leave the entry as it was.

## 3. The one path that deletes audit rows: the gated test reset

`Database.reset()` in `app/db.py` drops the update and delete triggers, deletes every table's rows
including `audit_log`, and recreates the triggers. It exists so automated tests can start from an
empty system. It is gated twice:

1. **The database refuses.** `Database(path, allow_reset=False)` is the default, and `reset()`
   raises `ResetNotAllowed` before touching anything unless `allow_reset` is true. `create_app`
   sets `allow_reset=settings.enable_test_endpoints`, which comes from `ENABLE_TEST_ENDPOINTS=true`.
2. **No route reaches it.** Its only callers are `POST /api/v1/test/reset`
   (`app/routers/test_support.py`) and the harness's `POST /test/setup` (`app/harness.py`). Both
   routers are mounted only when test endpoints are enabled.

Proof:

- `tests/unit/test_db.py::test_reset_refuses_unless_allowed_and_leaves_the_audit_log`: a database
  opened without `allow_reset` raises, and the audit row and all three triggers are still there.
- `tests/unit/test_reset_gate.py`: a production-configured app publishes no `/api/v1/test/*` or
  `/test*` path (while a test deployment does), its database refuses to reset, `POST
  /api/v1/test/reset`, `/test/setup` and `/test/run` return 404/405 and leave the audit log as it
  was, and a test deployment can still reset.

## 4. Known limits

- **The evaluation deployment enables test endpoints**, because the cross-team testers need
  `/api/v1/test/reset` and the `/test` harness (`deploy/gcp-startup.sh` defaults
  `ENABLE_TEST_ENDPOINTS` to true). There, a reset clears the audit log, by design and only through
  those test routes.
- **File access.** Anyone with write access to the SQLite file can drop the triggers and edit rows
  (Phase 2 report Q8.1). The nightly backups (`deploy/backup.sh`, 7 copies) are the mitigation; a
  tamper-evident log (hash chain) is out of scope.
- **The static scan reads SQL in string literals.** SQL assembled from variables (for example an
  f-string table name) would escape it; none exists, and review rejects it.
- **No authentication.** `user_id` is whatever the caller sends in `X-User-Id` (out of scope, report
  §2.2).
