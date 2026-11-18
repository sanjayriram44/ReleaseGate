"""CRA report data and generation (REQ-07; CLAUDE.md §6.2-§6.4). Pure functions, no I/O.

Which fields belong to which stage follows CRA Art. 14(2) as proposed in P5-Q1, and what counts
as missing follows P5-Q2: both are proposals built provisionally until Team 2 answers
(docs/decisions.md). Reports are computed on every read; nothing derived is stored. The system
never fills in, trims or rewrites report text, and never decides a field is not applicable.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from app.clock import format_utc
from app.errors import ApiError
from app.models import GeneratedReport, ReportData, ReportStage

# The contract's ReportData properties, in its order: missing_fields and data follow it.
FIELD_ORDER: tuple[str, ...] = tuple(ReportData.model_fields)
LIST_FIELDS = frozenset({"member_states"})


@dataclass(frozen=True)
class StageFields:
    required: tuple[str, ...]  # listed in missing_fields when missing
    optional: tuple[str, ...] = ()  # in data when supplied, never "missing"

    @property
    def all(self) -> tuple[str, ...]:
        return tuple(f for f in FIELD_ORDER if f in self.required or f in self.optional)


# The one stage-field table (CLAUDE.md §7 rule 2). fixtures/report_cases.json "stage_fields" is the
# same table for the tests and the tester; tests/unit/test_reports.py fails if they differ.
STAGE_FIELDS: dict[str, StageFields] = {
    # Art. 14(2)(a): early warning, including the Member States where the product is available.
    "early_warning": StageFields(required=("member_states",)),
    # Art. 14(2)(b): product, exploit and vulnerability, measures taken and for users; where
    # applicable, how sensitive the manufacturer considers the information.
    "vulnerability_notification": StageFields(
        required=(
            "product_information",
            "exploit_nature",
            "vulnerability_nature",
            "corrective_measures_taken",
            "user_mitigations",
        ),
        optional=("sensitivity",),
    ),
    # Art. 14(2)(c)(i)-(iii): description with severity and impact; where available, the
    # malicious actor; details of the security update or other corrective measures.
    "final_report": StageFields(
        required=("vulnerability_description", "severity", "impact", "corrective_measure_details"),
        optional=("malicious_actor_information",),
    ),
}


def _invalid(message: str) -> ApiError:
    return ApiError(400, "INVALID_REQUEST", message)


def check_stage(stage: str) -> ReportStage:
    """The stage, if it is one of the three; else 400 (P5-Q5)."""
    if stage not in STAGE_FIELDS:
        raise _invalid(f"stage must be one of {', '.join(STAGE_FIELDS)}")
    return cast(ReportStage, stage)


def _type_ok(field: str, value: Any) -> bool:
    if value is None:  # allowed: counts as missing (P5-Q2)
        return True
    if field in LIST_FIELDS:
        return isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)
    return isinstance(value, str)


def validate_report_data(stage: str, body: Any) -> dict[str, Any]:
    """The stage's report data exactly as sent, or ApiError(400) naming the first bad field
    (P5-Q4): another stage's field, an unknown field, or a wrong type."""
    if not isinstance(body, dict):
        raise _invalid("request body must be a JSON object")
    fields = STAGE_FIELDS[stage].all
    for key in body:
        if key not in FIELD_ORDER:
            raise _invalid(f"{key} is not a report data field")
        if key not in fields:
            raise _invalid(f"{key} does not belong to stage {stage}")
    for field in fields:
        if field in body and not _type_ok(field, body[field]):
            kind = "an array of non-empty strings" if field in LIST_FIELDS else "a string"
            raise _invalid(f"{field} must be {kind}")
    return dict(body)


def is_missing(value: Any) -> bool:
    """Absent or null, an empty or whitespace-only string, or an empty array (P5-Q2)."""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list):
        return not value
    return False


def missing_fields(stage: str, stored: dict[str, Any]) -> list[str]:
    """The stage's required fields that are missing, in the contract's order."""
    return [f for f in STAGE_FIELDS[stage].required if is_missing(stored.get(f))]


def report_data(stage: str, stored: dict[str, Any]) -> dict[str, Any]:
    """The stage's supplied fields, exactly as stored, without nulls, in the contract's order."""
    return {f: stored[f] for f in STAGE_FIELDS[stage].all if stored.get(f) is not None}


def build_report(
    incident_id: str, stage: ReportStage, stored: dict[str, Any] | None, now: datetime
) -> GeneratedReport:
    stored = stored or {}
    return GeneratedReport(
        incident_id=incident_id,
        stage=stage,
        generated_at=format_utc(now),
        data=ReportData(**report_data(stage, stored)),
        missing_fields=missing_fields(stage, stored),
    )
