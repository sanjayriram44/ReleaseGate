from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReleaseCreate(BaseModel):
    # strict: no coercion (ints for strings, datetimes for dates); dates must be YYYY-MM-DD.
    model_config = ConfigDict(strict=True, extra="ignore")

    product: str = Field(min_length=1)
    version: str = Field(min_length=1)
    support_end_date: date


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


class AuditEvent(BaseModel):
    event_id: str
    timestamp: str
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
