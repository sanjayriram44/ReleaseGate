# Full live run, 2026-11-23

**Commit:** `2106a7692d8e2c3956b2f58b6af1796ba5250858`
**Target:** `http://136.116.160.182:8080`
**Mode:** full (destructive: tester run, smoke test and an AC-10 restart; the demo data was re-seeded afterwards)
**Result:** 97/97 passed (required tester checks, AC-01..AC-09 and the contract, plus the run steps; 22/22 informational)
**AC-10:** PASS
**Latency:** slowest AC-04 query 0.03 s; slowest AC-05 error 0.02 s (limits 10 s and 15 s)

| Step | Result | Detail |
|---|---|---|
| health | PASS | ok, commit 2106a7692d8e |
| openapi | PASS | all 20 built contract operations listed |
| test-endpoints | PASS | on (GET /test answered 200) |
| malformed-request | PASS | 400 INVALID_REQUEST: product is required |
| cve-query | PASS | 404 CVE_UNKNOWN in 0.16 s |
| tester | PASS | 89/89 required, 22/22 informational |
| smoke | PASS | ALL CHECKS PASSED |
| ac10-restart | PASS | state unchanged after restart (same clock, exact JSON) |
| reseed | PASS | demo data at real time: release rel-b01da244, incident inc-d36b0bd4 |

**Main problem / owner:** none. Run approved by Daksh Agarwal on 2026-11-22 (ET; the file is dated in UTC), on the spec v2 harness and contract 1.1.0 deploy (`2026-11-22-deploy.md`). Afterwards the live audit log holds the demo's 5 events, and the demo incident's `vulnerability_notification` report lists `user_mitigations` as missing. The `phase5` tag is still on `271da8e`; a person moves it to `2106a76` (owner: Daksh).
