"""Pydantic models for API requests and responses."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

BodyName = Literal[
    "sun",
    "moon",
    "mercury",
    "venus",
    "mars",
    "jupiter",
    "saturn",
    "uranus",
    "neptune",
    "pluto",
]

SignName = Literal[
    "aries",
    "taurus",
    "gemini",
    "cancer",
    "leo",
    "virgo",
    "libra",
    "scorpio",
    "sagittarius",
    "capricorn",
    "aquarius",
    "pisces",
]

AspectName = Literal["conjunction", "sextile", "square", "trine", "opposition"]


class ErrorResponse(BaseModel):
    detail: str
    code: str


class PositionsQuery(BaseModel):
    dt: str | None = None
    bodies: str | None = None


class SnapshotQuery(BaseModel):
    date: str | None = None
    tz: str | None = None


class MoonAspectsQuery(BaseModel):
    date: str | None = None
    tz: str | None = None
    orb: str | None = None


class MoonPhaseQuery(BaseModel):
    dt: str | None = None


class AspectsQuery(BaseModel):
    dt: str | None = None
    bodies: str | None = None
    aspects: str | None = None
    orb: str | None = None


class RetrogradesQuery(BaseModel):
    dt: str | None = None
    bodies: str | None = None
    retrograde_only: bool | None = None


class DailyWindowsQuery(BaseModel):
    date: str | None = None
    tz: str | None = None
    orb: str | None = None
    bodies: str | None = None
    aspects: str | None = None


class BodyPosition(BaseModel):
    name: BodyName
    longitude: float = Field(ge=0.0, lt=360.0)
    latitude: float
    distance_au: float
    speed_deg_per_day: float
    is_retrograde: bool
    sign_index: int = Field(ge=0, le=11)
    sign: SignName
    degree_in_sign: float = Field(ge=0.0, lt=30.0)


class PositionsResponse(BaseModel):
    dt_utc: str
    bodies: list[BodyPosition]


class SnapshotResponse(PositionsResponse):
    date: str
    timezone: str
    cached: bool


class AspectResult(BaseModel):
    body: BodyName
    aspect: AspectName
    exact_angle: float
    actual_angle: float
    orb_used: float
    moon_longitude: float = Field(ge=0.0, lt=360.0)
    body_longitude: float = Field(ge=0.0, lt=360.0)
    moon_sign_index: int = Field(ge=0, le=11)
    moon_sign: SignName
    moon_degree_in_sign: float = Field(ge=0.0, lt=30.0)
    body_sign_index: int = Field(ge=0, le=11)
    body_sign: SignName
    body_degree_in_sign: float = Field(ge=0.0, lt=30.0)


class MoonAspectsResponse(BaseModel):
    date: str
    timezone: str
    orb: float
    aspects: list[AspectResult]


class MoonPhaseResponse(BaseModel):
    dt_utc: str
    phase_angle_deg: float = Field(ge=0.0, le=180.0)
    illuminated_fraction: float = Field(ge=0.0, le=1.0)
    is_waxing: bool
    phase_name: Literal[
        "new",
        "waxing_crescent",
        "first_quarter",
        "waxing_gibbous",
        "full",
        "waning_gibbous",
        "last_quarter",
        "waning_crescent",
    ]


class PairAspectResult(BaseModel):
    body_a: BodyName
    body_b: BodyName
    aspect: AspectName
    exact_angle: float
    separation_deg: float = Field(ge=0.0, le=180.0)
    orb_used: float = Field(ge=0.0)
    applying: bool
    body_a_longitude: float = Field(ge=0.0, lt=360.0)
    body_b_longitude: float = Field(ge=0.0, lt=360.0)
    body_a_sign_index: int = Field(ge=0, le=11)
    body_a_sign: SignName
    body_a_degree_in_sign: float = Field(ge=0.0, lt=30.0)
    body_b_sign_index: int = Field(ge=0, le=11)
    body_b_sign: SignName
    body_b_degree_in_sign: float = Field(ge=0.0, lt=30.0)


class AspectsResponse(BaseModel):
    dt_utc: str
    orb: float
    aspects: list[PairAspectResult]


class RetrogradeBody(BaseModel):
    name: BodyName
    longitude: float = Field(ge=0.0, lt=360.0)
    speed_deg_per_day: float
    is_retrograde: bool
    sign_index: int = Field(ge=0, le=11)
    sign: SignName
    degree_in_sign: float = Field(ge=0.0, lt=30.0)


class RetrogradesResponse(BaseModel):
    dt_utc: str
    bodies: list[RetrogradeBody]


class MoonSignIngressEvent(BaseModel):
    from_sign: SignName
    to_sign: SignName
    dt_utc: str


class MoonExactAspectEvent(BaseModel):
    body: BodyName
    aspect: AspectName
    exact_angle: float
    dt_utc: str
    moon_longitude: float = Field(ge=0.0, lt=360.0)
    body_longitude: float = Field(ge=0.0, lt=360.0)
    moon_sign_index: int = Field(ge=0, le=11)
    moon_sign: SignName
    moon_degree_in_sign: float = Field(ge=0.0, lt=30.0)
    body_sign_index: int = Field(ge=0, le=11)
    body_sign: SignName
    body_degree_in_sign: float = Field(ge=0.0, lt=30.0)


class DailyWindowsResponse(BaseModel):
    date: str
    timezone: str
    dt_start_utc: str
    dt_end_utc: str
    moon_sign_ingresses: list[MoonSignIngressEvent]
    moon_exact_aspects: list[MoonExactAspectEvent]
