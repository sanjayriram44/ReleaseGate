"""AC-10 (REQ-01, 02, 05, 06, 08): state survives a process restart, with 0 s timestamp drift.

A tester can't restart another team's server over HTTP, so AC-10 runs in two steps (P5-Q8,
proposed; docs/decisions.md):

    python -m tester.ac10 snapshot <base_url> <state.json>   # resets the target, seeds, saves
    # ... the system's owner restarts the service ...
    python -m tester.ac10 verify <base_url> <state.json>     # same clock, compare exactly

`snapshot` resets the target (it wipes its data), sets the test clock, and stores everything
AC-10 names plus the Phase 5 state: a release, an SBOM replaced by a second one, vulnerability
records and one CVE query result, a mandatory incident with a fix and a submission (computed
deadlines), report data for all three stages with the three generated reports, and the full
audit log. `verify` sets the same test clock again (it is held in memory, so a restart clears it)
and compares every response with the saved JSON. Only the shared contract and the test-control
endpoints are used, so it works against either team's system. Exit codes: 0 unchanged,
1 changed, 2 usage. scripts/container_smoke.py runs the same code in CI stage F.
"""

import json
import sys
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
USER = {"X-User-Id": "ac10-tester"}
JSON = {**USER, "Content-Type": "application/json"}
CLOCK = "2026-11-20T12:00:00Z"
CVE = "CVE-2023-25577"  # werkzeug 2.2.2, in sbom_25_components.json but not sbom_patched.json
STAGES = ("early_warning", "vulnerability_notification", "final_report")
KEYS = ("release", "components", "cve_query", "incident", "reports", "audit")


class SeedFailed(Exception):
    pass


def _ok(resp: httpx.Response, status: int) -> Any:
    if resp.status_code != status:
        raise SeedFailed(
            f"{resp.request.method} {resp.request.url.path}: {resp.status_code} {resp.text}"
        )
    return resp.json() if resp.content else None


def _read(resp: httpx.Response) -> Any:
    """The body of a 200; otherwise the status and text, so a lost record compares unequal."""
    if resp.status_code == 200:
        return resp.json()
    return {"status": resp.status_code, "body": resp.text}


def snapshot(client: httpx.Client, ids: dict[str, str]) -> dict[str, Any]:
    rid, iid = ids["release"], ids["incident"]
    return {
        "release": _read(client.get(f"/api/v1/releases/{rid}")),
        "components": _read(client.get(f"/api/v1/releases/{rid}/components")),
        "cve_query": _read(client.get(f"/api/v1/vulnerabilities/{CVE}/affected-releases")),
        "incident": _read(client.get(f"/api/v1/incidents/{iid}")),
        "reports": {s: _read(client.get(f"/api/v1/incidents/{iid}/reports/{s}")) for s in STAGES},
        "audit": _read(client.get("/api/v1/audit-logs")),
    }


def seed(client: httpx.Client, fixtures: Path = FIXTURES) -> dict[str, Any]:
    """Reset the target and store the AC-10 state; returns the ids, clock and snapshot."""
    cases = json.loads((fixtures / "report_cases.json").read_text())["incidents"]
    complete, incomplete = cases[0], cases[1]
    records = json.loads((fixtures / "vulnerabilities.json").read_text())["records"]

    _ok(client.post("/api/v1/test/reset"), 204)
    _ok(client.put("/api/v1/test/clock", json={"now": CLOCK}), 200)
    _ok(
        client.put(
            "/api/v1/test/vulnerability-source", json={"mode": "available", "records": records}
        ),
        200,
    )
    rel = _ok(
        client.post(
            "/api/v1/releases",
            json={"product": "AC10Gateway", "version": "1.0.0", "support_end_date": "2027-12-31"},
            headers=USER,
        ),
        201,
    )
    rid = rel["release_id"]
    for sbom in ("sbom_patched.json", "sbom_25_components.json"):  # store, then replace
        sbom_bytes = (fixtures / sbom).read_bytes()
        _ok(client.put(f"/api/v1/releases/{rid}/sbom", content=sbom_bytes, headers=JSON), 200)
    inc = _ok(
        client.post(
            "/api/v1/incidents",
            json={**complete["create"], "rationale": "AC-10 restart check."},
            headers=USER,
        ),
        201,
    )
    iid = inc["incident_id"]
    _ok(
        client.patch(
            f"/api/v1/incidents/{iid}",
            json={"fix_available_at": complete["fix_available_at"]},
            headers=USER,
        ),
        200,
    )
    _ok(
        client.post(
            f"/api/v1/incidents/{iid}/submissions",
            json={"stage": "early_warning", "submitted_at": "2026-11-10T18:00:00Z"},
            headers=USER,
        ),
        201,
    )
    for stage in STAGES:
        # The incomplete notification keeps missing_fields non-empty across the restart.
        source = incomplete if stage == "vulnerability_notification" else complete
        _ok(
            client.put(
                f"/api/v1/incidents/{iid}/report-data/{stage}",
                json=source["report_data"][stage],
                headers=USER,
            ),
            200,
        )
    ids = {"release": rid, "incident": iid}
    return {"ids": ids, "clock": CLOCK, "snapshot": snapshot(client, ids)}


def verify(client: httpx.Client, state: dict[str, Any]) -> list[str]:
    """The snapshot keys whose JSON differs after the restart, in KEYS order."""
    resp = client.put("/api/v1/test/clock", json={"now": state["clock"]})
    if resp.status_code != 200:
        return list(KEYS)
    now = snapshot(client, state["ids"])
    return [key for key in KEYS if now[key] != state["snapshot"][key]]


def make_client(base_url: str) -> httpx.Client:
    return httpx.Client(base_url=base_url.rstrip("/"), timeout=30)


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] not in ("snapshot", "verify"):
        print(__doc__)
        return 2
    command, url, path = argv
    with make_client(url) as client:
        if command == "snapshot":
            try:
                state = seed(client)
            except (SeedFailed, httpx.HTTPError) as exc:
                print(f"AC-10 snapshot FAILED: {exc}")
                return 1
            Path(path).write_text(json.dumps({"target": url, **state}, indent=2))
            print(f"AC-10 snapshot saved to {path}; restart the service, then run verify")
            return 0
        try:
            changed = verify(client, json.loads(Path(path).read_text()))
        except httpx.HTTPError as exc:
            print(f"AC-10 FAIL: target unreachable after restart: {exc}")
            return 1
    if changed:
        print(f"AC-10 FAIL: changed after restart: {', '.join(changed)}")
        return 1
    print("AC-10 PASS: state unchanged after restart")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
