# Full live run, 2026-11-18 (second run of the day: `main`; the first is `2026-11-18-deploy-full-c188b54.md`)

**Commit:** `271da8e0e973d0255e0c060a953e9704a6b209eb`
**Target:** `http://136.116.160.182:8080`
**Mode:** full (destructive: tester run, smoke test and an AC-10 restart via `docker compose restart api`
on the VM, run with `deploy/gcp.sh full` and approved by Daksh Agarwal; the demo data was re-seeded afterwards)
**Result:** 97/97 passed (required tester checks, AC-01..AC-09 and the contract, plus the run steps; 22/22 informational)
**AC-10:** PASS
**Latency:** slowest AC-04 query 0.03 s; slowest AC-05 error 0.10 s (limits 10 s and 15 s)

| Step | Result | Detail |
|---|---|---|
| health | PASS | ok, commit 271da8e0e973 |
| openapi | PASS | all 21 built contract operations listed |
| test-endpoints | PASS | on (GET /test answered 200) |
| malformed-request | PASS | 400 INVALID_REQUEST: product is required |
| cve-query | PASS | 404 CVE_UNKNOWN in 0.08 s |
| tester | PASS | 89/89 required, 22/22 informational |
| smoke | PASS | ALL CHECKS PASSED |
| ac10-restart | PASS | state unchanged after restart (same clock, exact JSON) |
| reseed | PASS | demo data at real time: release rel-3dc5c83f, incident inc-73f73158 |

Checked afterwards (read-only): the api container's start time (22:34:13 UTC) falls inside the
run, so the AC-10 restart happened; both `/test` pages say AC-01..AC-09; the live demo incident's
notification report lists `user_mitigations` as missing, and the 5 audit entries carry real-time
timestamps; the read-only harness probes pass on both URLs.

**Live data afterwards:** ExampleGateway 1.0.0 (supported to 2027-12-31) with
`fixtures/sbom_25_components.json`, the records from `fixtures/vulnerabilities.json`, and one
mandatory incident for CVE-2023-25577 (awareness 2026-11-01T09:00:00Z) with early-warning report
data and notification report data that leaves out `user_mitigations`.

**Main problem / owner:** AC-08's expected values come from the draft `fixtures/report_cases.json`
and the Phase 5 behavior rests on proposed pod answers (P5-Q1..Q8), so a pass shows agreement
with our proposals only (owner: Daksh, with Team 2). The `phase5` tag still points at `c188b54`
(owner: Daksh, to move it to `271da8e`).
