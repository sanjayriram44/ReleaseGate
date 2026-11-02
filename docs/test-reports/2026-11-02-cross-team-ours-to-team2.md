# Cross-team run: our tester against Team 2's service, 2026-11-02

**Target:** `https://cra-phase3-api-456725640364.us-central1.run.app` (Team 2's deployed service)
**Runner:** our deployed tester (`http://136.116.160.182:8081`), run `run-747cc7d5d0`, 15.5 s, run
by Daksh Agarwal from the tester page. Tester commit `e8643407b5aed0fa69ff671d98a9e78ec7854225`
(tag `phase4`).
**Result:** 48/50 passed (required checks; informational 8/9)

The common interface works and the report is well formed. Every AC-01 to AC-07 check passed,
including all five AC-04 CVE cases, AC-05 (known-but-unaffected, unknown 404, malformed 400,
unreachable 503) and every deadline rule (Q2 decisions included). Slowest CVE query 0.06 s.

## Failures

| Check | Expected | Actual | Owner |
|---|---|---|---|
| contract: `GET /api/v1/audit-logs` returns the recorded events | 200, non-empty `events` | 404 `HTTP_ERROR` "Not Found" | Team 2 (endpoint in the contract, not deployed) |
| teardown: audit log empty after reset | 200, `events=[]` | 404 | Team 2 (same cause) |
| info: rejected incidents stored nothing (audit unchanged) | audit unchanged | could not read the audit log | Team 2 (same cause) |

One cause: Team 2's service has no `GET /api/v1/audit-logs` route (REQ-07). Unresolved; reported
to Team 2.

## Coverage

- **Code:** not measurable (black-box HTTP against Team 2's deployment).
- **Component:** every contract resource: releases, SBOM upload, components, audit log (404),
  CVE query, incidents, fix time, submissions, plus test reset, clock and vulnerability source.
- **System model:** all seven acceptance criteria, AC-01 to AC-07, plus contract and provisional
  (decision Q1–Q7) checks.

The run reset Team 2's data.
