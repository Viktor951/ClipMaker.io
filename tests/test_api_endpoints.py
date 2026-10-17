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

        # 4. Checar status do projeto
        status_resp = await ac.get(f"/api/projects/{project_id}/status", headers=headers)
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "PENDING"


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
