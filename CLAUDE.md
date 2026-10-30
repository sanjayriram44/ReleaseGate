# ReleaseGate — Phase 4 Handoff for Claude Code

> **How to use this file:** move the current `CLAUDE.md` (the Phase 3 handoff) to `docs/PHASE3_HANDOFF.md` if it isn't there already, then save this file as `CLAUDE.md` in the repository root. Claude Code reads it automatically. Read Section 0 and Sections 1–5 before writing any code. Follow the order in §14.1: goal audit first, then the first CI stages, then the Phase 3 carry-over (Section 4).

---

## 0. Working method: read this before anything else

You work in two nested loops. The **outer loop** (Imprint, from lecture: <https://lethain.com/software-factory-experiment/>) keeps the work aligned with written, measured goals. The **inner loop** (§0.3) runs once for every small step and ends only when the result is verified to line up with the spec. Never skip either loop, even for "trivial" changes.

### 0.1 Outer loop (Imprint): goal → review → work → freshness

1. **Goal audit.** Check that `docs/goals.md` (the goals, with a measure for each) and `docs/metrics.md` (current values) exist. **If either is missing, stop: draft them from §0.2 and ask a team member to confirm before any code is written.** The audit refuses to run until the goal and its measure are written down.
2. **Review.** Read `docs/metrics.md` and the open issues. Use GitHub issues via `gh` if it's available; otherwise `docs/issues.md`, one checkbox per task with the test that proves it. Add or update issues for anything new you notice. Every task in §4 and §6 becomes one issue.
3. **Work.** Take **one unblocked task**: one whose open questions (§10) are answered and whose fixtures exist. Do it with the inner loop (§0.3), then open a pull request, request a human review, or ask a question. A task blocked on §10 or §5.2 gets a question, not a guess.
4. **Check freshness.** After each task, rerun `scripts/metrics.py` and ask: does `docs/goals.md` still describe what we're doing? If a pod decision, grader feedback or a spec change made it stale, go back to step 1 and update it with a team member. Otherwise take the next task.

### 0.2 Phase 4 goals and measures (draft for `docs/goals.md`; a human must confirm)

| Goal | Measure | Target |
|---|---|---|
| G1 Correct Phase 4 behavior | AC-04 to AC-07 pass in CI **and** via the tester against our live URL | 100% |
| G2 No regressions | AC-01 to AC-03, contract test (no missing or extra codes), all Phase 3 tests | 100% |
| G3 Interoperability (graded) | Team 2's suite against our service; our tester against Team 2's | ≥ 95% pass; every failure has an issue with an owner |
| G4 Timeliness | CVE query latency (AC-04); error latency (AC-05) | ≤ 10 s; ≤ 15 s |
| G5 Test strength | Line coverage of `app/` (`pytest --cov`) | ≥ 85% (Phase 3 baseline 88%), never decreasing |
| G6 Healthy deployment | Deployed commit equals the tagged commit; post-deploy checks (§16) pass | Every deploy |

`scripts/metrics.py` (build it in the first CI stage) writes `docs/metrics.md`: last CI result, pass/fail per AC, coverage %, latest cross-team results from `docs/test-reports/`, the deployed commit, and open blocking questions.

### 0.3 Inner loop: for every small step

1. **State the step's goal in one line** and name the test or check that will prove it (an AC, a unit test, a contract check, a deployment check).
2. **Read the spec for it:** the `openapi.yaml` section, `docs/decisions.md`, the AC text in the report, and the §5.2 examples.
3. **Write or update the test first.** Run it and confirm it **fails for the expected reason**. A test that passes before the change proves nothing.
4. **Implement the smallest change** that makes it pass.
5. **Run the local gate:** the targeted test, then `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`.
6. **Line-up check.** Compare actual output with the expected output field by field, not just status codes. Send the contract's example requests, diff the JSON against the documented response, and compare against `ground_truth.json` where it applies. Check the generated OpenAPI against `docs/openapi.yaml`. Any difference is a failure, even if the tests are green.
7. **Self-review the diff** against the checklist in §14.3.
8. **Debug loop if anything fails:** reproduce it with a failing test → isolate → state a hypothesis → fix → rerun the full gate. Add the reproduction as a permanent regression test. **After three failed attempts, or if the fix would change the contract, a fixture or a §10 answer, stop and ask.**
9. **Commit one step per commit**, push, and wait for CI to be green **before starting the next step.** Never stack new work on a red build.

### 0.4 Skills and tools

Before each kind of task, check which skills and plugins are installed (for example with `/skills` or the plugin list), and use the relevant one alongside this file. Examples, if installed: a **testing-strategy** skill when planning tests for a new endpoint; a **debug** skill inside the debug loop; a **code-review** skill for step 7 of §0.3; a **deploy-checklist** skill before every deployment; a **documentation** skill for README and decisions updates. If a skill disagrees with this file or the contract, **this file and the contract win**; mention the conflict to a team member. If no relevant skill is installed, follow the checklists in this file.

---

## 1. What we are building

ReleaseGate is a web service that tracks which software releases contain which components, tells a manufacturer which supported releases are affected when a CVE appears, and, for actively exploited vulnerabilities, tracks the EU Cyber Resilience Act's 24-hour, 72-hour and 14-day reporting deadlines and prepares the report data for a person to submit.

**Course context:** ECE 30861, Team 6, in a pod with Team 2. Both teams implement the *same* shared specification independently, and each team's deployed service is tested by the other team's automated suite through the common HTTP interface. **From Phase 4, cross-team results count toward the grade.** Matching the shared interface exactly matters more than anything else.

**Phase 4 in one line (report §6.2):** vulnerability querying with fault injection, and incident deadline tracking: REQ-03 to REQ-06, proven by AC-04 to AC-07.

---

## 2. Where we are after Phase 3

### 2.1 What exists and works (on `main`)

| Area | State |
|---|---|
| Releases | `POST /api/v1/releases`, `GET /api/v1/releases/{releaseId}`; support status computed on read; duplicate → 409 |
| SBOMs | `PUT /api/v1/releases/{releaseId}/sbom` with CycloneDX 1.4–1.6 schema validation, atomic replace; `GET .../components` |
| Audit log | Written in the same transaction as every change; SQLite triggers block UPDATE/DELETE; `GET /api/v1/audit-logs`; PATCH/DELETE → 405 |
| Test support | `POST /api/v1/test/reset`, `PUT /api/v1/test/clock` (gated by `ENABLE_TEST_ENDPOINTS`) |
| Autograder harness | `GET /test`, `/test/setup`, `/test/run`, `/test/report` on both the system and the tester (`app/harness.py`, `tester/harness.py`) |
| Tester | Separate service (`tester/`, port 8081) running AC-01–AC-03 + contract checks against any base URL; 32 required + 3 informational checks |
| Ops | `/health` (DB writable), Docker Compose, named volume, GCE e2-medium VM in `us-central1-a` (4 GB RAM), `deploy/gcp.sh update/status` |
| CI | ruff, ruff format, strict mypy, pytest, OpenAPI contract check |
| Docs | `docs/openapi.yaml` (contract), `docs/decisions.md`, README with models + known limitations, `spikes/dependency_track/RESULTS.md` |

**Requirement status:** REQ-01 complete (AC-01). REQ-02 partial: AC-02 and AC-03 pass, but nested components are not stored yet. REQ-08 partial: logging exists for releases and SBOMs only.

### 2.2 Cross-team results from Phase 3

| Direction | Result | Main problem |
|---|---|---|
| Our tester → Team 2 | 31/33 checks passed | Team 2 has no `GET /api/v1/audit-logs` yet (their item) |
| Team 2's suite → us | 128/157 passed | Our `PUT /api/v1/test/clock` rejected UTC offsets and dropped fractional seconds (**our item, fix in §4**) |

### 2.3 Known gaps carried into Phase 4

Prepared fixes from Phase 3 were **never merged**, and the patch files no longer apply cleanly because `test_support.py` and `main.py` changed. Re-implement them from the descriptions in §4.

---

## 3. Decisions already made (do not revisit without asking)

| Area | Decision | Why |
|---|---|---|
| Framework / DB | FastAPI + SQLite on a named volume (WAL, `BEGIN IMMEDIATE`) | Single-instance prototype |
| Deadlines | **Computed on read** from stored timestamps and the injectable clock. **No timer service, no Temporal, no TheHive, no background scheduler.** | Follows the test clock exactly (AC-07, 0 s tolerance); survives restarts (AC-10) |
| Awareness time | `awareness_at` is **supplied by a person**; the system never infers it | Pod agreement, Sept 26, 2026 (REQ-05) |
| Audit log | Same transaction as the change; triggers block edits | REQ-08 |
| Clock | One `Clock`; nothing else calls `datetime.now()` | Determinism |
| Shared fixtures | `fixtures/` used unchanged by both teams | Agreed with Team 2, Oct 17, 2026 |
| Nested components | **Recursively flatten**; count every depth | Agreed (exclusions and duplicates still proposals, see `docs/decisions.md`) |
| Vulnerability matching | **Pending pod decision.** The spike recommends **local matching in SQLite** instead of Dependency-Track (see §6.1). The shared spec currently says *"Dependency-Track is the only CVE source"* (report §2.2 limits) and shows DT in the shared boundary diagram (§2.1), so switching is a **shared-scope change**: both teams must agree and the instructor must sign off before §2.2 changes | DT needs ~8 GB RAM, the NVD mirror, and waiting for background analysis |
| Scope | **No scope cuts without sign-off.** Report §6.4 says the pod *would* drop voluntary classification (REQ-05) or unreachable-source fault injection (REQ-04, AC-05) if behind. Course rules forbid reducing shared scope unilaterally: if Phase 4 falls behind, tell a team member; never drop a requirement on your own | Phase 3 rules: both teams + instructor sign-off |
| Deadline alerts | **No push alerts in Phase 4.** Overdue status is visible on every `GET /incidents/{id}`. REQ-06 doesn't require alerts (report §7.2), but the shared boundary diagram (§2.1) and behavior model (§3.2) still show alerts, so they need updating (§11) | Compute-on-read design; a poller can add reminders later |

**Diagram and text warning:** Phase 2 diagrams still show an external timer service, deadline alerts, `Waiting`/`Late` deadline states, `timer_id`, and routes like `/cases`, `/cves/{id}` and `POST /cases/{id}/events`. Report text also says `awareness_time` (report §1.3; the contract field is **`awareness_at`**), and report §4.3 describes AC-05 as *stopping* the mock vulnerability service (the contract does it with `PUT /api/v1/test/vulnerability-source` and `mode: unreachable`). **All of that is outdated.** Where a diagram disagrees with `docs/openapi.yaml` or this file, follow the contract and this file.

---

## 4. Phase 3 carry-over (first coding task, in this order)

Each item is a separate commit with its own regression test.

1. **Non-blocking SBOM upload.** `put_sbom` in `app/routers/sbom.py` is `async` but calls blocking validation and SQLite code, which freezes the whole server during a large upload (`/health` took ~9 s at 5,000 components). Run `_store(...)` through `starlette.concurrency.run_in_threadpool`. `BEGIN IMMEDIATE` already makes concurrent writers safe.
2. **Flatten nested components** (agreed). Walk `components[].components[]` recursively. Apply the "missing version → reject whole SBOM" rule at every depth. `component_count` counts every stored component. Do **not** include `metadata.component` or `metadata.tools`. Error messages should give the path (for example, `components[3].components[0] is missing required field: version`).
3. **Timestamp parsing (our cross-team failure).** Change `parse_utc` in `app/routers/test_support.py` so that it:
   - accepts `Z` **or** a numeric offset (`+02:00`, `-05:30`, `-00:00`) and converts to UTC;
   - still rejects timestamps with no zone;
   - keeps fractional seconds (truncate beyond microseconds).

   Responses always end in `Z`: whole seconds when there's no fraction, otherwise six-digit microseconds (`2026-11-01T23:59:59.100000Z`). Move `parse_utc` and the formatter into `app/clock.py` (or a `timeutil.py`) because Phase 4 uses them for `awareness_at`, `fix_available_at` and `submitted_at` too. `app/harness.py` imports `parse_utc`, so update that import. Test with Team 2's exact inputs: `-00:00`, `+02:00`, `-05:30`, `+05:45`, `+23:59`, `-23:59`, `.1Z`, `.123456+02:00`, `.123456789Z`. This depends on the pod agreeing the Section 5 amendment (§10 Q1), but it's a superset of the current behavior, so build it now.
4. **Short duplicate-component error.** When the CycloneDX validator fails with `uniqueItems`, don't pass its message through (it embeds the whole array, about 37K characters). Return `components contains duplicate entries: components[i] repeats components[j]`.
5. **Blank names.** Whitespace-only `product` or `version` → 400 `must not be blank`. Store values exactly as sent.
6. **Content-Type message.** A JSON body sent with a non-JSON `Content-Type` → `Content-Type must be application/json`, not "not valid JSON".
7. **Stray 422 in generated OpenAPI.** Remove `422` from every operation and drop the `HTTPValidationError`/`ValidationError` schemas. Extend the contract test to fail on response codes the contract doesn't list, not only on missing ones.
8. **Smoke test DB.** `tests/unit/test_smoke.py` must use `tmp_path`, not `./data`.

After these, **tag the deployed commit** `phase3` (a human runs `git tag phase3 <hash> && git push origin phase3`), redeploy, and ask Team 2 to rerun their suite.

---

## 5. Materials

### 5.1 Already in the repo

| File | Use |
|---|---|
| `docs/openapi.yaml` | **Single source of truth** for paths, fields, enums, status codes |
| `docs/phase2_report.pdf` | §3.1 requirements, §4.1 acceptance criteria, §5.2 examples, §6.2 Phase 4 milestone, §7.2 design decisions, §9 risks |
| `docs/decisions.md` | Pod decisions and their status. Add every Phase 4 answer here |
| `fixtures/sbom_25_components.json`, `fixtures/releases.json` | Shared, signed off |
| `spikes/dependency_track/RESULTS.md`, `expected.json`, `spike.py` | DT findings; the five candidate CVEs; `replacement_sbom()` that builds a patched SBOM |

### 5.2 Needed before AC-04 can be automated (**REQUIRED**, human-verified, pod-shared)

| File (proposed) | Contents |
|---|---|
| `fixtures/sbom_patched.json` | Second SBOM with fixed versions (werkzeug 2.2.3, flask 2.2.5, requests 2.31.0; pyyaml dropped; tomli 2.0.1 added), as in the spike's `replacement_sbom()` |
| `fixtures/vulnerabilities.json` | `VulnerabilityFixture` records: `{cve_id, affected_purls}` for the seeded CVEs, loaded through `PUT /api/v1/test/vulnerability-source` |
| `fixtures/cve_dataset.json` | Seeded releases for AC-04: which release gets which SBOM, and support-end dates so some affected releases are **supported** and some **unsupported** at the reference clock |
| `fixtures/ground_truth.json` | For each test CVE: expected `supported` and `unsupported` release keys and matched purls. Include one **known CVE with no matches** (CVE-2019-11324) and one **unknown CVE** (CVE-2099-0001) for AC-05 |

> **Rule:** Claude Code may generate the *structure* of these files and draft candidate values from the spike, but **must not decide the expected results.** The spike's five CVEs are candidates checked against OSV on Oct 17, 2026, not pod ground truth. A team member checks every expected value, Team 2 signs off, and the date is recorded in `docs/decisions.md` **before** the AC-04 tests are treated as authoritative. If these files are missing, stop and ask.

### 5.3 Environment

- Deployment: GCE `e2-medium` (4 GB), API on 8080, tester on 8081. **Dependency-Track will not fit**; if the pod keeps DT, a human must upgrade the VM to ≥ 8 GB first.
- Secrets: none needed unless DT is used (then a DT API key in the host `.env` only).

---

## 6. Phase 4 scope: what to build

**Capability (report §6.2):** vulnerability querying with fault injection, and incident deadline tracking.

### 6.1 Vulnerability source (design)

Put matching behind one interface so the pod's DT decision doesn't change the rest of the code:

```python
class VulnerabilitySource(Protocol):
    def affected_purls(self, cve_id: str) -> frozenset[str] | None: ...
        # None  → CVE unknown to the source
        # raises SourceUnavailable → source unreachable
```

- **`FixtureSource` (required).** Backed by a SQLite table that `PUT /api/v1/test/vulnerability-source` fills. It has a `mode` of `available` or `unreachable`. This is what every graded test uses.
- **Production source (decide with the team before building).** If the pod accepts the spike's recommendation, this is a local table loaded from a saved OSV snapshot. If the pod keeps DT, write a `DependencyTrackSource` that waits for DT's processing token, needs the NVD mirror, and has SBOMs uploaded without `cpe` fields (a CPE caused a false positive in the spike). **Don't build either until a team member confirms.** Select the source by environment variable (for example `VULN_SOURCE=fixture|osv_snapshot|dependency_track`).

### 6.2 Endpoints to implement (exact paths from `openapi.yaml`)

| Method & path | Purpose | Reqs |
|---|---|---|
| `GET /api/v1/vulnerabilities/{cveId}/affected-releases` | Affected releases grouped by current support status → `200 AffectedReleaseResult`; `404 CVE_UNKNOWN`; `503 VULNERABILITY_SOURCE_UNREACHABLE` | REQ-03, REQ-04 |
| `PUT /api/v1/test/vulnerability-source` | Test only: `{mode, records}` → `200`. Gated like the other test endpoints | AC-04, AC-05 |
| `POST /api/v1/incidents` | Open a case → `201 Incident`; `400` invalid | REQ-05, REQ-06, REQ-08 |
| `GET /api/v1/incidents/{incidentId}` | Case with computed deadlines → `200`; `404` | REQ-05, REQ-06 |
| `PATCH /api/v1/incidents/{incidentId}` | Record `fix_available_at` → `200 Incident`; `400`; `404` | REQ-06, REQ-08 |
| `POST /api/v1/incidents/{incidentId}/submissions` | Record `{stage, submitted_at}` → `201 Incident`; `400`; `404` | REQ-06, REQ-08 |

Also: `POST /api/v1/test/reset` must now also clear incidents, submissions and the vulnerability-source table, and restore the source to its default state (§10 Q8). Extend `/health` to report the source mode, and for a real source, whether it's reachable.

### 6.3 CVE query behavior (REQ-03, REQ-04)

1. Validate the `cveId` format `^CVE-[0-9]{4}-[0-9]+$` (invalid format → see §10 Q6).
2. **Check reachability first.** If the source is unreachable → `503 VULNERABILITY_SOURCE_UNREACHABLE` (never an empty list, never 404), and do it within AC-05's 15 s, so real sources need a timeout.
3. If the CVE is unknown → `404 CVE_UNKNOWN`.
4. Otherwise, a release is affected if **any stored component's `purl` matches an affected purl** (matching rule: §10 Q7). Components without a purl can't match.
5. Group by support status **at the clock's current time** (same rule as REQ-01). Each entry lists `matched_components`.
6. A known CVE affecting nothing → `200` with empty `supported` and `unsupported` arrays.
7. Sort releases deterministically (for example by product, then version, then release_id) and components by name, then version.
8. Read-only: no audit entry.

### 6.4 Incident and deadline behavior (REQ-05, REQ-06)

**Create:** body `IncidentCreate` (`cve_id` optional/nullable, `awareness_at`, `classification` ∈ {mandatory, voluntary}, `rationale` non-blank). `created_by` comes from `X-User-Id`. Write `INCIDENT_CREATED` to the audit log in the same transaction.

**Store timestamps only.** Store `awareness_at`, `fix_available_at` and one row per submission. **Never store `deadline_at` or `status`**; compute both on every read. Drop `timer_id` from the Phase 2 data model.

**Deadline rules** (mandatory cases):

| Stage | `deadline_at` |
|---|---|
| `early_warning` | `awareness_at + 24 h` |
| `vulnerability_notification` | `awareness_at + 72 h` |
| `final_report` | `fix_available_at + 14 days` if recorded, else `null` |

**Status rules**, where `now` is the clock time and every comparison is a timezone-aware UTC `datetime`:

| Condition | `status` |
|---|---|
| Voluntary case, or `final_report` with no `fix_available_at` | `not_applicable` (`deadline_at: null`) |
| Submitted and `submitted_at ≤ deadline_at` | `met` |
| Submitted and `submitted_at > deadline_at` | `overdue` (proposal, §10 Q2) |
| Not submitted and `now ≤ deadline_at` | `pending` |
| Not submitted and `now > deadline_at` | `overdue` |

**Boundary semantics (AC-07, 0 s tolerance):** a submission **exactly at** the deadline is `met`. At `now == deadline_at` an unsubmitted stage is still `pending`, and one second later it is `overdue`. Use `timedelta(hours=24)`, `timedelta(hours=72)` and `timedelta(days=14)`. Never use local time or calendar libraries.

**PATCH fix_available_at:** sets the final-report deadline; audit `FIX_AVAILABLE_RECORDED`. **Submissions:** audit `SUBMISSION_RECORDED` with the stage. Edge cases are in §10 Q3–Q5; ask before choosing.

### 6.5 Data model additions

```
incidents(incident_id PK, cve_id NULL, awareness_at, created_by, classification, rationale,
          fix_available_at NULL, created_at)
submissions(incident_id FK, stage, submitted_at, recorded_by, recorded_at,
            PRIMARY KEY(incident_id, stage))     -- uniqueness depends on §10 Q3
vulnerability_fixture(cve_id, purl)               -- test source records
vulnerability_source_state(mode)                  -- 'available' | 'unreachable'
```

Add a migration for existing databases, as was done for `releases.sbom_stored_at`.

### 6.6 Acceptance criteria to automate

- **AC-04 (REQ-03):** Load `cve_dataset.json` and `vulnerabilities.json`, query the five test CVEs. Pass if each query finishes in ≤ 10 s and matches `ground_truth.json` with 100% recall, 100% precision, and correct supported/unsupported grouping.
- **AC-05 (REQ-04):** Query a known CVE with no matches (→ 200, empty arrays), an unknown CVE (→ 404 `CVE_UNKNOWN`), and a valid CVE with the source set to `unreachable` (→ 503 `VULNERABILITY_SOURCE_UNREACHABLE`). The errors must arrive within 15 s.
- **AC-06 (REQ-05):** Valid mandatory and voluntary cases are stored with user, classification and UTC awareness time (±2 s), and the rationale is intact. Missing rationale or invalid classification → 400 with nothing stored.
- **AC-07 (REQ-06):** Fixed awareness and fix-available times with the injected clock. Check the initial deadlines exactly. Record the early warning **exactly at** +24 h → `met`. Advance the clock to **72 h + 1 s** with no notification → `overdue`. Record the final report **13 days** after the fix → `met`.

Add **unit tests for the deadline math** covering before, at and after each deadline; month and year rollover (for example awareness `2026-12-31T23:30:00Z`); fractional seconds; offset inputs normalized to UTC; and a voluntary case. Add every new AC to `tester/checks.py` as required checks, and to the harness `/test/run`. A team member reviews the deadline code and its tests; AI-written tests alone don't count (report Q8.2).

### 6.7 Demonstration of completion (report §6.2)

Using the test clock, open a mandatory incident and show the computed 24 h and 72 h deadlines. Query a CVE and get the affected releases grouped by support status. Show 503 when the source is set to unreachable. AC-04 to AC-07 should pass in CI and in the tester against our live URL.

### 6.8 Out of scope for Phase 4 (Phase 5)

`PUT .../report-data/{stage}`, `GET .../reports/{stage}`, `missing_fields` (REQ-07, AC-08); the full AC-09 and AC-10 automation. Do write audit entries for every new Phase 4 change now.

---

## 7. Rules the implementation must follow

All Phase 3 rules still apply: the contract is law, the error shape is `{"error": {"code", "message"}}`, invalid input is 400 (never 422), there is one injectable clock, support status is never stored, `X-User-Id` is required on POST/PUT/PATCH (test endpoints exempt), uploads are atomic, the audit log is append-only and written in the same transaction, test endpoints are gated, and no secrets go in the repo. New for Phase 4:

1. **Deadlines and statuses are computed, never stored.** No timers, schedulers or background jobs.
2. **Reachability before existence.** An outage must never look like "CVE unknown" or "nothing affected."
3. **Never return an empty affected-release list on failure.** Empty arrays mean "known CVE, nothing affected" only.
4. **All timestamps through one parser and one formatter** (§4 item 3). Inputs may carry offsets; outputs are always UTC `Z`.
5. **No legal judgment in code.** Never infer awareness or classification, and never decide reportability.
6. **Every state change is audited**: incident created, fix recorded, submission recorded.
7. **Ground truth is human-verified** (§5.2).

---

## 8. Operations and observability (deferred from Phase 3, report §7.3)

- **Structured JSON request logs:** one line per request with request ID, `X-User-Id`, method, path, status, latency in ms, the clock value (and whether it's overridden), and any source error. Keep uvicorn's access log off or quiet so lines aren't duplicated.
- **Signals to make visible (report §7.3):** per-endpoint error rates, p95 latency against AC-04's 10 s limit, how often the vulnerability source is unreachable (503 rate), SBOM rejections by reason, and overdue-deadline counts. The request ID and clock value in each log line are what report §7.4 relies on to replay a failing test.
- **Nightly backup** with SQLite's online backup API, keeping 7 copies (a cron entry in `deploy/`).
- **Uptime monitor** polling `/health` (a human sets this up, for example UptimeRobot).
- Tag each deployed milestone (`phase4`) and redeploy with `deploy/gcp.sh update`.

---

## 9. Cross-team testing (graded from Phase 4)

- Before the milestone, run our tester against Team 2's base URL and have Team 2 run their suite against ours, at least once each way. Coordinate first: every run calls `/test/reset` and wipes the target's data.
- Record per direction: date, run/passed counts, main problem and owner, and coverage (component: operations exercised; system model: CVE-query outcomes and deadline states covered; code: our `coverage` % when they test us).
- Keep a short log in `docs/test-reports/` for each cross-team run.

---

## 10. Open questions: ask before deciding

Both teams must behave the same way, so don't pick an answer silently. Propose, ask a team member, and record the outcome in `docs/decisions.md`.

1. **Timestamp format amendment (Section 5).** Accept `Z` or numeric offsets on input, always return UTC `Z`, microsecond precision. *Proposal: yes (already implemented in §4).*
2. **Late submissions.** The enum has no `late`. *Proposal:* a submission after its deadline stays `overdue`, with `submitted_at` set. Phase 2 diagrams show `Late`, and the grader flagged the mismatch, so the diagrams must be updated either way.
3. **Duplicate submission for the same stage:** 409, replace, or keep the first? Submission for a `not_applicable` stage (voluntary case, or final report before a fix): 400? *Proposal: 400 for not_applicable; 409 for a duplicate.* The contract lists only 201/400/404, so a 409 needs a contract change; otherwise use 400.
4. **Timestamp sanity.** `submitted_at` or `fix_available_at` before `awareness_at`: reject with 400? `awareness_at` or `submitted_at` later than the clock's now? *Proposal:* reject anything before `awareness_at`; allow future times (the test clock can be anywhere).
5. **PATCH `fix_available_at` twice**, or on a voluntary case: overwrite, or reject? *Proposal:* allow overwrite (audited) on mandatory cases; on voluntary cases store it but deadlines stay `not_applicable`.
6. **Malformed CVE ID** (`CVE-26-1`, `abc`): the contract gives no 400 for this operation. *Proposal: 400 `INVALID_REQUEST`*, added to the contract.
7. **Matching key.** Exact `purl` string equality, as the fixture schema `affected_purls` suggests? Normalize case and qualifiers (`?package-id=…`)? What about components with no purl? *Proposal:* exact match after stripping qualifiers and subpaths; no purl → not matchable, and flag it in the logs.
8. **State after reset.** *Proposal:* source mode `available` with **zero records**, so every CVE is unknown until a test loads records.
9. **`cve_id` on an incident:** must it be known to the source? *Proposal:* format check only.
10. **Vulnerability matching for production:** local OSV snapshot (spike recommendation) or Dependency-Track (Phase 1/2 choice)? Both teams chose DT, and report §2.2 names DT as the only CVE source, so switching needs pod agreement **and** instructor sign-off.
11. **Deadline alerts:** confirm with the pod that Phase 4 has no push alerts (status is shown on read), and update the shared diagrams to match.

---

## 11. Spec housekeeping (human tasks, needed to "keep the common specification up to date")

Fix the Phase 2 grader's comments, and the report inconsistencies found in review, that affect shared material:
- REQ-06 text lists `pending`, `met` and `overdue` only; add `not_applicable`, which the contract already uses;
- report §1.3 says `awareness_time`; the contract and REQ-05 use `awareness_at`;
- report §4.3 says AC-05 stops the mock service; change it to `PUT /api/v1/test/vulnerability-source` with `mode: unreachable`;
- remove deadline alerts and escalations from the §2.1 boundary diagram and the §3.2 behavior model, or agree a reminder mechanism with the pod;
- if the pod switches from Dependency-Track, update the §2.2 limits and the §2.1 diagram (needs instructor sign-off);
- replace the §6.4 scope-reduction sentence with "any scope change needs both teams and instructor sign-off";
- deadline status names in diagrams vs API (`Waiting`/`Late` vs `pending`/`met`/`overdue`/`not_applicable`);
- remove the timer service from the 2.1, 3.1 and 7.1 diagrams;
- align 7.1 routes with the contract;
- state which report fields are required per stage (needed for Phase 5 anyway);
- give hour estimates as ranges, name risk owners, and number references in order of first use.

Apply the §10 answers to `docs/openapi.yaml` in a single commit agreed with Team 2.

---

## 12. Risks for Phase 4

| Risk | Effect | Mitigation |
|---|---|---|
| Ground truth not agreed in time | AC-04 can't be graded fairly; teams disagree | Draft from the spike's candidates now; get human check + Team 2 sign-off early |
| Teams answer §10 differently | Cross-team failures that aren't bugs, now graded | Settle Q1–Q8 with Team 2 before building the incident endpoints |
| Off-by-one at deadline boundaries | Wrong legal deadline; AC-07 fails | `≤` for met; unit tests at, ±1 s, rollover; human review |
| Purl mismatch (qualifiers, case) | Missed affected releases: false "all clear" | Agreed matching rule (Q7); recall test on the shared dataset |
| DT kept but VM too small | Production source can't run | Fixture source for all tests; VM upgrade only if DT is confirmed |

---

## 13. Repository layout additions

```
app/
├── clock.py                     # + parse_utc / format_utc shared by all routes (§4.3)
├── routers/
│   ├── vulnerabilities.py       # GET /vulnerabilities/{cveId}/affected-releases
│   ├── incidents.py             # POST/GET/PATCH /incidents, POST /submissions
│   └── test_support.py          # + PUT /test/vulnerability-source; reset clears new tables
└── services/
    ├── vulnerability_source.py  # Protocol, FixtureSource, SourceUnavailable (+ prod source later)
    ├── matching.py              # purl matching + grouping by support status
    ├── incidents.py
    └── deadlines.py             # pure functions: deadline_at(), status() — no I/O
fixtures/
├── sbom_patched.json            # human-verified, pod-shared
├── vulnerabilities.json
├── cve_dataset.json
└── ground_truth.json
tests/
├── unit/test_deadlines.py       # boundaries, rollovers, offsets, voluntary
├── acceptance/test_cve_query.py # AC-04, AC-05
├── acceptance/test_incidents.py # AC-06, AC-07
└── tester/                      # tester checks for AC-04..AC-07
scripts/
├── metrics.py                   # writes docs/metrics.md (§0.1)
└── post_deploy_check.sh         # deployment tests (§16.2)
docs/
├── goals.md                     # goals + measures, confirmed by a human (§0.2)
├── metrics.md                   # generated status vs goals
├── issues.md                    # only if GitHub issues aren't used
├── PHASE3_HANDOFF.md
└── test-reports/                # one file per cross-team run and per deploy
```

Keep `deadlines.py` as **pure functions** (inputs: stored timestamps and `now`; output: `deadline_at` and `status`) so the logic is easy to test and review.

---

## 14. How to work (instructions for Claude Code)

### 14.1 Order of work

Each line is one or more inner-loop steps (§0.3) with a green CI build in between:

1. Goal audit (§0.1): `docs/goals.md`, `scripts/metrics.py`, `docs/metrics.md`, issues for every task.
2. CI stage A–B (§15) so every later step is gated.
3. §4 carry-over, items 1–8, one commit each.
4. Shared time parsing and formatting.
5. `deadlines.py` pure functions, with the unit tests written first.
6. Incident endpoints (create, get, patch, submissions) with audit writes → AC-06, AC-07.
7. `/test/vulnerability-source` + `FixtureSource` → CVE query → AC-05, then AC-04 (only once `ground_truth.json` is human-verified).
8. Reset and health updates.
9. Tester checks + harness `/test/run` for AC-04 to AC-07.
10. CI stages C–F (§15).
11. JSON logging and metrics (§8).
12. Deploy with post-deploy checks (§16) → cross-team runs (§9) → tag `phase4`.

### 14.2 Rules for working

1. **Read first:** this file, `docs/openapi.yaml` (incidents, vulnerabilities and test sections), `docs/decisions.md`, and `spikes/dependency_track/RESULTS.md`. Summarize back the Phase 4 endpoints, the §6.4 deadline rules, the §10 questions, and the goals in §0.2 before writing code.
2. **Contract check:** the generated OpenAPI must match `docs/openapi.yaml`, with no missing and no extra status codes.
3. **Ask, don't assume:** anything in §10, any fixture's expected values, any contract change, the production vulnerability source, and anything that needs credentials. Stop and ask a team member.
4. **Humans own correctness** for the deadline logic and the ground truth. Mark deadline commits `needs-human-review` and don't merge them without a team member's approval.

### 14.3 Self-review checklist (step 7 of the inner loop)

- No `datetime.now()` outside the clock; every timestamp goes through the shared parser and formatter.
- No stored `deadline_at`, `status` or `support_status`.
- Every state change writes its audit entry in the same transaction.
- Invalid input returns 400 with the shared error shape (never 422); the error message names the problem.
- No path, field, enum or status code differs from the contract.
- Failures never return empty results (REQ-04).
- New code has tests, and coverage didn't drop.
- No secrets, no test endpoints enabled by default.

### 14.4 Definition of done for Phase 4

- AC-04 to AC-07 green in CI and in the tester against our live URL.
- All goals in `docs/goals.md` met or explained in `docs/metrics.md`.
- At least one cross-team run in each direction recorded in `docs/test-reports/`.
- `docs/decisions.md` and the README's Known limitations updated.
- The deployed commit tagged `phase4` and verified by the post-deploy checks.

---

## 15. CI pipeline: build it in stages

Extend `.github/workflows/ci.yml` **one stage at a time**. For each stage: add it, push, confirm it's green, then confirm it can actually fail. Do that locally (for example, run the stage's command against a deliberately broken input) or on a throwaway branch that is never merged. A gate that has never failed hasn't been tested. Use separate jobs linked with `needs:` so a failure shows which gate broke.

| Stage | Job | What it runs | Gate |
|---|---|---|---|
| A | `static` | `ruff check`, `ruff format --check`, `mypy` (exists today) | Any error fails |
| B | `unit` | `pytest tests/unit --cov=app --cov-report=xml`; upload the coverage report | Fails below the G5 threshold |
| C | `acceptance` | `pytest tests/acceptance tests/contract` (AC-01 to AC-07 and the contract check) | Any failure |
| D | `tester` | `pytest tests/tester tests/test_harness.py`: the tester's checks against the app in-process | Any required check failing |
| E | `docker-build` | Build the system and tester images, tagged with the commit SHA (`GIT_SHA` build arg) | Build failure |
| F | `container-smoke` | `docker compose up -d` with test endpoints on; wait for `/health`; run `scripts/smoke.sh localhost:8080` and the tester against `http://localhost:8080`; register a release, upload an SBOM and open a mandatory incident, `docker compose restart api`, then confirm the release, components, incident, computed deadlines and audit entries are unchanged (AC-10 covers REQ-05 and REQ-06 too); `docker compose down -v` | Any check failing, or `/health` not ready within 60 s |
| G | `deploy` (optional) | Only on a `phase*` tag or a manual `workflow_dispatch`. Needs GCP credentials stored as GitHub secrets, which **a human must create** (prefer Workload Identity Federation over a key file). Until then, deploy by hand with `deploy/gcp.sh update` | Runs only after A–F pass |
| H | `post-deploy` | `scripts/post_deploy_check.sh <base_url> <sha>` against the live URL (§16) | Failure triggers rollback |

Stages A–F run on every push and pull request. Stages G–H run only on deploys.

---

## 16. Deployment and deployment tests

### 16.1 Make the deployment checkable

- Pass the commit SHA into the image (`GIT_SHA` build arg → environment variable) and include it in `GET /health`, as `{"status": "ok", "commit": "...", "source_mode": "..."}`. `/health` is our own endpoint, not part of the contract, so this doesn't affect Team 2.
- `deploy/gcp.sh update` should build from a **tag or explicit commit**, not just "latest `main`", then run the post-deploy checks automatically and print `PASS` or `FAIL`.
- Add `deploy/gcp.sh rollback <tag>`: check out the previous tag on the VM, rebuild, and rerun the post-deploy checks.

### 16.2 `scripts/post_deploy_check.sh <base_url> <expected_sha> [--full]`

Default mode is **non-destructive**, so it's safe to run at any time:

1. `GET /health` returns 200 within 60 s of the deploy, `commit` equals the expected SHA, and the database is writable.
2. `GET /openapi.json` lists every Phase 4 path from `docs/openapi.yaml`.
3. Test endpoints are on or off as expected for this environment (`ENABLE_TEST_ENDPOINTS`).
4. A malformed request (for example `POST /api/v1/releases` with `{}`) returns 400 with the shared error shape, which proves the 400-not-422 handler is live.
5. `GET /api/v1/vulnerabilities/CVE-2099-0001/affected-releases` returns a contract-valid response (404 `CVE_UNKNOWN` or 503) within 15 s.

`--full` mode is **destructive**: it resets the target. Use it only on the evaluation deployment, and only after warning Team 2 and checking nobody else is testing:

6. Run the tester against the live URL; every required check, AC-01 to AC-07, must pass.
7. Run `scripts/smoke.sh`.
8. Persistence: register a release, restart the container on the VM, and confirm the release and its audit entry survive.

If any check fails, the deploy counts as failed. Roll back with `deploy/gcp.sh rollback <previous-tag>`, open an issue with the failing check's output, and fix it through the inner loop. Never "fix forward" directly on the VM.

### 16.3 Before every deploy (deploy checklist)

- CI stages A–F are green on the exact commit being deployed.
- `docs/metrics.md` regenerated; no goal regressed.
- Team 2 warned if `--full` will run.
- The previous tag is known, for rollback.
- After deploy: post-deploy checks pass, the commit is tagged, and the result is recorded in `docs/test-reports/`.
