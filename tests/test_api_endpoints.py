import uuid
import pytest
from httpx import AsyncClient
from backend.app.main import app

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
