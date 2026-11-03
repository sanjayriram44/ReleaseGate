"""Coverage in /test/run and /test/report (autograder Q2): code, component and system model, in %.

- code: line coverage of the system's app/ package by its own test suite (.coverage-baseline,
  kept current by scripts/metrics.py). Only the system knows it; the tester copies it from the
  target's /test/report and reports null for a target that doesn't publish one.
- component: share of the pod contract's API operations (OPERATIONS) the run called.
- system: share of the system-model acceptance criteria, AC-01..AC-07, the run exercised.
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
ACCEPTANCE_CRITERIA = tuple(f"AC-0{i}" for i in range(1, 8))

_PATTERNS = [
    (method, template, re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", template) + "$"))
    for method, template in OPERATIONS
]


def operation(method: str, path: str) -> str | None:
    """'GET /api/v1/releases/{releaseId}' for GET /api/v1/releases/rel-1; None if not listed."""
    for op_method, template, pattern in _PATTERNS:
        if op_method == method.upper() and pattern.match(path):
            return f"{op_method} {template}"
    return None


def code_coverage(path: Path = Path(".coverage-baseline")) -> float | None:
    try:
        return round(float(path.read_text().strip()), 2)
    except (OSError, ValueError):
        return None


def _percent(part: int, whole: int) -> float:
    return round(100 * part / whole, 1)


def summarize(report: "Report | None", code: float | None) -> dict[str, Any]:
    """The coverage object; component and system are null until a run has finished."""
    if report is None:
        return {"code": code, "component": None, "system": None}
    exercised = {c.ac for c in report.checks if c.ac in ACCEPTANCE_CRITERIA}
    return {
        "code": code,
        "component": _percent(len(set(report.operations)), len(OPERATIONS)),
        "system": _percent(len(exercised), len(ACCEPTANCE_CRITERIA)),
        "operations_called": sorted(set(report.operations)),
        "acceptance_criteria_exercised": sorted(exercised),
    }
