from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from backend.app.core.config import settings
from backend.app.api.deps import limiter
from backend.app.api.routers import auth, video, project
from backend.app.db.db_service import init_pool, close_pool
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    yield
    await close_pool()

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION, lifespan=lifespan)

# Rate Limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://localhost"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrando Roteadores
app.include_router(auth.router, prefix="/api/v1")
app.include_router(video.router, prefix="/api/v1")
app.include_router(project.router, prefix="/api/v1")

@app.get("/health")
def health_check():
    return {"status": "ok", "version": settings.VERSION}
