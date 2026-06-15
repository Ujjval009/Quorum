from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.config import settings
from app.core.logging import configure_logging, logger
from app.models.base import SessionLocal

REQUEST_BODY_MAX_SIZE = 10 * 1024 * 1024  # 10 MB


async def _check_body_size(request: Request) -> None:
    """Reject requests with bodies larger than the limit."""
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > REQUEST_BODY_MAX_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Request body too large (max {REQUEST_BODY_MAX_SIZE // 1024 // 1024} MB)",
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("Starting Quorum API", version="0.1.0")
    # Startup validation
    db_ok = False
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_ok = True
    except Exception as e:
        logger.warning("Database connection failed at startup", error=str(e))
    logger.info("Startup checks", database=db_ok)
    yield
    logger.info("Shutting down Quorum API")


app = FastAPI(
    title="Quorum",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    await _check_body_size(request)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException):
        raise exc
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception(
        "Unhandled exception",
        path=request.url.path,
        method=request.method,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )


app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(documents_router)


@app.get("/health")
def health(request: Request):
    db_ok = True
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        db.close()
    except Exception:
        db_ok = False
        try:
            db.close()
        except Exception:
            pass

    request_id = getattr(request.state, "request_id", None)
    return {
        "status": "ok" if db_ok else "degraded",
        "version": "0.1.0",
        "database": "connected" if db_ok else "disconnected",
        "timestamp": datetime.now(UTC).isoformat(),
        "request_id": request_id,
    }
