"""The destructive --full post-deploy run (CLAUDE.md §8): `post_deploy_check.sh --full`.

WARNING: it resets the target, so run it only on the evaluation deployment after warning Team 2.
After the non-destructive checks pass, it runs, printing PASS/FAIL/SKIP for each:

1. tester: the whole shared suite (AC-01..AC-09 and the contract) against the target over HTTP.
2. smoke: scripts/smoke.sh against the target.
3. ac10-restart: AC-10 snapshot (tester/ac10.py), the --restart-cmd you give (for the VM:
   `docker compose restart api` over gcloud ssh), wait for /health, then verify. SKIP without a
   restart command.
4. reseed: reset (which returns the clock to real time) and the demo data: ExampleGateway 1.0.0
   with the 25-component SBOM, the fixture vulnerability records, one mandatory incident for
   CVE-2023-25577 with early-warning and notification report data (one field left out).

--report FILE writes the Mode: full deploy report that scripts/metrics.py reads (Result, AC-10
and Latency lines).
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from scripts.post_deploy_check import Check
from tester import ac10
from tester.checks import Fixtures, Report, run

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
DEMO_USER = {"X-User-Id": "demo-seed"}
_SECONDS = re.compile(r"\bin ([0-9]+(?:\.[0-9]+)?) s\b")

Connect = Callable[[], httpx.Client]
Step = Callable[[], tuple[bool, str]]


@dataclass
class FullResult:
    checks: list[Check] = field(default_factory=list)
    tester: Report | None = None
    ac10: str = "SKIP"  # PASS, FAIL or SKIP
    latency: tuple[float | None, float | None] = (None, None)


def latency(report: Report) -> tuple[float | None, float | None]:
    """The slowest AC-04 query and AC-05 error the tester timed ("... in 0.03 s")."""

    def slowest(ac: str) -> float | None:
        times = [
            float(m.group(1))
            for c in report.checks
            if c.ac == ac
            for m in [_SECONDS.search(c.actual)]
            if m
        ]
        return max(times) if times else None

    return slowest("AC-04"), slowest("AC-05")


def _ok(resp: httpx.Response, status: int) -> Any:
    if resp.status_code != status:
        raise ac10.SeedFailed(
            f"{resp.request.method} {resp.request.url.path}: {resp.status_code} {resp.text[:200]}"
        )
    return resp.json() if resp.content else None


def seed_demo(client: httpx.Client, fixtures: Path = FIXTURES) -> dict[str, str]:
    """Reset the target (real clock again) and store the demo data; returns the ids."""
    records = json.loads((fixtures / "vulnerabilities.json").read_text())["records"]
    complete = json.loads((fixtures / "report_cases.json").read_text())["incidents"][0]
    _ok(client.post("/api/v1/test/reset"), 204)
    _ok(
        client.put(
            "/api/v1/test/vulnerability-source", json={"mode": "available", "records": records}
        ),
        200,
    )
    rel = _ok(
        client.post(
            "/api/v1/releases",
            json={
                "product": "ExampleGateway",
                "version": "1.0.0",
                "support_end_date": "2027-12-31",
            },
            headers=DEMO_USER,
        ),
        201,
    )
    sbom = (fixtures / "sbom_25_components.json").read_bytes()
    _ok(
        client.put(
            f"/api/v1/releases/{rel['release_id']}/sbom",
            content=sbom,
            headers={**DEMO_USER, "Content-Type": "application/json"},
        ),
        200,
    )
    inc = _ok(
        client.post(
            "/api/v1/incidents",
            json={
                "cve_id": "CVE-2023-25577",
                "awareness_at": "2026-11-01T09:00:00Z",
                "classification": "mandatory",
                "rationale": "Demo: active exploitation of werkzeug 2.2.2 in ExampleGateway 1.0.0.",
            },
            headers=DEMO_USER,
        ),
        201,
    )
    iid = inc["incident_id"]
    notification = {
        k: v
        for k, v in complete["report_data"]["vulnerability_notification"].items()
        if k != "user_mitigations"  # left out so the report shows a missing field
    }
    for stage, data in (
        ("early_warning", complete["report_data"]["early_warning"]),
        ("vulnerability_notification", notification),
    ):
        _ok(
            client.put(
                f"/api/v1/incidents/{iid}/report-data/{stage}", json=data, headers=DEMO_USER
            ),
            200,
        )
    return {"release": rel["release_id"], "incident": iid}


def _step(name: str, action: Callable[[], tuple[bool, str]]) -> Check:
    try:
        ok, detail = action()
    except (httpx.HTTPError, ac10.SeedFailed) as exc:
        return Check(name, "FAIL", f"{type(exc).__name__}: {exc}")
    return Check(name, "PASS" if ok else "FAIL", detail)


def run_full(
    connect: Connect,
    smoke: Step,
    restart: Step | None,
    wait_healthy: Callable[[], Check],
    fixtures: Path = FIXTURES,
) -> FullResult:
    result = FullResult()

    def tester() -> tuple[bool, str]:
        with connect() as client:
            report = run(client, Fixtures.load(fixtures), str(client.base_url))
        result.tester = report
        result.latency = latency(report)
        s = report.summary
        req = f"{s['required_passed']}/{s['required_passed'] + s['required_failed']}"
        info = (
            f"{s['informational_passed']}/{s['informational_passed'] + s['informational_failed']}"
        )
        failed = [c.id for c in report.checks if c.required and not c.passed]
        detail = f"{req} required, {info} informational"
        detail += f"; failed: {', '.join(failed[:5])}" if failed else ""
        detail += f"; {report.error}" if report.error else ""
        return report.result == "pass", detail

    result.checks.append(_step("tester", tester))
    result.checks.append(_step("smoke", smoke))

    if restart is None:
        result.checks.append(Check("ac10-restart", "SKIP", "no --restart-cmd given"))
    else:

        def restart_check() -> tuple[bool, str]:
            with connect() as client:
                state = ac10.seed(client)
            restarted, how = restart()
            if not restarted:
                return False, f"restart failed: {how}"
            health = wait_healthy()
            if health.outcome != "PASS":
                return False, f"after restart: {health.detail}"
            with connect() as client:
                changed = ac10.verify(client, state)
            if changed:
                return False, f"changed after restart: {', '.join(changed)}"
            return True, "state unchanged after restart (same clock, exact JSON)"

        check = _step("ac10-restart", restart_check)
        result.checks.append(check)
        result.ac10 = check.outcome

    def reseed() -> tuple[bool, str]:
        with connect() as client:
            ids = seed_demo(client, fixtures)
        return True, f"demo data at real time: release {ids['release']}, incident {ids['incident']}"

    result.checks.append(_step("reseed", reseed))
    return result


def counts(nondestructive: list[Check], result: FullResult) -> tuple[int, int]:
    """Passed and total: the tester's required checks plus every non-skipped run step."""
    steps = [
        c for c in nondestructive + result.checks if c.name != "tester" and c.outcome != "SKIP"
    ]
    passed = sum(c.outcome == "PASS" for c in steps)
    total = len(steps)
    if result.tester is not None:
        s = result.tester.summary
        passed += s["required_passed"]
        total += s["required_passed"] + s["required_failed"]
    return passed, total


def write_report(
    path: Path, sha: str, base_url: str, nondestructive: list[Check], result: FullResult
) -> None:
    passed, total = counts(nondestructive, result)
    cve, err = result.latency
    lat = (
        f"slowest AC-04 query {cve:.2f} s; slowest AC-05 error {err:.2f} s (limits 10 s and 15 s)"
        if cve is not None and err is not None
        else "not measured (the tester's AC-04/AC-05 checks didn't run)"
    )
    info = ""
    if result.tester is not None:
        s = result.tester.summary
        informational = s["informational_passed"] + s["informational_failed"]
        info = f"; {s['informational_passed']}/{informational} informational"
    rows = [
        f"| {c.name} | {c.outcome} | {c.detail.replace('|', '/')} |"
        for c in nondestructive + result.checks
    ]
    lines = [
        f"# Full live run, {datetime.now(UTC):%Y-%m-%d}",
        "",
        f"**Commit:** `{sha}`",
        f"**Target:** `{base_url}`",
        "**Mode:** full (destructive: tester run, smoke test and an AC-10 restart; the demo data"
        " was re-seeded afterwards)",
        f"**Result:** {passed}/{total} passed (required tester checks, AC-01..AC-09 and the"
        f" contract, plus the run steps{info})",
        f"**AC-10:** {result.ac10}",
        f"**Latency:** {lat}",
        "",
        "| Step | Result | Detail |",
        "|---|---|---|",
        *rows,
        "",
        "**Main problem / owner:** _(fill in)_",
        "",
    ]
    path.write_text("\n".join(lines))
