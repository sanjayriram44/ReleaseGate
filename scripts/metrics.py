"""Measure the goals in docs/goals.md and write the current values to docs/metrics.md.

    .venv/bin/python scripts/metrics.py            # everything, including the network reads
    .venv/bin/python scripts/metrics.py --offline  # skip GitHub CI status and the live /health

Nothing here is destructive: the AC checks run in-process against a throwaway database, and the
live deployment is only read (GET /health). A tester run against the live URL resets its data,
so live and cross-team results come from docs/test-reports/ instead, named
YYYY-MM-DD-<cross-team-ours-to-team2 | cross-team-team2-to-ours | deploy>.md, each with a
"Result: X/Y passed" line and the commit SHA. Coverage above .coverage-baseline raises it.
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

LIVE_SYSTEM = "http://136.116.160.182:8080"
REPORTS = ROOT / "docs/test-reports"
BASELINE = ROOT / ".coverage-baseline"
COVERAGE_TARGET = 85.0
INTEROP_TARGET = 0.95
NOT_YET = "not measurable yet"
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


def live_commit() -> str | None:
    """The commit the live /health reports; None until §16.1 adds it (or if unreachable)."""
    try:
        commit = _get_json(f"{LIVE_SYSTEM}/health").get("commit")
    except Exception:
        return None
    return str(commit) if commit else None


@dataclass(frozen=True)
class RunReport:
    name: str
    passed: int | None
    total: int | None
    commit: str | None

    @property
    def result(self) -> str:
        if self.passed is None or self.total is None:
            return f"`{self.name}`: no `Result: X/Y passed` line"
        return f"`{self.name}`: {self.passed}/{self.total}"


def latest_report(kind: str) -> RunReport | None:
    """The newest docs/test-reports/YYYY-MM-DD-<kind>.md, parsed."""
    paths = sorted(REPORTS.glob(f"????-??-??-{kind}.md"), reverse=True)
    if not paths:
        return None
    text = paths[0].read_text()
    result = re.search(r"Result:\**\s*(\d+)\s*/\s*(\d+) passed", text)
    commit = re.search(r"(?i)commit\W+([0-9a-f]{7,40})\b", text)
    return RunReport(
        paths[0].name,
        int(result.group(1)) if result else None,
        int(result.group(2)) if result else None,
        commit.group(1) if commit else None,
    )


def coverage_baseline(coverage: float | None) -> float | None:
    """The stored baseline; raised to the current coverage when coverage rises."""
    baseline = float(BASELINE.read_text()) if BASELINE.exists() else None
    if coverage is not None and (baseline is None or round(coverage, 2) > baseline):
        BASELINE.write_text(f"{coverage:.2f}\n")
    return baseline


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


def _all_pass(checks: dict[str, tuple[int, int]], acs: list[str]) -> bool:
    return all(ac in checks and checks[ac][0] == checks[ac][1] for ac in acs)


def _yes(ok: bool) -> str:
    return "yes" if ok else "no"


def g1(checks: dict[str, tuple[int, int]]) -> tuple[str, str]:
    value = ", ".join(f"{ac} {_ac_cell(checks, ac)}" for ac in PHASE4_ACS)
    if not any(ac in checks for ac in PHASE4_ACS):
        return value, f"{NOT_YET} (AC-04..AC-07 not built)"
    if not _all_pass(checks, PHASE4_ACS):
        return value, "no"
    live = latest_report("deploy")
    if live is None or live.total is None:
        return value + "; live: no `--full` deploy report", f"{NOT_YET} (no live run)"
    return value + f"; live {live.result}", _yes(live.passed == live.total)


def g3() -> tuple[str, str]:
    reports = {d: latest_report(f"cross-team-{d}") for d in ("ours-to-team2", "team2-to-ours")}
    value = "; ".join(r.result if r else f"{d}: no report" for d, r in reports.items())
    found = [r for r in reports.values() if r and r.total]
    if len(found) < len(reports):
        return value, f"{NOT_YET} (needs a report each way)"
    ok = all(
        r.passed is not None and r.total and r.passed / r.total >= INTEROP_TARGET for r in found
    )
    return value + " (failure owners: see the reports)", _yes(ok)


def g4(checks: dict[str, tuple[int, int]]) -> tuple[str, str]:
    if "AC-04" not in checks or "AC-05" not in checks:
        return "AC-04/AC-05 checks not built", NOT_YET
    return (
        "in-process run is a lower bound only; see container-smoke and the live `--full` run",
        f"{NOT_YET} (no container-smoke or live latency recorded)",
    )


def g5(coverage: float | None) -> tuple[str, str]:
    if coverage is None:
        return "no pytest-cov", NOT_YET
    baseline = coverage_baseline(coverage)
    base = f"{baseline:.2f}%" if baseline is not None else "none stored"
    ok = coverage >= COVERAGE_TARGET and (baseline is None or round(coverage, 2) >= baseline)
    return f"{coverage:.2f}% (baseline {base})", _yes(ok)


def g6(offline: bool) -> tuple[str, str]:
    if offline:
        return "skipped (--offline)", NOT_YET
    live = live_commit()
    if live is None:
        return "live `/health` reports no commit yet (§16.1)", NOT_YET
    deploy = latest_report("deploy")
    if deploy is None or deploy.commit is None:
        return f"live `{live[:7]}`; no deploy report", NOT_YET
    same = live.startswith(deploy.commit) or deploy.commit.startswith(live)
    passed = deploy.total is not None and deploy.passed == deploy.total
    return f"live `{live[:7]}`; {deploy.result}, commit `{deploy.commit[:7]}`", _yes(
        same and passed
    )


def render(offline: bool) -> str:
    checks = tester_checks()
    summary, coverage = pytest_result()
    ci = "skipped (--offline)" if offline else ci_status()
    head = _git("rev-parse", "--short", "HEAD")
    g2_value = ", ".join(f"{ac} {_ac_cell(checks, ac)}" for ac in PHASE3_ACS)
    g2_ok = _all_pass(checks, PHASE3_ACS) and "failed" not in summary
    rows = [
        ("G1 Phase 4 ACs", *g1(checks), "100% in-process and live"),
        ("G2 No regressions", f"{g2_value}; pytest: {summary}", _yes(g2_ok), "100%"),
        ("G3 Interoperability", *g3(), "≥ 95% of in-scope tests each way"),
        ("G4 Timeliness", *g4(checks), "≤ 10 s; ≤ 15 s"),
        ("G5 Coverage of `app/`", *g5(coverage), f"≥ {COVERAGE_TARGET:.0f}%, ≥ baseline"),
        ("G6 Deployment", *g6(offline), "live commit = deployed commit; checks pass"),
    ]
    lines = [
        "# Metrics",
        "",
        f"Generated by `scripts/metrics.py` at {datetime.now(UTC):%Y-%m-%dT%H:%M:%SZ}"
        f" from `{head}`. Goals: `docs/goals.md`.",
        "",
        "| Goal | Current value | Target | Met |",
        "|---|---|---|---|",
        *(f"| {goal} | {value} | {target} | {met} |" for goal, value, met, target in rows),
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
