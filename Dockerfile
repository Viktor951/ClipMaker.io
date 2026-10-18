# ==============================================================================
# ClipMakerAI — Dockerfile multi-stage (produção)
# Targets:
#   - runtime: imagem CPU padrão (usada por api, cleanup e worker em modo CPU)
#   - runtime-gpu: worker com suporte a GPU NVIDIA (CUDA / cuBLAS / cuDNN)
# ==============================================================================

# ── ESTÁGIO 1: BUILDER (CPU) ─────────────────────────────────────────────────
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


# ── ESTÁGIO 1B: BUILDER GPU (cuBLAS e cuDNN para CTranslate2) ─────────────────
FROM builder AS builder-gpu
RUN pip install --no-cache-dir nvidia-cublas-cu12 nvidia-cudnn-cu12


# ── ESTÁGIO 2: RUNTIME (CPU) ─────────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

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

COPY --chown=appuser:appuser backend/ ./backend/
COPY --chown=appuser:appuser scripts/ ./scripts/

RUN mkdir -p /app/backend/temp_videos /app/cache /app/logs \
    && chown -R appuser:appuser /app/backend/temp_videos /app/cache /app/logs

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--limit-concurrency", "50", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]


# ── ESTÁGIO 3: RUNTIME GPU (Worker com suporte a NVIDIA CUDA) ────────────────
FROM python:3.11-slim-bookworm AS runtime-gpu

RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --home-dir /home/appuser \
        --create-home --shell /usr/sbin/nologin appuser

COPY --from=builder-gpu /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    LD_LIBRARY_PATH="/opt/venv/lib/python3.11/site-packages/nvidia/cublas/lib:/opt/venv/lib/python3.11/site-packages/nvidia/cudnn/lib:${LD_LIBRARY_PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MALLOC_ARENA_MAX=2 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    HF_HOME=/app/cache/huggingface \
    XDG_CACHE_HOME=/app/cache \
    NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,video

WORKDIR /app

COPY --chown=appuser:appuser backend/ ./backend/
COPY --chown=appuser:appuser scripts/ ./scripts/

RUN mkdir -p /app/backend/temp_videos /app/cache /app/logs \
    && chown -R appuser:appuser /app/backend/temp_videos /app/cache /app/logs

USER appuser
CMD ["sh", "-c", "python -c 'from backend.app.services.ai_service import preload_whisper_model; preload_whisper_model()' && huey_consumer backend.app.worker.worker.huey -w 1 -k thread"]
