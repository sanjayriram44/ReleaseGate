# Autograder harness run against the live URLs, 2026-11-18

**Commit:** `c188b549dae52137e45717009d3c311aada6da67` (live `/health` before the run)
**Targets:** system `http://136.116.160.182:8080`, tester `http://136.116.160.182:8081`
**When:** 2026-11-18T21:29:51Z to 21:29:58Z, approved by Daksh Agarwal. Destructive: setup and run
reset the live data; the demo data was re-seeded right after (below).
**How:** driven like the course autograder, in this order on each URL: `GET /test`, `GET
/test/report?session_id=<never seen>`, `POST /test/setup` (the tester's with `{"target_url":
<system>}`), `POST /test/run {session_id}`, `GET /test/report?session_id=…`. Every response was
validated with `jsonschema` against the `/test` schemas in `docs/openapi.yaml`.
**Result:** 10/10 harness calls passed (5 per URL), both runs `pass`

| Service | Harness calls | Run result | Checks | Coverage | `target_url` |
|---|---|---|---|---|---|
| System `:8080` | 5/5 schema-valid (setup 201, unseen session 200) | pass | 89/89 required, 22/22 informational, 111 results | code 99.2, component 100, system 100 | null (runs against itself) |
| Tester `:8081` | 5/5 schema-valid (setup 201, unseen session 200) | pass | 89/89 required, 22/22 informational, 111 results | code 99.2, component 100, system 100 | `http://136.116.160.182:8080` |

Acceptance criteria exercised in each run: AC-01..AC-09 (AC-10 needs a restart; it passed live in
`2026-11-18-deploy-full-c188b54.md`). All 14 contract operations were called.

**Known gap:** the `/test` description strings still say "AC-01..AC-07" although the run
executes AC-01..AC-09; they change once the Phase 5 assignment text is in the repo
(`docs/issues.md`).

**Live data afterwards:** re-seeded with `scripts/post_deploy_full.py` `seed_demo` at real time:
ExampleGateway 1.0.0 with the 25-component SBOM and the fixture CVE records (`CVE-2023-25577`
returns it as supported), one mandatory incident for CVE-2023-25577 whose notification report
lists `user_mitigations` as missing; 5 audit entries stamped with the real clock.

**Main problem / owner:** none in the run. The checks rest on the proposed P5 answers and the
draft AC-04/AC-08 fixtures (owner: Daksh, with Team 2).
