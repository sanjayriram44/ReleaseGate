# Phase 4 pod questions: Team 6 to Team 2

Sent 2026-10-30 by Team 6 (ReleaseGate). Please reply by: ____

## Why we're asking

Both teams build the same shared specification, and from Phase 4 each team's suite runs against
the other's service for a grade. For Phase 4 (CVE query with fault injection, incident deadlines)
the contract in `docs/openapi.yaml` leaves the questions below open. If we answer them
differently, the cross-team runs will fail on differences that aren't bugs.

For each question, please reply **agree** or give a **counter-proposal**. We record every answer,
with its date, in `docs/decisions.md`. Answers that change the contract go into
`docs/openapi.yaml` in a single commit that both teams approve.

We haven't built the incident endpoints or the CVE query yet. We're waiting on these answers.

## Summary

| # | Topic | Our proposal | Contract change? | Blocks |
|---|---|---|---|---|
| Q1 | Timestamp format | Accept `Z` or a numeric offset; always return UTC `Z` | Section 5 wording | Sign-off only (already built) |
| Q2 | Late submission | Stays `overdue`, with `submitted_at` set | No (yes if you prefer a `late` status) | Deadline status |
| Q3 | Duplicate or not-applicable submission | Duplicate: 409. Not applicable: 400 | Yes, for 409 | Submissions |
| Q4 | Timestamps before awareness | 400. Future times allowed | No | PATCH, submissions |
| Q5 | Fix time set twice, or on a voluntary case | Overwrite (audited). Voluntary: store it, deadlines stay `not_applicable` | No | PATCH |
| Q6 | Malformed CVE ID | 400 `INVALID_REQUEST` | Yes, adds 400 | CVE query |
| Q7 | Purl matching | Exact match after dropping qualifiers and subpath | No | CVE query |
| Q8 | Vulnerability source after reset | `available`, zero records; each PUT replaces all records | No | Test endpoints |
| Q9 | `cve_id` on an incident | Format check only | No | Create incident |
| Q10 | Production vulnerability source | Local OSV snapshot (needs instructor sign-off) | Report §2.2, not the API | Production only |
| Q11 | Deadline alerts | None in Phase 4; status shown on every read | Report diagrams only | Diagrams |
| Q12 | Deadline boundaries | Submitted exactly at the deadline: `met`. Unsubmitted at the deadline: `pending`; 1 s later: `overdue` | No | AC-07 |
| Q13 | Order of affected releases | Tests compare as sets; both teams also sort the same way | No | AC-04 tests |
| F | AC-04 fixtures | We draft them from our spike; both teams check the expected values | New shared fixtures | AC-04 |

## Questions

### Q1. Timestamp format (Section 5 amendment)

**Question:** Which timestamp forms do the timestamp fields accept, and how are they returned?

**Why it matters:** In Phase 3, your suite sent offsets such as `+02:00` and fractional seconds to
`PUT /api/v1/test/clock`, and we rejected them. Phase 4 adds more timestamp inputs:
`awareness_at`, `fix_available_at` and `submitted_at`.

**Our proposal:**
- Accept `Z` or a numeric offset up to ±23:59 (`+02:00`, `-05:30`, `-00:00`), and convert it to UTC.
- Reject a timestamp with no zone (400).
- Keep fractional seconds, truncating anything beyond microseconds.
- Always return UTC ending in `Z`: whole seconds when there's no fraction, otherwise six digits
  (`2026-11-01T23:59:59.100000Z`).

This is live on our service as of 2026-10-30.

**Contract change:** reword Section 5 and the harness's "UTC, trailing Z" description to match.

**Team 2 answer:** ____

### Q2. Submission after its deadline

**Question:** What is a stage's status once its report was submitted after the deadline?

**Why it matters:** The status enum is `pending`, `met`, `overdue` and `not_applicable`, with no
`late`. The Phase 2 diagrams still show `Late`, and the grader flagged that mismatch.

**Our proposal:** It stays `overdue`, and `submitted_at` shows when it was sent. We update the
diagrams either way.

**Alternative:** Add `late` to the enum. That's a contract change.

**Team 2 answer:** ____

### Q3. Duplicate submissions, and submissions for a stage that doesn't apply

**Question:** What happens when `POST /api/v1/incidents/{id}/submissions` is sent:
1. a second time for the same stage?
2. for a `not_applicable` stage: any stage of a voluntary case, or `final_report` before
   `fix_available_at` is set?

**Our proposal:**
1. 409 Conflict, and the first submission stays.
2. 400 `INVALID_REQUEST`.

**Contract change:** The operation lists only 201, 400 and 404, so 409 has to be added. If you'd
rather not change the contract, we'd use 400 for duplicates too.

**Alternatives for duplicates:** replace the earlier submission (audited), or silently keep the
first.

**Team 2 answer:** ____

### Q4. Timestamp sanity checks

**Question:** Should we reject `submitted_at` or `fix_available_at` earlier than the incident's
`awareness_at`? And should we reject times later than the clock's current time?

**Our proposal:** Reject anything earlier than `awareness_at` with 400. Allow times later than
the clock's now, because the test clock can be set anywhere and tests move it forward and back.

**Team 2 answer:** ____

### Q5. Setting `fix_available_at` more than once, or on a voluntary case

**Our proposal:**
- **Mandatory case:** a second `PATCH` overwrites the value, the final-report deadline moves to
  the new time + 14 days, and each change is written to the audit log.
- **Voluntary case:** store the value, but every deadline stays `not_applicable`.

**Team 2 answer:** ____

### Q6. Malformed CVE ID in the query

**Question:** What does `GET /api/v1/vulnerabilities/{cveId}/affected-releases` return for an ID
that doesn't match `^CVE-[0-9]{4}-[0-9]+$`, such as `CVE-26-1` or `abc`?

**Why it matters:** The path parameter already declares that pattern, but the operation lists only
200, 404 and 503.

**Our proposal:** 400 `INVALID_REQUEST`, adding 400 to the operation.

**Alternative:** 404 `CVE_UNKNOWN`, with no contract change.

**Team 2 answer:** ____

### Q7. How a component's purl matches an affected purl

**Question:** When does a stored component match an entry in a fixture's `affected_purls`?

**Why it matters:** In the shared 25-component SBOM, the `purl` fields have no qualifiers; only
the `bom-ref` values carry `?package-id=…`. So this rule doesn't change AC-04, but it decides what
happens with other SBOMs, where a qualifier would otherwise hide a real match.

**Our proposal:**
- Compare the purls exactly, after removing qualifiers (`?…`) and subpath (`#…`) from both sides.
  So `pkg:pypi/requests@2.28.2?package-id=abc` matches `pkg:pypi/requests@2.28.2`.
- No other normalization: case is significant.
- A component without a purl never matches. We log it so it's visible.
- `affected_purls` lists exact versions, not ranges: a fixture lists every affected version it
  wants matched.

**Team 2 answer:** ____

### Q8. Vulnerability source after a reset, and what a PUT does

**Our proposal:**
- After `POST /api/v1/test/reset`, the source is `available` with zero records, so every CVE is
  `CVE_UNKNOWN` until a test loads records.
- `PUT /api/v1/test/vulnerability-source` replaces all records. If `records` is omitted, the
  record set is empty.
- In `unreachable` mode the records are kept, but every query returns 503
  `VULNERABILITY_SOURCE_UNREACHABLE`, checked before anything else.

**Team 2 answer:** ____

### Q9. `cve_id` on an incident

**Question:** If `POST /api/v1/incidents` includes a `cve_id`, must the vulnerability source know
that CVE?

**Our proposal:** No. Check the format only (`^CVE-[0-9]{4}-[0-9]+$`, else 400). An incident can be
opened before any source knows the CVE.

**Team 2 answer:** ____

### Q10. Production vulnerability source

**Question:** Where do CVE matches come from outside tests?

**Background:** Both teams chose Dependency-Track in Phase 2, and report §2.2 names it as the only
CVE source. Our spike found that it needs about 8 GB of RAM and the NVD mirror, results arrive only
after background analysis, and a CPE in an SBOM caused a false positive. Our VM has 4 GB.

**Our proposal:** Match locally against a saved OSV snapshot. That changes report §2.2 and the §2.1
diagram, so it needs both teams and the instructor to sign off.

**Note:** Graded tests use the fixture source (`PUT /api/v1/test/vulnerability-source`) either
way, so this doesn't affect cross-team results.

**Team 2 answer:** ____

### Q11. Deadline alerts

**Our proposal:** No push alerts in Phase 4. Every `GET /api/v1/incidents/{id}` shows each stage's
status, including `overdue`. REQ-06 doesn't require alerts.

**Change needed:** remove alerts and escalations from the §2.1 boundary diagram and the §3.2
behavior model, or agree on a reminder mechanism for later.

**Team 2 answer:** ____

### Q12. Deadline boundaries (AC-07, 0 s tolerance)

**Our proposal:**
- **Deadlines:** `early_warning` = `awareness_at` + 24 h; `vulnerability_notification` =
  `awareness_at` + 72 h; `final_report` = `fix_available_at` + 14 days (`null` until a fix time
  is recorded). All are exact UTC durations, with no calendar or local-time arithmetic.
- **Submitted:** `submitted_at` ≤ deadline is `met`, so a submission exactly at the deadline is
  `met`.
- **Not submitted:** at `now` = deadline it's still `pending`; one second later it's `overdue`.
- **Storage:** deadlines and statuses are computed on every read from the stored times and the
  test clock, never stored.

**Team 2 answer:** ____

### Q13. Order of affected releases

**Question:** May cross-team tests depend on the order of `supported`, `unsupported` and
`matched_components`?

**Our proposal:** Tests compare them as sets. Both teams also sort releases by product, then
version, then `release_id`, and components by name, then version, so responses are easy to diff.

**Team 2 answer:** ____

### F. AC-04 shared fixtures

AC-04 needs four new shared files:
- `fixtures/sbom_patched.json`
- `fixtures/vulnerabilities.json`
- `fixtures/cve_dataset.json`
- `fixtures/ground_truth.json`

**Our proposal:** We draft them from our Dependency-Track spike. A person on each team checks every
expected value, and the sign-off date goes in `docs/decisions.md` before the AC-04 tests count.

The candidate CVEs, against the shared 25-component SBOM, were checked against OSV on 2026-10-17
and are not yet verified:

| CVE | Package (fixture version) | Fixed in |
|---|---|---|
| CVE-2023-25577 | werkzeug 2.2.2 | 2.2.3 |
| CVE-2023-32681 | requests 2.28.2 | 2.31.0 |
| CVE-2023-30861 | flask 2.2.2 | 2.2.5 |
| CVE-2023-23931 | cryptography 39.0.0 | 39.0.1 |
| CVE-2023-37920 | certifi 2022.12.7 | 2023.7.22 |

For AC-05 we'd also use:
- **CVE-2019-11324:** a known CVE that matches nothing (200, empty arrays).
- **CVE-2099-0001:** an unknown CVE (404 `CVE_UNKNOWN`).

The patched SBOM moves werkzeug to 2.2.3, flask to 2.2.5 and requests to 2.31.0, drops pyyaml, and
adds tomli 2.0.1. The dataset gives some affected releases a support end date after the reference
clock (`supported`) and some before it (`unsupported`).

**Team 2 answer (who checks, and by when):** ____

## Logistics

- **Every run resets the target's data:** `/test/setup` and the tester call
  `POST /api/v1/test/reset`. Please tell us before running your suite against our service, and
  we'll do the same.
- **Ready for a rerun:** our Phase 3 timestamp fix is live, and we'd welcome a rerun of your suite
  once our redeploy is done. Our system is at `http://136.116.160.182:8080` and our tester at
  `http://136.116.160.182:8081`.
- **Recording results:** we log each cross-team run in `docs/test-reports/`: date, passed and run
  counts, the main problem and its owner.
