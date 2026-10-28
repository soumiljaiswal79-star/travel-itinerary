from datetime import date, time
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class TravelStyle(StrEnum):
    relaxed = "relaxed"
    balanced = "balanced"
    packed = "packed"


class StopKind(StrEnum):
    attraction = "attraction"
    dining = "dining"
    experience = "experience"


class TripInput(BaseModel):
    destination: Annotated[str, Field(min_length=2, max_length=120)]
    start_date: date
    end_date: date
    budget: Annotated[float, Field(gt=0, le=1_000_000)]
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] = "USD"
    interests: Annotated[list[str], Field(min_length=1, max_length=12)]
    travel_style: TravelStyle = TravelStyle.balanced
    group_size: Annotated[int, Field(ge=1, le=30)] = 1

    @field_validator("destination")
    @classmethod
    def clean_destination(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Destination must contain at least two non-space characters.")
        return value

    @field_validator("interests")
    @classmethod
    def clean_interests(cls, values: list[str]) -> list[str]:
        interests = list(dict.fromkeys(item.strip() for item in values if item.strip()))
        if not interests:
            raise ValueError("Choose at least one non-empty interest.")
        return interests

    @model_validator(mode="after")
    def validate_trip_dates(self) -> "TripInput":
        if self.end_date < self.start_date:
            raise ValueError("End date must be on or after the start date.")
        if (self.end_date - self.start_date).days > 13:
            raise ValueError("Trips can be at most 14 days long.")
        return self

    @property
    def day_count(self) -> int:
        return (self.end_date - self.start_date).days + 1


class ItineraryStop(BaseModel):
    time: time
    kind: StopKind
    title: Annotated[str, Field(min_length=2, max_length=160)]
    description: Annotated[str, Field(min_length=4, max_length=600)]
    location: Annotated[str, Field(min_length=2, max_length=240)]
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    duration_minutes: Annotated[int, Field(ge=15, le=720)]
    estimated_cost: Annotated[float, Field(ge=0)]
    image_url: str | None = None

    model_config = ConfigDict(extra="forbid")


class Accommodation(BaseModel):
    name: Annotated[str, Field(min_length=2, max_length=160)]
    neighborhood: Annotated[str, Field(min_length=2, max_length=160)]
    nightly_cost: Annotated[float, Field(ge=0)]
    notes: Annotated[str, Field(min_length=2, max_length=400)]

    model_config = ConfigDict(extra="forbid")


class ItineraryDay(BaseModel):
    day_number: Annotated[int, Field(ge=1, le=14)]
    date: date
    theme: Annotated[str, Field(min_length=2, max_length=120)]
    stops: Annotated[list[ItineraryStop], Field(min_length=1, max_length=14)]
    accommodation: Accommodation
    transportation: Annotated[list[str], Field(min_length=1, max_length=6)]
    estimated_cost: Annotated[float, Field(ge=0)]

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_stop_times(self) -> "ItineraryDay":
        times = [stop.time for stop in self.stops]
        if times != sorted(times):
            raise ValueError("Stops must be in chronological order.")
        return self


class ItineraryPlan(BaseModel):
    title: Annotated[str, Field(min_length=3, max_length=160)]
    summary: Annotated[str, Field(min_length=10, max_length=1200)]
    total_estimated_cost: Annotated[float, Field(ge=0)]
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    days: Annotated[list[ItineraryDay], Field(min_length=1, max_length=14)]

    model_config = ConfigDict(extra="forbid")


class GenerateTripRequest(TripInput):
    refinement: Annotated[str, Field(max_length=800)] = ""


class RegenerateRequest(BaseModel):
    refinement: Annotated[str, Field(max_length=800)] = ""


class TripUpdate(BaseModel):
    title: Annotated[str, Field(min_length=3, max_length=160)] | None = None
    budget: Annotated[float, Field(gt=0, le=1_000_000)] | None = None
    interests: Annotated[list[str], Field(min_length=1, max_length=12)] | None = None
    travel_style: TravelStyle | None = None


class DayUpdate(BaseModel):
    day: ItineraryDay


class ShareRequest(BaseModel):
    email: EmailStr
    role: str = "editor"

    @model_validator(mode="after")
    def validate_role(self) -> "ShareRequest":
        if self.role not in {"editor", "viewer"}:
            raise ValueError("Role must be editor or viewer.")
        return self


class AuthCredentials(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=8, max_length=128)]


class RefreshRequest(BaseModel):
    refresh_token: Annotated[str, Field(min_length=1)]


class SessionTokens(BaseModel):
    access_token: str | None
    refresh_token: str | None
    expires_in: int | None
    token_type: str | None


class AuthResponse(BaseModel):
    user: dict
    session: SessionTokens | None


class TripResponse(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    destination: str
    start_date: date
    end_date: date
    budget: float
    currency: str
    interests: list[str]
    travel_style: TravelStyle
    group_size: int
    total_estimated_cost: float
    summary: str
    days: list[ItineraryDay]
    role: str = "owner"
    created_at: str | None = None
    updated_at: str | None = None
