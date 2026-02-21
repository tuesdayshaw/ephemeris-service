"""Shared zodiac sign derivation utilities."""

from __future__ import annotations

from app.models import SignName

SIGNS: tuple[SignName, ...] = (
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
)


def derive_sign_fields(longitude: float) -> tuple[int, SignName, float]:
    """Return sign metadata for an ecliptic longitude."""
    normalized = longitude % 360.0
    sign_index = int(normalized // 30) % 12
    degree_in_sign = normalized % 30
    return sign_index, SIGNS[sign_index], degree_in_sign
