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

## Phase 4 CVE fixtures (AC-04, AC-05): DRAFT, not verified

> **Status: draft (2026-11-01).** Built by Team 6's Claude Code session from the Dependency-Track
> spike's candidates (`spikes/dependency_track/expected.json`, OSV ranges checked 2026-10-17).
> **Nobody has verified the expected values yet.** Per decision Q7, one person per team checks
> them before the Phase 4 milestone; record their names and the date here and in
> `docs/decisions.md`, then drop the `_status` fields and `test_fixtures_are_marked_as_drafts`.

| File | Contents |
|---|---|
| `sbom_patched.json` | `sbom_25_components.json` with werkzeug 2.2.3, flask 2.2.5 and requests 2.31.0, pyyaml removed and tomli 2.0.1 added: the spike's `replacement_sbom()`, unchanged |
| `vulnerabilities.json` | `VulnerabilityFixture` records for `PUT /api/v1/test/vulnerability-source`: the five test CVEs, plus CVE-2019-11324 as a known CVE that no release contains |
| `cve_dataset.json` | Reference clock and five releases: which SBOM each gets and its support-end date, so affected releases fall in both groups (1.0.0 unsupported; 1.1.0, the 1.2.0 boundary release and 2.0.0 supported; 2.1.0 has no SBOM) |
| `ground_truth.json` | For each CVE, the expected `supported` and `unsupported` release keys with matched purls, compared as sets. Also the unknown CVE (CVE-2099-0001 → 404) and the unreachable case (→ 503) |

`ground_truth.json` was derived mechanically from the other three files. The values a person has
to check are the `affected_purls`:

- [ ] Each of the five CVEs: the listed fixture version is inside the advisory's affected range
  (links in `spikes/dependency_track/RESULTS.md`), and the `sbom_patched.json` version is outside
  it for werkzeug, flask and requests.
- [ ] CVE-2019-11324: urllib3 1.26.14 is not affected, and 1.24.1 is (affected below 1.24.2).
- [ ] `sbom_patched.json`: the `syft:cpe23` properties still name the old versions (the spike
  only rewrote version, purl, bom-ref and cpe). Matching uses purls only, so decide whether that
  matters.
- [ ] The supported/unsupported grouping at `reference_clock` follows REQ-01.
