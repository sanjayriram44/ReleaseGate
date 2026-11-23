"""Model coverage (spec v2): the design-requirement table in tester/model.py matches
docs/design-requirements.md, every mapped check exists, and suite results map checks to outcomes."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tester.checks import Check, Fixtures, Report, run
from tester.model import DESIGN_REQUIREMENTS, covered_requirements, evaluated, model
from tester.suite import results

DOC = Path("docs/design-requirements.md")


def _report(tmp_path: Path) -> Report:
    app = create_app(Settings(db_path=str(tmp_path / "m.db"), enable_test_endpoints=True))
    with TestClient(app) as client:
        return run(client, Fixtures.load(Path("fixtures")), "in-process")


def test_the_doc_lists_the_same_requirements_and_checks() -> None:
    rows = re.findall(r"^\| (DR-\d\d) \| (.+?) \|", DOC.read_text(encoding="utf-8"), re.M)
    assert [dr for dr, _ in rows] == [dr for dr, _, _ in DESIGN_REQUIREMENTS]
    assert [text for _, text in rows] == [text for _, text, _ in DESIGN_REQUIREMENTS]
    assert f"`total: {len(DESIGN_REQUIREMENTS)}`" in DOC.read_text(encoding="utf-8")


def test_every_mapped_check_exists_and_a_run_covers_all_but_the_restart(tmp_path: Path) -> None:
    report = _report(tmp_path)
    ids = [c.id for c in report.checks]
    for dr, _, prefixes in DESIGN_REQUIREMENTS:
        for prefix in prefixes:
            assert any(evaluated(i, (prefix,)) for i in ids), f"{dr}: no check {prefix}"
    assert covered_requirements(report) == [dr for dr, _, p in DESIGN_REQUIREMENTS if p]
    m = model(report)
    assert (m["covered"], m["total"]) == (13, 14) and "DR-01..DR-14" in m["basis"]


def test_prefix_and_exact_matching() -> None:
    assert evaluated("ac01.past", ("ac01.",))
    assert evaluated("contract.unknown_release", ("contract.unknown_release",))
    assert not evaluated("contract.unknown_release_components", ("contract.unknown_release",))


def _check(cid: str, passed: bool, status: int | None, required: bool = True) -> Check:
    return Check(cid, "AC-01", "Title", required, passed, "200", str(status), status=status)


def test_results_map_checks_to_outcomes() -> None:
    report = Report("r", "http://t", "2026-11-22T00:00:00Z")
    report.checks = [
        _check("a", True, 200),
        _check("b", False, 400),
        _check("c", False, 500),
        _check("d", False, 503),  # the contract's own 503 is an answer, not a crash
        _check("a", True, 200),  # duplicate id
        _check("e", False, None, required=False),
    ]
    report.error = "Target unreachable: GET /x: ConnectError"
    out = results(report)
    assert [(r["test_id"], r["outcome"], r.get("source")) for r in out] == [
        ("a", "pass", None),
        ("b", "fail", None),
        ("c", "error", "system"),
        ("d", "fail", None),
        ("a#2", "pass", None),
        ("e", "fail", None),
        ("suite.stopped", "error", "communication"),
    ]
    assert all(r["message"].strip() for r in out)
    assert "Informational" in out[5]["message"]
