import os
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from backend.app.core.logging_config import setup_logging

from backend.app.core.config import settings
from backend.app.api.deps import limiter
from backend.app.api.routers import auth, video, project
from backend.app.db.db_service import init_pool, close_pool
from contextlib import asynccontextmanager

setup_logging()
logger = logging.getLogger("clipmaker.api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()

_is_prod = settings.ENVIRONMENT == "production"
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Erro não tratado em %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Erro interno do servidor."})


# Rate Limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
cors_origins = [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",") if origin.strip()]
if not _is_prod:
    for common_origin in [
        "http://localhost", "http://localhost:8000", "http://localhost:3000", "http://localhost:5173", "http://localhost:8080",
        "http://127.0.0.1", "http://127.0.0.1:8000", "http://127.0.0.1:3000", "http://127.0.0.1:5173", "http://127.0.0.1:8080",
    ]:
        if common_origin not in cors_origins:
            cors_origins.append(common_origin)
else:
    # Em produção, remove estritamente 'null' e origens locais (S6.2)
    cors_origins = [
        o for o in cors_origins
        if o != "null" and not o.startswith("http://localhost") and not o.startswith("http://127.0.0.1")
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With", "Range"],
    expose_headers=["Content-Disposition", "Content-Length", "Accept-Ranges", "Content-Range"],
)

# Registrando Roteadores (compatibilidade total: /api/auth, /api/videos, /api/projects e /api/v1)
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])

app.include_router(video.router, prefix="/api/video", tags=["video"])
app.include_router(video.router, prefix="/api/videos", tags=["video"])
app.include_router(video.router, prefix="/api/v1/video", tags=["video"])
app.include_router(video.router, prefix="/api/v1/videos", tags=["video"])

app.include_router(project.router, prefix="/api/project", tags=["project"])
app.include_router(project.router, prefix="/api/projects", tags=["project"])
app.include_router(project.router, prefix="/api/v1/project", tags=["project"])
app.include_router(project.router, prefix="/api/v1/projects", tags=["project"])

@app.get("/health")
@app.get("/api/health")
def health_check():
    return {"status": "ok", "version": settings.VERSION}

@app.get("/api/config")
@app.get("/api/v1/config")
def get_config():
    return {
        "max_file_size_mb": settings.MAX_FILE_SIZE_MB,
        "max_duration_sec": settings.MAX_DURATION_SEC,
        "max_source_height": settings.MAX_SOURCE_HEIGHT,
        "min_password_length": settings.MIN_PASSWORD_LENGTH,
        "version": settings.VERSION,
    }

# Servir o frontend estático diretamente na rota raiz (/) via HTTP
_frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if os.getenv("SERVE_FRONTEND", "true").lower() in ("true", "1") and _frontend_dir.exists() and (_frontend_dir / "index.html").exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")



