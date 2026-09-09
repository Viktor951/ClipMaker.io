from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Depends, Request
from fastapi.responses import FileResponse
from backend.app.api.deps import limiter, get_current_user
from backend.app.db.db_service import create_project
from backend.app.services.video_service import get_video_info
from backend.app.worker.worker import process_video_task
import os
import uuid
import subprocess
from pathlib import Path

router = APIRouter(prefix="/video", tags=["video"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
TEMP_DIR = BASE_DIR / "temp_videos"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
MAX_FILE_SIZE_MB = 2000
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_DURATION_SEC = 14400 # 4 hours

@router.post("/upload-and-process/")
@limiter.limit("5/minute")
async def process_video(request: Request, file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    content_length = request.headers.get('content-length')
    if content_length and int(content_length) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"Arquivo muito grande (Limite de {MAX_FILE_SIZE_MB}MB).")

    safe_filename = f"{uuid.uuid4()}.mp4"
    input_path = TEMP_DIR / safe_filename

    try:
        with open(input_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                buffer.write(chunk)
                if input_path.stat().st_size > MAX_FILE_SIZE:
                    break
    except Exception as e:
        if input_path.exists(): input_path.unlink()
        raise HTTPException(status_code=500, detail=f"Erro ao salvar arquivo: {str(e)}")
    finally:
        await file.close()

    if input_path.exists() and input_path.stat().st_size > MAX_FILE_SIZE:
        input_path.unlink()
        raise HTTPException(status_code=400, detail=f"Arquivo muito grande (Limite de {MAX_FILE_SIZE_MB}MB).")

    if not input_path.exists() or input_path.stat().st_size == 0:
        if input_path.exists(): input_path.unlink()
        raise HTTPException(status_code=400, detail="Arquivo vazio ou inválido.")

    try:
        _, _, duration = get_video_info(str(input_path))
        if duration > MAX_DURATION_SEC:
            input_path.unlink()
            raise HTTPException(status_code=400, detail="O vídeo excede o limite de duração (Máximo 4 horas).")
    except Exception as e:
        input_path.unlink()
        raise HTTPException(status_code=400, detail=f"Arquivo de vídeo inválido ou corrompido: {str(e)}")

    project_id = await create_project(
        user_id=current_user['id'], 
        title=file.filename, 
        source_file_key=safe_filename, 
        duration_sec=duration
    )
    
    process_video_task(project_id, str(input_path), str(TEMP_DIR))
    return {"status": "processing", "project_id": project_id}

@router.post("/upload-url/")
@limiter.limit("5/minute")
async def process_url(request: Request, url: str = Form(...), current_user: dict = Depends(get_current_user)):
    safe_filename = f"{uuid.uuid4()}.mp4"
    input_path = TEMP_DIR / safe_filename
    video_duration = 0.0

    try:
        import sys
        probe_result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--force-ipv4", "--print", "duration", url],
            capture_output=True, text=True, timeout=60
        )
        if probe_result.returncode != 0:
            raise HTTPException(status_code=400, detail="Não foi possível acessar o vídeo. Ele pode ser privado, inválido ou restrito.")
            
        try:
            video_duration = float(probe_result.stdout.strip() or "0")
            if video_duration > MAX_DURATION_SEC:
                raise HTTPException(status_code=400, detail="O vídeo excede o limite de duração (Máximo 4 horas).")
        except ValueError:
            pass 

        download_cmd = [
            sys.executable, "-m", "yt_dlp", 
            "--force-ipv4",
            "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4", 
            "-o", str(input_path), 
            url
        ]
        
        result = subprocess.run(download_cmd, capture_output=True, text=True, timeout=600)
        
        if result.returncode != 0:
            error_line = result.stderr.strip().splitlines()[-1] if result.stderr else "Desconhecido"
            raise HTTPException(status_code=400, detail=f"Erro ao baixar o vídeo. {error_line}")
            
    except HTTPException:
        if input_path.exists(): input_path.unlink()
        raise
    except Exception as e:
        if input_path.exists(): input_path.unlink()
        raise HTTPException(status_code=500, detail=f"Erro inesperado: {str(e)}")

    if not input_path.exists() or input_path.stat().st_size == 0:
        if input_path.exists(): input_path.unlink()
        raise HTTPException(status_code=400, detail="Falha ao baixar o arquivo (Arquivo vazio).")

    project_id = await create_project(
        user_id=current_user['id'], 
        title="Importação por URL", 
        source_file_key=safe_filename, 
        duration_sec=video_duration,
        source_url=url
    )
    
    process_video_task(project_id, str(input_path), str(TEMP_DIR))
    return {"status": "processing", "project_id": project_id}

@router.get("/download/{clip_id}")
async def download_clip(clip_id: str):
    safe_id = os.path.basename(clip_id)
    file_path = TEMP_DIR / safe_id
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    return FileResponse(path=str(file_path), media_type="video/mp4", headers={"Content-Disposition": f'attachment; filename="{safe_id}"'})
