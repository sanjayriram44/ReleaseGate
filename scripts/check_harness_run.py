"""Drive the course autograder harness (spec v2) the way a grader does, and check the format.

    python scripts/check_harness_run.py <tester_url> <target_url> [--own] [--system-url URL]

POST {tester}/test/setup {"target_url"} -> 201 {"session_id"}; POST /test/run -> 200 suite
report; GET /test/report -> the same body; a second run -> 409. With --system-url, also reads
the system's GET /test/report for the session (in CI the tester reaches the system as
http://api:8080 while this script reaches it as localhost). --own: the target is our own system,
so the report must carry coverage.model. Prints PASS or the problems; exits 1 on any problem.
WARNING: the run resets the target's data.
"""

import argparse
import sys
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tester.coverage import is_entry  # noqa: E402

OUTCOMES = {"pass", "fail", "error", "skip"}
SOURCES = {"tester", "system", "communication", "unknown"}


def _error_ok(resp: httpx.Response, status: int) -> bool:
    try:
        body = resp.json()
    except ValueError:
        return False
    return (
        resp.status_code == status
        and isinstance(body, dict)
        and isinstance(body.get("message"), str)
        and bool(body["message"].strip())
        and body.get("source") in SOURCES
    )


def check(
    tester: httpx.Client, target_url: str, own: bool, system: httpx.Client | None = None
) -> list[str]:
    problems: list[str] = []
    setup = tester.post("/test/setup", json={"target_url": target_url})
    body = (
        setup.json() if setup.headers.get("content-type", "").startswith("application/json") else {}
    )
    if setup.status_code != 201 or set(body) != {"session_id"} or not body.get("session_id"):
        return [
            f"tester setup: expected 201 {{session_id}}, got {setup.status_code} {setup.text[:200]}"
        ]
    sid = body["session_id"]
    if system is not None:
        sys_report = system.get("/test/report", params={"session_id": sid})
        code = (
            (sys_report.json().get("coverage") or {}).get("code")
            if sys_report.status_code == 200
            else None
        )
        if not is_entry(code):
            problems.append(f"system report: no valid coverage.code ({sys_report.status_code})")
    if not _error_ok(tester.get("/test/report", params={"session_id": sid}), 409):
        problems.append("tester report before the run: expected 409 {message, source}")
    run = tester.post("/test/run", json={"session_id": sid})
    if run.status_code != 200:
        return problems + [f"tester run: expected 200, got {run.status_code} {run.text[:200]}"]
    report: dict[str, Any] = run.json()
    for key in ("session_id", "target_url", "results", "coverage"):
        if key not in report:
            problems.append(f"report: missing {key}")
    if report.get("session_id") != sid or report.get("target_url") != target_url:
        problems.append("report: session_id or target_url differs from setup")
    results = report.get("results") or []
    ids = [r.get("test_id") for r in results]
    if not results or len(ids) != len(set(ids)) or not all(ids):
        problems.append("results: test_id values must be nonempty and unique")
    for r in results:
        if r.get("outcome") not in OUTCOMES or not str(r.get("message", "")).strip():
            problems.append(f"result {r.get('test_id')}: bad outcome or empty message")
        if r.get("outcome") == "error" and r.get("source") not in SOURCES:
            problems.append(f"result {r.get('test_id')}: error without a valid source")
        if r.get("required", True) and r.get("outcome") != "pass":
            problems.append(f"result {r.get('test_id')}: {r.get('outcome')}: {r.get('message')}")
    coverage = report.get("coverage") or {}
    wanted = {"code", "component", "system"} | ({"model"} if own else set())
    if set(coverage) != wanted:
        problems.append(f"coverage: expected keys {sorted(wanted)}, got {sorted(coverage)}")
    problems += [f"coverage.{k}: not a valid entry" for k, v in coverage.items() if not is_entry(v)]
    again = tester.get("/test/report", params={"session_id": sid})
    if again.status_code != 200 or again.json() != report:
        problems.append("tester report after the run: expected 200 with the same body")
    if not _error_ok(tester.post("/test/run", json={"session_id": sid}), 409):
        problems.append("a second run of the same session: expected 409 {message, source}")
    return problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tester_url")
    parser.add_argument("target_url")
    parser.add_argument("--own", action="store_true")
    parser.add_argument("--system-url")
    args = parser.parse_args(argv)
    with httpx.Client(base_url=args.tester_url, timeout=600) as tester:
        system = httpx.Client(base_url=args.system_url, timeout=30) if args.system_url else None
        try:
            problems = check(tester, args.target_url, args.own, system)
        finally:
            if system is not None:
                system.close()
    for p in problems:
        print(f"FAIL {p}")
    print("PASS harness run matches spec v2" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
