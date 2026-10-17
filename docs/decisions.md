# Decisions

Provisional = taken from the Phase 3 handoff proposals; needs pod (Team 2) confirmation.

| Topic | Answer | Status |
|---|---|---|
| Missing `X-User-Id` | 400 `INVALID_REQUEST` | provisional |
| CycloneDX versions | 1.4, 1.5, 1.6 accepted; others rejected with a reason | provisional |
| Component without `version` | Reject the whole SBOM | provisional |
| Error codes beyond the contract | `INVALID_JSON`, `INVALID_SBOM`, `RELEASE_NOT_FOUND`, `RELEASE_EXISTS`, `AUDIT_IMMUTABLE` | provisional |
| Nested components | Only top-level `components[]` stored | provisional |
| Unregistered release + SBOM | 404 checked before body validation | provisional |
| SBOM schema strictness | Official CycloneDX schemas bundled with `cyclonedx-python-lib` (non-vendored); unknown properties that the official schema forbids are rejected | implementation choice |
| Shared fixtures | `fixtures/` (25-component SBOM and releases fixture) reviewed by Team 6 and used unchanged by both teams | agreed with Team 2 (2026-10-17) |
