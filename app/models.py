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
    aspect: Literal["conjunction", "sextile", "square", "trine", "opposition"]
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
