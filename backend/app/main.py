from fastapi.openapi.utils import get_openapi

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings, validate_runtime_settings
from app.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.routers import (
    admin,
    auth,
    chat,
    interests,
    listings,
    needs,
    notifications,
    pickup_areas,
    users,
)
from app.services.cleanup import cleanup_loop
from app.services.maintenance import maintenance_loop
from app.services.migration import apply_migrations
from app.utils.logging_utils import get_security_logger, request_id_var, setup_logging

setup_logging()

security_logger = get_security_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):

    # Missing configuration is a startup failure in production, never a silent default. The log names the
    # setting that is missing, not its value.
    problems = validate_runtime_settings(settings)
    if problems:
        for problem in problems:
            logger.error("Configuration problem: %s", problem)
        if settings.environment.lower() == "production":
            raise RuntimeError("Refusing to start: " + "; ".join(problems))

    apply_migrations()

    security_logger.info(
        "service_started environment=%s",
        settings.environment,
    )

    cleanup_task = asyncio.create_task(
        cleanup_loop()
    )

    maintenance_task = asyncio.create_task(
        maintenance_loop()
    )

    yield

    for task in (cleanup_task, maintenance_task):
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

    security_logger.info("service_stopped")


is_production = settings.environment.lower() == "production"

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
    openapi_url=None if is_production else "/openapi.json",
)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )

    # Swagger UI currently has trouble rendering
    # OpenAPI 3.1 contentMediaType file arrays.
    # Convert file schemas to the older format: binary.
    components = schema.get("components", {}).get("schemas", {})

    for schema_obj in components.values():
        properties = schema_obj.get("properties", {})

        for prop in properties.values():

            # Multiple file uploads
            if prop.get("type") == "array":
                items = prop.get("items", {})

                if items.get("contentMediaType") == "application/octet-stream":
                    items.pop("contentMediaType", None)
                    items["type"] = "string"
                    items["format"] = "binary"

            # Single file upload
            if (
                prop.get("type") == "string"
                and prop.get("contentMediaType") == "application/octet-stream"
            ):
                prop.pop("contentMediaType", None)
                prop["format"] = "binary"

    app.openapi_schema = schema

    return app.openapi_schema


app.openapi = custom_openapi


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    # So the SPA can read the request id from a failed response (shown to admins, never to members).
    expose_headers=["X-Request-ID"],
)

# Opt-in host header validation for deployments where the public host is known
if settings.allowed_hosts.strip():
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[
            host.strip()
            for host in settings.allowed_hosts.split(",")
            if host.strip()
        ],
    )

app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(listings.router)
app.include_router(pickup_areas.router)
app.include_router(interests.router)
app.include_router(chat.router)
app.include_router(notifications.router)
app.include_router(needs.router)
app.include_router(admin.router)


from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
import logging

logger = logging.getLogger(__name__)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        field = " -> ".join([str(loc) for loc in err.get("loc", []) if loc != "body"])
        errors.append(f"{field}: {err.get('msg')}" if field else err.get("msg", "Invalid input"))
    return JSONResponse(
        status_code=422,
        content={"detail": errors if len(errors) > 1 else (errors[0] if errors else "Validation failed")},
    )

def _server_error(request, detail: str, log_message: str) -> JSONResponse:
    """Log the full error with the request id, and answer with a generic message plus that id as `ref`.

    Nothing else about the fault leaves the server. Admins can quote the ref; members never see it.
    """
    ref = getattr(request.state, "request_id", None) or "-"
    token = request_id_var.set(ref)
    try:
        logger.error(log_message, exc_info=True)
    finally:
        request_id_var.reset(token)
    return JSONResponse(status_code=500, content={"detail": detail, "ref": ref}, headers={"X-Request-ID": ref})


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request, exc: SQLAlchemyError):
    return _server_error(
        request,
        "A database error occurred. Internal database details are masked for security.",
        f"Database error during request {request.method} {request.url.path}: {exc}",
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    return _server_error(
        request,
        "An internal server error occurred.",
        f"Unhandled exception during request {request.method} {request.url.path}: {exc}",
    )

@app.get("/")
def root():
    return {
        "message": "InfyExchange API is running"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }