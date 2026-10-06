import os
import uuid
import subprocess
import socket
import ipaddress
import logging
from pathlib import Path
from urllib.parse import urlparse
import sys

from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Depends, Request
from fastapi.responses import FileResponse

from backend.app.api.deps import limiter, get_current_user
from backend.app.core.config import settings
from backend.app.db.db_service import create_project, get_clip, get_project_with_clips
from backend.app.services.video_service import get_video_info
from backend.app.worker.worker import process_video_task

logger = logging.getLogger("clipmaker.api.video")
router = APIRouter(prefix="/video", tags=["video"])

TEMP_DIR = Path(settings.TEMP_DIR)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = settings.MAX_FILE_SIZE_MB * 1024 * 1024
MAX_DURATION_SEC = settings.MAX_DURATION_SEC


def _is_safe_public_url(url: str) -> bool:
    """Proteção contra SSRF: bloqueia URLs internas, IPs privados e esquemas inválidos."""
    if not url or url.startswith("-"):
        return False
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    hostname = parsed.hostname
    if not hostname:
        return False

    # Bloqueia nomes internos do Docker e localhost
    blocked_hosts = {"localhost", "127.0.0.1", "db", "redis", "api", "worker", "proxy", "cleanup"}
    if hostname.lower() in blocked_hosts:
        return False

    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
            return False
    except ValueError:
        try:
            resolved_ip = socket.gethostbyname(hostname)
            ip = ipaddress.ip_address(resolved_ip)
            if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                return False
        except Exception:
            pass

    return True


@router.post("/upload-and-process/")
@limiter.limit("5/minute")
async def process_video(
    request: Request,
    file: UploadFile = File(...),
    aspect_ratio: str = Form("9:16"),
    current_user: dict = Depends(get_current_user)
):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"Arquivo muito grande (Limite de {settings.MAX_FILE_SIZE_MB}MB).")

    safe_filename = f"{uuid.uuid4()}.mp4"
    input_path = TEMP_DIR / safe_filename

    try:
        with open(input_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                buffer.write(chunk)
                if input_path.stat().st_size > MAX_FILE_SIZE:
                    break
    except Exception as e:
        if input_path.exists():
            input_path.unlink()
        logger.error(f"Erro ao salvar arquivo de upload: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao salvar arquivo enviado.")
    finally:
        await file.close()

    if input_path.exists() and input_path.stat().st_size > MAX_FILE_SIZE:
        input_path.unlink()
        raise HTTPException(status_code=400, detail=f"Arquivo muito grande (Limite de {settings.MAX_FILE_SIZE_MB}MB).")

    if not input_path.exists() or input_path.stat().st_size == 0:
        if input_path.exists():
            input_path.unlink()
        raise HTTPException(status_code=400, detail="Arquivo vazio ou inválido.")

    try:
        _, _, duration = get_video_info(str(input_path))
        if duration > MAX_DURATION_SEC:
            input_path.unlink()
            raise HTTPException(status_code=400, detail="O vídeo excede o limite de duração permitido.")
    except HTTPException:
        raise
    except Exception as e:
        input_path.unlink()
        logger.warning(f"Vídeo inválido enviado: {e}")
        raise HTTPException(status_code=400, detail="Arquivo de vídeo inválido ou corrompido.")

    project_id = await create_project(
        user_id=str(current_user["id"]),
        title=file.filename or "Upload de Vídeo",
        source_file_key=safe_filename,
        duration_sec=duration
    )

    process_video_task(project_id, str(input_path), str(TEMP_DIR), aspect_ratio)
    return {"status": "processing", "project_id": project_id}


@router.post("/upload-url/")
@limiter.limit("5/minute")
async def process_url(
    request: Request,
    url: str = Form(...),
    aspect_ratio: str = Form("9:16"),
    current_user: dict = Depends(get_current_user)
):
    clean_url = url.strip()
    if not _is_safe_public_url(clean_url):
        raise HTTPException(status_code=400, detail="URL inválida ou não permitida.")

    safe_filename = f"{uuid.uuid4()}.mp4"
    input_path = TEMP_DIR / safe_filename
    video_duration = 0.0

    try:
        probe_result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--force-ipv4", "--print", "duration", "--", clean_url],
            capture_output=True, text=True, timeout=60
        )
        if probe_result.returncode != 0:
            raise HTTPException(status_code=400, detail="Não foi possível acessar o vídeo. Ele pode ser privado ou restrito.")

        try:
            video_duration = float(probe_result.stdout.strip() or "0")
            if video_duration > MAX_DURATION_SEC:
                raise HTTPException(status_code=400, detail="O vídeo excede o limite de duração permitido.")
        except ValueError:
            pass

        download_cmd = [
            sys.executable, "-m", "yt_dlp",
            "--force-ipv4",
            "--quiet", "--no-progress",
            "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "-o", str(input_path),
            "--", clean_url
        ]

        result = subprocess.run(download_cmd, capture_output=True, text=True, timeout=1800)
        if result.returncode != 0:
            logger.warning(f"yt-dlp falhou: {result.stderr}")
            raise HTTPException(status_code=400, detail="Erro ao baixar o vídeo do link informado.")

    except HTTPException:
        if input_path.exists():
            input_path.unlink()
        raise
    except Exception as e:
        if input_path.exists():
            input_path.unlink()
        logger.error(f"Erro inesperado no download por URL: {e}")
        raise HTTPException(status_code=500, detail="Erro ao processar URL.")

    if not input_path.exists() or input_path.stat().st_size == 0:
        if input_path.exists():
            input_path.unlink()
        raise HTTPException(status_code=400, detail="Falha ao obter o vídeo (arquivo vazio).")

    project_id = await create_project(
        user_id=str(current_user["id"]),
        title="Importação por URL",
        source_file_key=safe_filename,
        duration_sec=video_duration,
        source_url=clean_url
    )

    process_video_task(project_id, str(input_path), str(TEMP_DIR), aspect_ratio)
    return {"status": "processing", "project_id": project_id}


@router.get("/download/{clip_id}")
async def download_clip(clip_id: str, current_user: dict = Depends(get_current_user)):
    safe_id = os.path.basename(clip_id)

    real_id = safe_id
    if real_id.startswith("clip_"):
        real_id = real_id[5:]
    if real_id.startswith("clean_"):
        real_id = real_id[6:]
    if real_id.endswith(".mp4"):
        real_id = real_id[:-4]

    clip_record = await get_clip(real_id)
    if not clip_record:
        raise HTTPException(status_code=404, detail="Registro do clipe não encontrado.")

    project = await get_project_with_clips(clip_record["projectid"])
    if not project or str(project["userid"]) != str(current_user["id"]):
        raise HTTPException(status_code=403, detail="Acesso negado.")

    file_path = TEMP_DIR / safe_id
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo de vídeo não encontrado.")

    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        headers={"Content-Disposition": f'inline; filename="{safe_id}"'}
    )
