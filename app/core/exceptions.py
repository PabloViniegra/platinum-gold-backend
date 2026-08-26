from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class AppError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(status_code=status_code, detail=message)


async def http_exception_handler(
    _request: Request,
    exception: Exception,
) -> JSONResponse:
    if not isinstance(exception, HTTPException):
        raise exception
    if isinstance(exception, AppError):
        code = exception.code
        message = exception.message
    elif exception.status_code == 404:
        code = "NOT_FOUND"
        message = "Resource not found"
    else:
        code = f"HTTP_{exception.status_code}"
        message = "Request failed"
    error = ErrorResponse(error=ErrorDetail(code=code, message=message))
    return JSONResponse(
        status_code=exception.status_code,
        content=error.model_dump(),
        headers=exception.headers,
    )


async def validation_exception_handler(
    _request: Request,
    _exception: Exception,
) -> JSONResponse:
    error = ErrorResponse(
        error=ErrorDetail(
            code="VALIDATION_ERROR",
            message="Request validation failed",
        )
    )
    return JSONResponse(status_code=422, content=error.model_dump())


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
