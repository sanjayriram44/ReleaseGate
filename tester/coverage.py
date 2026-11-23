"""Coverage in the tester's suite report (spec v2, "Coverage fields"): code, component, system and,
when the tester tests our own system, model. Each entry is {"covered", "total", "basis"} with
nonnegative integer counts; an unavailable measure has null counts and says why.

- code: source lines the target executed during the session. Only the target can measure it; the
  tester copies it from the target system's GET /test/report.
- component: the pod contract's API operations (OPERATIONS) the suite called.
- system: the pod's acceptance criteria AC-01..AC-10 (Phase 2 report, Section 4.1) the suite
  evaluated. AC-10 needs a restart, so a single run can't evaluate it; tester/ac10.py runs it in
  two steps.
- model: our Phase 5 design requirements the suite evaluated (tester/model.py).
"""

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # tester.checks imports operation() from here
    from tester.checks import Report

# docs/openapi.yaml without the test-support and harness endpoints; tests/test_harness.py keeps
# the two in step.
OPERATIONS: tuple[tuple[str, str], ...] = (
    ("POST", "/api/v1/releases"),
    ("GET", "/api/v1/releases/{releaseId}"),
    ("PUT", "/api/v1/releases/{releaseId}/sbom"),
    ("GET", "/api/v1/releases/{releaseId}/components"),
    ("GET", "/api/v1/vulnerabilities/{cveId}/affected-releases"),
    ("POST", "/api/v1/incidents"),
    ("GET", "/api/v1/incidents/{incidentId}"),
    ("PATCH", "/api/v1/incidents/{incidentId}"),
    ("POST", "/api/v1/incidents/{incidentId}/submissions"),
    ("PUT", "/api/v1/incidents/{incidentId}/report-data/{stage}"),
    ("GET", "/api/v1/incidents/{incidentId}/reports/{stage}"),
    ("GET", "/api/v1/audit-logs"),
    ("PATCH", "/api/v1/audit-logs/{eventId}"),
    ("DELETE", "/api/v1/audit-logs/{eventId}"),
)
ACCEPTANCE_CRITERIA = tuple(f"AC-{i:02d}" for i in range(1, 11))

_PATTERNS = [
    (method, template, re.compile(re.sub(r"\{[^}]+\}", "[^/]+", template)))
    for method, template in OPERATIONS
]


def operation(method: str, path: str) -> str | None:
    """'GET /api/v1/releases/{releaseId}' for GET /api/v1/releases/rel-1; None if not listed."""
    for op_method, template, pattern in _PATTERNS:
        if op_method == method.upper() and pattern.fullmatch(path):
            return f"{op_method} {template}"
    return None


def code_coverage(path: Path = Path(".coverage-baseline")) -> float | None:
    """Our own test suite's app/ line coverage in percent (kept current by scripts/metrics.py)."""
    try:
        return round(float(path.read_text().strip()), 2)
    except (OSError, ValueError):
        return None


def entry(covered: int | None, total: int | None, basis: str) -> dict[str, Any]:
    return {"covered": covered, "total": total, "basis": basis}


def unavailable(basis: str) -> dict[str, Any]:
    """An unavailable measure: null counts (never zero) and the reason."""
    return entry(None, None, basis)


def is_entry(value: Any) -> bool:
    """A well-formed coverage entry: counts both null, or integers with 0 <= covered <= total."""
    if not isinstance(value, dict) or not isinstance(value.get("basis"), str):
        return False
    covered, total = value.get("covered"), value.get("total")
    if covered is None and total is None:
        return bool(value["basis"].strip())
    if not isinstance(covered, int) or not isinstance(total, int):
        return False
    if isinstance(covered, bool) or isinstance(total, bool) or not 0 <= covered <= total:
        return False
    return bool(value["basis"].strip())


def component(report: "Report") -> dict[str, Any]:
    called = set(report.operations) & {f"{m} {p}" for m, p in OPERATIONS}
    return entry(
        len(called),
        len(OPERATIONS),
        "Operations of the pod's shared project API (docs/openapi.yaml, test-support endpoints "
        "excluded); an operation counts once the suite has called it at least once.",
    )


def system(report: "Report") -> dict[str, Any]:
    evaluated = {c.ac for c in report.checks if c.ac in ACCEPTANCE_CRITERIA}
    return entry(
        len(evaluated),
        len(ACCEPTANCE_CRITERIA),
        "Acceptance criteria AC-01..AC-10 of the pod's shared specification (Phase 2 report, "
        "Section 4.1); a criterion counts once at least one of its checks ran. AC-10 needs a "
        "service restart between two sessions, so it is evaluated by the separate two-step "
        "tester.ac10 procedure, not in a single run.",
    )
