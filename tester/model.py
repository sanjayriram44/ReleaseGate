"""Model coverage (spec v2): our Phase 5 design requirements and the tester checks that evaluate
them. Reported only when the tester tests our own system.

docs/design-requirements.md is the human-readable copy of this table, and
tests/unit/test_model_coverage.py keeps the two in step. A requirement counts as covered once at
least one of its checks ran in the session (coverage records what was evaluated, not whether it
passed). DRAFT: drawn by Claude from the Phase 5 models (architecture, behavior and information
schema) and docs/decisions.md; the team reviews the list.
"""

from typing import TYPE_CHECKING, Any

from tester.coverage import entry

if TYPE_CHECKING:
    from tester.checks import Report

DESIGN_VERSION = "Phase 5 design, docs/design-requirements.md (2026-11-22)"
MAPPING_URL = "https://github.com/sanjayriram44/ReleaseGate/blob/main/docs/design-requirements.md"

# (id, requirement, check-id prefixes that evaluate it)
DESIGN_REQUIREMENTS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "DR-01",
        "A release's support status is computed on every read from the injectable clock and is "
        "never stored.",
        ("ac01.",),
    ),
    (
        "DR-02",
        "A release is unique per product and version, and an unknown release is 404.",
        ("contract.duplicate", "contract.unknown_release"),
    ),
    (
        "DR-03",
        "The components of a valid CycloneDX SBOM, nested ones flattened, are stored for its "
        "release and listed back.",
        ("ac02.",),
    ),
    (
        "DR-04",
        "An SBOM upload checks the release first (404), then the JSON and the CycloneDX schema; "
        "a rejection states its reason and stores nothing.",
        ("ac03.",),
    ),
    (
        "DR-05",
        "A new valid SBOM replaces the release's components in one transaction; an invalid one "
        "leaves them unchanged.",
        ("contract.replace", "contract.invalid_keeps_existing"),
    ),
    (
        "DR-06",
        "The CVE query asks the vulnerability source first (503 when it is unreachable), then "
        "answers 404 for an unknown CVE.",
        ("ac05.",),
    ),
    (
        "DR-07",
        "Affected releases come from purl matching against stored components and are grouped by "
        "support status at the clock's time.",
        ("ac04.",),
    ),
    (
        "DR-08",
        "An incident stores the human-supplied awareness_at, classification and rationale; "
        "invalid input is 400 and stores nothing.",
        ("ac06.",),
    ),
    (
        "DR-09",
        "Deadlines (awareness + 24 h, + 72 h, fix + 14 days) and their status are computed on "
        "every read from stored timestamps and the clock, with no timer.",
        ("ac07.",),
    ),
    (
        "DR-10",
        "Report data is checked against one stage-field table, and each stage's report is built "
        "on read from the stored data, with missing_fields.",
        ("ac08.",),
    ),
    (
        "DR-11",
        "Every successful state change writes exactly one audit entry in the same transaction, "
        "with the user and the clock's time; a rejected request writes none.",
        (
            "ac09.steps",
            "ac09.rejected_adds_nothing",
            "ac09.four_events",
            "ac09.order",
            "ac09.timestamps",
            "contract.audit_list",
        ),
    ),
    (
        "DR-12",
        "Audit entries cannot be changed or deleted through the API (405).",
        ("ac09.immutable", "contract.audit_patch", "contract.audit_delete"),
    ),
    (
        "DR-13",
        "The gated test endpoints reset all state, including the audit log, and set the "
        "injectable clock.",
        ("setup.", "teardown.", "ac09.reset"),
    ),
    (
        "DR-14",
        # A single run cannot restart the service: only the two-step tester.ac10 procedure
        # evaluates this one.
        "All stored data survives a process restart with no timestamp drift (AC-10).",
        (),
    ),
)


def evaluated(check_id: str, prefixes: tuple[str, ...]) -> bool:
    return any(check_id == p or (p.endswith(".") and check_id.startswith(p)) for p in prefixes)


def covered_requirements(report: "Report") -> list[str]:
    ids = [c.id for c in report.checks]
    return [
        dr for dr, _, prefixes in DESIGN_REQUIREMENTS if any(evaluated(i, prefixes) for i in ids)
    ]


def model(report: "Report") -> dict[str, Any]:
    return entry(
        len(covered_requirements(report)),
        len(DESIGN_REQUIREMENTS),
        f"Design requirements DR-01..DR-{len(DESIGN_REQUIREMENTS):02d} of our {DESIGN_VERSION}; "
        f"a requirement counts once one of its mapped checks ran. Mapping to tests: {MAPPING_URL}",
    )
