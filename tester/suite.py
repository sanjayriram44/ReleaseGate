"""The tester's suite report (spec v2, POST /test/run): one result per planned test and coverage.

Each check becomes one result with a unique test_id, an outcome (pass, fail, error or skip) and a
nonempty message. A check that failed because the target answered with an internal failure (5xx
other than the contract's 503 for an unreachable vulnerability source) is an error with source
"system". If the run stopped early, one more result records why, with the error's source.
"""

from typing import Any

from tester.checks import Check, Report
from tester.coverage import component, system
from tester.model import model

MESSAGE_LIMIT = 400


def _message(check: Check) -> str:
    text = f"{check.title}. Expected {check.expected}; received {check.actual}."
    if not check.required:
        text += " Informational: rests on a pod proposal that isn't agreed yet."
    return text if len(text) <= MESSAGE_LIMIT else text[: MESSAGE_LIMIT - 1] + "…"


def _outcome(check: Check) -> tuple[str, str | None]:
    if check.passed:
        return "pass", None
    if check.status is not None and check.status >= 500 and check.status != 503:
        return "error", "system"
    return "fail", None


def results(report: Report) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for check in report.checks:
        test_id, n = check.id, 2
        while test_id in seen:  # every result needs a unique test_id
            test_id, n = f"{check.id}#{n}", n + 1
        seen.add(test_id)
        outcome, source = _outcome(check)
        item: dict[str, Any] = {"test_id": test_id, "outcome": outcome}
        if source:
            item["source"] = source
        item.update({"message": _message(check), "ac": check.ac, "required": check.required})
        out.append(item)
    if report.error:
        source = "communication" if report.error.startswith("Target unreachable") else "system"
        out.append(
            {
                "test_id": "suite.stopped",
                "outcome": "error",
                "source": source,
                "message": f"The suite stopped early: {report.error}",
                "ac": "suite",
                "required": True,
            }
        )
    return out


def summary(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"pass": 0, "fail": 0, "error": 0, "skip": 0}
    for item in items:
        counts[item["outcome"]] += 1
    return counts


def suite_report(
    session_id: str,
    target_url: str,
    report: Report,
    code: dict[str, Any],
    own_system: bool,
) -> dict[str, Any]:
    """The complete suite report. coverage.model only when the target is our own system."""
    items = results(report)
    coverage: dict[str, Any] = {
        "code": code,
        "component": component(report),
        "system": system(report),
    }
    if own_system:
        coverage["model"] = model(report)
    return {
        "session_id": session_id,
        "target_url": target_url,
        "results": items,
        "coverage": coverage,
        "summary": summary(items),
        "started_at": report.started_at,
        "finished_at": report.finished_at,
    }
