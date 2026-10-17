"""Dependency-Track spike for Risk 1 (CLAUDE.md §8, Phase 2 report Q9.1).

Not part of the app. Talks to a local Dependency-Track 4.x API server started
with this folder's docker-compose.yml and measures what Phase 4 depends on:

  upload    two projects (releases); the 25-component fixture goes to one
  replace   a second SBOM replaces the first on the same project
  reset     both projects deleted

After each step it checks the stored components and runs the CVE queries in
expected.json, timing how long after the upload the answers become correct.

Usage (from the repo root, DT running):
  .venv/bin/python spikes/dependency_track/spike.py setup [--no-nvd]  # admin + mirrors
  .venv/bin/python spikes/dependency_track/spike.py mirror      # mirror status
  .venv/bin/python spikes/dependency_track/spike.py run         # the measured scenario
  .venv/bin/python spikes/dependency_track/spike.py crosscheck  # last run vs. OSV API
  .venv/bin/python spikes/dependency_track/spike.py inject      # internal-vuln fixtures

Environment: DT_PORT (default 8081); SPIKE_STRIP_CPE=1 uploads the SBOMs
without their `cpe` fields, so DT matches on purl only; SPIKE_LABEL is added
to the results file name.
"""

from __future__ import annotations

import copy
import json
import os
import secrets
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FIXTURE = REPO / "fixtures" / "sbom_25_components.json"
EXPECTED = HERE / "expected.json"
PASSWORD_FILE = HERE / ".dt-admin-password"
RESULTS_DIR = HERE / "results"

BASE = f"http://127.0.0.1:{os.environ.get('DT_PORT', '8081')}/api"
STRIP_CPE = os.environ.get("SPIKE_STRIP_CPE") == "1"
LABEL = os.environ.get("SPIKE_LABEL", "")
PRODUCT = "spike-example-gateway"
RELEASE_A = "1.0.0"  # gets the SBOM
RELEASE_B = "1.1.0"  # never gets an SBOM

AC04_LIMIT_S = 10.0
POLL_S = 0.25
TIMEOUT_S = 120.0

# The replacement SBOM: same release, three packages upgraded to their fixed
# versions, one removed, one added. See RESULTS.md for the advisory ranges.
UPGRADES = {"werkzeug": "2.2.3", "flask": "2.2.5", "requests": "2.31.0"}
REMOVED = {"pyyaml"}
ADDED = ("tomli", "2.0.1")


def now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def log(msg: str) -> None:
    print(f"[{now()}] {msg}", flush=True)


# --------------------------------------------------------------------- client


class DT:
    def __init__(self) -> None:
        self.http = httpx.Client(base_url=BASE, timeout=30)

    def wait_ready(self) -> float:
        start = time.monotonic()
        while True:
            try:
                if self.http.get("/version").status_code == 200:
                    return time.monotonic() - start
            except httpx.TransportError:
                pass
            if time.monotonic() - start > 300:
                sys.exit("Dependency-Track did not come up within 300 s")
            time.sleep(2)

    def login(self) -> None:
        """Log in as admin. On a fresh instance, replace the default password
        with a random one kept in a git-ignored file next to this script."""
        if not PASSWORD_FILE.exists():
            PASSWORD_FILE.write_text(secrets.token_urlsafe(18))
            PASSWORD_FILE.chmod(0o600)
        password = PASSWORD_FILE.read_text().strip()
        r = self.http.post("/v1/user/login", data={"username": "admin", "password": password})
        if r.status_code == 401:
            r = self.http.post("/v1/user/login", data={"username": "admin", "password": "admin"})
            if r.status_code == 401 and "FORCE_PASSWORD_CHANGE" in r.text:
                self.http.post(
                    "/v1/user/forceChangePassword",
                    data={
                        "username": "admin",
                        "password": "admin",
                        "newPassword": password,
                        "confirmPassword": password,
                    },
                ).raise_for_status()
                r = self.http.post(
                    "/v1/user/login", data={"username": "admin", "password": password}
                )
        r.raise_for_status()
        self.http.headers["Authorization"] = f"Bearer {r.text}"

    def get(self, path: str, **params: Any) -> httpx.Response:
        return self.http.get(path, params=params or None)

    # projects / BOMs ------------------------------------------------------

    def projects(self, name: str) -> list[dict[str, Any]]:
        r = self.get("/v1/project", name=name, pageSize=100)
        r.raise_for_status()
        return [p for p in r.json() if p["name"] == name]

    def create_project(self, name: str, version: str) -> str:
        r = self.http.put(
            "/v1/project", json={"name": name, "version": version, "classifier": "APPLICATION"}
        )
        r.raise_for_status()
        return str(r.json()["uuid"])

    def delete_project(self, uuid: str) -> None:
        self.http.delete(f"/v1/project/{uuid}").raise_for_status()

    def upload_bom(self, project: str, bom: dict[str, Any]) -> str:
        r = self.http.post(
            "/v1/bom",
            data={"project": project},
            files={"bom": ("bom.json", json.dumps(bom).encode(), "application/json")},
        )
        r.raise_for_status()
        return str(r.json()["token"])

    def processing(self, token: str) -> bool:
        r = self.get(f"/v1/event/token/{token}")
        r.raise_for_status()
        return bool(r.json()["processing"])

    def components(self, project: str) -> set[tuple[str, str]]:
        r = self.get(f"/v1/component/project/{project}", pageSize=1000, pageNumber=1)
        r.raise_for_status()
        return {(c["name"], c["version"]) for c in r.json()}

    def components_by_purl(self, purl: str) -> int:
        r = self.get("/v1/component/identity", purl=purl)
        r.raise_for_status()
        return len(r.json())

    def findings(self, project: str) -> list[dict[str, Any]]:
        r = self.get(f"/v1/finding/project/{project}")
        r.raise_for_status()
        return list(r.json())

    # CVE query ------------------------------------------------------------

    def resolve_cve(self, cve: str) -> list[tuple[str, str]]:
        """The DT records that stand for this CVE: the NVD record plus the
        GitHub (GHSA) and OSV (PYSEC) records DT has aliased to it. Empty means
        DT does not know the CVE."""
        r = self.get(f"/v1/vulnerability/source/NVD/vuln/{cve}")
        if r.status_code == 404:
            return []
        r.raise_for_status()
        records = {("NVD", cve)}
        for alias in r.json().get("aliases") or []:
            if alias.get("ghsaId"):
                records.add(("GITHUB", alias["ghsaId"]))
            if alias.get("osvId"):
                records.add(("OSV", alias["osvId"]))
        return sorted(records)

    def affected_projects(self, cve: str) -> dict[str, Any]:
        """What the app's GET /vulnerabilities/{cve}/affected-releases would do."""
        start = time.monotonic()
        records = self.resolve_cve(cve)
        projects: set[str] = set()
        for source, vuln_id in records:
            r = self.get(f"/v1/vulnerability/source/{source}/vuln/{vuln_id}/projects")
            if r.status_code == 404:
                continue
            r.raise_for_status()
            projects |= {f"{p['name']}@{p['version']}" for p in r.json() if p["name"] == PRODUCT}
        return {
            "known": bool(records),
            "records": [f"{s}:{v}" for s, v in records],
            "projects": sorted(projects),
            "latency_s": round(time.monotonic() - start, 3),
        }


# ---------------------------------------------------------------- SBOM inputs


def fixture_sbom() -> dict[str, Any]:
    bom = dict(json.loads(FIXTURE.read_text()))
    if STRIP_CPE:
        for c in bom["components"]:
            c.pop("cpe", None)
    return bom


def replacement_sbom() -> dict[str, Any]:
    bom = copy.deepcopy(fixture_sbom())
    bom["serialNumber"] = "urn:uuid:5d1f0c8e-2b0a-4c39-9b8e-7f3a1c2d4e5f"
    out = []
    for c in bom["components"]:
        if c["name"] in REMOVED:
            continue
        if c["name"] in UPGRADES:
            old, new = c["version"], UPGRADES[c["name"]]
            for key in ("version", "purl", "bom-ref", "cpe"):
                if key in c:
                    c[key] = c[key].replace(old, new)
        out.append(c)
    name, version = ADDED
    out.append(
        {
            "bom-ref": f"pkg:pypi/{name}@{version}",
            "type": "library",
            "name": name,
            "version": version,
            "purl": f"pkg:pypi/{name}@{version}",
        }
    )
    bom["components"] = out
    return bom


def pairs(bom: dict[str, Any]) -> set[tuple[str, str]]:
    return {(c["name"], c["version"]) for c in bom["components"]}


# ------------------------------------------------------------------ commands


def cmd_setup(no_nvd: bool = False) -> None:
    dt = DT()
    log(f"DT ready after {dt.wait_ready():.1f} s of waiting")
    dt.login()
    props = [
        # OSV's PyPI feed carries GHSA and PYSEC advisories with purl ranges.
        ("vuln-source", "google.osv.enabled", "PyPI"),
        ("vuln-source", "google.osv.alias.sync.enabled", "true"),
        # OSS Index now needs Sonatype credentials and calls out per component.
        ("scanner", "ossindex.enabled", "false"),
    ]
    if no_nvd:
        props.append(("vuln-source", "nvd.enabled", "false"))
    dt.http.post(
        "/v1/configProperty/aggregate",
        json=[{"groupName": g, "propertyName": p, "propertyValue": v} for g, p, v in props],
    ).raise_for_status()
    log("configured; the OSV mirror only starts on the next restart or after 24 h")


def cmd_mirror() -> None:
    dt = DT()
    dt.login()
    expected = json.loads(EXPECTED.read_text())
    total = dt.get("/v1/vulnerability", pageSize=1).headers.get("X-Total-Count")
    log(f"vulnerabilities in DT: {total}")
    for case in expected["cves"]:
        r = dt.get(f"/v1/vulnerability/source/GITHUB/vuln/{case['ghsa']}")
        log(f"{case['cve']}: GHSA {r.status_code}, resolves to {dt.resolve_cve(case['cve'])}")


def wait_until_correct(
    dt: DT, token: str, expected: dict[str, list[str]], t0: float
) -> dict[str, Any]:
    """Poll the BOM token and all CVE queries until every answer matches.

    Queries also run while DT is still processing, to see what a client that
    asks straight after the upload would get."""
    token_done_s = None
    first_correct_s = None
    rounds: list[dict[str, Any]] = []
    max_latency = 0.0
    last: dict[str, Any] = {}
    while time.monotonic() - t0 < TIMEOUT_S:
        processing = dt.processing(token)
        if token_done_s is None and not processing:
            token_done_s = time.monotonic() - t0
        last = {cve: dt.affected_projects(cve) for cve in expected}
        at = time.monotonic() - t0
        max_latency = max(max_latency, *(v["latency_s"] for v in last.values()))
        wrong = sorted(cve for cve, want in expected.items() if last[cve]["projects"] != want)
        rounds.append({"at_s": round(at, 2), "processing": processing, "wrong": wrong})
        if not wrong and first_correct_s is None:
            first_correct_s = at
        if token_done_s is not None and not wrong:
            return {
                "token_done_s": round(token_done_s, 2),
                "first_correct_s": round(first_correct_s or at, 2),
                "correct_and_done_s": round(at, 2),
                "within_ac04_limit": at <= AC04_LIMIT_S,
                "max_single_query_s": max_latency,
                "rounds": rounds,
                "answers": last,
            }
        time.sleep(POLL_S)
    return {
        "timed_out": True,
        "token_done_s": token_done_s,
        "rounds_total": len(rounds),
        "rounds": rounds[:5] + rounds[-5:],  # first and last five only
        "answers": last,
    }


def brief(step: dict[str, Any]) -> str:
    skip = {"answers", "rounds", "cves_by_component"}
    return json.dumps({k: v for k, v in step.items() if k not in skip})


def cves_by_component(findings: list[dict[str, Any]]) -> dict[str, list[str]]:
    """CVE IDs DT reports per component, through the finding itself or its aliases."""
    out: dict[str, set[str]] = {}
    for f in findings:
        key = f"{f['component']['name']}@{f['component']['version']}"
        vuln = f["vulnerability"]
        ids = {vuln["vulnId"]} | {a.get("cveId") for a in vuln.get("aliases") or []}
        out.setdefault(key, set()).update(i for i in ids if i and i.startswith("CVE-"))
    return {k: sorted(v) for k, v in sorted(out.items())}


def score(answers: dict[str, Any], expected: dict[str, list[str]]) -> dict[str, Any]:
    tp = fp = fn = 0
    for cve, want in expected.items():
        got = set(answers[cve]["projects"])
        tp += len(got & set(want))
        fp += len(got - set(want))
        fn += len(set(want) - got)
    return {
        "true_pos": tp,
        "false_pos": fp,
        "false_neg": fn,
        "recall": round(tp / (tp + fn), 3) if tp + fn else 1.0,
        "precision": round(tp / (tp + fp), 3) if tp + fp else 1.0,
    }


def cmd_run() -> None:
    dt = DT()
    dt.wait_ready()
    dt.login()
    spec = json.loads(EXPECTED.read_text())
    a, _b = f"{PRODUCT}@{RELEASE_A}", f"{PRODUCT}@{RELEASE_B}"
    report: dict[str, Any] = {
        "started": now(),
        "dt_version": dt.get("/version").json()["version"],
        "dt_port": BASE,
        "strip_cpe": STRIP_CPE,
        "label": LABEL,
        "vulnerabilities_in_dt": dt.get("/v1/vulnerability", pageSize=1).headers.get(
            "X-Total-Count"
        ),
    }

    def expected_for(step: str) -> dict[str, list[str]]:
        want = {c["cve"]: [a] if step in c["affects_release_a_after"] else [] for c in spec["cves"]}
        want[spec["known_no_match"]["cve"]] = []
        return want

    for p in dt.projects(PRODUCT):  # leftovers from an aborted run
        dt.delete_project(p["uuid"])
    uuid_a = dt.create_project(PRODUCT, RELEASE_A)
    uuid_b = dt.create_project(PRODUCT, RELEASE_B)

    # 1. upload ---------------------------------------------------------------
    log("upload: 25-component fixture to release A")
    t0 = time.monotonic()
    token = dt.upload_bom(uuid_a, fixture_sbom())
    step = wait_until_correct(dt, token, expected_for("upload"), t0)
    step["components_a_match_fixture"] = dt.components(uuid_a) == pairs(fixture_sbom())
    step["component_count_a"] = len(dt.components(uuid_a))
    step["component_count_b"] = len(dt.components(uuid_b))
    step["findings_a"] = len(dt.findings(uuid_a))
    step["cves_by_component"] = cves_by_component(dt.findings(uuid_a))
    step["score"] = score(step["answers"], expected_for("upload"))
    report["upload"] = step
    log(f"upload: {brief(step)}")

    # 2. replace --------------------------------------------------------------
    log("replace: second SBOM to release A")
    new = replacement_sbom()
    t0 = time.monotonic()
    token = dt.upload_bom(uuid_a, new)
    step = wait_until_correct(dt, token, expected_for("replace"), t0)
    stored = dt.components(uuid_a)
    step["components_a_match_replacement"] = stored == pairs(new)
    step["stale_components"] = sorted(f"{n}@{v}" for n, v in stored - pairs(new))
    step["missing_components"] = sorted(f"{n}@{v}" for n, v in pairs(new) - stored)
    findings = dt.findings(uuid_a)
    step["findings_a"] = len(findings)
    step["stale_findings"] = sorted(
        {
            f"{f['component']['name']}@{f['component']['version']}"
            for f in findings
            if (f["component"]["name"], f["component"]["version"]) not in pairs(new)
        }
    )
    step["score"] = score(step["answers"], expected_for("replace"))
    report["replace"] = step
    log(f"replace: {brief(step)}")

    # 3. reset ----------------------------------------------------------------
    log("reset: delete both projects")
    t0 = time.monotonic()
    dt.delete_project(uuid_a)
    dt.delete_project(uuid_b)
    step = {"delete_s": round(time.monotonic() - t0, 2)}
    step["projects_left"] = len(dt.projects(PRODUCT))
    probe = sorted({c["purl"] for c in fixture_sbom()["components"] + new["components"]})
    step["components_left"] = sum(dt.components_by_purl(p) for p in probe)
    step["answers"] = {cve: dt.affected_projects(cve) for cve in expected_for("reset")}
    step["score"] = score(step["answers"], expected_for("reset"))
    report["reset"] = step
    log(f"reset: {brief(step)}")

    # 4. unknown vs. known-with-no-match --------------------------------------
    unknown = spec["unknown_cve"]
    no_match = spec["known_no_match"]["cve"]
    report["unknown_cve"] = {
        unknown: dt.affected_projects(unknown),
        no_match: dt.affected_projects(no_match),
        "distinguishable": not dt.affected_projects(unknown)["known"]
        and dt.affected_projects(no_match)["known"],
    }
    log(f"unknown CVE: {json.dumps(report['unknown_cve'])}")

    report["finished"] = now()
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = RESULTS_DIR / f"run-{stamp}{'-' + LABEL if LABEL else ''}.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    log(f"wrote {out.relative_to(REPO)}")


def cmd_inject() -> None:
    """Can DT serve the contract's /test/vulnerability-source fixtures? Create an
    INTERNAL vulnerability with a CVE-shaped ID and an exact purl, then see
    whether DT's analyzer attributes it to a project that has that purl."""
    dt = DT()
    dt.login()
    cve = "CVE-2099-424242"
    purl = "pkg:pypi/six@1.16.0"
    for p in dt.projects(PRODUCT):
        dt.delete_project(p["uuid"])
    existing = dt.get(f"/v1/vulnerability/source/INTERNAL/vuln/{cve}")
    if existing.status_code == 200:
        dt.http.delete(f"/v1/vulnerability/{existing.json()['uuid']}").raise_for_status()
    r = dt.http.put(
        "/v1/vulnerability",
        json={
            "vulnId": cve,
            "source": "INTERNAL",
            "title": "spike fixture",
            "severity": "HIGH",
            "affectedComponents": [
                {"identityType": "PURL", "identity": purl, "versionType": "EXACT"}
            ],
        },
    )
    log(f"create internal vuln: {r.status_code} {r.text[:300]}")
    uuid = dt.create_project(PRODUCT, RELEASE_A)
    t0 = time.monotonic()
    token = dt.upload_bom(uuid, fixture_sbom())
    while dt.processing(token) and time.monotonic() - t0 < TIMEOUT_S:
        time.sleep(POLL_S)
    log(f"bom processed in {time.monotonic() - t0:.2f} s")
    r = dt.get(f"/v1/vulnerability/source/INTERNAL/vuln/{cve}/projects")
    log(f"projects for INTERNAL {cve}: {r.status_code} {r.text[:300]}")
    hits = [f for f in dt.findings(uuid) if f["vulnerability"]["vulnId"] == cve]
    log(f"findings for {cve}: {[f['component']['purl'] for f in hits]}")
    log(f"NVD lookup for {cve}: {dt.get(f'/v1/vulnerability/source/NVD/vuln/{cve}').status_code}")
    dt.delete_project(uuid)


def cmd_crosscheck() -> None:
    """Compare the CVEs DT found per component in the latest run with what the
    OSV API returns for the same purls. Needs internet access."""
    run_file = sorted(RESULTS_DIR.glob("run-*.json"))[-1]
    dt_cves = json.loads(run_file.read_text())["upload"]["cves_by_component"]
    osv = httpx.Client(timeout=30)
    report: dict[str, Any] = {"run": run_file.name, "checked": now(), "components": {}}
    for c in fixture_sbom()["components"]:
        key = f"{c['name']}@{c['version']}"
        r = osv.post("https://api.osv.dev/v1/query", json={"package": {"purl": c["purl"]}})
        r.raise_for_status()
        want = {a for v in r.json().get("vulns", []) for a in [v["id"], *v.get("aliases", [])]}
        want = {a for a in want if a.startswith("CVE-")}
        got = set(dt_cves.get(key, []))
        report["components"][key] = {
            "osv": len(want),
            "dt": len(got),
            "only_osv": sorted(want - got),
            "only_dt": sorted(got - want),
        }
    for key, row in report["components"].items():
        if row["only_osv"] or row["only_dt"]:
            log(f"{key}: {row}")
    totals = {
        k: sum(len(r[k]) for r in report["components"].values()) for k in ("only_osv", "only_dt")
    }
    totals["osv"] = sum(r["osv"] for r in report["components"].values())
    totals["dt"] = sum(r["dt"] for r in report["components"].values())
    report["totals"] = totals
    log(f"totals: {totals}")
    (RESULTS_DIR / f"crosscheck-{run_file.stem.removeprefix('run-')}.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )


if __name__ == "__main__":
    commands = {
        "setup": cmd_setup,
        "mirror": cmd_mirror,
        "run": cmd_run,
        "inject": cmd_inject,
        "crosscheck": cmd_crosscheck,
    }
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        sys.exit(f"usage: spike.py {{{'|'.join(commands)}}}")
    if sys.argv[1] == "setup":
        cmd_setup(no_nvd="--no-nvd" in sys.argv[2:])
    else:
        commands[sys.argv[1]]()
