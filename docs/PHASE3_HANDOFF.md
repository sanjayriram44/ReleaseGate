# ReleaseGate — Phase 3 Handoff for Claude Code

> **How to use this file:** put it in the repository root as `CLAUDE.md` (Claude Code reads that automatically), then attach or copy the materials listed in **Section 3** into the repo before asking Claude Code to start. Read Sections 1–4 before writing any code.

---

## 1. What we are building (in two lines)

ReleaseGate is a web service that tracks which software releases contain which components, tells a manufacturer which supported releases are affected when a CVE appears, and — for actively exploited vulnerabilities — tracks the EU Cyber Resilience Act's 24-hour, 72-hour, and 14-day reporting deadlines and prepares the report data for a human to submit.

**Course context:** ECE 30861, Team 6. We are in a pod with Team 2. Both teams implement the *same* shared specification independently, and each team's deployed service will be tested by the other team's automated test suite through a common HTTP interface. **Matching the shared interface exactly matters more than anything else.**

---

## 2. Decisions already made (do not revisit without asking)

| Area | Decision | Why |
|---|---|---|
| Web framework | **Python + FastAPI** | Request validation and generated OpenAPI we can check against the shared contract |
| Database | **SQLite**, one file on a persistent volume | Single-instance prototype; no DB server to run |
| Vulnerability matching | **OWASP Dependency-Track** (Phase 4), behind our own release/component tables | Pod-wide Phase 1 decision; fallback is local matching (see §8) |
| Deadlines | **Computed on read** from stored timestamps against an injectable clock. **No timer service, no Temporal, no TheHive.** | Must follow the test clock exactly (AC-07, 0-second tolerance) and survive restarts (AC-10) |
| Audit log | Append-only table, written in the **same transaction** as the change; SQLite triggers block UPDATE/DELETE | REQ-08, AC-09 |
| Deployment | Docker Compose on a cloud VM; only our API port public | Must be network-accessible from Phase 3 |
| CI | GitHub Actions: lint (ruff), type check (mypy), tests (pytest), OpenAPI contract check | Section 7.4 of our report |

**Note on diagrams:** some of our Phase 2 diagrams (especially the behavior model and possibly the 2.1 boundary diagram) still show an external **timer service**. That design was dropped. Where a diagram and this file disagree about deadlines, **follow this file**.

---

## 3. Materials to give Claude Code before it starts

Put these in a `docs/` folder in the repo. Items marked **REQUIRED** must be present before implementation begins; if one is missing, Claude Code should stop and ask rather than guess.

### 3.1 Specification documents

| File (suggested name) | What it is | Status |
|---|---|---|
| `docs/openapi.yaml` | **The shared OpenAPI 3.1 contract** (Section 5.1 of the Phase 2 report; currently a `.txt` in our team Drive). **This is the single source of truth** for paths, status codes, schemas, and error shapes. | **REQUIRED** |
| `docs/phase2_report.pdf` (or `.docx`) | Full Phase 2 report. Key sections: 3.1 requirements, 4.1 acceptance criteria, 5.2 examples, 5.3 test setup, 6.1 Phase 3 milestone, 7.2–7.4 our design | **REQUIRED** |
| `docs/requirements.md` | REQ-01 to REQ-08 copied out of the report (see §5 below for a summary) | Recommended |
| `docs/acceptance_criteria.md` | AC-01 to AC-10 copied out of the report | Recommended |

### 3.2 Diagrams and models

| File | What it shows | Use it for |
|---|---|---|
| `docs/diagrams/2.1.svg` | System boundary: users, external systems, what crosses the boundary, responsibilities kept by humans | Understanding scope; ignore the timer-service box |
| `docs/diagrams/3.1_information.svg` | **Data model**: RELEASE (product, version, support_end_date) → at most one current SBOM → many COMPONENTs (name, version, purl) | Database schema — Phase 3 core |
| `docs/diagrams/3.1_behavior.svg` | **Behavior models**: SBOM submission workflow, CVE query flowchart (unreachable → unknown → match), incident/deadline state machine, report schema and audit-log invariants | SBOM validation flow now; CVE query and deadlines in Phase 4; reports/audit in Phase 5 |
| `docs/diagrams/7.1.svg` | **Our team's architecture**: FastAPI app, SQLite, Dependency-Track, where common-interface requests enter | Module layout and data flow |

SVGs are text — Claude Code can read their labels directly.

### 3.3 Shared pod test fixtures

| File | Contents | Status |
|---|---|---|
| `fixtures/sbom_25_components.json` | The pod's shared 25-component CycloneDX JSON SBOM (used by AC-02 and the Phase 3 demo) | **REQUIRED for AC-02** — get from the pod |
| `fixtures/invalid_inputs/` | Malformed JSON, JSON missing CycloneDX required fields, plaintext (AC-03) | Can be created by us, but expected results must be human-checked |
| `fixtures/releases.json` | Seeded releases with past / boundary / future support-end dates (AC-01) | Pod-shared |
| `fixtures/ground_truth.json` | Expected affected releases per CVE (Phase 4, AC-04) | Pod-shared, not needed yet |

> **Rule:** Claude Code may write test *code*, but must **never invent the expected results** in shared fixtures or ground-truth files. We committed in our report (Q4.2, Q8.2) that ground truth is human-verified, not AI-generated. If a fixture is missing, ask.

### 3.4 Environment details (fill in, never commit secrets)

- Deployment host: `[fill in — VM with ≥8 GB RAM, 4 cores for Dependency-Track later]`
- GitHub repo URL: `[fill in]`
- `.env.example` (committed) lists variable names only; real `.env` stays on the host and is git-ignored.

---

## 4. Phase 3 scope — what to build now

From Section 6.1 of our report.

**Capability:** release registration, CycloneDX SBOM ingestion, and baseline testability.

### 4.1 Endpoints to implement (exact paths from `openapi.yaml`)

| Method & path | Purpose | Reqs |
|---|---|---|
| `POST /api/v1/releases` | Register a release → `201` with `Release`; `400` invalid; `409` duplicate product+version | REQ-01, REQ-08 |
| `GET /api/v1/releases/{releaseId}` | Fetch release with computed `support_status` → `200`; `404` | REQ-01 |
| `PUT /api/v1/releases/{releaseId}/sbom` | Submit or **replace** the release's SBOM → `200 {release_id, component_count}`; `400` with reason; `404` unknown release | REQ-02, REQ-08 |
| `GET /api/v1/releases/{releaseId}/components` | Stored components; empty array if no SBOM; `404` unknown release | REQ-02 |
| `POST /api/v1/test/reset` | Clear all data **including audit log**, reset clock and vulnerability fixtures → `204` | Test setup (Q5.3) |
| `PUT /api/v1/test/clock` | Set reference UTC time `{ "now": "...Z" }` → `200 { "now": ... }` | Test setup |
| `GET /health` | Our own: DB writable (Dependency-Track check added in Phase 4) | Q7.3 |

**Also build now, even though it is validated in Phase 5:** write an audit-log entry for every state change (release registered, SBOM stored, SBOM replaced). Retrofitting this later is harder. `GET /api/v1/audit-logs` is cheap to add now too.

### 4.2 Acceptance criteria to automate in Phase 3

- **AC-01 (REQ-01):** With a fixed reference clock, register four releases: support-end in the past, equal to today, in the future, and one missing `support_end_date`. Pass if today and future are `supported`, past is `unsupported`, and the incomplete one is rejected with `400` and **nothing saved**.
- **AC-02 (REQ-02):** Two releases of one product. Upload the 25-component SBOM to the first. Pass if the first returns all 25 components with matching names and versions and the second returns zero.
- **AC-03 (REQ-02):** Submit malformed JSON, JSON missing required CycloneDX fields, plaintext, and a valid SBOM for an unregistered release. Pass if all four are rejected, **zero components stored**, and each error message states the specific reason.

### 4.3 Demonstration of completion

API deployed to a network-accessible server, a release registered, and the pod's shared SBOM persisted, with AC-01–AC-03 passing in CI.

### 4.4 Out of scope for Phase 3 (do not build yet)

Incidents, deadlines, CVE queries, Dependency-Track integration in the main app, report generation, `/test/vulnerability-source`. These are Phases 4 and 5.

---

## 5. Requirements summary (full text in the report)

- **REQ-01** Register release with product, version, support-end date; treat as supported through that date.
- **REQ-02** Store CycloneDX JSON SBOM components against a registered release; reject invalid files with a stated reason.
- **REQ-03** CVE query returns every affected release grouped by support status; 100% recall on the seeded dataset. *(Phase 4)*
- **REQ-04** Unknown CVE or unreachable source → explicit error, never an empty result. *(Phase 4)*
- **REQ-05** Incident records UTC awareness time, user, mandatory/voluntary classification, rationale. *(Phase 4)*
- **REQ-06** Mandatory deadlines: awareness+24h, awareness+72h, fix-available+14d; status pending/met/overdue. *(Phase 4)*
- **REQ-07** Per-stage report JSON listing missing fields. *(Phase 5)*
- **REQ-08** Log every change with time and user; log is uneditable; all data survives restarts. *(writes now, validation Phase 5)*

---

## 6. Rules the implementation must follow

These come from the shared contract and our report. Violating them fails the other team's tests.

1. **The OpenAPI file is law.** Do not rename paths, fields, enum values, or status codes. If the contract is silent on something, list it as a question (see §7) instead of inventing behavior.
2. **Error shape everywhere:** `{"error": {"code": "...", "message": "..."}}`.
   ⚠️ **FastAPI returns `422` for validation errors by default.** Override the `RequestValidationError` handler so invalid input returns **`400`** with the shared error shape. This is the most likely way to silently fail AC-01 and AC-03.
3. **UTC only.** Timestamps are ISO 8601 with trailing `Z`. Dates are `YYYY-MM-DD`.
4. **One injectable clock.** Every "now" in the codebase comes from a single clock provider. `PUT /test/clock` sets it; `POST /test/reset` restores it to real system time. Never call `datetime.now()` directly anywhere else.
5. **Support status is never stored.** Compute it on every read: `supported` if the clock's UTC date ≤ `support_end_date`, otherwise `unsupported`. A release is supported through the end of its end date.
6. **`X-User-Id` header is required on every state-changing request** (POST/PUT/PATCH). It identifies the actor for the audit log; it is not authentication.
7. **SBOM uploads are atomic.** Validate fully *before* writing. An invalid upload must not change stored components. A valid upload to a release that already has an SBOM **replaces** its components in one transaction.
8. **SBOM validation** uses the official CycloneDX JSON schema (for example via `cyclonedx-python-lib`'s validator or `jsonschema` with the published schemas — verify which works best). Error messages must name the actual problem (e.g., "missing required field: bomFormat").
9. **Audit log is append-only.** Insert the audit row in the same transaction as the change. Add SQLite triggers that `RAISE(ABORT, ...)` on UPDATE or DELETE of the audit table. The only exception is `POST /test/reset`, which clears everything.
10. **Test endpoints are gated.** `/api/v1/test/*` only exists when an environment variable (e.g., `ENABLE_TEST_ENDPOINTS=true`) is set, and only in the evaluation environment with synthetic data.
11. **Persistence:** SQLite file on a named Docker volume so data survives container restarts (AC-10 later).
12. **No secrets in the repo.** `.env` is git-ignored.

---

## 7. Open questions — ask before deciding these

The shared spec does not settle these. Flag them; do not silently pick an answer, because Team 2 must behave the same way.

1. **Missing `X-User-Id` header** — which status code? Proposal: `400 INVALID_REQUEST`. Needs pod confirmation.
2. **Accepted CycloneDX versions** — the example uses `specVersion: "1.6"`. Proposal: accept 1.4–1.6, reject others with a clear reason.
3. **Component without a `version`** — CycloneDX allows it, but our contract's `Component` requires `version`. Reject the whole SBOM, or store with an empty version?
4. **Late submissions (Phase 4)** — our Q3.3 proposes that a submission after its deadline stays `overdue` (no `late` status exists in the enum). Needs pod confirmation.
5. **Matching key (Phase 4)** — package URL (`purl`) vs. name+version. The test fixture schema uses `affected_purls`, suggesting purl.

Record answers in `docs/decisions.md` as they are settled.

---

## 8. Risk to investigate during Phase 3 (Risk 1 in our report)

**Before the Phase 3 milestone**, run a separate spike (not in the main app yet):

- Start a Dependency-Track instance locally with Docker Compose.
- Upload the shared 25-component SBOM, replace it with a second SBOM for the same release, reset, and run five seeded CVE queries.
- **Evidence needed:** queries return within AC-04's 10-second limit right after upload; no stale components after replacement or reset; 100% recall on the seeded manifest; an unknown CVE gets a response distinguishable from "no matches."
- **If it fails:** fallback is matching in our own app against the components already in SQLite, using a local vulnerability table loaded from the shared test data or a saved OSV feed.

Put the spike in `spikes/dependency_track/` with a short `RESULTS.md`.

---

## 9. Suggested repository layout

```
releasegate/
├── CLAUDE.md                  # this file
├── docs/
│   ├── openapi.yaml           # shared contract (source of truth)
│   ├── phase2_report.pdf
│   ├── decisions.md           # answers to §7 as they are settled
│   └── diagrams/              # 2.1, 3.1_information, 3.1_behavior, 7.1 SVGs
├── app/
│   ├── main.py                # FastAPI app, routers, error handlers
│   ├── clock.py               # injectable UTC clock
│   ├── db.py                  # SQLite connection, migrations, triggers
│   ├── models.py              # Pydantic schemas matching openapi.yaml
│   ├── routers/
│   │   ├── releases.py
│   │   ├── sbom.py
│   │   ├── audit.py
│   │   └── test_support.py    # /test/reset, /test/clock (gated)
│   └── services/
│       ├── sbom_validation.py
│       └── audit.py
├── tests/
│   ├── unit/                  # support-status boundaries, validation reasons
│   └── acceptance/            # AC-01, AC-02, AC-03 over HTTP
├── fixtures/                  # pod-shared data (do not invent expected results)
├── spikes/dependency_track/
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── .github/workflows/ci.yml
```

---

## 10. How to work (instructions for Claude Code)

1. **Read first.** Read `docs/openapi.yaml`, this file, and the 3.1 diagrams. Summarize back the Phase 3 endpoints and the rules in §6 before writing code.
2. **Plan, then build in small steps:** scaffold + CI → clock + DB + triggers → releases → SBOM upload and validation → components → test endpoints → audit writes → Docker → deploy.
3. **Test as you go.** Every endpoint gets an acceptance test that calls it over HTTP. Run the full suite before each commit.
4. **Check against the contract.** Compare the app's generated OpenAPI with `docs/openapi.yaml` and fix any differences in paths, status codes, or schemas.
5. **Ask, don't assume.** Anything touching §7, shared fixtures, or the contract → stop and ask.
6. **Keep humans in the loop on correctness.** Deadline logic (Phase 4) and audit-log protection are reviewed by a team member, not just by AI-written tests.
