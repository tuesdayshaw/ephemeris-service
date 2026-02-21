"""Thin wrapper around Swiss Ephemeris calls."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import swisseph as swe

from app.errors import ApiError
from app.models import BodyPosition

BODY_TO_SWISS: dict[str, int] = {
    "sun": swe.SUN,
    "moon": swe.MOON,
    "mercury": swe.MERCURY,
    "venus": swe.VENUS,
    "mars": swe.MARS,
    "jupiter": swe.JUPITER,
    "saturn": swe.SATURN,
    "uranus": swe.URANUS,
    "neptune": swe.NEPTUNE,
    "pluto": swe.PLUTO,
}

DEFAULT_BODIES: list[str] = list(BODY_TO_SWISS.keys())


class EphemerisEngine:
    """Encapsulates all calls to `swisseph` for easier future swapping."""

    def __init__(self, ephe_path: str) -> None:
        self._ephe_path = ephe_path
        swe.set_ephe_path(ephe_path)

    def calculate_positions(self, dt_utc: datetime, body_names: list[str]) -> list[BodyPosition]:
        jd_ut = self._to_julian_day(dt_utc)
        result: list[BodyPosition] = []
        flags = swe.FLG_SWIEPH | swe.FLG_SPEED

        for body_name in body_names:
            body_id = BODY_TO_SWISS[body_name]
            try:
                values, _ = swe.calc_ut(jd_ut, body_id, flags)
            except swe.Error as exc:
                self._raise_calc_error(str(exc))

            lon, lat, distance, speed_lon = values[0], values[1], values[2], values[3]
            result.append(
                BodyPosition(
                    name=body_name,
                    longitude=float(lon) % 360.0,
                    latitude=float(lat),
                    distance_au=float(distance),
                    speed_deg_per_day=float(speed_lon),
                    is_retrograde=bool(speed_lon < 0),
                )
            )
        return result

    def local_midnight_to_utc(self, for_date: date, tz_name: str) -> datetime:
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError as exc:
            raise ApiError(422, "INVALID_DATE", f"Invalid timezone: {tz_name}") from exc

        local_dt = datetime.combine(for_date, time(0, 0, 0), tzinfo=tz)
        return local_dt.astimezone(timezone.utc)

    @staticmethod
    def _to_julian_day(dt_utc: datetime) -> float:
        if dt_utc.tzinfo is None:
            raise ApiError(422, "INVALID_DATE", "Datetime must include UTC timezone information")
        dt_utc = dt_utc.astimezone(timezone.utc)
        hour = dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0
        return swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, hour, swe.GREG_CAL)

    @staticmethod
    def _raise_calc_error(error_message: str) -> None:
        lowered = error_message.lower()
        if "range" in lowered or "out of" in lowered or "beyond" in lowered:
            raise ApiError(422, "DATE_OUT_OF_RANGE", "Date is outside the supported ephemeris range")
        raise ApiError(500, "CALC_ERROR", "Internal ephemeris calculation error")
