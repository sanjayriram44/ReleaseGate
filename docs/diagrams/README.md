# Phase 2 diagrams

Original SVGs from the Phase 2 report (`docs/phase2_report.pdf`). They are kept as submitted;
where they disagree with the current design, the notes below and `docs/openapi.yaml` win.

| File | Report section | Notes |
|---|---|---|
| `3.1_information.svg` | 3.2 Information schema | `DEADLINE.timer_id` and the timer invariants are superseded: deadlines are computed on read (Phase 4). Phase 3 implements `RELEASE`, `COMPONENT` and `LOG_ENTRY`. |
| `3.1_behavior.svg` | 3.2 Behavior models | The SBOM upload flow is implemented as drawn. The deadline state machine's timer service, `Waiting` and `Late` states are superseded by the contract's `pending` / `met` / `overdue` / `not_applicable`. |
| `7.1.svg` | 7.1 Architecture | Routes such as `/cases`, `/cves` and `GET /releases/{id}/sbom` predate the shared contract; the real paths are in `docs/openapi.yaml`. The database engine is SQLite. |

The 2.1 boundary diagram is not included: only an earlier draft was available, not the version
in the report.
