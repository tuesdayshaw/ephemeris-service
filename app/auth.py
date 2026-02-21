"""API key authorization dependency."""

from __future__ import annotations

from fastapi import Header

from app.errors import ApiError


class ApiKeyAuth:
    def __init__(self, configured_api_key: str) -> None:
        self._configured_api_key = configured_api_key

    async def __call__(self, x_api_key: str | None = Header(default=None)) -> None:
        if not self._configured_api_key:
            return
        if x_api_key != self._configured_api_key:
            raise ApiError(401, "INVALID_API_KEY", "Missing or invalid API key")
