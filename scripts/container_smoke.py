"""CI stage F helpers (CLAUDE.md §15): the tester against a running system, and the restart check.

    python scripts/container_smoke.py tester <base_url>
    python scripts/container_smoke.py seed <base_url> <state.json>
    python scripts/container_smoke.py verify <base_url> <state.json>

`tester` runs every check (AC-01..AC-07) and fails unless all required checks pass; it resets
the target. `seed` and `verify` are AC-10's two steps (tester/ac10.py, the same code the
cross-team `python -m tester.ac10 snapshot|verify` runs): `seed` resets the target and stores a
release with a replaced SBOM, vulnerability records and a CVE query result, an incident with a fix
and a submission, report data for all three stages, and saves every response including the audit
log. After `docker compose restart api`, `verify` sets the same clock (the test clock is in
memory) and checks that every response is unchanged. Exits 0 on success, 1 on failure.
"""

import json
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tester import ac10  # noqa: E402  (needs ROOT on sys.path)


def run_tester(client: httpx.Client) -> bool:
    from tester.checks import Fixtures, run

    report = run(client, Fixtures.load(ROOT / "fixtures"), str(client.base_url))
    for check in report.checks:
        if check.required and not check.passed:
            print(f"FAIL {check.id}: expected {check.expected}; got {check.actual}")
    print(f"tester: {report.result} {report.summary} {report.error or ''}")
    return report.result == "pass"


def seed(client: httpx.Client) -> dict[str, Any]:
    return ac10.seed(client)


def verify(client: httpx.Client, state: dict[str, Any]) -> list[str]:
    return ac10.verify(client, state)


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
