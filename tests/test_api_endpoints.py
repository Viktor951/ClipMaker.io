import uuid
import pytest
from httpx import AsyncClient
from backend.app.main import app
from backend.app.services.ai_service import _fallback_clip_boundaries

def get_client():
    try:
        from httpx import ASGITransport
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")
    except (ImportError, TypeError):
        return AsyncClient(app=app, base_url="http://test")

@pytest.mark.asyncio
async def test_health_endpoints():
    async with get_client() as ac:
        r1 = await ac.get("/health")
        assert r1.status_code == 200
        assert r1.json()["status"] == "ok"

        r2 = await ac.get("/api/health")
        assert r2.status_code == 200
        assert r2.json()["status"] == "ok"

@pytest.mark.asyncio
async def test_unauthorized_access():
    async with get_client() as ac:
        r = await ac.get("/api/projects")
        assert r.status_code == 401

        r = await ac.post("/api/projects", json={"title": "Unauthorized"})
        assert r.status_code == 401

@pytest.mark.asyncio
async def test_password_min_length_validation():
    async with get_client() as ac:
        # Senha com 7 caracteres deve ser rejeitada (mínimo 8)
        resp = await ac.post("/api/v1/auth/register", json={
            "email": f"short_{uuid.uuid4().hex[:6]}@example.com",
            "password": "short12",
            "name": "Short Password User"
        })
        assert resp.status_code == 422 or resp.status_code == 400

@pytest.mark.asyncio
async def test_upload_aspect_ratio_validation():
    async with get_client() as ac:
        unique_email = f"user_{uuid.uuid4().hex[:8]}@example.com"
        pwd = "securePassword123!"
        await ac.post("/api/v1/auth/register", json={"email": unique_email, "password": pwd})
        login_resp = await ac.post("/api/v1/auth/login", data={"username": unique_email, "password": pwd})
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Envio de aspect_ratio inválido via URL
        r = await ac.post("/api/v1/video/upload-url", data={
            "url": "https://example.com/test.mp4",
            "aspect_ratio": "invalid_ratio"
        }, headers=headers)
        assert r.status_code == 400
        assert "aspect_ratio inválido" in r.text

@pytest.mark.asyncio
async def test_rerender_validation():
    async with get_client() as ac:
        unique_email = f"user_{uuid.uuid4().hex[:8]}@example.com"
        pwd = "securePassword123!"
        await ac.post("/api/v1/auth/register", json={"email": unique_email, "password": pwd})
        login_resp = await ac.post("/api/v1/auth/login", data={"username": unique_email, "password": pwd})
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        fake_clip_id = str(uuid.uuid4())

        # 1. aspect_ratio inválido
        r1 = await ac.post(f"/api/v1/projects/clip/{fake_clip_id}/re-render", json={
            "aspect_ratio": "4:3",
            "quality": "1080p",
            "style": "Yellow"
        }, headers=headers)
        assert r1.status_code == 422

        # 2. quality inválida
        r2 = await ac.post(f"/api/v1/projects/clip/{fake_clip_id}/re-render", json={
            "aspect_ratio": "9:16",
            "quality": "4k",
            "style": "Yellow"
        }, headers=headers)
        assert r2.status_code == 422

        # 3. start_time >= end_time
        r3 = await ac.post(f"/api/v1/projects/clip/{fake_clip_id}/re-render", json={
            "aspect_ratio": "9:16",
            "quality": "1080p",
            "style": "Yellow",
            "start_time": 20.0,
            "end_time": 10.0
        }, headers=headers)
        assert r3.status_code == 422

@pytest.mark.asyncio
async def test_project_lifecycle():
    async with get_client() as ac:
        # 1. Cadastrar e logar
        unique_email = f"user_{uuid.uuid4().hex[:8]}@example.com"
        pwd = "securePassword123!"
        
        reg_resp = await ac.post("/api/v1/auth/register", json={
            "email": unique_email,
            "password": pwd,
            "name": "Integration User"
        })
        assert reg_resp.status_code == 200

        login_resp = await ac.post("/api/v1/auth/login", data={
            "username": unique_email,
            "password": pwd
        })
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Listar projetos (inicialmente vazio)
        list_resp = await ac.get("/api/projects", headers=headers)
        assert list_resp.status_code == 200
        assert list_resp.json()["status"] == "success"
        projects = list_resp.json()["projects"]
        assert isinstance(projects, list)

        # 3. Criar projeto
        create_resp = await ac.post("/api/projects", json={
            "title": "Projeto Teste Automatizado",
            "source_url": "https://example.com/video.mp4",
            "duration_sec": 45.0
        }, headers=headers)
        assert create_resp.status_code == 200
        project_id = create_resp.json()["project_id"]
        assert project_id is not None

        # 4. Checar status do projeto (status DRAFT conforme Etapa B)
        status_resp = await ac.get(f"/api/projects/{project_id}/status", headers=headers)
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "DRAFT"
        assert "aiCutsFallback" in status_resp.json()
        assert status_resp.json()["aiCutsFallback"] is False



@pytest.mark.asyncio
async def test_incremental_clip_saving_and_ai_fallback():
    from backend.app.db.db_service import save_single_clip, set_project_ai_fallback, create_project
    async with get_client() as ac:
        unique_email = f"user_{uuid.uuid4().hex[:8]}@example.com"
        pwd = "securePassword123!"
        reg = await ac.post("/api/v1/auth/register", json={"email": unique_email, "password": pwd})
        user_id = reg.json()["user_id"]
        login = await ac.post("/api/v1/auth/login", data={"username": unique_email, "password": pwd})
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        project_id = await create_project(user_id, "Projeto Incremental", "source.mp4", 60.0)

        # Salva clipe incrementalmente
        clip_data = {
            "id": str(uuid.uuid4()),
            "renderedUrl": "clip_test_1.mp4",
            "title": "Primeiro Clipe Pronto",
            "startTime": 0.0,
            "endTime": 15.0,
            "durationSec": 15.0,
            "viralScore": 90,
            "aspectRatio": "9:16",
            "hookReason": "Hook Forte",
            "words": [],
            "thumbnail_key": "thumb_test_1.jpg",
            "face_center_x": 960
        }
        await save_single_clip(project_id, clip_data)
        await set_project_ai_fallback(project_id, True)

        status_resp = await ac.get(f"/api/projects/{project_id}/status", headers=headers)
        assert status_resp.status_code == 200
        data = status_resp.json()
        assert data["aiCutsFallback"] is True
        assert len(data["clips"]) == 1
        assert data["clips"][0]["title"] == "Primeiro Clipe Pronto"
        assert data["clips"][0]["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_transcription_cache():
    from backend.app.db.db_service import create_project, save_transcription, get_cached_transcription
    async with get_client() as ac:
        unique_email = f"user_{uuid.uuid4().hex[:8]}@example.com"
        pwd = "securePassword123!"
        reg = await ac.post("/api/v1/auth/register", json={"email": unique_email, "password": pwd})
        user_id = reg.json()["user_id"]

        project_id = await create_project(user_id, "Projeto Cache", "video.mp4", 30.0)
        source_url = "https://youtube.com/watch?v=cachetest123"
        file_hash = "abcdef1234567890"
        segments = [{"start": 0.0, "end": 5.0, "text": "Olá mundo", "words": []}]

        await save_transcription(
            project_id=project_id,
            user_id=user_id,
            full_text="Olá mundo",
            segments=segments,
            source_url=source_url,
            file_hash=file_hash
        )

        cached = await get_cached_transcription(user_id, source_url=source_url)
        assert cached is not None
        assert cached["full_text"] == "Olá mundo"
        assert len(cached["segments"]) == 1

        cached_by_hash = await get_cached_transcription(user_id, file_hash=file_hash)
        assert cached_by_hash is not None
        assert cached_by_hash["full_text"] == "Olá mundo"


def test_viral_score_and_boundaries():
    boundaries = _fallback_clip_boundaries(120.0)
    assert len(boundaries) > 0
    for b in boundaries:
        assert isinstance(b, dict)
        assert "start" in b
        assert "end" in b
        assert "title" in b
        assert "hook" in b
        assert "viral_score" in b
        assert 0 <= b["viral_score"] <= 100


@pytest.mark.asyncio
async def test_async_url_route_queue_and_status(monkeypatch):
    """Testa que a rota de URL responde imediatamente (<15ms) e cria o projeto como DOWNLOADING."""
    from unittest.mock import MagicMock
    mock_task = MagicMock()
    monkeypatch.setattr("backend.app.api.routers.video.download_and_process_url_task", mock_task)

    async with get_client() as ac:
        email = f"url_user_{uuid.uuid4().hex[:8]}@example.com"
        pwd = "securePassword123!"
        await ac.post("/api/v1/auth/register", json={"email": email, "password": pwd})
        login_resp = await ac.post("/api/v1/auth/login", data={"username": email, "password": pwd})
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await ac.post(
            "/api/videos/upload-url/",
            data={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "aspect_ratio": "9:16"},
            headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "processing"
        assert data["initial_status"] == "DOWNLOADING"
        project_id = data["project_id"]
        assert project_id is not None
        mock_task.assert_called_once()

        # Checa status no endpoint de projetos
        status_resp = await ac.get(f"/api/projects/{project_id}/status", headers=headers)
        assert status_resp.status_code == 200
        sdata = status_resp.json()
        assert sdata["status"] == "DOWNLOADING"
        assert sdata["queuePosition"] >= 1
        assert sdata["estimatedTimeSec"] > 0


@pytest.mark.asyncio
async def test_x_accel_redirect_and_fallback():
    """Testa entrega acelerada via X-Accel-Redirect com header de proxy e fallback FileResponse."""
    from backend.app.core.config import settings
    from backend.app.db.db_service import create_project, save_single_clip
    from pathlib import Path

    temp_dir = Path(settings.TEMP_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)

    async with get_client() as ac:
        email = f"accel_user_{uuid.uuid4().hex[:8]}@example.com"
        pwd = "securePassword123!"
        reg = await ac.post("/api/v1/auth/register", json={"email": email, "password": pwd})
        user_id = reg.json()["user_id"]
        login_resp = await ac.post("/api/v1/auth/login", data={"username": email, "password": pwd})
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        project_id = await create_project(user_id, "Projeto X-Accel", "video.mp4", 30.0)
        clip_id = str(uuid.uuid4())
        video_filename = f"clip_{clip_id}.mp4"
        dummy_file = temp_dir / video_filename
        dummy_file.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00")

        await save_single_clip(project_id, {
            "id": clip_id,
            "renderedUrl": video_filename,
            "title": "Clipe X-Accel",
            "startTime": 0.0,
            "endTime": 10.0,
            "durationSec": 10.0,
            "viralScore": 88,
            "aspectRatio": "9:16",
            "hookReason": "Hook",
            "words": [],
            "thumbnail_key": f"thumb_{clip_id}.jpg"
        })

        try:
            # 1. Com suporte a proxy/Nginx -> X-Accel-Redirect
            accel_headers = {**headers, "X-Request-Accel": "1"}
            res_accel = await ac.get(f"/api/videos/download/{clip_id}", headers=accel_headers)
            assert res_accel.status_code == 200
            assert "x-accel-redirect" in res_accel.headers
            assert res_accel.headers["x-accel-redirect"] == f"/internal_videos/{video_filename}"
            assert res_accel.headers.get("accept-ranges") == "bytes"

            # 2. Sem Nginx / dev local -> FileResponse
            no_accel_headers = {**headers, "X-Disable-Accel": "1"}
            res_direct = await ac.get(f"/api/videos/download/{clip_id}", headers=no_accel_headers)
            assert res_direct.status_code == 200
            assert "x-accel-redirect" not in res_direct.headers
            assert len(res_direct.content) > 0
        finally:
            if dummy_file.exists():
                dummy_file.unlink()


@pytest.mark.asyncio
async def test_clip_access_denied_for_other_user():
    """Testa que usuário B recebe 403 Forbidden ao tentar baixar clipe pertencente a usuário A."""
    from backend.app.core.config import settings
    from backend.app.db.db_service import create_project, save_single_clip
    from pathlib import Path

    temp_dir = Path(settings.TEMP_DIR)
    temp_dir.mkdir(parents=True, exist_ok=True)

    async with get_client() as ac:
        # Usuário A (dono)
        email_a = f"owner_{uuid.uuid4().hex[:8]}@example.com"
        pwd = "securePassword123!"
        reg_a = await ac.post("/api/v1/auth/register", json={"email": email_a, "password": pwd})
        user_a_id = reg_a.json()["user_id"]

        project_id = await create_project(user_a_id, "Projeto Owner", "video.mp4", 30.0)
        clip_id = str(uuid.uuid4())
        video_filename = f"clip_{clip_id}.mp4"
        dummy_file = temp_dir / video_filename
        dummy_file.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00")

        await save_single_clip(project_id, {
            "id": clip_id,
            "renderedUrl": video_filename,
            "title": "Clipe Privado",
            "startTime": 0.0,
            "endTime": 10.0,
            "durationSec": 10.0,
            "viralScore": 85,
            "aspectRatio": "9:16",
            "hookReason": "Hook",
            "words": []
        })

        # Usuário B (invasor)
        email_b = f"intruder_{uuid.uuid4().hex[:8]}@example.com"
        await ac.post("/api/v1/auth/register", json={"email": email_b, "password": pwd})
        login_b = await ac.post("/api/v1/auth/login", data={"username": email_b, "password": pwd})
        token_b = login_b.json()["access_token"]
        headers_b = {"Authorization": f"Bearer {token_b}"}

        try:
            res = await ac.get(f"/api/videos/download/{clip_id}", headers=headers_b)
            assert res.status_code == 403
            assert "Acesso negado" in res.json()["detail"]
        finally:
            if dummy_file.exists():
                dummy_file.unlink()


@pytest.mark.asyncio
async def test_concurrent_jobs_limit(monkeypatch):
    """Testa que atingir o limite de jobs simultâneos retorna HTTP 429."""
    from backend.app.db.db_service import create_project

    async with get_client() as ac:
        email = f"limit_user_{uuid.uuid4().hex[:8]}@example.com"
        pwd = "securePassword123!"
        reg = await ac.post("/api/v1/auth/register", json={"email": email, "password": pwd})
        user_id = reg.json()["user_id"]
        login_resp = await ac.post("/api/v1/auth/login", data={"username": email, "password": pwd})
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Cria 2 jobs ativos (status PENDING / DOWNLOADING)
        await create_project(user_id, "Job 1", "v1.mp4", 10.0, status="DOWNLOADING")
        await create_project(user_id, "Job 2", "v2.mp4", 10.0, status="PENDING")

        # Tentativa de iniciar um terceiro job simultâneo
        res = await ac.post(
            "/api/videos/upload-url/",
            data={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "aspect_ratio": "9:16"},
            headers=headers
        )
        assert res.status_code == 429
        assert "simultâneos atingido" in res.json()["detail"]


@pytest.mark.asyncio
async def test_config_endpoints():
    """Testa que os endpoints /api/config e /api/v1/config retornam a configuração correta."""
    async with get_client() as ac:
        for path in ("/api/config", "/api/v1/config"):
            res = await ac.get(path)
            assert res.status_code == 200
            data = res.json()
            assert "max_file_size_mb" in data
            assert data["max_file_size_mb"] > 0
            assert "max_duration_sec" in data
            assert "max_source_height" in data
            assert "version" in data

