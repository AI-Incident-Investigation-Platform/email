import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.core.context import get_trace_id
from src.core.errors import AppError, ErrorReport, IntegrationError, InternalError

log = logging.getLogger(__name__)


class ApiErrorHandler:
    """Ответ об ошибке служебных роутов: у воркера нет публичного API."""

    @staticmethod
    def register(app: FastAPI) -> None:
        app.add_exception_handler(AppError, ApiErrorHandler.handle_app_error)

    @staticmethod
    async def handle_app_error(request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, IntegrationError):
            status, code, message = HTTPStatus.SERVICE_UNAVAILABLE, exc.code, exc.message
            level = logging.WARNING
        else:
            status, code, message = (
                HTTPStatus.INTERNAL_SERVER_ERROR,
                InternalError.code,
                InternalError.message,
            )
            level = logging.ERROR
        log.log(
            level,
            "Служебный запрос завершился ошибкой",
            extra={"error": ErrorReport.from_exception(exc).to_log(), "path": request.url.path},
        )
        return JSONResponse(
            status_code=status.value,
            content={"error": {"code": code, "message": message, "request_id": get_trace_id()}},
        )
