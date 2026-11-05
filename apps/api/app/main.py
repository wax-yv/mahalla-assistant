from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.db import Base, advisory_lock, engine, schema_ready
from app.core.errors import APIError
from app.routers import (
    admin,
    agents,
    auth,
    cases,
    citizens,
    cron,
    dashboard,
    documents,
    health,
    hierarchy,
    legislation,
    programs,
    reports,
    setup,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        with advisory_lock("mahalla_schema"):
            if not schema_ready():
                Base.metadata.create_all(bind=engine)
    except Exception as error:  # the database may not be attached yet
        print(f"[startup] create_all skipped: {error}")
    yield


app = FastAPI(
    title="Mahalla Assistant API",
    version=settings.app_version,
    description="Xorazm viloyati, Urganch shahri, Navbahor mahallasi uchun demo boshqaruv tizimi.",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID", "Authorization"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError):
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(getattr(request.state, "request_id", None)),
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    details = []
    for error in exc.errors()[:20]:
        details.append(
            {
                "field": ".".join(str(part) for part in error.get("loc", []) if part != "body"),
                "message": error.get("msg", "Noto'g'ri qiymat"),
            }
        )
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Kiritilgan ma'lumotlar noto'g'ri.",
                "details": details,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": "HTTP_ERROR",
                "message": str(exc.detail) if exc.detail else "So'rov bajarilmadi.",
                "details": [],
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    print(f"[error] {type(exc).__name__}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Serverda kutilmagan xatolik yuz berdi. Keyinroq qayta urinib ko'ring.",
                "details": [],
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


for router in (
    health.router,
    auth.router,
    dashboard.router,
    citizens.router,
    hierarchy.router,
    cases.router,
    documents.router,
    reports.router,
    legislation.router,
    programs.router,
    agents.router,
    admin.router,
    setup.router,
    cron.router,
):
    app.include_router(router, prefix="/api/v1")
