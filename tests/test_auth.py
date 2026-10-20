import uuid
import pytest
from httpx import AsyncClient
from backend.app.main import app

@pytest.mark.asyncio
async def test_register_and_login():
    try:
        from httpx import ASGITransport
        transport = ASGITransport(app=app)
        client = AsyncClient(transport=transport, base_url="http://test")
    except (ImportError, TypeError):
        client = AsyncClient(app=app, base_url="http://test")

    unique_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    password = "strongpassword123"

    async with client as ac:
        # 1. Register
        response = await ac.post("/api/v1/auth/register", json={
            "email": unique_email,
            "password": password,
            "name": "Test User"
        })
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert "user_id" in response.json()
        
        # 2. Login
        response = await ac.post("/api/v1/auth/login", data={
            "username": unique_email,
            "password": password
        })
        assert response.status_code == 200
        assert "access_token" in response.json()
        assert response.json()["token_type"] == "bearer"

        # 3. Duplicate registration should return 400
        dup_response = await ac.post("/api/v1/auth/register", json={
            "email": unique_email,
            "password": password,
            "name": "Duplicate User"
        })
        assert dup_response.status_code == 400

        # 4. Invalid credentials should return 400
        bad_response = await ac.post("/api/v1/auth/login", data={
            "username": unique_email,
            "password": "wrongpassword123"
        })
        assert bad_response.status_code == 400

        # 5. Delete account (LGPD - Direito ao Esquecimento)
        auth_headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        del_response = await ac.delete("/api/v1/auth/me", headers=auth_headers)
        assert del_response.status_code == 200
        assert del_response.json()["status"] == "success"

        # 6. Re-registering with the same email succeeds because previous account was deleted
        re_reg_response = await ac.post("/api/v1/auth/register", json={
            "email": unique_email,
            "password": password,
            "name": "Recreated User"
        })
        assert re_reg_response.status_code == 200

