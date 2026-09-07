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
from backend.worker import process_video_task

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(BASE_DIR, "temp_videos")
os.makedirs(TEMP_DIR, exist_ok=True)

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="ClipMaker AI SaaS", version="3.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Update for production domain
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
    safe_filename = f"{uuid.uuid4()}.mp4"
    input_path = os.path.join(TEMP_DIR, safe_filename)

    try:
        contents = await file.read()
        with open(input_path, "wb") as buffer:
            buffer.write(contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar arquivo: {str(e)}")
    finally:
        await file.close()

    if os.path.getsize(input_path) == 0:
        os.remove(input_path)
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    # Criar projeto no DB
    project_id = await create_project(
        user_id=current_user['id'], 
        title=file.filename, 
        source_file_key=safe_filename, 
        duration_sec=0.0 # Will be updated by probe later
    )
    
    # Enviar para a fila (Celery/Huey)
    process_video_task(project_id, input_path, TEMP_DIR)
    
    return {"status": "processing", "project_id": project_id}

@app.post("/upload-url/")
@limiter.limit("5/minute")
async def process_url(request: Request, url: str = Form(...), current_user: dict = Depends(get_current_user)):
    safe_filename = f"{uuid.uuid4()}.mp4"
    input_path = os.path.join(TEMP_DIR, safe_filename)

    try:
        import sys
        result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "--merge-output-format", "mp4", "-o", input_path, url],
            capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            raise Exception(f"yt-dlp error: {result.stderr}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Erro download: {str(e)}")

    project_id = await create_project(
        user_id=current_user['id'], 
        title="Importação por URL", 
        source_file_key=safe_filename, 
        duration_sec=0.0,
        source_url=url
    )
    
    process_video_task(project_id, input_path, TEMP_DIR)
    
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
