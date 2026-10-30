"""The CI jobs (CLAUDE.md §15 stages B-D) run every test file exactly once, and the G5 gate
covers the whole suite by combining their coverage data."""

import shlex
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SUITE_JOBS = ("unit", "acceptance", "tester")


def make_workflow() -> dict[str, Any]:
    workflow: dict[str, Any] = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    return workflow


def make_runs(job: dict[str, Any]) -> list[str]:
    return [str(step["run"]) for step in job["steps"] if "run" in step]


def make_pytest_paths(job: dict[str, Any]) -> list[Path]:
    [command] = [run for run in make_runs(job) if "pytest" in run]
    return [ROOT / arg for arg in shlex.split(command) if arg.startswith("tests")]


def test_every_test_file_runs_in_exactly_one_job() -> None:
    jobs = make_workflow()["jobs"]
    paths = {name: make_pytest_paths(jobs[name]) for name in SUITE_JOBS}
    for name, job_paths in paths.items():
        assert job_paths, f"{name} names no test paths"
        assert all(p.exists() for p in job_paths), f"{name} names a missing path"
    for test_file in sorted((ROOT / "tests").rglob("test_*.py")):
        owners = [
            name
            for name, job_paths in paths.items()
            for p in job_paths
            if test_file == p or p in test_file.parents
        ]
        assert len(owners) == 1, f"{test_file.relative_to(ROOT)} runs in {owners or 'no job'}"


def test_coverage_gate_combines_every_suite_job() -> None:
    jobs = make_workflow()["jobs"]
    gate = jobs["coverage"]
    assert set(gate["needs"]) == set(SUITE_JOBS)
    runs = "\n".join(make_runs(gate))
    assert "coverage combine" in runs and "--fail-under=85" in runs
    for name in SUITE_JOBS:
        [command] = [run for run in make_runs(jobs[name]) if "pytest" in run]
        assert "--cov=app" in command, f"{name} doesn't collect coverage"
