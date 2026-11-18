# Audit-log immutability (AC-09 code-inspection evidence)

**Status: in progress.** This file is the code-inspection half of AC-09 (REQ-08): "no update or
delete paths exist" for audit entries. The write-route inventory, the triggers, the INSERT-only
`app/services/audit.py`, the 405 routes and the G7 static test are added in CLAUDE.md §13 step 7.

## The one path that deletes audit rows: the gated test reset

`Database.reset()` in `app/db.py` drops the two audit triggers, deletes every table's rows
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
  opened without `allow_reset` raises, and the audit row and both triggers are still there.
- `tests/unit/test_reset_gate.py`: a production-configured app publishes no `/api/v1/test/*` or
  `/test*` path (while a test deployment does), its database refuses to reset, `POST
  /api/v1/test/reset`, `/test/setup` and `/test/run` return 404/405 and leave the audit log as it
  was, and a test deployment can still reset.

**Known limit.** The evaluation deployment runs with test endpoints enabled, because the
cross-team testers need `/api/v1/test/reset` and the `/test` harness. There, a reset does clear the
audit log, by design and only through those test routes. Separately, anyone with write access to
the SQLite file can drop the triggers (Phase 2 report Q8.1); the nightly backups are the
mitigation.
