# Dependency-Track spike: results

## Why this spike exists

The Phase 2 report commits Team 6 to this spike before the **Phase 3 milestone**
(§6.1):

- **§9.1, Risk 1 (highest):** "Dependency-Track matching, replacement, and fault
  behavior". The report plans to set up a test instance, upload the shared
  25-component SBOM, replace it with a second SBOM for the same release, reset,
  and run five seeded CVE queries. It names four pieces of evidence needed
  before Phase 4: query results within AC-04's 10 s right after upload, no
  stale components after replace or reset, 100% recall, and an unknown CVE that
  is distinguishable from "no matches". If those can't be shown, the fallback is
  local matching in SQLite against a vulnerability table loaded from the shared
  test data or a saved OSV feed.
- **§9.2:** the pod has to agree on related points. Before the Phase 3
  milestone, it must decide whether a new SBOM fully replaces a release's
  components. Before Phase 4, it must decide whether REQ-03 and AC-04 match on
  full package identifiers (purl) or on name and version.

So this spike **decides whether Phase 4's CVE query (REQ-03/REQ-04,
AC-04/AC-05) uses Dependency-Track (DT) or the local-matching fallback.** See
CLAUDE.md §8 as well.

## Setup

- **Deployment method.** The setup follows the official Docker guide the report
  cites as reference [2],
  <https://docs.dependencytrack.org/getting-started/deploy-docker/>, using its
  Docker Compose method.
- **Which compose file.** The guide's quickstart URL,
  `https://dependencytrack.org/docker-compose.yml`, now serves the DT 5.2.0
  stack. So `docker-compose.yml` here is the compose file DT ships for
  **4.14.5**, the newest 4.x release
  (`src/main/docker/docker-compose.yml` at tag 4.14.5). It runs:
  - the API server on port 8081;
  - the frontend on port 8080;
  - PostgreSQL 17.
- **Deviations from that file** (each marked `spike:` in the YAML):
  - images pinned to exact versions and digests;
  - ports bound to `127.0.0.1` only;
  - an 8 GB memory limit, which is the guide's recommended size.
- **Where it ran.** Locally on Docker Desktop: a Mac with Docker Engine 29.6.2,
  8 CPUs, and 11.7 GiB of memory for Docker.
  - It did not run on the e2-medium GCP VM. That VM has 4 GB of RAM, below the
    8 GB DT recommends.
  - The report's §7.3 assumed a VM with at least 8 GB of RAM and 4 cores for DT,
    so if DT stays in the plan, the deployment host needs to be upgraded.
- **Raw evidence.** All results are in `results/`.
  - `results/h2-embedded/` holds an earlier round that used the API server
    alone with its embedded H2 database. It gave the same answers and is kept
    for comparison.

## Short answer

With both the NVD mirror and the OSV PyPI mirror loaded, DT met all four §9.1
checks on every run:

| Check (§9.1) | Result (PostgreSQL setup, 7 runs) |
|---|---|
| Query within AC-04's 10 s right after upload | Correct answers 0.78–2.56 s after the upload started; one CVE query took ≤ 0.10 s |
| No stale components after replace or reset | 0 stale components and 0 stale findings after replace; 0 projects and 0 components after reset |
| 100% recall on the seeded list | 5/5 after upload and 2/2 after replace; precision was also 100% |
| Unknown CVE is distinguishable from "no matches" | Yes: `CVE-2099-0001` has no DT record, while `CVE-2019-11324` has a record but no affected project |

That only holds under three conditions, and the third affects whether the team
can run deterministic tests (next section):

1. **The app must wait for DT to finish processing.**
   - DT analyses an upload in the background. Queries sent while it was still
     working gave wrong answers in every run: missed CVEs after an upload, and a
     stale werkzeug match after a replace.
   - The answers were correct as soon as DT's processing token cleared, 0.36–2.43
     s after the upload. No answer was wrong after that point.
2. **The NVD mirror is required, not just OSV.**
   - Without NVD, DT has no record named by the CVE ID. The GHSA and PYSEC
     records carry the CVE only as an alias, and no DT endpoint searches aliases.
   - On an OSV-only instance, recall was 0/5 and the unknown CVE could not be told
     apart from a known one.
   - Loading NVD into PostgreSQL took 15.3 minutes.
3. **Matching on CPEs adds a false positive.** The fixture's Syft-generated
   CPEs match NVD data incorrectly for one component (details below). When the
   SBOMs were uploaded without `cpe` fields, DT's results were identical to OSV's.

**Recommendation: use the fallback (local matching in SQLite) for Phase 4, and
keep DT out of the request path for now.** DT works, but the graded tests run
on fixed vulnerability records, and DT adds cost there without improving the
results. The reasoning is below. Both teams chose DT in Phase 1, so this change
needs team and pod agreement before anyone builds on it.

## What was run

`spike.py run` does the following against a running DT:

1. **Upload.**
   - Creates two projects (releases) of `spike-example-gateway`: `1.0.0` (A) and
     `1.1.0` (B).
   - Uploads `fixtures/sbom_25_components.json` to A only.
   - Polls DT's processing token and the CVE queries every 0.25 s, until both are
     done and all answers match.
2. **Replace.**
   - Uploads a second SBOM to A, generated by `spike.py`'s `replacement_sbom()`.
     It upgrades werkzeug to 2.2.3, flask to 2.2.5 and requests to 2.31.0 (the
     fixed versions), drops pyyaml, and adds tomli 2.0.1.
   - Checks that A's components exactly match the new SBOM, and that no finding
     refers to a removed component.
3. **Reset.** Deletes both projects, then checks that:
   - no project remains;
   - no component exists for any purl from either SBOM;
   - the CVE queries return no releases.
4. **Unknown CVE.** Compares `CVE-2099-0001`, which does not exist, with
   `CVE-2019-11324`, which is real but does not affect the fixture.

The CVE query is what `GET /vulnerabilities/{cveId}/affected-releases` would do
on top of DT:

1. Look up the record `NVD/CVE-…`. If there is none, the CVE is unknown.
2. Take the GHSA and PYSEC IDs from that record's aliases.
3. Ask DT which projects each of those records affects, and combine the answers.

### The five CVEs (spike inputs, not pod ground truth)

Each one was checked against its OSV record on 2026-10-17 using the OSV API. The
version ranges are copied into `expected.json`. Before anything here goes into
`fixtures/ground_truth.json`, a team member has to check it (see the checklist).

| CVE | Advisory | Package in fixture | Affected range (OSV) | Fixed in replacement SBOM? |
|---|---|---|---|---|
| CVE-2023-25577 | [GHSA-xg9f-g7g7-2323](https://github.com/pallets/werkzeug/security/advisories/GHSA-xg9f-g7g7-2323), [NVD](https://nvd.nist.gov/vuln/detail/CVE-2023-25577) | werkzeug 2.2.2 | < 2.2.3 | yes (2.2.3) |
| CVE-2023-32681 | [GHSA-j8r2-6x86-q33q](https://github.com/psf/requests/security/advisories/GHSA-j8r2-6x86-q33q), [NVD](https://nvd.nist.gov/vuln/detail/CVE-2023-32681) | requests 2.28.2 | ≥ 2.3.0, < 2.31.0 | yes (2.31.0) |
| CVE-2023-30861 | [GHSA-m2qf-hxjv-5gpq](https://github.com/pallets/flask/security/advisories/GHSA-m2qf-hxjv-5gpq), [NVD](https://nvd.nist.gov/vuln/detail/CVE-2023-30861) | flask 2.2.2 | < 2.2.5; ≥ 2.3.0, < 2.3.2 | yes (2.2.5) |
| CVE-2023-23931 | [GHSA-w7pp-m8wf-vj6r](https://github.com/pyca/cryptography/security/advisories/GHSA-w7pp-m8wf-vj6r), [NVD](https://nvd.nist.gov/vuln/detail/CVE-2023-23931) | cryptography 39.0.0 | ≥ 1.8, < 39.0.1 | no, still affected |
| CVE-2023-37920 | [GHSA-xqr8-7jwr-rhp7](https://github.com/certifi/python-certifi/security/advisories/GHSA-xqr8-7jwr-rhp7), [NVD](https://nvd.nist.gov/vuln/detail/CVE-2023-37920) | certifi 2022.12.7 | ≥ 2015.4.28, < 2023.7.22 | no, still affected |
| CVE-2019-11324 (known, no match) | [GHSA-mh33-7rrq-662w](https://github.com/advisories/GHSA-mh33-7rrq-662w), [NVD](https://nvd.nist.gov/vuln/detail/CVE-2019-11324) | urllib3 1.26.14 | < 1.24.2 | not affected |
| CVE-2099-0001 (unknown) | none (OSV API returns 404) | | | |

## Measurements

Times are in seconds from the start of the upload request. "Done" means DT's
processing token had cleared.

**PostgreSQL setup** (`docker-compose.yml`), `results/run-*-pg-*.json`, all
taken with the NVD and OSV mirrors fully loaded:

| Run | Upload: done / correct | Replace: done / correct | Slowest single query | Recall / precision (upload, replace, reset) |
|---|---|---|---|---|
| pg-1 (first run after mirroring) | 2.43 / 2.56 | 0.81 / 0.91 | 0.076 | 100% / 100% |
| pg-2 … pg-5 | 0.70–0.81 / 0.78–0.92 | 0.36–0.42 / 0.43–0.49 | 0.052 | 100% / 100% |
| pg-nocpe (SBOMs without `cpe`) | 0.76 / 0.84 | 0.36 / 0.46 | 0.032 | 100% / 100% |
| pg-after-restart | 1.80 / 1.96 | 1.07 / 1.29 | 0.100 | 100% / 100% |

**Earlier H2 round** (`results/h2-embedded/`): the API server alone with its
embedded H2 database. Its compose file was replaced by the guide-aligned one.

- 8 runs with NVD loaded or loading: upload 0.44–3.38 s to correct, replace
  0.45–1.15 s. All runs had 100% recall and precision, and no stale data.
- 1 run on a fresh **OSV-only** instance (`setup --no-nvd`): the CVE queries never
  became correct. Recall was 0% and the unknown CVE was not distinguishable.
  This is condition 2 above.

**Wrong answers while DT is processing.** In every run that recorded per-poll
answers, some queries were wrong while DT was still processing:

- PostgreSQL setup: at 0.10–1.68 s after the upload, up to 5 of the 6 queries
  were wrong.
- H2 round: at 0.12–1.13 s after the upload, up to 5 of the 6 queries were wrong.

No query was wrong after the processing token had cleared. This is condition 1
above.

**Stale data.** No run left any stale data.

- After replace, A's 25 components exactly matched the replacement SBOM, and
  findings dropped from 153 to 144, none of them referring to a removed version.
- After reset, 0 projects and 0 components were left. A project deletion took
  ≤ 0.1 s.
- B never had any components.

**Persistence.** `docker compose restart apiserver` stopped the server at
21:27:34, it was ready again at 21:27:46, and the full run passed.

**Unreachable source (AC-05).** With the API server stopped, the client got a
`ConnectError` after 0.05 s.

- In the H2 round, a host that does not answer gave a `ConnectTimeout` when the
  client's timeout ran out (5 s).
- In both cases the app can return 503 within AC-05's 15 s.

### Recall and precision beyond the five CVEs

`spike.py crosscheck` compares the CVEs DT reported for each component with
what the OSV API returns for the same purl (`results/crosscheck-*.json`). Both
setups gave the same results.

- **With CPEs in the SBOM:** DT found 66 CVEs and OSV 65, and every OSV CVE was
  found. The extra one is **CVE-2018-17175 on marshmallow 3.19.0**, a false
  positive from DT's NVD CPE matching:
  - NVD's configuration is `cpe:…:marshmallow_project:marshmallow:*:…:python`,
    with `versionStartIncluding 3.0` and `versionEndExcluding 3.0.0b9`.
  - DT treats 3.19.0 as inside that range.
  - When the same component is uploaded without its `cpe`, the finding does not
    appear.
- **Without CPEs:** DT and OSV both found 65, with no differences.

## Populating the vulnerability data

Times are from the DT logs.

| Source | How it is enabled | First load | Disk |
|---|---|---|---|
| NVD (CVE records and CPE ranges) | On by default; downloads the yearly NVD JSON 2.0 feeds (2002–2026) | **PostgreSQL: 918 s (15.3 min)**: 8 s to download, 869 s to parse. H2: about 7 min. | PostgreSQL setup: 3.0 GB of database and 3.6 GB of DT data (6.6 GB in total). The H2 round used 13 GB. |
| OSV, PyPI ecosystem | Config property `vuln-source/google.osv.enabled = PyPI`. It only starts at startup or on the 24 h schedule, so it needs one restart after the property is set. | 32 s: 1 s to download `PyPI/all.zip`, 31 s to parse 26,379 advisories | 383 MB on the OSV-only H2 instance |
| GitHub advisories | Needs a GitHub token (`github.advisories.access.token`) | Not tried. The OSV PyPI feed already includes the GHSA records. | |
| OSS Index | On by default | Turned off: it now needs Sonatype credentials and calls an external service for each component | |

Some CPE strings in the NVD data fail to parse, and DT logs them.

- **Cold start for the PostgreSQL setup.**
  - `docker compose up` began at 21:09:18 and DT was ready at 21:09:32.
  - The OSV mirror finished at 21:10:25.
  - The NVD mirror finished at 21:26:00.
  - So it took about **17 minutes** before CVE IDs resolved.
- **Memory.** Spot checks after mirroring showed about 0.9 GB for the API
  server and 0.6 GB for PostgreSQL. Peak memory was not measured.
- **OSV only.** An OSV-only instance was ready in 54 s, but it cannot answer
  CVE-ID queries (condition 2 above).
- **Daily refresh.** Every mirror refreshes every 24 h by default
  (`task-scheduler/*.cadence`). Results for the same SBOM can therefore change
  from one day to the next. For example, the OSV data already lists CVE-2026-*
  records against these 2023 versions.

### Making DT deterministic for tests

The contract's `PUT /test/vulnerability-source` sends `{cve_id, affected_purls}`
records. `spike.py inject` tested whether DT can serve them.

- DT can store such a record as an INTERNAL vulnerability with a CVE-shaped ID
  (`CVE-2099-424242`) and an exact purl.
- DT matched it on upload and reported it through
  `/vulnerability/source/INTERNAL/vuln/{id}/projects`.
- When the record was created after the upload (tested in the H2 round), DT only
  matched it after an explicit `POST /finding/project/{uuid}/analyze` (0.2 s).

For seeded tests, the app would then have to:

- look up only INTERNAL records, or turn the mirrors off. Otherwise the real
  NVD and GHSA records for the same CVE IDs add matches the fixture does not
  list, and precision fails;
- re-analyse every project whenever the fixtures change;
- delete the INTERNAL records on `/test/reset`;
- simulate "unreachable" in the app itself.

## Recommendation

**Use the fallback for Phase 4:** match vulnerabilities in our own app against
the components already stored in SQLite, using a vulnerability table loaded from
the shared test data.

- **Why the fallback fits the graded path.** AC-04, AC-05 and Team 2's tests run
  on `PUT /test/vulnerability-source` records, which are exact `cve_id → purl`
  lists. In SQLite that is a join on purl, inside the same transaction as the
  components. As a result:
  - there is no background processing to wait for;
  - replace and reset are already atomic;
  - "unknown CVE" means the CVE ID is not in the table;
  - "unreachable" is a flag;
  - results stay the same every day.
- **What DT would add on that path.** DT passed the spike, but using it for the
  graded tests means extra work:
  - waiting on the processing token for every upload;
  - keeping two data stores in sync;
  - injecting INTERNAL vulnerabilities and re-analysing projects;
  - turning off or ignoring the mirrors in test mode;
  - running a third and fourth container (DT and PostgreSQL), which need an
    8 GB host instead of the current 4 GB e2-medium;
  - an NVD mirror that takes about 15 min to load, only so that CVE IDs resolve.

  None of this improves the AC-04 or AC-05 results.
- **Real vulnerability data later.** Beyond the seeded tests, the same table can
  be filled from OSV's `PyPI/all.zip`, which downloaded in 1–2 s. The work is:
  - comparing PyPI version ranges (PEP 440, using the `packaging` library);
  - recording aliases so that CVE IDs resolve.
- **If the team wants DT for production data anyway.** The spike shows it can
  work behind the same interface, with these rules:
  - mirror NVD and OSV PyPI;
  - strip `cpe` fields before uploading;
  - block `PUT /sbom` until DT's processing token clears;
  - map a missing NVD record to `404 CVE_UNKNOWN`;
  - map connection errors to `503`;
  - size the host to at least 8 GB.
- **DT 5.x.** It has been released since the Phase 2 report (5.0.0 on
  2026-06-07; 5.2.0 is current), and the guide's quickstart URL now installs it.
  This spike only tested 4.14.5. If DT comes back into the plan, decide between
  4.x and 5.x first.

### Needs a decision

- [ ] Team 6 agrees on the recommendation.
- [ ] The pod agrees, because DT was a pod-wide Phase 1 choice. Record the
  outcome in `docs/decisions.md`.
- [ ] The pod settles the §9.2 matching key (CLAUDE.md §7.5). This spike
  matched on purl.

### Human check of the spike inputs

- [ ] Someone checked each row of the CVE table against the linked advisory.
  This includes confirming that the fixture version is in the affected range,
  and that the replacement version is outside it for werkzeug, flask and
  requests.
- [ ] Someone confirmed that CVE-2019-11324 does not affect urllib3 1.26.14.

## Re-running

Run these locally, not on the 4 GB VM:

```bash
docker compose -f spikes/dependency_track/docker-compose.yml up -d
.venv/bin/python spikes/dependency_track/spike.py setup         # add --no-nvd for OSV only
docker compose -f spikes/dependency_track/docker-compose.yml restart apiserver   # starts the OSV mirror
.venv/bin/python spikes/dependency_track/spike.py mirror        # repeat until all five resolve (~17 min cold)
.venv/bin/python spikes/dependency_track/spike.py run
.venv/bin/python spikes/dependency_track/spike.py crosscheck    # needs internet access (OSV API)
.venv/bin/python spikes/dependency_track/spike.py inject
```

- **Credentials.** `setup` replaces DT's default admin password with a random
  one and saves it in `.dt-admin-password`, which git ignores. The PostgreSQL
  credentials are the guide's defaults, and the database is not published
  outside the Docker network.
- **Ports.** The frontend is at <http://localhost:8080>. If the app is also
  running on 8080, set `DT_FRONTEND_PORT`.
- **Cleanup.** To remove the containers and their 6.6 GB of volumes, run
  `docker compose -f spikes/dependency_track/docker-compose.yml down -v`.
