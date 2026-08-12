from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api import auth, dashboard, leads, lists, workspace
from app.core.config import settings
from app.core.database import mongo
from app.services.seeding import seed_database

VERSION = "1.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo.connect()
    seed_database()
    yield
    mongo.close()


docs_url = "/docs" if settings.enable_api_docs else None
app = FastAPI(
    title=settings.app_name,
    version=VERSION,
    lifespan=lifespan,
    docs_url=docs_url,
    redoc_url=None,
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith(settings.api_prefix) else "no-cache"
    return response


app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(dashboard.router, prefix=settings.api_prefix)
app.include_router(leads.router, prefix=settings.api_prefix)
app.include_router(lists.router, prefix=settings.api_prefix)
app.include_router(workspace.router, prefix=settings.api_prefix)


@app.get("/")
def root():
    return {"name": settings.app_name, "version": VERSION}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": VERSION,
        "database": "mongodb",
        "cloudinary": settings.cloudinary_configured,
        "providers": {
            "google_places": bool(settings.google_places_api_key),
            "geoapify": bool(settings.geoapify_api_key),
            "openstreetmap": True,
            "website_contact_enrichment": settings.enable_website_contact_enrichment,
        },
    }
