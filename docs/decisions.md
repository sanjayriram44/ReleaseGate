# Decisions

Agreed answers and outstanding proposals are recorded below. Proposed details still need pod (Team 2) confirmation.

| Topic | Answer | Status |
|---|---|---|
| Missing `X-User-Id` | Endpoints requiring the header return 400 with `INVALID_REQUEST` when it is missing. Test-control endpoints are exempt. | agreed |
| CycloneDX versions | Accept valid CycloneDX JSON with `specVersion` 1.4, 1.5, or 1.6. Reject unsupported versions with 400 and an explanatory message. | agreed |
| Component without `version` | Reject the entire SBOM with 400 if an inventory component, including a nested component, is missing a required version. | agreed |
| Error-code assertions | Check exact error codes for explicitly agreed cases, alongside HTTP statuses and meaningful nonempty messages. For other cases, check the status and error envelope until specific code values are agreed. | recommended |
| Nested components | Recursively flatten nested inventory components and include every component at every depth in storage and `component_count`. Proposed details: exclude metadata and tool components, and retain repeated occurrences unless agreed otherwise. | recursive flattening agreed; exclusions and repeated occurrences proposed |
| Unregistered release + SBOM | Check release existence before validating the SBOM body. Unknown release IDs return 404. | agreed |
| SBOM schema strictness | Official CycloneDX schemas bundled with `cyclonedx-python-lib` (non-vendored); unknown properties that the official schema forbids are rejected | implementation choice |
| Shared fixtures | `fixtures/` (25-component SBOM and releases fixture) reviewed by Team 6 and used unchanged by both teams | agreed with Team 2 (2026-10-17) |
