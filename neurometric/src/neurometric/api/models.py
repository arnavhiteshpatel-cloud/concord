"""Request bodies (unknown fields are rejected everywhere)."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginIn(Strict):
    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=1000)


class UserIn(Strict):
    username: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=12, max_length=1000)
    role: Literal["participant", "care_partner", "coordinator", "investigator",
                  "sponsor_analyst", "admin"]
    display_name: str = ""
    participant_id: Optional[str] = None
    site_ids: list[str] = []
    linked_participants: list[str] = []


class ReasonIn(Strict):
    reason: str = Field(min_length=1, max_length=2000)


class SiteIn(Strict):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)


class SponsorIn(Strict):
    name: str = Field(min_length=1, max_length=200)


class StudyIn(Strict):
    code: str = Field(min_length=1, max_length=60)
    title: str = Field(min_length=1, max_length=300)
    sponsor_id: Optional[str] = None
    is_demo: bool = False
    withdrawal_action_default: Literal["retain", "delete"] = "retain"
    min_cell_size: int = Field(3, ge=1, le=100)


class StudyPatch(Strict):
    changes: dict[str, Any]
    reason: str = Field(min_length=1, max_length=2000)


class ProtocolIn(Strict):
    version: str
    effective_date: str
    summary: str = ""
    consent_document_id: str = ""


class ScheduleIn(Strict):
    name: str
    definition: dict[str, Any]
    protocol_version_id: Optional[str] = None


class ParticipantIn(Strict):
    site_id: str
    cohort: str = ""
    primary_modality: str = ""
    identifier: Optional[str] = Field(None, max_length=500)


class TransitionIn(Strict):
    to_state: str
    reason: str = ""


class ReidIn(Strict):
    identifier: str = Field(min_length=1, max_length=500)


class ConsentIn(Strict):
    consent_document_id: str
    consent_version: str
    scopes: dict[str, bool]


class WithdrawIn(Strict):
    reason: str = Field(min_length=1, max_length=2000)
    scopes: Optional[list[str]] = None
    action: Optional[Literal["retain", "delete"]] = None


class GenerateVisitsIn(Strict):
    schedule_id: str
    anchor_date: Optional[str] = None


class DeviceIn(Strict):
    modality: str
    make_model: str = ""
    settings: dict[str, Any] = {}
    calibration_state: str = "unknown"


class SessionIn(Strict):
    task_id: str
    events: list[dict[str, Any]]
    stimulus_seed: int
    stimulus_hash: str
    battery_version: Optional[str] = None
    visit_id: Optional[str] = None
    device_config_id: Optional[str] = None
    provenance: Literal["live", "simulated", "replayed"] = "live"
    modality: Optional[str] = None
    performed_at: Optional[str] = None


class ResponseIn(Strict):
    instrument_id: str
    version: Optional[str] = None
    answers: dict[str, Any]
    visit_id: Optional[str] = None
    language: str = "en"


class ScoreIn(Strict):
    version: Optional[str] = None
    answers: dict[str, Any]


class DeviationIn(Strict):
    category: str
    description: str
    severity: Literal["minor", "major"] = "minor"
    participant_id: Optional[str] = None
    visit_id: Optional[str] = None


class MissingIn(Strict):
    item_type: Literal["visit", "task", "instrument", "telemetry"]
    item_ref: str
    reason_code: str
    note: str = ""
    visit_id: Optional[str] = None


class QueryIn(Strict):
    record_table: str
    record_id: str
    question: str
    field: str = ""


class AnswerIn(Strict):
    answer: str = Field(min_length=1, max_length=4000)


class CloseIn(Strict):
    reason: str = ""


class CorrectionIn(Strict):
    changes: dict[str, Any]
    reason: str = Field(min_length=1, max_length=2000)


class SignIn(Strict):
    record_table: str
    record_id: str
    meaning: Literal["authored", "reviewed", "approved", "verified"]
    password: str


class TelemetryStateIn(Strict):
    state: Literal["active", "paused", "stopped"]
    reason: str = ""


class RetentionIn(Strict):
    data_category: str
    retain_days: int = Field(ge=0, le=36500)


class BackupVerifyIn(Strict):
    name: str = Field(pattern=r"^[A-Za-z0-9_.-]+\.sqlite$")
