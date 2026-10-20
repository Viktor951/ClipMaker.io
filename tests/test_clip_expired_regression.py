import uuid
import pytest
from pathlib import Path
from httpx import AsyncClient

from backend.app.main import app
from backend.app.core.config import settings
from backend.app.core.security import create_signed_url_token
from backend.app.db.db_service import create_project, save_single_clip, mark_file_records_expired

def get_client():
    try:
        from httpx import ASGITransport
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")
    except (ImportError, TypeError):
        return AsyncClient(app=app, base_url="http://test")

@pytest.mark.asyncio
async def test_clip_download_410_gone_when_file_deleted():
    """Testa que se o clipe existe no banco mas o arquivo físico foi removido, a API retorna 410 Gone (não 404)."""
    async with get_client() as ac:
        email = f"user_{uuid.uuid4().hex[:8]}@example.com"
        pwd = "securePassword123!"
        reg = await ac.post("/api/v1/auth/register", json={"email": email, "password": pwd})
        user_id = reg.json()["user_id"]
        login = await ac.post("/api/v1/auth/login", data={"username": email, "password": pwd})
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        project_id = await create_project(user_id, "Projeto Expirado", "source_exp.mp4", 45.0)
        clip_id = str(uuid.uuid4())
        clip_filename = f"clip_{clip_id}.mp4"

        # Garante que o arquivo físico NÃO existe no disco
        physical_file = Path(settings.TEMP_DIR) / clip_filename
        if physical_file.exists():
            physical_file.unlink()

        await save_single_clip(project_id, {
            "id": clip_id,
            "renderedUrl": clip_filename,
            "title": "Clipe que Expirou",
            "startTime": 0.0,
            "endTime": 15.0,
            "durationSec": 15.0,
            "viralScore": 88,
            "aspectRatio": "9:16",
            "hookReason": "Hook de Teste",
            "words": []
        })

        sig = create_signed_url_token(user_id, clip_id, expires_in_sec=3600)

        # 1. Download do clipe com arquivo ausente deve retornar 410 Gone com código clip_expired
        res = await ac.get(f"/api/videos/download/{clip_id}?sig={sig}")
        assert res.status_code == 410
        body = res.json()
        assert body["detail"]["code"] == "clip_expired"

        # 2. Obtenção de nova URL assinada para clipe ausente deve retornar 410 Gone
        res_sig = await ac.post(f"/api/videos/{clip_id}/signed-url", headers=headers)
        assert res_sig.status_code == 410
        assert res_sig.json()["detail"]["code"] == "clip_expired"

        # 3. Miniatura ausente para clipe existente deve retornar 410 Gone
        res_thumb = await ac.get(f"/api/videos/thumbnail/{clip_id}?sig={sig}")
        assert res_thumb.status_code == 410
        assert res_thumb.json()["detail"]["code"] == "clip_expired"

@pytest.mark.asyncio
async def test_clip_download_404_when_record_not_found():
    """Testa que se o clipe nem sequer existe no banco de dados, a API retorna 404 Not Found (não 410)."""
    async with get_client() as ac:
        email = f"user_{uuid.uuid4().hex[:8]}@example.com"
        pwd = "securePassword123!"
        reg = await ac.post("/api/v1/auth/register", json={"email": email, "password": pwd})
        user_id = reg.json()["user_id"]

        fake_clip_id = str(uuid.uuid4())
        sig = create_signed_url_token(user_id, fake_clip_id, expires_in_sec=3600)

        res = await ac.get(f"/api/videos/download/{fake_clip_id}?sig={sig}")
        assert res.status_code == 404
        assert "não encontrado" in res.json()["detail"]

@pytest.mark.asyncio
async def test_project_status_reflects_expired_when_files_missing():
    """Testa que se um projeto READY tiver seus clipes removidos do disco, a API de status reflete status EXPIRED."""
    async with get_client() as ac:
        email = f"user_{uuid.uuid4().hex[:8]}@example.com"
        pwd = "securePassword123!"
        reg = await ac.post("/api/v1/auth/register", json={"email": email, "password": pwd})
        user_id = reg.json()["user_id"]
        login = await ac.post("/api/v1/auth/login", data={"username": email, "password": pwd})
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        project_id = await create_project(user_id, "Projeto Arquivos Limpos", "source.mp4", 30.0, status="READY")
        clip_id = str(uuid.uuid4())
        clip_filename = f"clip_{clip_id}.mp4"

        # Garante ausência física
        p_file = Path(settings.TEMP_DIR) / clip_filename
        if p_file.exists():
            p_file.unlink()

        await save_single_clip(project_id, {
            "id": clip_id,
            "renderedUrl": clip_filename,
            "title": "Clipe 1",
            "startTime": 0.0,
            "endTime": 10.0,
            "durationSec": 10.0,
            "viralScore": 80,
            "aspectRatio": "9:16",
            "words": []
        })

        status_res = await ac.get(f"/api/projects/{project_id}/status", headers=headers)
        assert status_res.status_code == 200
        data = status_res.json()
        assert data["status"] == "EXPIRED"
        assert len(data["clips"]) == 1
        assert data["clips"][0]["status"] == "EXPIRED"
        assert data["clips"][0]["videoExists"] is False

@pytest.mark.asyncio
async def test_cleanup_mark_file_records_expired():
    """Testa a função de marcação no banco de dados invocada pelo cleanup.py."""
    async with get_client() as ac:
        email = f"user_{uuid.uuid4().hex[:8]}@example.com"
        pwd = "securePassword123!"
        reg = await ac.post("/api/v1/auth/register", json={"email": email, "password": pwd})
        user_id = reg.json()["user_id"]

        project_id = await create_project(user_id, "Proj Cleanup", "cleaned_source.mp4", 20.0, status="READY")
        clip_id = str(uuid.uuid4())
        clip_filename = f"clip_{clip_id}.mp4"

        await save_single_clip(project_id, {
            "id": clip_id,
            "renderedUrl": clip_filename,
            "title": "Clipe Removido",
            "startTime": 0.0,
            "endTime": 10.0,
            "durationSec": 10.0,
            "viralScore": 85,
            "aspectRatio": "9:16",
            "words": []
        })

        result = await mark_file_records_expired([clip_filename, "cleaned_source.mp4"])
        assert result["expired_clips"] >= 1
        assert result["expired_projects"] >= 1
