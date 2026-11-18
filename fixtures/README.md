# Shared pod test fixtures

> **Status: Agreed with Team 2 on 2026-10-17.** Created by Team 6, reviewed by Team 6 and signed off by Team 2 for cross-team testing.
> Do not change the expected results in these files without the same review and pod agreement.

| File | Used by | Contents |
|---|---|---|
| `sbom_25_components.json` | AC-02, Phase 3 demo | CycloneDX 1.6 JSON SBOM with 25 components |
| `releases.json` | AC-01, AC-02 | Reference clock, release requests and expected results |
| `sbom_source/` | provenance | The inputs used to generate the SBOM |

## `sbom_25_components.json`

A real dependency set, not made-up package names. It is the full locked dependency tree of a small Python web service (Flask, requests, PyYAML, cryptography, SQLAlchemy, python-dateutil, gunicorn, pydantic, marshmallow, PyJWT), locked to versions available on 2023-01-15.

How it was made:

```bash
# 1. Lock the top-level packages in sbom_source/requirements.in
uv pip compile requirements.in --exclude-newer 2023-01-15 --python-version 3.10 \
  --no-header --no-annotate -o requirements.txt

# 2. Generate the SBOM from the locked file (Syft v1.18.1)
docker run --rm -v "$PWD":/project:ro anchore/syft:v1.18.1 dir:/project \
  --source-name example-gateway --source-version 1.0.0 -o cyclonedx-json
```

Checks already run:

- Validates against the official CycloneDX 1.6 JSON schema (`cyclonedx-python-lib` strict validator).
- Exactly 25 entries in `components`, flat (no nested components).
- Every component has `name`, `version` and a `pkg:pypi/...` `purl`; no duplicate name+version pairs.

The expected AC-02 result is the SBOM itself: the release with the SBOM must return these same 25 name/version pairs, and the other release must return none.

Several of these 2023 versions have since had published vulnerabilities. That makes the set usable for the Phase 4 CVE fixtures (`affected_purls`), but the CVE ground truth must be built and checked by people separately.

## `releases.json`

- `reference_clock` is `2026-11-01T23:59:59Z`. That is the last second of the boundary day, so it tests "supported through the end of `support_end_date`" as strictly as possible.
- AC-01 dates are one day before, equal to, and one day after the clock date. The fourth case leaves out `support_end_date` and must be rejected with `400`.
- "Nothing saved" for the rejected case can be checked over the common interface: no audit event is written for it, and registering `ExampleRouter 4.0.0` again with a valid date returns `201` (not `409`).
- `ac01_rollover` is an extra check beyond the AC-01 wording: one second later, the boundary release becomes `unsupported`.
- `error_code: INVALID_REQUEST` comes from the Section 5.2 example. The contract doesn't require a specific code, so the pod should confirm whether tests check it.

## Review checklist

- [x] A Team 6 member checked the 25 components against `sbom_source/requirements.txt`.
- [x] A Team 6 member checked every expected result in `releases.json` against REQ-01, AC-01 and AC-02.
- [x] Sent to Team 2; they agreed to use these files unchanged.
- [x] The decision is recorded in `docs/decisions.md`.

## Phase 4 CVE fixtures (AC-04, AC-05): DRAFT, Team 6 verified, Team 2 pending

> **Status: draft (2026-11-01); Team 6 check done (2026-11-18, Donovan Baran).** Built by Team 6's
> Claude Code session from the Dependency-Track spike's candidates
> (`spikes/dependency_track/expected.json`, OSV ranges checked 2026-10-17). Team 6's checker
> confirmed every expected value on 2026-11-18 (below); no value changed. **Team 2's checker is
> not yet named (P5-Q11)**, so per decision Q7 AC-04 is not authoritative yet. Once Team 2 signs
> off, record their name and date here and in `docs/decisions.md`, then drop the `_status` fields
> and `test_fixtures_are_marked_as_drafts`.

| File | Contents |
|---|---|
| `sbom_patched.json` | `sbom_25_components.json` with werkzeug 2.2.3, flask 2.2.5 and requests 2.31.0, pyyaml removed and tomli 2.0.1 added: the spike's `replacement_sbom()`, unchanged |
| `vulnerabilities.json` | `VulnerabilityFixture` records for `PUT /api/v1/test/vulnerability-source`: the five test CVEs, plus CVE-2019-11324 as a known CVE that no release contains |
| `cve_dataset.json` | Reference clock and five releases: which SBOM each gets and its support-end date, so affected releases fall in both groups (1.0.0 unsupported; 1.1.0, the 1.2.0 boundary release and 2.0.0 supported; 2.1.0 has no SBOM) |
| `ground_truth.json` | For each CVE, the expected `supported` and `unsupported` release keys with matched purls, compared as sets. Also the unknown CVE (CVE-2099-0001 → 404) and the unreachable case (→ 503) |

`ground_truth.json` was derived mechanically from the other three files. The values a person has
to check are the `affected_purls`:

- [x] Each of the five CVEs: the listed fixture version is inside the advisory's affected range
  (links in `spikes/dependency_track/RESULTS.md`), and the `sbom_patched.json` version is outside
  it for werkzeug, flask and requests.
- [x] CVE-2019-11324: urllib3 1.26.14 is not affected, and 1.24.1 is (affected below 1.24.2).
- [x] `sbom_patched.json`: the `syft:cpe23` properties still name the old versions (the spike
  only rewrote version, purl, bom-ref and cpe). Matching uses purls only, so decide whether that
  matters. **Decision: fine, leave the file unchanged** (see below).
- [x] The supported/unsupported grouping at `reference_clock` follows REQ-01.
- [ ] Team 2's checker verifies the same values (P5-Q11).

**Team 6 check: Donovan Baran, 2026-11-18.** Each range was read from the GHSA advisory and its
PYSEC alias in the OSV database (`api.osv.dev`, fetched 2026-11-18; the two sources agree, and
both match the 2026-10-17 spike ranges).

| CVE | Advisory | Affected range | `sbom_25_components.json` | `sbom_patched.json` |
|---|---|---|---|---|
| CVE-2023-25577 | GHSA-xg9f-g7g7-2323 / PYSEC-2023-58 | werkzeug < 2.2.3 | 2.2.2: affected | 2.2.3: not affected |
| CVE-2023-32681 | GHSA-j8r2-6x86-q33q / PYSEC-2023-74 | requests ≥ 2.3.0, < 2.31.0 | 2.28.2: affected | 2.31.0: not affected |
| CVE-2023-30861 | GHSA-m2qf-hxjv-5gpq / PYSEC-2023-62 | flask < 2.2.5; ≥ 2.3.0, < 2.3.2 | 2.2.2: affected | 2.2.5: not affected |
| CVE-2023-23931 | GHSA-w7pp-m8wf-vj6r / PYSEC-2023-11 | cryptography ≥ 1.8, < 39.0.1 | 39.0.0: affected | 39.0.0: affected |
| CVE-2023-37920 | GHSA-xqr8-7jwr-rhp7 / PYSEC-2023-135 | certifi ≥ 2015.4.28, < 2023.7.22 | 2022.12.7: affected | 2022.12.7: affected |
| CVE-2019-11324 | GHSA-mh33-7rrq-662w / PYSEC-2019-133 | urllib3 < 1.24.2 | 1.26.14: not affected | 1.26.14: not affected |

The `affected_purls` in `vulnerabilities.json` are exactly the affected versions above, plus
`urllib3@1.24.1` for CVE-2019-11324, which is inside its range and in no SBOM, so no release
matches it.

Grouping at `2026-11-01T23:59:59Z` (supported through the end of `support_end_date`, REQ-01):
gw-1.0.0 (ends 2026-10-31) is unsupported; gw-1.1.0 (2027-12-31), gw-1.2.0 (2026-11-01, the
boundary case) and gw-2.0.0 (2028-06-30) are supported; gw-2.1.0 has no SBOM and appears in no
result. Recomputing `ground_truth.json` from the other three files gives the same releases and
matched purls for all six CVEs.

Stale `syft:cpe23` properties: in `sbom_patched.json`, werkzeug 2.2.3 and flask 2.2.5 still carry
`syft:cpe23` property values naming 2.2.2 (requests has none; each component's top-level `cpe` is
correct). They don't affect AC-04: decision Q5 matches by purl only, and nothing in `app/` reads
CPEs. Editing the file would mean a new pod sign-off for no change in any expected result, so it
stays as it is. A system that matched by CPE would report false positives here, but that is
outside the contract.

## Phase 5 report fixtures (AC-08): DRAFT, not verified

> **Status: draft (2026-11-18).** Written by Team 6's Claude session from CRA Art. 14(2)(a)–(c)
> and the Section 5 `ReportData` schema. The stage-to-field mapping is a proposal
> (`docs/pod-questions-phase5.md`, P5-Q1). **Nobody has verified it yet.** One person per team
> checks it and Team 2 signs off; record the names and date here and in `docs/decisions.md`, then
> drop the `_status` field.

| File | Contents |
|---|---|
| `report_cases.json` | `stage_fields` (which fields each stage has, required and optional), two mandatory incidents with report data for all three stages and the expected `missing_fields`, and informational edge cases |

Both AC-08 incidents supply every optional field, so their expected `missing_fields` (none for
the complete case; `exploit_nature` and `user_mitigations` for the incomplete case's
notification) hold however P5-Q1 settles required versus optional, as long as the stage-to-field
mapping stays. The edge cases depend on P5-Q1, Q2, Q4 and Q5 and stay informational until those
are answered. All report text is synthetic.

**Who reads it.** `stage_fields` is the shared stage-field table (CLAUDE.md §7 rule 2): the tester
(`tester/phase5.py`) and the acceptance tests read it, and `tests/unit/test_reports.py` fails if
`app/services/reports.py` `STAGE_FIELDS` or the contract's `ReportData` `x-fields-by-stage`
differs from it. If the pod settles P5-Q1 differently, a person updates this file first; the
tests then show what else must change. The complete and incomplete cases also seed AC-10
(`tester/ac10.py`) and the demo data (`scripts/post_deploy_full.py`).

- [ ] The stage-to-field mapping matches CRA Art. 14(2)(a), (b) and (c) and the `ReportData` schema.
- [ ] The incomplete case's notification leaves out exactly two required fields.
- [ ] Every edge case's expectation matches the agreed P5 answer it depends on (or is updated).
