"""CI stage F helpers (CLAUDE.md §15): the tester against a running system, and the restart check.

    python scripts/container_smoke.py tester <base_url>
    python scripts/container_smoke.py seed <base_url> <state.json>
    python scripts/container_smoke.py verify <base_url> <state.json>

`tester` runs every check (AC-01..AC-07) and fails unless all required checks pass; it resets
the target. `seed` registers a release, uploads the shared SBOM and opens a mandatory incident
with one submission, then saves what the API returned. After `docker compose restart api`,
`verify` sets the same clock (the test clock is in memory) and checks that the release,
components, incident, computed deadlines and audit entries are unchanged (AC-10 for REQ-01,
REQ-02, REQ-05, REQ-06). Exits 0 on success, 1 on failure.
"""

import json
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

USER = {"X-User-Id": "container-smoke"}
CLOCK = "2026-11-03T12:00:00Z"


def run_tester(client: httpx.Client) -> bool:
    from tester.checks import Fixtures, run

    report = run(client, Fixtures.load(ROOT / "fixtures"), str(client.base_url))
    for check in report.checks:
        if check.required and not check.passed:
            print(f"FAIL {check.id}: expected {check.expected}; got {check.actual}")
    print(f"tester: {report.result} {report.summary} {report.error or ''}")
    return report.result == "pass"


def _ok(resp: httpx.Response, status: int) -> Any:
    if resp.status_code != status:
        raise SystemExit(
            f"{resp.request.method} {resp.request.url.path}: {resp.status_code} {resp.text}"
        )
    return resp.json() if resp.content else None


def snapshot(client: httpx.Client, release_id: str, incident_id: str) -> dict[str, Any]:
    return {
        "release": _ok(client.get(f"/api/v1/releases/{release_id}"), 200),
        "components": _ok(client.get(f"/api/v1/releases/{release_id}/components"), 200),
        "incident": _ok(client.get(f"/api/v1/incidents/{incident_id}"), 200),
        "audit": _ok(client.get("/api/v1/audit-logs"), 200),
    }


def seed(client: httpx.Client) -> dict[str, Any]:
    _ok(client.post("/api/v1/test/reset"), 204)
    _ok(client.put("/api/v1/test/clock", json={"now": CLOCK}), 200)
    rel = _ok(
        client.post(
            "/api/v1/releases",
            json={"product": "SmokeGateway", "version": "1.0.0", "support_end_date": "2027-12-31"},
            headers=USER,
        ),
        201,
    )
    sbom = (ROOT / "fixtures/sbom_25_components.json").read_bytes()
    _ok(
        client.put(
            f"/api/v1/releases/{rel['release_id']}/sbom",
            content=sbom,
            headers={**USER, "Content-Type": "application/json"},
        ),
        200,
    )
    inc = _ok(
        client.post(
            "/api/v1/incidents",
            json={
                "awareness_at": "2026-11-01T10:00:00Z",
                "classification": "mandatory",
                "rationale": "Restart check.",
            },
            headers=USER,
        ),
        201,
    )
    _ok(
        client.post(
            f"/api/v1/incidents/{inc['incident_id']}/submissions",
            json={"stage": "early_warning", "submitted_at": "2026-11-02T09:00:00Z"},
            headers=USER,
        ),
        201,
    )
    return {
        "ids": [rel["release_id"], inc["incident_id"]],
        **snapshot(client, rel["release_id"], inc["incident_id"]),
    }


def verify(client: httpx.Client, state: dict[str, Any]) -> list[str]:
    _ok(client.put("/api/v1/test/clock", json={"now": CLOCK}), 200)
    now = snapshot(client, *state["ids"])
    return [key for key in ("release", "components", "incident", "audit") if now[key] != state[key]]


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in ("tester", "seed", "verify"):
        print(__doc__)
        return 2
    with httpx.Client(base_url=argv[1].rstrip("/"), timeout=30) as client:
        if argv[0] == "tester":
            return 0 if run_tester(client) else 1
        state_file = Path(argv[2])
        if argv[0] == "seed":
            state_file.write_text(json.dumps(seed(client)))
            print("seeded", state_file)
            return 0
        changed = verify(client, json.loads(state_file.read_text()))
        print("unchanged after restart" if not changed else f"CHANGED after restart: {changed}")
        return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
