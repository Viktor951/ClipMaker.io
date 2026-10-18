import os
import uuid
import socket
import ipaddress
import logging
import asyncio
from pathlib import Path
from urllib.parse import urlparse

from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Depends, Request, Query
from fastapi.responses import FileResponse, Response

from backend.app.api.deps import limiter, get_current_user, get_current_user_optional
from backend.app.core.config import settings
from backend.app.core.security import create_signed_url_token, verify_signed_url_token
from backend.app.db.db_service import create_project, get_clip_with_owner, count_active_projects_by_user
from backend.app.services.video_service import get_video_info
from backend.app.worker.worker import process_video_task, download_and_process_url_task

logger = logging.getLogger("clipmaker.api.video")
router = APIRouter(tags=["video"])

TEMP_DIR = Path(settings.TEMP_DIR)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = settings.MAX_FILE_SIZE_MB * 1024 * 1024
MAX_DURATION_SEC = settings.MAX_DURATION_SEC


def _is_safe_public_url(url: str) -> bool:
    """
    Proteção robusta contra SSRF:
    - Rejeita URLs vazias, iniciadas por '-' ou com esquemas diferentes de http/https.
    - Bloqueia hostnames internos conhecidos e loopback.
    - Resolve o hostname via socket.getaddrinfo (IPv4 e IPv6).
    - Valida que TODOS os endereços IP resolvidos sejam estritamente globais/públicos (ip.is_global).
    - Falha fechada (rejeita / retorna False) se a resolução de DNS falhar ou levantar qualquer exceção.
    """
    if not url or url.startswith("-"):
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    raw_host = hostname.strip("[]").strip()
    if not raw_host:
        return False

    blocked_hosts = {"localhost", "127.0.0.1", "db", "redis", "api", "worker", "proxy", "cleanup"}
    if raw_host.lower() in blocked_hosts:
        return False

    # Se for um IP literal direto
    try:
        ip = ipaddress.ip_address(raw_host)
        return ip.is_global
    except ValueError:
        pass

    # Resolução de DNS completa (IPv4 e IPv6)
    try:
        addr_infos = socket.getaddrinfo(raw_host, None)
        if not addr_infos:
            return False

        for addr in addr_infos:
            sockaddr = addr[4]
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            if not ip.is_global:
                return False

        return True
    except Exception:
        # Falha fechado caso o DNS não resolva (gaierror, timeout, etc.)
        return False


def _save_upload_file_sync(file_obj, destination_path: Path, max_size: int) -> int:
    """Gravação síncrona em blocos para execução em worker thread dedicada."""
    written = 0
    with open(destination_path, "wb") as buffer:
        while True:
            chunk = file_obj.read(1024 * 1024)
            if not chunk:
                break
            buffer.write(chunk)
            written += len(chunk)
            if written > max_size:
                raise ValueError("Arquivo muito grande")
    return written


@router.post("/upload-and-process/")
@router.post("/upload-and-process")
@router.post("/upload")
@limiter.limit("5/minute")
async def process_video(
    request: Request,
    file: UploadFile = File(...),
    aspect_ratio: str = Form("9:16"),
    current_user: dict = Depends(get_current_user)
):
    if aspect_ratio not in ("9:16", "1:1", "16:9"):
        raise HTTPException(status_code=400, detail="aspect_ratio inválido. Permitidos: '9:16', '1:1', '16:9'.")

    # Limite de concorrência por usuário
    active_jobs = await count_active_projects_by_user(str(current_user["id"]))
    if active_jobs >= settings.MAX_CONCURRENT_JOBS_PER_USER:
        raise HTTPException(
            status_code=429,
            detail=f"Limite de {settings.MAX_CONCURRENT_JOBS_PER_USER} processamentos simultâneos atingido. Aguarde a conclusão dos projetos em andamento."
        )

    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"Arquivo muito grande (Limite de {settings.MAX_FILE_SIZE_MB}MB).")

    safe_filename = f"{uuid.uuid4()}.mp4"
    input_path = TEMP_DIR / safe_filename

    try:
        # Gravação assíncrona desacoplada do event loop via threadpool
        await asyncio.to_thread(_save_upload_file_sync, file.file, input_path, MAX_FILE_SIZE)
    except ValueError:
        if input_path.exists():
            input_path.unlink()
        raise HTTPException(status_code=400, detail=f"Arquivo muito grande (Limite de {settings.MAX_FILE_SIZE_MB}MB).")
    except Exception as e:
        if input_path.exists():
            input_path.unlink()
        logger.error(f"Erro ao salvar arquivo de upload: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao salvar arquivo enviado.")
    finally:
        await file.close()

    if not input_path.exists() or input_path.stat().st_size == 0:
        if input_path.exists():
            input_path.unlink()
        raise HTTPException(status_code=400, detail="Arquivo vazio ou inválido.")

    try:
        # Extração de metadados/duração via ffprobe desacoplada do event loop
        _, _, duration = await asyncio.to_thread(get_video_info, str(input_path))
        if duration > MAX_DURATION_SEC:
            input_path.unlink()
            raise HTTPException(status_code=400, detail="O vídeo excede o limite de duração permitido.")
    except HTTPException:
        raise
    except Exception as e:
        if input_path.exists():
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
@router.post("/upload-url")
@router.post("/process-url")
@limiter.limit("5/minute")
async def process_url(
    request: Request,
    url: str = Form(...),
    aspect_ratio: str = Form("9:16"),
    current_user: dict = Depends(get_current_user)
):
    if aspect_ratio not in ("9:16", "1:1", "16:9"):
        raise HTTPException(status_code=400, detail="aspect_ratio inválido. Permitidos: '9:16', '1:1', '16:9'.")

    # Limite de concorrência por usuário
    active_jobs = await count_active_projects_by_user(str(current_user["id"]))
    if active_jobs >= settings.MAX_CONCURRENT_JOBS_PER_USER:
        raise HTTPException(
            status_code=429,
            detail=f"Limite de {settings.MAX_CONCURRENT_JOBS_PER_USER} processamentos simultâneos atingido. Aguarde a conclusão dos projetos em andamento."
        )

    clean_url = url.strip()
    if not _is_safe_public_url(clean_url):
        raise HTTPException(status_code=400, detail="URL inválida ou não permitida.")

    safe_filename = f"{uuid.uuid4()}.mp4"

    # Cria o projeto imediatamente com status inicial DOWNLOADING
    project_id = await create_project(
        user_id=str(current_user["id"]),
        title="Importação por URL",
        source_file_key=safe_filename,
        duration_sec=0.0,
        source_url=clean_url,
        status="DOWNLOADING"
    )

    # Dispara a tarefa de download e probe assíncronos na fila do Huey, liberando a rota em < 15ms
    download_and_process_url_task(project_id, clean_url, str(TEMP_DIR), aspect_ratio)
    return {"status": "processing", "project_id": project_id, "initial_status": "DOWNLOADING"}


@router.post("/signed-url/{clip_id}")
@router.post("/{clip_id}/signed-url")
async def generate_signed_url_endpoint(
    clip_id: str,
    current_user: dict = Depends(get_current_user)
):
    safe_id = os.path.basename(clip_id)
    real_id = safe_id
    if real_id.startswith("clip_"):
        real_id = real_id[5:]
    if real_id.startswith("clean_"):
        real_id = real_id[6:]
    if real_id.endswith(".mp4"):
        real_id = real_id[:-4]

    clip_record = await get_clip_with_owner(real_id)
    if not clip_record:
        raise HTTPException(status_code=404, detail="Registro do clipe não encontrado.")

    if str(clip_record["userId"]) != str(current_user["id"]):
        raise HTTPException(status_code=403, detail="Acesso negado.")

    sig = create_signed_url_token(str(current_user["id"]), real_id, expires_in_sec=300)
    return {
        "status": "success",
        "clip_id": real_id,
        "sig": sig,
        "download_url": f"/api/videos/download/{real_id}?sig={sig}",
        "thumbnail_url": f"/api/videos/thumbnail/{real_id}?sig={sig}",
        "expires_in": 300
    }


@router.get("/download/{clip_id}")
async def download_clip(
    clip_id: str,
    request: Request,
    sig: Optional[str] = Query(None),
    current_user: Optional[dict] = Depends(get_current_user_optional)
):
    safe_id = os.path.basename(clip_id)

    real_id = safe_id
    if real_id.startswith("clip_"):
        real_id = real_id[5:]
    if real_id.startswith("clean_"):
        real_id = real_id[6:]
    if real_id.endswith(".mp4"):
        real_id = real_id[:-4]

    user_id = None
    if sig:
        sig_data = verify_signed_url_token(sig, expected_clip_id=real_id)
        if not sig_data:
            raise HTTPException(status_code=403, detail="Assinatura inválida ou expirada.")
        user_id = sig_data["user_id"]
    elif current_user:
        user_id = str(current_user["id"])
    else:
        raise HTTPException(status_code=401, detail="Não autenticado.")

    # Consulta otimizada com JOIN único: traz clipe e userId do dono sem carregar todos os clipes nem fazer parse JSON
    clip_record = await get_clip_with_owner(real_id)
    if not clip_record:
        raise HTTPException(status_code=404, detail="Registro do clipe não encontrado.")

    if str(clip_record["userId"]) != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado.")

    # Nome do arquivo derivado estritamente do banco de dados (renderedUrl)
    rendered_url = clip_record.get("renderedUrl") or f"clip_{real_id}.mp4"
    filename = os.path.basename(rendered_url)

    # Verificação de segurança: confirma que o caminho resolvido está estritamente dentro de TEMP_DIR
    temp_dir_resolved = TEMP_DIR.resolve()
    file_path = (TEMP_DIR / filename).resolve()
    try:
        file_path.relative_to(temp_dir_resolved)
    except ValueError:
        raise HTTPException(status_code=403, detail="Acesso a caminho de arquivo não permitido.")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo de vídeo não encontrado.")

    # Suporte a entrega acelerada de vídeo pelo Nginx via X-Accel-Redirect
    use_accel = os.getenv("USE_NGINX_ACCEL", "false").lower() in ("true", "1")

    if use_accel:
        response = Response(status_code=200)
        response.headers["X-Accel-Redirect"] = f"/internal_videos/{filename}"
        response.headers["Content-Type"] = "video/mp4"
        response.headers["Content-Disposition"] = f'inline; filename="{filename}"'
        response.headers["Accept-Ranges"] = "bytes"
        return response

    # Fallback para FileResponse caso não esteja rodando com proxy Nginx
    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )


@router.get("/thumbnail/{clip_id}")
async def get_thumbnail(
    clip_id: str,
    request: Request,
    sig: Optional[str] = Query(None),
    current_user: Optional[dict] = Depends(get_current_user_optional)
):
    safe_id = os.path.basename(clip_id)

    real_id = safe_id
    if real_id.startswith("clip_") or real_id.startswith("thumb_"):
        real_id = real_id[real_id.find("_") + 1:]
    if real_id.endswith(".mp4") or real_id.endswith(".jpg"):
        real_id = real_id[:real_id.rfind(".")]

    user_id = None
    if sig:
        sig_data = verify_signed_url_token(sig, expected_clip_id=real_id)
        if not sig_data:
            raise HTTPException(status_code=403, detail="Assinatura inválida ou expirada.")
        user_id = sig_data["user_id"]
    elif current_user:
        user_id = str(current_user["id"])
    else:
        raise HTTPException(status_code=401, detail="Não autenticado.")

    clip_record = await get_clip_with_owner(real_id)
    if not clip_record:
        raise HTTPException(status_code=404, detail="Registro do clipe não encontrado.")

    if str(clip_record["userId"]) != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado.")

    thumb_key = clip_record.get("thumbnail_key") or f"thumb_{real_id}.jpg"
    filename = os.path.basename(thumb_key)

    temp_dir_resolved = TEMP_DIR.resolve()
    thumb_path = (TEMP_DIR / filename).resolve()
    try:
        thumb_path.relative_to(temp_dir_resolved)
    except ValueError:
        raise HTTPException(status_code=403, detail="Acesso a caminho não permitido.")

    if not thumb_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo de miniatura não encontrado.")

    return FileResponse(
        path=str(thumb_path),
        media_type="image/jpeg",
        headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )
