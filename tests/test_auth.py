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

    async with client as ac:
        # 1. Register
        response = await ac.post("/api/v1/auth/register", json={
            "email": "test@example.com",
            "password": "strongpassword123",
            "name": "Test User"
        })
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        
        # 2. Login
        response = await ac.post("/api/v1/auth/login", data={
            "username": "test@example.com",
            "password": "strongpassword123"
        })
        assert response.status_code == 200
        assert "access_token" in response.json()

