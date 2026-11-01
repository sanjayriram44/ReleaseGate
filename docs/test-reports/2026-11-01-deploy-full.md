# Full live run, 2026-11-01

**Commit:** `68011ca48a4362ba71a7506a0ec821ff3dd5c4a1` (deployed earlier the same day; see
`2026-11-01-deploy.md`)
**Mode:** full (destructive: tester runs, smoke test and a container restart against
`http://136.116.160.182:8080`, approved by Daksh Agarwal; the live data was re-seeded afterwards)
**Result:** 52/52 passed (required checks, AC-01..AC-07 and the contract; 9/9 informational)
**Latency:** slowest AC-04 query 0.03 s; slowest AC-05 error 0.03 s (from a laptop over the
internet; limits 10 s and 15 s)

| Check | Result |
|---|---|
| Deployed tester (`POST :8081/api/v1/runs`, run `run-09da568061`) against the live system | pass: 52/52 required, 9/9 informational, 1.5 s. Per AC: AC-01 9/9, AC-02 5/5, AC-03 6/6, AC-04 6/6, AC-05 3/3, AC-06 5/5, AC-07 6/6, contract 8/8 |
| Autograder harness on the tester (`:8081`): `/test/setup` → `/test/run` → `/test/report` | pass, 61 checks, completed |
| Autograder harness on the system (`:8080`): `/test/setup` → `/test/run` → `/test/report` | pass, 61 checks, completed |
| Tester from a laptop over the internet (`scripts/container_smoke.py tester`) | pass: 52/52 required |
| `scripts/smoke.sh 136.116.160.182:8080` | all checks passed |
| Persistence: seed a release, SBOM and mandatory incident with a submission, `docker compose restart api` on the VM, compare (`scripts/container_smoke.py seed`/`verify`) | release, components, incident, computed deadlines and audit log unchanged |

**Live data afterwards:** reset, then ExampleGateway 1.0.0 (supported to 2027-12-31) with
`fixtures/sbom_25_components.json`, the vulnerability records from `fixtures/vulnerabilities.json`
(so `CVE-2023-25577` returns the release, matched on werkzeug 2.2.2) and one mandatory incident
for CVE-2023-25577 (awareness 2026-11-01T09:00:00Z). The clock is real time.

**Main problem / owner:** AC-04's expected values are still the draft ground truth (decision
Q7; owner: one checker per team). No cross-team run yet in either direction (owner: Daksh, with
Team 2).
