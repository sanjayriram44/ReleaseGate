import re
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise ValueError("must be a date in YYYY-MM-DD format")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("must be a valid calendar date in YYYY-MM-DD format") from exc


IsoDate = Annotated[date, BeforeValidator(_parse_date)]


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value  # stored exactly as sent


NonBlank = Annotated[str, AfterValidator(_not_blank)]


class ReleaseCreate(BaseModel):
    # strict: no coercion (ints for strings, datetimes for dates); dates must be YYYY-MM-DD.
    model_config = ConfigDict(strict=True, extra="ignore")

    product: NonBlank
    version: NonBlank
    support_end_date: IsoDate


class Release(BaseModel):
    release_id: str
    product: str
    version: str
    support_end_date: date
    support_status: Literal["supported", "unsupported"]


class Component(BaseModel):
    name: str
    version: str
    purl: str | None = None


class ComponentList(BaseModel):
    release_id: str
    components: list[Component]


class SbomStored(BaseModel):
    release_id: str
    component_count: int = Field(ge=0)


DateTimeStr = Annotated[str, Field(json_schema_extra={"format": "date-time"})]


class AuditEvent(BaseModel):
    event_id: str
    timestamp: DateTimeStr
    user_id: str
    action: str
    entity_type: str
    entity_id: str
    details: dict[str, object] | None = None


class AuditLogList(BaseModel):
    events: list[AuditEvent]


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, object] | None = None


class Error(BaseModel):
    error: ErrorBody


CVE_ID = re.compile(r"^CVE-[0-9]{4}-[0-9]+$")


def _cve_format(value: str | None) -> str | None:
    if value is not None and not CVE_ID.match(value):
        raise ValueError("must match ^CVE-[0-9]{4}-[0-9]+$ (e.g. CVE-2023-25577)")
    return value


Classification = Literal["mandatory", "voluntary"]
ReportStage = Literal["early_warning", "vulnerability_notification", "final_report"]


class IncidentCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    # Format check only; the CVE needn't be known to the source (decision Q4).
    cve_id: Annotated[str | None, AfterValidator(_cve_format)] = None
    awareness_at: DateTimeStr  # parsed by app.clock.parse_utc
    classification: Classification
    rationale: NonBlank


class FixAvailable(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    fix_available_at: DateTimeStr


class SubmissionCreate(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    stage: ReportStage
    submitted_at: DateTimeStr


class Deadline(BaseModel):
    deadline_at: DateTimeStr | None = None
    submitted_at: DateTimeStr | None = None
    status: Literal["pending", "met", "overdue", "not_applicable"]


class Deadlines(BaseModel):
    early_warning: Deadline
    vulnerability_notification: Deadline
    final_report: Deadline


class Incident(BaseModel):
    incident_id: str
    cve_id: str | None = None
    awareness_at: DateTimeStr
    created_by: str
    classification: Classification
    rationale: str
    fix_available_at: DateTimeStr | None = None
    deadlines: Deadlines
