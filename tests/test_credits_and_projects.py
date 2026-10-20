import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from backend.app.main import app
from backend.app.db.db_service import get_user_by_id, deduct_user_credits, add_user_credits, create_project


def get_client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_get_me_endpoint():
    async with get_client() as ac:
        email = f"me_test_{uuid.uuid4().hex[:8]}@example.com"
        pwd = "securePassword123!"
        reg = await ac.post("/api/v1/auth/register", json={"email": email, "password": pwd, "name": "João"})
        assert reg.status_code == 200
        user_id = reg.json()["user_id"]

        login = await ac.post("/api/v1/auth/login", data={"username": email, "password": pwd})
        assert login.status_code == 200
        token = login.json()["access_token"]

        # Chama /api/auth/me
        resp = await ac.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        user = data["user"]
        assert user["id"] == user_id
        assert user["email"] == email
        assert user["name"] == "João"
        assert user["credits"] == 60


@pytest.mark.asyncio
async def test_deduct_and_add_credits():
    async with get_client() as ac:
        email = f"credits_{uuid.uuid4().hex[:8]}@example.com"
        pwd = "securePassword123!"
        reg = await ac.post("/api/v1/auth/register", json={"email": email, "password": pwd})
        user_id = reg.json()["user_id"]

        user = await get_user_by_id(user_id)
        assert user["credits"] == 60

        # Deduz 10 créditos
        ok = await deduct_user_credits(user_id, amount=10)
        assert ok is True
        user = await get_user_by_id(user_id)
        assert user["credits"] == 50

        # Tenta deduzir mais do que o saldo
        fail = await deduct_user_credits(user_id, amount=100)
        assert fail is False
        user = await get_user_by_id(user_id)
        assert user["credits"] == 50

        # Adiciona 25 créditos
        ok_add = await add_user_credits(user_id, amount=25)
        assert ok_add is True
        user = await get_user_by_id(user_id)
        assert user["credits"] == 75


@pytest.mark.asyncio
async def test_insufficient_credits_blocks_processing(monkeypatch):
    import socket
    from unittest.mock import MagicMock
    mock_task = MagicMock()
    monkeypatch.setattr("backend.app.api.routers.video.download_and_process_url_task", mock_task)

    def mock_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('142.250.190.46', 80))]

    monkeypatch.setattr("socket.getaddrinfo", mock_getaddrinfo)

    async with get_client() as ac:
        email = f"zero_cred_{uuid.uuid4().hex[:8]}@example.com"
        pwd = "securePassword123!"
        reg = await ac.post("/api/v1/auth/register", json={"email": email, "password": pwd})
        user_id = reg.json()["user_id"]

        login = await ac.post("/api/v1/auth/login", data={"username": email, "password": pwd})
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Zera os créditos do usuário
        await deduct_user_credits(user_id, amount=60)
        user = await get_user_by_id(user_id)
        assert user["credits"] == 0

        # Tentativa de processar URL deve retornar 402 Payment Required
        resp = await ac.post(
            "/api/videos/upload-url/",
            data={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "aspect_ratio": "9:16"},
            headers=headers
        )
        assert resp.status_code == 402
        assert "Saldo de créditos insuficiente" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_delete_project_endpoint():
    async with get_client() as ac:
        email_owner = f"owner_{uuid.uuid4().hex[:8]}@example.com"
        email_other = f"other_{uuid.uuid4().hex[:8]}@example.com"
        pwd = "securePassword123!"

        reg_owner = await ac.post("/api/v1/auth/register", json={"email": email_owner, "password": pwd})
        owner_id = reg_owner.json()["user_id"]
        login_owner = await ac.post("/api/v1/auth/login", data={"username": email_owner, "password": pwd})
        token_owner = login_owner.json()["access_token"]
        headers_owner = {"Authorization": f"Bearer {token_owner}"}

        reg_other = await ac.post("/api/v1/auth/register", json={"email": email_other, "password": pwd})
        login_other = await ac.post("/api/v1/auth/login", data={"username": email_other, "password": pwd})
        token_other = login_other.json()["access_token"]
        headers_other = {"Authorization": f"Bearer {token_other}"}

        # Cria projeto para o dono
        project_id = await create_project(owner_id, "Projeto Deletável", "key.mp4", 45.0)

        # Outro usuário tenta deletar -> deve retornar 404 (não autorizado/não encontrado)
        del_other = await ac.delete(f"/api/projects/{project_id}", headers=headers_other)
        assert del_other.status_code == 404

        # Dono lista projetos -> encontra o projeto
        list_resp = await ac.get("/api/projects", headers=headers_owner)
        assert list_resp.status_code == 200
        assert any(p["id"] == project_id for p in list_resp.json()["projects"])

        # Dono deleta o próprio projeto -> sucesso 200
        del_owner = await ac.delete(f"/api/projects/{project_id}", headers=headers_owner)
        assert del_owner.status_code == 200
        assert del_owner.json()["status"] == "success"

        # Dono lista novamente -> projeto removido
        list_resp2 = await ac.get("/api/projects", headers=headers_owner)
        assert not any(p["id"] == project_id for p in list_resp2.json()["projects"])
