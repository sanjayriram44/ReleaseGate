"""Black-box checks of any ReleaseGate-compatible system over the shared HTTP contract.

Required checks come from docs/openapi.yaml and AC-01..AC-03 and decide pass/fail.
Informational checks cover provisional pod decisions (docs/decisions.md); they are reported
but never fail a run, so another team is not penalised for a choice the pod has not made.
"""

import json
import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

USER = {"X-User-Id": "releasegate-tester"}
JSON = {"Content-Type": "application/json"}
EXCERPT = 400


@dataclass
class Check:
    id: str
    ac: str
    title: str
    required: bool
    passed: bool
    expected: str
    actual: str
    request: str = ""
    response: str = ""
    note: str = ""


@dataclass
class Report:
    run_id: str
    target_base_url: str
    started_at: str
    finished_at: str = ""
    duration_ms: int = 0
    result: str = "error"  # pass | fail | error
    error: str | None = None
    summary: dict[str, int] = field(default_factory=dict)
    checks: list[Check] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Fixtures:
    releases: dict[str, Any]
    sbom_bytes: bytes

    @classmethod
    def load(cls, directory: Path) -> "Fixtures":
        releases = json.loads((directory / "releases.json").read_text())
        return cls(releases, (directory / releases["ac02"]["sbom_file"]).read_bytes())

    @property
    def sbom_components(self) -> list[tuple[str, str]]:
        doc = json.loads(self.sbom_bytes)
        return [(c["name"], c["version"]) for c in doc["components"]]


class TargetUnreachable(Exception):
    pass


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _excerpt(resp: httpx.Response) -> str:
    text = resp.text
    return text if len(text) <= EXCERPT else text[:EXCERPT] + "…"


def _json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except ValueError:
        return None


def _error_message(resp: httpx.Response) -> str | None:
    """The shared error shape: {"error": {"code": str, "message": str}}."""
    body = _json(resp)
    if not isinstance(body, dict) or not isinstance(body.get("error"), dict):
        return None
    err = body["error"]
    if not isinstance(err.get("code"), str) or not isinstance(err.get("message"), str):
        return None
    return str(err["message"])


class Runner:
    def __init__(self, client: httpx.Client, fixtures: Fixtures) -> None:
        self.client = client
        self.fx = fixtures
        self.checks: list[Check] = []

    # -- plumbing ---------------------------------------------------------------------------

    def call(self, method: str, path: str, **kw: Any) -> httpx.Response:
        try:
            return self.client.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise TargetUnreachable(f"{method} {path}: {type(exc).__name__}: {exc}") from exc

    def record(
        self,
        cid: str,
        ac: str,
        title: str,
        passed: bool,
        expected: str,
        actual: str,
        resp: httpx.Response | None = None,
        required: bool = True,
        note: str = "",
    ) -> bool:
        self.checks.append(
            Check(
                id=cid,
                ac=ac,
                title=title,
                required=required,
                passed=passed,
                expected=expected,
                actual=actual,
                request=f"{resp.request.method} {resp.request.url.path}" if resp else "",
                response=_excerpt(resp) if resp is not None else "",
                note=note,
            )
        )
        return passed

    def expect_status(
        self, cid: str, ac: str, title: str, resp: httpx.Response, want: int, required: bool = True
    ) -> bool:
        return self.record(
            cid,
            ac,
            title,
            resp.status_code == want,
            str(want),
            str(resp.status_code),
            resp,
            required,
        )

    def expect_rejection(
        self, cid: str, ac: str, title: str, resp: httpx.Response, want: int, required: bool = True
    ) -> bool:
        """A rejection needs the right status and the shared error shape with a reason."""
        msg = _error_message(resp)
        ok = resp.status_code == want and bool(msg and msg.strip())
        return self.record(
            cid,
            ac,
            title,
            ok,
            f"{want} with error.code and a non-empty error.message",
            f"{resp.status_code}, message: {msg!r}",
            resp,
            required,
            note="Error message is shown for human inspection (AC-03)." if ac == "AC-03" else "",
        )

    def register(self, body: dict[str, Any]) -> httpx.Response:
        return self.call("POST", "/api/v1/releases", json=body, headers=USER)

    def components(self, rid: str) -> httpx.Response:
        return self.call("GET", f"/api/v1/releases/{rid}/components")

    def put_sbom(
        self, rid: str, body: bytes, headers: dict[str, str] | None = None
    ) -> httpx.Response:
        h = {**USER, **JSON} if headers is None else headers
        return self.call("PUT", f"/api/v1/releases/{rid}/sbom", content=body, headers=h)

    def set_clock(self, now: str) -> httpx.Response:
        return self.call("PUT", "/api/v1/test/clock", json={"now": now})

    # -- sections ---------------------------------------------------------------------------

    def setup(self) -> bool:
        r = self.call("POST", "/api/v1/test/reset")
        if not self.expect_status(
            "setup.reset", "setup", "POST /test/reset clears the system", r, 204
        ):
            return False
        r = self.set_clock(self.fx.releases["reference_clock"])
        return self.expect_status("setup.clock", "setup", "PUT /test/clock sets the clock", r, 200)

    def ac01(self) -> None:
        spec = self.fx.releases["ac01"]
        ids: dict[str, str] = {}
        for case in spec["cases"]:
            exp = case["expected"]
            r = self.register(case["request"])
            if exp["http_status"] == 201:
                body = _json(r) or {}
                got = body.get("support_status") if r.status_code == 201 else None
                self.record(
                    f"ac01.{case['id']}",
                    "AC-01",
                    f"Register '{case['id']}' release → 201, {exp['support_status']}",
                    r.status_code == 201 and got == exp["support_status"],
                    f"201, support_status={exp['support_status']}",
                    f"{r.status_code}, support_status={got}",
                    r,
                )
                if r.status_code == 201 and isinstance(body.get("release_id"), str):
                    ids[case["id"]] = body["release_id"]
                    g = self.call("GET", f"/api/v1/releases/{body['release_id']}")
                    read = (_json(g) or {}).get("support_status")
                    self.record(
                        f"ac01.{case['id']}.read",
                        "AC-01",
                        f"GET '{case['id']}' release → {exp['support_status']}",
                        g.status_code == 200 and read == exp["support_status"],
                        f"200, support_status={exp['support_status']}",
                        f"{g.status_code}, support_status={read}",
                        g,
                    )
            else:
                self.expect_rejection(
                    f"ac01.{case['id']}",
                    "AC-01",
                    f"Register '{case['id']}' release → rejected",
                    r,
                    exp["http_status"],
                )
                retry = {**case["request"], "support_end_date": "2030-01-01"}
                r2 = self.register(retry)
                self.record(
                    f"ac01.{case['id']}.nothing_saved",
                    "AC-01",
                    "Rejected release was not saved (same product/version registers → 201)",
                    r2.status_code == 201,
                    "201",
                    str(r2.status_code),
                    r2,
                )

        roll = self.fx.releases["ac01_rollover"]
        if roll["case_id"] in ids:
            self.set_clock(roll["clock"])
            g = self.call("GET", f"/api/v1/releases/{ids[roll['case_id']]}")
            got = (_json(g) or {}).get("support_status")
            want = roll["expected"]["support_status"]
            self.record(
                "ac01.rollover",
                "AC-01",
                f"One second after the end date the boundary release is {want}",
                g.status_code == 200 and got == want,
                f"200, support_status={want}",
                f"{g.status_code}, support_status={got}",
                g,
            )
            self.set_clock(self.fx.releases["reference_clock"])

        r = self.register(
            {"product": "ExampleRouter", "version": "2.0.0", "support_end_date": "2030-01-01"}
        )
        self.expect_rejection(
            "contract.duplicate", "contract", "Duplicate product+version → 409", r, 409
        )
        g = self.call("GET", f"/api/v1/releases/rel-does-not-exist-{uuid.uuid4().hex[:6]}")
        self.expect_rejection(
            "contract.unknown_release", "contract", "GET unknown release → 404", g, 404
        )

    def ac02(self) -> str | None:
        spec = self.fx.releases["ac02"]
        ids: dict[str, str] = {}
        for rel in spec["releases"]:
            r = self.register(rel["request"])
            ok = self.expect_status(
                f"ac02.register.{rel['id']}", "AC-02", f"Register '{rel['id']}'", r, 201
            )
            if ok and isinstance((_json(r) or {}).get("release_id"), str):
                ids[rel["id"]] = _json(r)["release_id"]
        with_sbom = next(rel for rel in spec["releases"] if rel["upload_sbom"])
        without = next(rel for rel in spec["releases"] if not rel["upload_sbom"])
        if with_sbom["id"] not in ids or without["id"] not in ids:
            return None
        rid = ids[with_sbom["id"]]

        r = self.put_sbom(rid, self.fx.sbom_bytes)
        body = _json(r) or {}
        want = with_sbom["expected"]["component_count"]
        self.record(
            "ac02.upload",
            "AC-02",
            f"Upload the shared {want}-component SBOM → 200, component_count={want}",
            r.status_code == 200
            and body.get("component_count") == want
            and body.get("release_id") == rid,
            f"200, release_id={rid}, component_count={want}",
            f"{r.status_code}, release_id={body.get('release_id')}, "
            f"component_count={body.get('component_count')}",
            r,
        )

        g = self.components(rid)
        comps = (_json(g) or {}).get("components") or []
        got: Counter[tuple[str, str]] = Counter(
            (str(c.get("name")), str(c.get("version"))) for c in comps if isinstance(c, dict)
        )
        expected: Counter[tuple[str, str]] = Counter(self.fx.sbom_components)
        missing, unexpected = (expected - got).total(), (got - expected).total()
        self.record(
            "ac02.components",
            "AC-02",
            f"First release returns all {want} components with matching names and versions",
            g.status_code == 200 and got == expected,
            f"200 and the {want} fixture name/version pairs",
            f"{g.status_code}, {got.total()} components, "
            f"{missing} missing, {unexpected} unexpected",
            g,
        )
        g2 = self.components(ids[without["id"]])
        comps2 = (_json(g2) or {}).get("components")
        self.record(
            "ac02.second_release_empty",
            "AC-02",
            "Second release returns zero components",
            g2.status_code == 200 and comps2 == [],
            "200, components=[]",
            f"{g2.status_code}, components={'[]' if comps2 == [] else type(comps2).__name__}",
            g2,
        )
        g3 = self.components(f"rel-does-not-exist-{uuid.uuid4().hex[:6]}")
        self.expect_rejection(
            "contract.unknown_release_components",
            "contract",
            "Components of unknown release → 404",
            g3,
            404,
        )
        return rid

    def ac03(self, rid_with_sbom: str | None) -> None:
        r = self.register(
            {"product": "AC03Product", "version": "1.0.0", "support_end_date": "2030-01-01"}
        )
        if not self.expect_status("ac03.register", "AC-03", "Register a release for AC-03", r, 201):
            return
        rid = _json(r)["release_id"]
        doc = json.loads(self.fx.sbom_bytes)
        missing_field = {k: v for k, v in doc.items() if k != "bomFormat"}
        cases: list[tuple[str, str, bytes]] = [
            ("malformed", "Malformed JSON → 400 with reason", b'{"bomFormat": "CycloneDX", '),
            (
                "missing_field",
                "JSON missing required CycloneDX field (bomFormat) → 400 with reason",
                json.dumps(missing_field).encode(),
            ),
            ("plaintext", "Plaintext → 400 with reason", b"this is plain text, not an SBOM"),
        ]
        for cid, title, body in cases:
            self.expect_rejection(f"ac03.{cid}", "AC-03", title, self.put_sbom(rid, body), 400)
        unreg = self.put_sbom(f"rel-unregistered-{uuid.uuid4().hex[:6]}", self.fx.sbom_bytes)
        self.expect_rejection(
            "ac03.unregistered", "AC-03", "Valid SBOM for unregistered release → 404", unreg, 404
        )
        g = self.components(rid)
        comps = (_json(g) or {}).get("components")
        self.record(
            "ac03.nothing_stored",
            "AC-03",
            "Zero components stored after the four rejected inputs",
            g.status_code == 200 and comps == [],
            "200, components=[]",
            f"{g.status_code}, components={comps if comps == [] else f'{len(comps or [])} items'}",
            g,
        )

        if rid_with_sbom:
            before = (_json(self.components(rid_with_sbom)) or {}).get("components")
            self.put_sbom(rid_with_sbom, b"not json at all")
            self.put_sbom(rid_with_sbom, json.dumps(missing_field).encode())
            after_resp = self.components(rid_with_sbom)
            after = (_json(after_resp) or {}).get("components")
            self.record(
                "contract.invalid_keeps_existing",
                "contract",
                "Invalid upload does not change a release's stored components",
                after == before,
                f"{len(before or [])} components unchanged",
                f"{len(after or [])} components, {'unchanged' if after == before else 'CHANGED'}",
                after_resp,
            )
            small = {
                "bomFormat": "CycloneDX",
                "specVersion": "1.6",
                "version": 1,
                "components": [{"type": "library", "name": "only-one", "version": "1.0.0"}],
            }
            r = self.put_sbom(rid_with_sbom, json.dumps(small).encode())
            g = self.components(rid_with_sbom)
            names = [c.get("name") for c in (_json(g) or {}).get("components") or []]
            self.record(
                "contract.replace",
                "contract",
                "A second valid SBOM replaces the release's components",
                r.status_code == 200 and names == ["only-one"],
                "200, then components=['only-one']",
                f"{r.status_code}, then components={names[:5]}{'…' if len(names) > 5 else ''}",
                g,
            )

        # Provisional pod decisions: reported, never counted.
        self.expect_rejection(
            "info.missing_user_id",
            "provisional",
            "Missing X-User-Id → 400",
            self.put_sbom(rid, self.fx.sbom_bytes, headers=JSON),
            400,
            required=False,
        )
        old = {**doc, "specVersion": "1.3"}
        self.expect_rejection(
            "info.spec_1_3",
            "provisional",
            "specVersion 1.3 rejected (pod proposal: accept 1.4–1.6)",
            self.put_sbom(rid, json.dumps(old).encode()),
            400,
            required=False,
        )
        nover = {**doc, "components": [{"type": "library", "name": "x"}]}
        self.expect_rejection(
            "info.component_without_version",
            "provisional",
            "Component without version rejected",
            self.put_sbom(rid, json.dumps(nover).encode()),
            400,
            required=False,
        )

    def audit_and_reset(self) -> None:
        g = self.call("GET", "/api/v1/audit-logs")
        raw_events = (_json(g) or {}).get("events")
        events: list[Any] = raw_events if isinstance(raw_events, list) else []
        ok = g.status_code == 200 and len(events) > 0
        self.record(
            "contract.audit_list",
            "contract",
            "GET /audit-logs returns the recorded events",
            ok,
            "200, non-empty events array",
            f"{g.status_code}, {len(events)} events",
            g,
        )
        if ok and isinstance(events[0], dict) and "event_id" in events[0]:
            eid = events[0]["event_id"]
            for method in ("PATCH", "DELETE"):
                r = self.call(method, f"/api/v1/audit-logs/{eid}", headers=USER)
                self.expect_status(
                    f"contract.audit_{method.lower()}",
                    "contract",
                    f"{method} audit entry → 405",
                    r,
                    405,
                )
        r = self.call("POST", "/api/v1/test/reset")
        self.expect_status("teardown.reset", "teardown", "Final POST /test/reset", r, 204)
        g = self.call("GET", "/api/v1/audit-logs")
        self.record(
            "teardown.audit_empty",
            "teardown",
            "Audit log is empty after reset",
            g.status_code == 200 and (_json(g) or {}).get("events") == [],
            "200, events=[]",
            f"{g.status_code}, events={(_json(g) or {}).get('events')!r:.40}",
            g,
        )


def run(client: httpx.Client, fixtures: Fixtures, target: str) -> Report:
    report = Report(
        run_id=f"run-{uuid.uuid4().hex[:10]}", target_base_url=target, started_at=_utc_now()
    )
    t0 = time.monotonic()
    runner = Runner(client, fixtures)
    try:
        if runner.setup():
            runner.ac01()
            rid = runner.ac02()
            runner.ac03(rid)
            runner.audit_and_reset()
        else:
            report.error = (
                "Setup failed: the test endpoints (/test/reset, /test/clock) must be enabled."
            )
    except TargetUnreachable as exc:
        report.error = f"Target unreachable: {exc}"
    except Exception as exc:  # a malformed target response must still yield a report
        report.error = f"Tester stopped on an unexpected response: {type(exc).__name__}: {exc}"

    required = [c for c in runner.checks if c.required]
    info = [c for c in runner.checks if not c.required]
    report.checks = runner.checks
    report.summary = {
        "required_passed": sum(c.passed for c in required),
        "required_failed": sum(not c.passed for c in required),
        "informational_passed": sum(c.passed for c in info),
        "informational_failed": sum(not c.passed for c in info),
    }
    if report.error:
        report.result = "error"
    else:
        report.result = "pass" if report.summary["required_failed"] == 0 else "fail"
    report.finished_at = _utc_now()
    report.duration_ms = int((time.monotonic() - t0) * 1000)
    return report
