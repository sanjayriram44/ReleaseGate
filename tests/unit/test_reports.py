"""Report generation as pure functions (REQ-07, CLAUDE.md §6.2-§6.4; proposals P5-Q1, Q2, Q4, Q6).

The stage-field table is a proposal (P5-Q1) until Team 2 answers; these tests pin the proposal.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.errors import ApiError
from app.services.reports import (
    FIELD_ORDER,
    STAGE_FIELDS,
    build_report,
    check_stage,
    is_missing,
    missing_fields,
    report_data,
    validate_report_data,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
COMPLETE = json.loads((ROOT / "fixtures/report_cases.json").read_text())["incidents"][0][
    "report_data"
]


# -- the stage-field table --------------------------------------------------------------------


def test_field_order_is_the_contract_report_data_schema_order() -> None:
    contract = yaml.safe_load((ROOT / "docs/openapi.yaml").read_text())
    assert FIELD_ORDER == tuple(contract["components"]["schemas"]["ReportData"]["properties"])


def test_stage_fields_match_the_fixture_table() -> None:
    # One table: the tester and acceptance tests read the fixture's stage_fields (ground truth);
    # the app's copy must agree with it (CLAUDE.md §7 rule 2).
    fixture = json.loads((ROOT / "fixtures/report_cases.json").read_text())["stage_fields"]
    assert set(STAGE_FIELDS) == set(fixture)
    for stage, fields in STAGE_FIELDS.items():
        assert list(fields.required) == fixture[stage]["required"], stage
        assert list(fields.optional) == fixture[stage]["optional"], stage


def test_every_report_data_field_belongs_to_exactly_one_stage() -> None:
    owners = [f for fields in STAGE_FIELDS.values() for f in fields.all]
    assert sorted(owners) == sorted(FIELD_ORDER)


def test_stage_fields_are_in_schema_order() -> None:
    for fields in STAGE_FIELDS.values():
        assert list(fields.all) == [f for f in FIELD_ORDER if f in fields.all]
        assert list(fields.required) == [f for f in fields.all if f in fields.required]


# -- what counts as missing (P5-Q2) ------------------------------------------------------------


def test_nothing_stored_means_every_required_field_is_missing() -> None:
    assert missing_fields("early_warning", {}) == ["member_states"]
    assert missing_fields("vulnerability_notification", {}) == [
        "product_information",
        "exploit_nature",
        "vulnerability_nature",
        "corrective_measures_taken",
        "user_mitigations",
    ]
    assert missing_fields("final_report", {}) == [
        "vulnerability_description",
        "severity",
        "impact",
        "corrective_measure_details",
    ]


def test_complete_data_has_no_missing_fields() -> None:
    for stage, data in COMPLETE.items():
        assert missing_fields(stage, data) == [], stage


def test_optional_fields_are_never_missing() -> None:
    data = {k: v for k, v in COMPLETE["vulnerability_notification"].items() if k != "sensitivity"}
    assert missing_fields("vulnerability_notification", data) == []
    data = {k: v for k, v in COMPLETE["final_report"].items() if k != "malicious_actor_information"}
    assert missing_fields("final_report", data) == []


@pytest.mark.parametrize("value", [None, "", " ", "\t\n"])
def test_null_empty_or_blank_strings_are_missing(value: Any) -> None:
    data = {**COMPLETE["vulnerability_notification"], "user_mitigations": value}
    assert missing_fields("vulnerability_notification", data) == ["user_mitigations"]


def test_empty_member_states_is_missing() -> None:
    assert missing_fields("early_warning", {"member_states": []}) == ["member_states"]
    assert missing_fields("early_warning", {"member_states": None}) == ["member_states"]


def test_missing_fields_follow_schema_order_not_input_order() -> None:
    data = {"vulnerability_nature": "x", "product_information": "y", "user_mitigations": "z"}
    assert missing_fields("vulnerability_notification", data) == [
        "exploit_nature",
        "corrective_measures_taken",
    ]


# -- validation (P5-Q4) ------------------------------------------------------------------------


def _error(stage: str, body: Any) -> str:
    with pytest.raises(ApiError) as exc:
        validate_report_data(stage, body)
    assert exc.value.status == 400 and exc.value.code == "INVALID_REQUEST"
    return exc.value.message


def test_valid_data_is_returned_exactly_as_sent() -> None:
    body = {"member_states": [" DE", "fr "]}
    assert validate_report_data("early_warning", body) == {"member_states": [" DE", "fr "]}
    text = {"product_information": "  padded  ", "exploit_nature": ""}
    assert validate_report_data("vulnerability_notification", text) == text


def test_partial_and_null_values_are_accepted() -> None:
    body = {"severity": None, "impact": "Denial of service"}
    assert validate_report_data("final_report", body) == body
    assert validate_report_data("final_report", {}) == {}


@pytest.mark.parametrize("body", [[], "text", 5, None, ["member_states"]])
def test_body_must_be_an_object(body: Any) -> None:
    assert _error("early_warning", body) == "request body must be a JSON object"


def test_field_from_another_stage_is_named() -> None:
    message = _error("early_warning", {"member_states": ["DE"], "severity": "High"})
    assert message == "severity does not belong to stage early_warning"


def test_unknown_field_is_named() -> None:
    assert _error("final_report", {"colour": "red"}) == "colour is not a report data field"


@pytest.mark.parametrize("value", ["DE", [1], ["DE", None], [""], ["  "], {"DE": True}, 3, True])
def test_member_states_must_be_an_array_of_non_empty_strings(value: Any) -> None:
    message = _error("early_warning", {"member_states": value})
    assert message == "member_states must be an array of non-empty strings"


@pytest.mark.parametrize("value", [5, 1.5, True, ["text"], {"a": "b"}])
def test_text_fields_must_be_strings(value: Any) -> None:
    assert _error("final_report", {"severity": value}) == "severity must be a string"


def test_first_problem_in_schema_order_is_reported() -> None:
    body = {"impact": 1, "vulnerability_description": 2}
    assert _error("final_report", body) == "vulnerability_description must be a string"


# -- report data and build_report (P5-Q6) ------------------------------------------------------


def test_report_data_drops_nulls_and_keeps_schema_order() -> None:
    stored = {"impact": "x", "severity": None, "vulnerability_description": "y"}
    data = report_data("final_report", stored)
    assert data == {"vulnerability_description": "y", "impact": "x"}
    assert list(data) == ["vulnerability_description", "impact"]


def test_report_data_keeps_empty_strings_as_sent() -> None:
    # Missing for missing_fields, but still what the person stored.
    assert report_data("final_report", {"severity": ""}) == {"severity": ""}


def test_build_report_shape() -> None:
    stored = {k: v for k, v in COMPLETE["vulnerability_notification"].items()}
    stored.pop("exploit_nature")
    report = build_report("inc-1", "vulnerability_notification", stored, NOW)
    assert report.model_dump(exclude_unset=True) == {
        "incident_id": "inc-1",
        "stage": "vulnerability_notification",
        "generated_at": "2026-11-20T12:00:00Z",
        "data": stored,
        "missing_fields": ["exploit_nature"],
    }


def test_build_report_with_nothing_stored() -> None:
    report = build_report("inc-1", "early_warning", None, NOW).model_dump(exclude_unset=True)
    assert report["data"] == {} and report["missing_fields"] == ["member_states"]


def test_build_report_does_not_change_its_input() -> None:
    stored = {"severity": None, "impact": "x"}
    build_report("inc-1", "final_report", stored, NOW)
    assert stored == {"severity": None, "impact": "x"}


def test_check_stage() -> None:
    assert check_stage("final_report") == "final_report"
    with pytest.raises(ApiError) as exc:
        check_stage("interim_report")
    assert exc.value.status == 400 and exc.value.message == (
        "stage must be one of early_warning, vulnerability_notification, final_report"
    )


@pytest.mark.parametrize(
    ("value", "missing"),
    [(None, True), ("", True), ("  ", True), ([], True), ("x", False), (["DE"], False), (0, False)],
)
def test_is_missing(value: Any, missing: bool) -> None:
    assert is_missing(value) is missing


def test_contract_fields_by_stage_match_the_table() -> None:
    contract = yaml.safe_load((ROOT / "docs/openapi.yaml").read_text())
    by_stage = contract["components"]["schemas"]["ReportData"]["x-fields-by-stage"]
    assert set(by_stage) == set(STAGE_FIELDS)
    for stage, fields in STAGE_FIELDS.items():
        assert by_stage[stage] == {
            "required": list(fields.required),
            "optional": list(fields.optional),
        }
