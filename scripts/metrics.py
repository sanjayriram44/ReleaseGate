"""Measure the goals in docs/goals.md and write the current values to docs/metrics.md.

    .venv/bin/python scripts/metrics.py            # everything, including the network reads
    .venv/bin/python scripts/metrics.py --offline  # skip GitHub CI status and the live /health

Nothing here is destructive: the AC checks run in-process against a throwaway database, and the
live deployment is only read (GET /health). A tester run against the live URL resets its data,
so that result comes from docs/test-reports/ instead.
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LIVE_SYSTEM = "http://136.116.160.182:8080"
COVERAGE_TARGET = 85.0
PHASE4_ACS = ["AC-04", "AC-05", "AC-06", "AC-07"]
PHASE3_ACS = ["AC-01", "AC-02", "AC-03", "contract"]


def _get_json(url: str, timeout: float = 10) -> Any:
    resp = httpx.get(url, headers={"Accept": "application/json"}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else ""


def tester_checks() -> dict[str, tuple[int, int]]:
    """Required checks per AC from an in-process tester run: {ac: (passed, total)}."""
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app
    from tester.checks import Fixtures, run

    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(Settings(db_path=f"{tmp}/metrics.db", enable_test_endpoints=True))
        with TestClient(app) as client:
            report = run(client, Fixtures.load(ROOT / "fixtures"), "in-process")
    per_ac: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for check in report.checks:
        if check.required:
            per_ac[check.ac][0] += int(check.passed)
            per_ac[check.ac][1] += 1
    return {ac: (p, t) for ac, (p, t) in per_ac.items()}


def pytest_result() -> tuple[str, float | None]:
    """The pytest summary line and app/ line coverage (None without pytest-cov)."""
    with tempfile.TemporaryDirectory() as tmp:
        cov_file = Path(tmp) / "coverage.json"
        cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
        has_cov = subprocess.run(
            [sys.executable, "-c", "import pytest_cov"], capture_output=True
        ).returncode
        if has_cov == 0:
            cmd += ["--cov=app", f"--cov-report=json:{cov_file}"]
        out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        lines = [ln for ln in out.stdout.splitlines() if re.search(r"\d+ (passed|failed)", ln)]
        summary = lines[-1].strip("= ") if lines else f"pytest exited {out.returncode}"
        coverage = None
        if cov_file.exists():
            coverage = float(json.loads(cov_file.read_text())["totals"]["percent_covered"])
    return summary, coverage


def ci_status() -> str:
    remote = _git("remote", "get-url", "origin")
    match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", remote)
    if not match:
        return "unknown (no GitHub remote)"
    try:
        data = _get_json(
            f"https://api.github.com/repos/{match.group(1)}/actions/runs?branch=main&per_page=1"
        )
    except Exception as exc:
        return f"unknown ({type(exc).__name__})"
    if not data.get("workflow_runs"):
        return "no runs"
    run = data["workflow_runs"][0]
    result = run["conclusion"] or run["status"]
    return f"{result} on `{run['head_sha'][:7]}` ({run['display_title']})"


def deployed_commit() -> str:
    try:
        health = _get_json(f"{LIVE_SYSTEM}/health")
    except Exception as exc:
        return f"unreachable ({type(exc).__name__})"
    return str(health.get("commit") or "not reported by /health yet")


def latest_phase_tag() -> tuple[str, str]:
    tag = _git("describe", "--tags", "--match", "phase*", "--abbrev=0")
    return (tag, _git("rev-list", "-n", "1", tag)) if tag else ("none", "")


def cross_team_reports() -> list[tuple[str, str]]:
    """(file, result line) for each docs/test-reports/*cross-team*.md, newest first."""
    out = []
    for path in sorted((ROOT / "docs/test-reports").glob("*cross-team*.md"), reverse=True):
        match = re.search(r"^\*\*Result:\*\*\s*(.+)$", path.read_text(), re.MULTILINE)
        out.append((path.name, match.group(1) if match else "no **Result:** line"))
    return out


def blocked_issues() -> list[str]:
    path = ROOT / "docs/issues.md"
    if not path.exists():
        return []
    return [
        line[len("- [ ] ") :]
        for line in path.read_text().splitlines()
        if line.startswith("- [ ] ") and "**blocked:" in line
    ]


def _ac_cell(checks: dict[str, tuple[int, int]], ac: str) -> str:
    if ac not in checks:
        return "not built"
    passed, total = checks[ac]
    return f"{passed}/{total}" + (" ✅" if passed == total else " ❌")


def render(offline: bool) -> str:
    checks = tester_checks()
    summary, coverage = pytest_result()
    tag, tag_sha = latest_phase_tag()
    deployed = "skipped (--offline)" if offline else deployed_commit()
    ci = "skipped (--offline)" if offline else ci_status()
    reports = cross_team_reports()
    head = _git("rev-parse", "--short", "HEAD")

    def all_pass(acs: list[str]) -> bool:
        return all(ac in checks and checks[ac][0] == checks[ac][1] for ac in acs)

    cov_text = f"{coverage:.1f}%" if coverage is not None else "not measured (no pytest-cov)"
    cov_ok = coverage is not None and coverage >= COVERAGE_TARGET
    g6_ok = bool(tag_sha) and deployed.startswith(tag_sha[:7])
    lines = [
        "# Metrics",
        "",
        f"Generated by `scripts/metrics.py` at {datetime.now(UTC):%Y-%m-%dT%H:%M:%SZ}"
        f" from `{head}`. Goals: `docs/goals.md`.",
        "",
        "| Goal | Current value | Target | Met |",
        "|---|---|---|---|",
        "| G1 Phase 4 ACs (in-process tester) | "
        + ", ".join(f"{ac} {_ac_cell(checks, ac)}" for ac in PHASE4_ACS)
        + " | 100%, also against the live URL | "
        + ("yes" if all_pass(PHASE4_ACS) else "no")
        + " |",
        "| G2 No regressions | "
        + ", ".join(f"{ac} {_ac_cell(checks, ac)}" for ac in PHASE3_ACS)
        + f"; pytest: {summary} | 100% | "
        + ("yes" if all_pass(PHASE3_ACS) and "failed" not in summary else "no")
        + " |",
        "| G3 Interoperability | "
        + ("; ".join(f"`{name}`: {res}" for name, res in reports[:2]) or "no cross-team report")
        + " | ≥ 95% each way | see reports |",
        "| G4 Timeliness | measured by the AC-04/AC-05 checks"
        + ("" if "AC-04" in checks else " (not built yet)")
        + " | ≤ 10 s; ≤ 15 s | "
        + ("yes" if all_pass(["AC-04", "AC-05"]) else "no")
        + " |",
        f"| G5 Coverage of `app/` | {cov_text} | ≥ {COVERAGE_TARGET:.0f}% |"
        f" {'yes' if cov_ok else 'no'} |",
        f"| G6 Deployment | deployed: {deployed}; latest tag: {tag}"
        + (f" (`{tag_sha[:7]}`)" if tag_sha else "")
        + f" | deployed = tagged | {'yes' if g6_ok else 'no'} |",
        "",
        f"**Last CI run on main:** {ci}",
        "",
        "## Open blocking questions",
        "",
    ]
    blocked = blocked_issues()
    lines += [f"- {item}" for item in blocked] if blocked else ["None."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true", help="skip network reads")
    parser.add_argument("--output", default=str(ROOT / "docs/metrics.md"))
    args = parser.parse_args()
    Path(args.output).write_text(render(args.offline))
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
