"""scripts/metrics.py measures the Phase 5 goals in docs/goals.md (CLAUDE.md §0.2)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def make_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("metrics", ROOT / "scripts/metrics.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["metrics"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def metrics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = make_module()
    monkeypatch.setattr(module, "REPORTS", tmp_path)
    return module


def write_report(directory: Path, name: str, body: str) -> None:
    (directory / name).write_text(body)


ALL_PASS = {
    ac: (3, 3) for ac in ["AC-01", "AC-02", "AC-03", "AC-04", "AC-05", "AC-06", "AC-07"]
} | {"contract": (8, 8)}


def test_phase5_and_regression_acs_split_as_in_the_goals(metrics: ModuleType) -> None:
    assert metrics.PHASE5_ACS == ["AC-08", "AC-09", "AC-10"]
    assert metrics.REGRESSION_ACS == [
        "AC-01",
        "AC-02",
        "AC-03",
        "AC-04",
        "AC-05",
        "AC-06",
        "AC-07",
        "contract",
    ]


def test_g1_not_measurable_until_phase5_checks_exist(metrics: ModuleType) -> None:
    value, met = metrics.g1(ALL_PASS)
    assert "AC-08 not built" in value and "AC-09 not built" in value
    assert met.startswith(metrics.NOT_YET)


def test_g1_needs_a_phase5_live_run_with_ac10(metrics: ModuleType, tmp_path: Path) -> None:
    checks = ALL_PASS | {"AC-08": (6, 6), "AC-09": (5, 5)}
    # A Phase 4 full run doesn't count, even though it passed.
    write_report(tmp_path, "2026-11-01-deploy-full.md", "**Mode:** full\n**Result:** 52/52 passed")
    assert metrics.g1(checks)[1].startswith(metrics.NOT_YET)
    write_report(
        tmp_path,
        "2026-12-01-deploy-full.md",
        "**Mode:** full\n**Result:** 70/70 passed\n**AC-10:** PASS (restart on the VM)\n",
    )
    value, met = metrics.g1(checks)
    assert met == "yes"
    assert "AC-10 live PASS" in value


def test_g1_fails_when_live_ac10_fails(metrics: ModuleType, tmp_path: Path) -> None:
    checks = ALL_PASS | {"AC-08": (6, 6), "AC-09": (5, 5)}
    write_report(
        tmp_path,
        "2026-12-01-deploy-full.md",
        "**Mode:** full\n**Result:** 70/70 passed\n**AC-10:** FAIL (audit log changed)\n",
    )
    assert metrics.g1(checks)[1] == "no"


def test_g2_covers_ac01_to_ac07_and_the_contract(metrics: ModuleType) -> None:
    value, met = metrics.g2(ALL_PASS, "300 passed in 12s")
    assert "AC-07 3/3" in value and "contract 8/8" in value
    assert met == "yes"
    assert metrics.g2(ALL_PASS | {"AC-06": (4, 5)}, "300 passed")[1] == "no"
    assert metrics.g2(ALL_PASS, "1 failed, 299 passed")[1] == "no"


def test_g3_counts_only_phase5_cross_team_reports(metrics: ModuleType, tmp_path: Path) -> None:
    write_report(
        tmp_path,
        "2026-11-02-cross-team-team2-to-ours.md",
        "**Result:** 341/353 passed (in scope)",
    )
    write_report(
        tmp_path, "2026-11-02-cross-team-ours-to-team2.md", "**Result:** 48/50 passed (in scope)"
    )
    # Both Phase 4 runs are ≥ 95%, but they aren't the final Phase 5 runs.
    value, met = metrics.g3()
    assert "341/353" in value  # shown for context
    assert met.startswith(metrics.NOT_YET)
    write_report(
        tmp_path, "2026-12-02-cross-team-team2-to-ours.md", "**Result:** 400/400 passed (in scope)"
    )
    write_report(
        tmp_path, "2026-12-02-cross-team-ours-to-team2.md", "**Result:** 90/100 passed (in scope)"
    )
    assert metrics.g3()[1] == "no"  # 90% < 95%
    write_report(
        tmp_path, "2026-12-03-cross-team-ours-to-team2.md", "**Result:** 99/100 passed (in scope)"
    )
    assert metrics.g3()[1] == "yes"


def test_g6_requires_the_phase5_tag_on_the_live_commit(
    metrics: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sha = "a" * 40
    write_report(tmp_path, "2026-12-01-deploy.md", f"**Commit:** `{sha}`\n**Result:** 12/12 passed")
    monkeypatch.setattr(metrics, "live_commit", lambda: sha)
    monkeypatch.setattr(metrics, "phase5_tag", lambda offline: None)
    value, met = metrics.g6(offline=False)
    assert "no `phase5` tag" in value and met == "no"
    monkeypatch.setattr(metrics, "phase5_tag", lambda offline: sha)
    assert metrics.g6(offline=False)[1] == "yes"
    monkeypatch.setattr(metrics, "phase5_tag", lambda offline: "b" * 40)
    assert metrics.g6(offline=False)[1] == "no"


def test_g6_live_commit_without_a_deploy_report_is_a_failure(
    metrics: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_report(
        tmp_path, "2026-11-01-deploy.md", "**Commit:** `e864340`\n**Result:** 12/12 passed"
    )
    monkeypatch.setattr(metrics, "live_commit", lambda: "bee2b44990c491f9")
    monkeypatch.setattr(metrics, "phase5_tag", lambda offline: None)
    value, met = metrics.g6(offline=False)
    assert "live `bee2b44`" in value and "`e864340`" in value
    assert met == "no"


def test_g7_not_measurable_until_its_test_exists(
    metrics: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(metrics, "G7_TEST", tmp_path / "test_audit_immutability.py")
    value, met = metrics.g7()
    assert met.startswith(metrics.NOT_YET)


def test_g7_reports_the_immutability_test_result(
    metrics: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test = tmp_path / "test_audit_immutability.py"
    test.write_text("def test_ok() -> None:\n    assert True\n")
    monkeypatch.setattr(metrics, "G7_TEST", test)
    value, met = metrics.g7()
    assert "1 passed" in value and met == "yes"
    test.write_text("def test_bad() -> None:\n    assert False\n")
    assert metrics.g7()[1] == "no"


def test_phase5_tag_resolves_an_annotated_tag_to_its_commit(
    metrics: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    listing = "\n".join(
        [
            f"{'1' * 40}\trefs/tags/phase4",
            f"{'2' * 40}\trefs/tags/phase4^{{}}",
            f"{'3' * 40}\trefs/tags/phase5",
            f"{'4' * 40}\trefs/tags/phase5^{{}}",
        ]
    )

    def fake_git(*args: str) -> str:
        # Like git: a ref pattern on ls-remote drops the peeled "^{}" lines.
        patterns = [a for a in args if a.startswith("refs/")]
        lines = listing.splitlines()
        return "\n".join(ln for ln in lines if not patterns or ln.split("\t")[1] in patterns)

    monkeypatch.setattr(metrics, "_git", fake_git)
    assert metrics.phase5_tag(offline=False) == "4" * 40
    monkeypatch.setattr(metrics, "_git", lambda *args: f"{'5' * 40}\trefs/tags/phase5")
    assert metrics.phase5_tag(offline=False) == "5" * 40  # lightweight tag
    monkeypatch.setattr(metrics, "_git", lambda *args: listing.split("\n")[0])
    assert metrics.phase5_tag(offline=False) is None
