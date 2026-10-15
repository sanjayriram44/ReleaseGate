# Phase 3 test report — 2026-10-15

**Reviewed:** `main` at `d994938` (Sanjay's 11 commits, `5c9f253`..`d994938`)
**Verdict:** Works. AC-01, AC-02 and AC-03 pass both in the test suite and against a running server, and so does the Docker deployment. There are two medium issues to fix before cross-team testing, plus a few small ones.

## What was run

| Check | Result |
|---|---|
| `pytest` (unit, acceptance, contract) | **65 / 65 passed** in 0.5 s |
| `ruff check` / `ruff format --check` | Clean / 41 files already formatted |
| `mypy` (strict) | No issues in 19 files |
| GitHub Actions on `d994938` | **success** |
| `scripts/smoke.sh` against a live `uvicorn` server | **All checks passed** (AC-01, AC-02, AC-03, replace, clock, audit, reset) |
| Black-box edge-case probes over HTTP (32 requests) | Details below |
| `docker compose up --build` | Builds and starts; runs as non-root (`uid 10001`) |
| Test endpoints with default compose settings | `404`, so they're off by default as intended |
| Persistence: `restart` and `down` + `up` with the same volume | Components and audit log are byte-identical afterwards |

## Acceptance criteria

| AC | Result | Evidence |
|---|---|---|
| AC-01 | Pass | Fixture cases give past → `unsupported`, boundary and future → `supported`, missing date → `400 "support_end_date is required"`. The rejected release can be registered afterwards, and it wrote no audit event. Boundary +1 s → `unsupported`. |
| AC-02 | Pass | All 25 fixture components come back with matching names and versions in fixture order; the second release returns `[]`. |
| AC-03 | Pass | Malformed JSON, missing `bomFormat`, plaintext and an unregistered release all return `400`/`404`, each with a specific message. Zero components are stored, and an existing SBOM is left untouched. |

## Findings

### 1. Medium: a large SBOM upload blocks the whole server

- **Where:** `app/routers/sbom.py:33`. `put_sbom` is `async def`, but it calls the blocking `_store()` (schema validation plus SQLite) directly on the event loop.
- **Evidence:** CycloneDX schema validation time grows with the square of the component count. This is the `uniqueItems` check on `components`.

  | Components | Validation time |
  |---|---|
  | 25 | ~0 s |
  | 500 | 0.11 s |
  | 2,000 | 1.6 s |
  | 5,000 | 9.7 s |

  During a 5,000-component upload, `GET /health` took **9.0 s** to answer.
- **Impact:** None on the Phase 3 ACs (the 25-component fixture takes about 8 ms). But any request that arrives during a big upload stalls. That includes Team 2's test requests and the Docker healthcheck (5 s timeout), and in Phase 4 it would eat into AC-04's 10 s budget.
- **Fix:** run the work off the event loop with `return await run_in_threadpool(_store, releaseId, raw, user_id, db, clock)` from `starlette.concurrency`. Optionally, set a documented component limit or check uniqueness ourselves to avoid the quadratic cost.

### 2. Medium: nested components are silently dropped

- **Where:** `app/services/sbom_validation.py:80`. Only top-level `components[]` are read, as recorded in `docs/decisions.md` (provisional).
- **Evidence:** an SBOM whose parent component has a child stores only `["parent"]`. A nested child *without* a `version` is also accepted, even though a top-level one is rejected.
- **Impact:** this is the exact "uncertainty to reduce" named for Phase 3 in report §6.1. If Team 2 flattens nested components and we don't, AC-02 counts differ. Dropped children also can't be matched in Phase 4 (REQ-03 recall).
- **Fix:** get a pod decision. If the answer is "flatten", walk `components[].components[]` recursively and apply the same version rule.

### 3. Low: the duplicate-component error message is huge

- **Evidence:** the 25-component fixture with one component duplicated returns `400` with a **37,645-character** message, because the raw `jsonschema` message includes the entire `components` array.
- **Impact:** AC-03 requires a person to verify that the message "states the specific failure reason".
- **Fix:** special-case `uniqueItems` in `sbom_validation.py` with a message like `components contains duplicate entries`, or truncate validator messages.

### 4. Low: a whitespace-only product or version is accepted

- **Evidence:** `{"product": "   ", ...}` returns `201`. Report §5.2 says product and version are non-empty.
- **Fix:** strip whitespace before the `min_length` check (`str_strip_whitespace=True` or a pattern) in `ReleaseCreate`.

### 5. Low: a misleading error when a JSON body has the wrong Content-Type

- **Evidence:** `POST /releases` with valid JSON but `Content-Type: text/plain` returns `400 "request body is not valid JSON"`. `PUT /sbom`, by contrast, accepts any Content-Type.
- **Fix:** either accept the body regardless of Content-Type, or say "Content-Type must be application/json".

### 6. Low: the generated OpenAPI advertises `422` on 7 operations

- **Evidence:** the API never returns `422` (it is remapped to `400`), but `/openapi.json` still lists it. The contract test only checks for *missing* status codes, not extra ones.
- **Fix:** remove `422` in `_require_user_id_in_schema` (`app/main.py`), and make the contract test flag extra codes.

### 7. Trivial: a test writes a database inside the repo

- `tests/unit/test_smoke.py` calls `create_app()` with default settings, which creates `./data/releasegate.db`. The file is git-ignored, so it's harmless.
- **Fix:** pass `Settings(db_path=str(tmp_path / "x.db"))`.

## Edge cases that behaved correctly

- `PUT /sbom` with Content-Type `text/plain`, `application/vnd.cyclonedx+json` or none: valid SBOM → `200`, plaintext → `400`.
- Empty body, JSON `null`, `NaN`, numeric `specVersion`, and spec versions 1.3, 2.0 and "abc" → `400`, each with a reason.
- Invalid dates (`null`, `2026-02-30`, `15/06/2026`, a datetime) → `400`. A whitespace `X-User-Id` → `400`.
- Unknown path → `404`; an unsupported method → `405`. Both use the shared error shape.
- 20 parallel uploads to 2 releases all returned `200`, each release ended with 25 components, there were no lock errors, and there was one audit event per upload.
- Replacing an SBOM is logged as `SBOM_REPLACED`. Failed requests write no audit events, and the triggers still block `UPDATE` and `DELETE` after a reset.
- Product and version are case-sensitive, so `P 1` and `p 1` are different releases. That matches the provisional decision.

## Not covered by this review

- **Cloud VM deployment.** No host is chosen yet, and it's required for the Phase 3 demo.
- **Dependency-Track spike** (handoff §8, report Risk 1). `spikes/dependency_track/` doesn't exist yet, and it's due before the Phase 3 milestone.
- **Cross-team run.** Team 2's suite hasn't been run against us yet.
- **Pending decisions.** Every row in `docs/decisions.md` is still provisional, and the `fixtures/` review checklist isn't signed off.
