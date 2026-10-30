"""Check a deployment without changing it (CLAUDE.md §16.2, default mode).

    bash scripts/post_deploy_check.sh <base_url> <expected_sha> [--test-endpoints on|off]

1. GET /health answers 200 within --wait seconds (60), the database is writable, and the commit
   it reports is the expected one.
2. GET /openapi.json lists every contract operation this checkout has built (contract minus
   app/contract_status.py; minus the test endpoints when they're expected off).
3. The test endpoints are on or off as expected (GET /test, which only describes the service).
4. A malformed POST /api/v1/releases ({}) is 400 with the shared error shape, not 422.
5. GET /api/v1/vulnerabilities/CVE-2099-0001/affected-releases is 404 CVE_UNKNOWN or 503
   VULNERABILITY_SOURCE_UNREACHABLE within 15 s; skipped until that operation is built.

Run it from a checkout of the deployed commit: checks 2 and 5 read the contract and the
not-yet-built list from this checkout. Prints PASS/FAIL/SKIP per check, then PASS or FAIL;
exits 0 on PASS, 1 on FAIL, 2 on bad arguments. --full (destructive: tester run, smoke test,
restart) is not built yet.
"""

import argparse
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import yaml

from app.contract_status import NOT_YET_IMPLEMENTED

ROOT = Path(__file__).resolve().parent.parent
METHODS = ("get", "put", "post", "patch", "delete")
CVE_QUERY = ("/api/v1/vulnerabilities/{cveId}/affected-releases", "get")
UNKNOWN_CVE = "CVE-2099-0001"
CVE_LIMIT_S = 15.0
_SHA = re.compile(r"^[0-9a-f]{7,40}$")


@dataclass
class Response:
    status: int  # 0 when there was no HTTP answer (refused, timed out)
    body: Any  # parsed JSON, or None
    seconds: float


@dataclass(frozen=True)
class Check:
    name: str
    outcome: str  # PASS, FAIL or SKIP
    detail: str


Fetch = Callable[[str, str, Any, dict[str, str], float], Response]


def http_fetch(base_url: str) -> Fetch:
    base = base_url.rstrip("/")

    def fetch(
        method: str, path: str, body: Any, headers: dict[str, str], timeout: float
    ) -> Response:
        started = time.perf_counter()
        try:
            r = httpx.request(method, base + path, json=body, headers=headers, timeout=timeout)
        except httpx.HTTPError:
            return Response(0, None, time.perf_counter() - started)
        try:
            parsed = r.json()
        except ValueError:
            parsed = None
        return Response(r.status_code, parsed, time.perf_counter() - started)

    return fetch


def load_contract(path: Path = ROOT / "docs/openapi.yaml") -> dict[str, Any]:
    contract: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return contract


def _operations(doc: dict[str, Any]) -> set[tuple[str, str]]:
    return {(p, m) for p, item in doc.get("paths", {}).items() for m in METHODS if m in item}


def _is_test_path(path: str) -> bool:
    return path == "/test" or path.startswith(("/test/", "/api/v1/test/"))


def _error(body: Any) -> tuple[str, str] | None:
    """(code, message) if body has the shared error shape with non-empty strings, else None."""
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return None
    code, message = error.get("code"), error.get("message")
    if isinstance(code, str) and code and isinstance(message, str) and message:
        return code, message
    return None


def check_health(fetch: Fetch, expected_sha: str, wait_s: float) -> Check:
    deadline = time.monotonic() + wait_s
    while True:
        r = fetch("GET", "/health", None, {}, 10)
        if r.status != 0 or time.monotonic() >= deadline:
            break
        time.sleep(2)
    if r.status == 0:
        return Check("health", "FAIL", f"no answer within {wait_s:.0f} s")
    body = r.body if isinstance(r.body, dict) else {}
    if r.status != 200 or body.get("status") != "ok":
        return Check("health", "FAIL", f"{r.status} {body} (database not writable?)")
    live = str(body.get("commit", ""))
    if (
        not live
        or live == "unknown"
        or not (live.startswith(expected_sha) or expected_sha.startswith(live))
    ):
        return Check("health", "FAIL", f"commit {live or 'missing'}, expected {expected_sha}")
    return Check("health", "PASS", f"ok, commit {live[:12]}")


def check_openapi(
    fetch: Fetch, contract: dict[str, Any], test_endpoints: bool, not_built: set[tuple[str, str]]
) -> Check:
    r = fetch("GET", "/openapi.json", None, {}, 10)
    if r.status != 200 or not isinstance(r.body, dict):
        return Check("openapi", "FAIL", f"GET /openapi.json answered {r.status}")
    expected = {
        op for op in _operations(contract) - not_built if test_endpoints or not _is_test_path(op[0])
    }
    missing = sorted(expected - _operations(r.body))
    if missing:
        names = ", ".join(f"{m.upper()} {p}" for p, m in missing)
        return Check("openapi", "FAIL", f"missing {names}")
    return Check("openapi", "PASS", f"all {len(expected)} built contract operations listed")


def check_test_endpoints(fetch: Fetch, test_endpoints: bool) -> Check:
    r = fetch("GET", "/test", None, {}, 10)
    want = 200 if test_endpoints else 404
    state = "on" if test_endpoints else "off"
    if r.status != want:
        return Check("test-endpoints", "FAIL", f"expected {state}, GET /test answered {r.status}")
    return Check("test-endpoints", "PASS", f"{state} (GET /test answered {r.status})")


def check_malformed_request(fetch: Fetch) -> Check:
    r = fetch("POST", "/api/v1/releases", {}, {"X-User-Id": "post-deploy-check"}, 10)
    error = _error(r.body)
    if r.status != 400 or error is None or error[0] != "INVALID_REQUEST":
        return Check("malformed-request", "FAIL", f"{r.status} {r.body}")
    return Check("malformed-request", "PASS", f"400 {error[0]}: {error[1]}")


def check_cve_query(fetch: Fetch, not_built: set[tuple[str, str]]) -> Check:
    if CVE_QUERY in not_built:
        return Check("cve-query", "SKIP", "affected-releases is not built yet")
    path = CVE_QUERY[0].replace("{cveId}", UNKNOWN_CVE)
    r = fetch("GET", path, None, {}, CVE_LIMIT_S)
    error = _error(r.body)
    allowed = {(404, "CVE_UNKNOWN"), (503, "VULNERABILITY_SOURCE_UNREACHABLE")}
    if r.status == 0:
        return Check("cve-query", "FAIL", f"no answer within {CVE_LIMIT_S:.0f} s")
    if error is None or (r.status, error[0]) not in allowed:
        return Check("cve-query", "FAIL", f"{r.status} {r.body}")
    if r.seconds > CVE_LIMIT_S:
        return Check("cve-query", "FAIL", f"{r.status} {error[0]} after {r.seconds:.1f} s")
    return Check("cve-query", "PASS", f"{r.status} {error[0]} in {r.seconds:.2f} s")


def run_checks(
    fetch: Fetch,
    expected_sha: str,
    test_endpoints: bool,
    contract: dict[str, Any],
    wait_s: float = 60,
    not_built: set[tuple[str, str]] | None = None,
) -> list[Check]:
    pending = set(NOT_YET_IMPLEMENTED) if not_built is None else not_built
    return [
        check_health(fetch, expected_sha, wait_s),
        check_openapi(fetch, contract, test_endpoints, pending),
        check_test_endpoints(fetch, test_endpoints),
        check_malformed_request(fetch),
        check_cve_query(fetch, pending),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("base_url")
    parser.add_argument("expected_sha")
    parser.add_argument("--test-endpoints", choices=["on", "off"], default="on")
    parser.add_argument("--wait", type=float, default=60, help="seconds to wait for /health")
    parser.add_argument("--full", action="store_true", help="destructive checks (not built)")
    args = parser.parse_args(argv)
    if args.full:
        print("--full (destructive) mode is not built yet", file=sys.stderr)
        return 2
    sha = args.expected_sha.lower()
    if not _SHA.match(sha):
        print(f"expected_sha must be 7-40 hex digits, got {args.expected_sha}", file=sys.stderr)
        return 2
    checks = run_checks(
        http_fetch(args.base_url), sha, args.test_endpoints == "on", load_contract(), args.wait
    )
    for c in checks:
        print(f"{c.outcome:4}  {c.name:17}  {c.detail}")
    failed = any(c.outcome == "FAIL" for c in checks)
    print("FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
