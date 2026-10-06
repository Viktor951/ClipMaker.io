# ==============================================================================
# ClipMakerAI — Dockerfile multi-stage (produção)
# Usado por: api, worker, cleanup (mesma imagem, comandos diferentes)
# ==============================================================================

# ── ESTÁGIO 1: BUILDER ──────────────────────────────────────────────────────
# Cria um virtualenv completo. gcc/headers ficam SÓ aqui e são descartados.
FROM python:3.11-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY backend/requirements.txt .
RUN pip install -r requirements.txt


# ── ESTÁGIO 2: RUNTIME ──────────────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS runtime

# ffmpeg = única dependência de sistema em runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Usuário não-root com UID/GID fixos (facilita permissões em volumes).
RUN groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --home-dir /home/appuser \
        --create-home --shell /usr/sbin/nologin appuser

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MALLOC_ARENA_MAX=2 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    HF_HOME=/app/cache/huggingface \
    XDG_CACHE_HOME=/app/cache

WORKDIR /app

# Apenas o código necessário (sem tests/, frontend/, .git, .env — ver .dockerignore).
COPY --chown=appuser:appuser backend/ ./backend/
COPY --chown=appuser:appuser scripts/ ./scripts/

# Diretórios de dados (em produção são montados a partir de D:/docker-data/...).
RUN mkdir -p /app/backend/temp_videos /app/cache /app/logs \
    && chown -R appuser:appuser /app/backend/temp_videos /app/cache /app/logs

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

# --proxy-headers: respeita X-Forwarded-For do Caddy (rate limit por IP real).
# --workers 1: cada worker extra duplica a RAM; escale via mem_limit/replicas.
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--limit-concurrency", "50", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
