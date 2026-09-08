from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Depends, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
import os
import uuid
import subprocess
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from backend.services.auth_service import verify_password, get_password_hash, create_access_token, decode_access_token
from backend.services.db_service import get_user_by_email, create_user_safe, create_project, get_project_with_clips
from backend.services.video_service import get_video_info
from backend.worker import process_video_task
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
TEMP_DIR = BASE_DIR / "temp_videos"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
MAX_FILE_SIZE_MB = 2000
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024
MAX_DURATION_SEC = 14400 # 4 hours

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="ClipMaker AI SaaS", version="3.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    email = payload.get("sub")
    user = await get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

class UserCreate(BaseModel):
    email: str
    password: str
    name: str = None

@app.post("/auth/register")
async def register(user: UserCreate):
    existing = await get_user_by_email(user.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email já cadastrado")
    hashed = get_password_hash(user.password)
    new_user = await create_user_safe(user.email, hashed, user.name)
    return {"status": "success", "user_id": new_user['id']}

@app.post("/auth/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await get_user_by_email(form_data.username)
    if not user or not verify_password(form_data.password, user['passwordHash']):
        raise HTTPException(status_code=400, detail="Email ou senha incorretos")
    
    access_token = create_access_token(data={"sub": user['email']})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/upload-and-process/")
@limiter.limit("5/minute")
async def process_video(request: Request, file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    content_length = request.headers.get('content-length')
    if content_length and int(content_length) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Arquivo muito grande (Limite de 500MB).")

    safe_filename = f"{uuid.uuid4()}.mp4"
    input_path = TEMP_DIR / safe_filename

    try:
        with open(input_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024): # Ler em chunks de 1MB
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
        raise HTTPException(status_code=400, detail="Arquivo muito grande (Limite de 500MB).")

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

    # Criar projeto no DB
    project_id = await create_project(
        user_id=current_user['id'], 
        title=file.filename, 
        source_file_key=safe_filename, 
        duration_sec=duration
    )
    
    # Enviar para a fila (Celery/Huey)
    process_video_task(project_id, str(input_path), str(TEMP_DIR))
    
    return {"status": "processing", "project_id": project_id}

@app.post("/upload-url/")
@limiter.limit("5/minute")
async def process_url(request: Request, url: str = Form(...), current_user: dict = Depends(get_current_user)):
    safe_filename = f"{uuid.uuid4()}.mp4"
    input_path = TEMP_DIR / safe_filename
    video_duration = 0.0

    try:
        import sys
        
        # 1. Verificar a duração e disponibilidade antes de baixar
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

        # 2. Baixar o vídeo limitando a 1080p
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
        import traceback
        traceback.print_exc()
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

@app.get("/project/{project_id}/status")
async def get_project_status(project_id: str, current_user: dict = Depends(get_current_user)):
    project = await get_project_with_clips(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
    if project['userId'] != current_user['id']:
        raise HTTPException(status_code=403, detail="Acesso negado")
        
    return {
        "status": project['status'],
        "error": project['errorMessage'],
        "clips": project.get('clips', [])
    }

@app.get("/download/{clip_id}")
async def download_clip(clip_id: str):
    safe_id = os.path.basename(clip_id)
    file_path = os.path.join(TEMP_DIR, safe_id)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    return FileResponse(path=file_path, media_type="video/mp4", headers={"Content-Disposition": f'attachment; filename="{safe_id}"'})
