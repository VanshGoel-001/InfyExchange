from fastapi.openapi.utils import get_openapi

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.models import (
    Interest,
    Listing,
    ListingImage,
    Need,
    User,
)
from app.routers import (
    auth,
    interests,
    listings,
    needs,
    users,
)
from app.services.cleanup import cleanup_loop


@asynccontextmanager
async def lifespan(app: FastAPI):

    Base.metadata.create_all(
        bind=engine
    )

    cleanup_task = asyncio.create_task(
        cleanup_loop()
    )

    yield

    cleanup_task.cancel()

    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
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
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(auth.router)
app.include_router(users.router)
app.include_router(listings.router)
app.include_router(interests.router)
app.include_router(needs.router)


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