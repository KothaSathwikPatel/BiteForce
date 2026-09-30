"""Pydantic models for the HTTP API (input validation lives here)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .security import sanitize_stall_name
from .timeutil import ensure_utc


class Kind(StrEnum):
    street_food = "street_food"
    restaurant = "restaurant"
    tea_snack = "tea_snack"


class Symptom(StrEnum):
    vomiting = "vomiting"
    diarrhoea = "diarrhoea"
    stomach_cramps = "stomach_cramps"
    nausea = "nausea"
    fever = "fever"
    blood_in_stool = "blood_in_stool"


class NewStall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: Kind = Kind.street_food
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        return sanitize_stall_name(value)


class ReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stall_id: int | None = Field(default=None, ge=1)
    new_stall: NewStall | None = None
    symptoms: list[Symptom] = Field(min_length=1, max_length=6)
    eaten_at: datetime
    onset_at: datetime
    reporter_lat: float | None = Field(default=None, ge=-90, le=90)
    reporter_lng: float | None = Field(default=None, ge=-180, le=180)
    hp: str = Field(default="", max_length=200)  # honeypot: real people never see or fill it
    form_ms: int | None = Field(default=None, ge=0, le=86_400_000)  # time spent on the form

    @field_validator("eaten_at", "onset_at")
    @classmethod
    def _aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Timestamps must include a timezone offset (ISO 8601).")
        return ensure_utc(value)

    @field_validator("symptoms")
    @classmethod
    def _unique(cls, value: list[Symptom]) -> list[Symptom]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def _one_place(self) -> Self:
        if (self.stall_id is None) == (self.new_stall is None):
            raise ValueError("Provide exactly one of stall_id or new_stall.")
        if (self.reporter_lat is None) != (self.reporter_lng is None):
            raise ValueError("Provide both reporter_lat and reporter_lng, or neither.")
        return self


class SimulateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stall_id: int = Field(ge=1)
    cases: int = Field(default=6, ge=1, le=12)


class GoogleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credential: str = Field(min_length=20, max_length=4096)
