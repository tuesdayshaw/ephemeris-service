"""Custom API errors and exception handlers."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

LOGGER = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": exc.code},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        has_missing = any(err.get("type") == "missing" for err in exc.errors())
        code = "MISSING_PARAM" if has_missing else "INVALID_DATE"
        detail = "Missing required parameter" if has_missing else "Invalid request parameters"
        return JSONResponse(status_code=422, content={"detail": detail, "code": code})

    @app.exception_handler(Exception)
    async def handle_uncaught(_: Request, exc: Exception) -> JSONResponse:
        LOGGER.exception("Unhandled exception", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal ephemeris calculation error", "code": "CALC_ERROR"},
        )
