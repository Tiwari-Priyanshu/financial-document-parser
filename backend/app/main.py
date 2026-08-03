"""
Application entrypoint.

Run locally with:
    uvicorn app.main:app --reload
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from app.api import auth
from app.core.config import settings
from app.core.database import close_mongo_connection, connect_to_mongo

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s  %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup / shutdown hooks.

    The MongoDB connection pool is opened once here and reused for the life of
    the process. Opening a client per request would be catastrophically slow.
    """
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)
    await connect_to_mongo()
    if not settings.GEMINI_API_KEY:
        logger.warning(
            "GEMINI_API_KEY is not set - document parsing will fail. "
            "Add it to your .env file."
        )
    yield
    await close_mongo_connection()
    logger.info("Shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Upload bank statements, ITRs, GST returns, salary slips, invoices, "
        "balance sheets and P&L statements. The service classifies each "
        "document, extracts structured fields, validates them, and generates "
        "downloadable reports."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Surfaces per-request latency, which the spec asks us to monitor."""
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{time.perf_counter() - start:.4f}"
    return response


# --- Exception handlers -------------------------------------------------
# Without these, a validation error returns FastAPI's default shape and an
# unhandled DB error returns a raw stack trace. Both are handled explicitly so
# the frontend only ever has to parse one error format.


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [
        {
            "field": ".".join(str(p) for p in err["loc"][1:]) or "body",
            "message": err["msg"],
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation failed", "errors": errors},
    )


@app.exception_handler(PyMongoError)
async def database_exception_handler(request: Request, exc: PyMongoError):
    logger.exception("Database error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "A database error occurred"},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred"},
    )


# --- Routers ------------------------------------------------------------
app.include_router(auth.router)


@app.get("/", tags=["Health"], summary="Service metadata")
def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"], summary="Health check for uptime monitoring")
def health():
    return {"status": "ok"}
