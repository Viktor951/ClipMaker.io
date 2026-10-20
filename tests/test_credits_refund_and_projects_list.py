import uuid
import pytest
from httpx import AsyncClient

from backend.app.main import app
from backend.app.db.db_service import (
    create_project,
    save_single_clip,
    deduct_user_credits,
    refund_project_credits,
    get_user_by_id,
    update_project_status
)

def get_client():
    try:
        from httpx import ASGITransport
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")
    except (ImportError, TypeError):
        return AsyncClient(app=app, base_url="http://test")

@pytest.mark.asyncio
async def test_idempotent_credit_refund_on_project_failure():
    """
    Testa que quando um job falha, o crédito é estornado uma única vez,
    e invocações repetidas de refund_project_credits (ex.: watchdog ou retry) não duplicam o crédito.
    """
    async with get_client() as ac:
        email = f"refund_user_{uuid.uuid4().hex[:8]}@example.com"
        pwd = "securePassword123!"
        reg = await ac.post("/api/v1/auth/register", json={"email": email, "password": pwd})
        user_id = reg.json()["user_id"]

        user_before = await get_user_by_id(user_id)
        initial_credits = user_before["credits"]

        # 1. Débito de 1 crédito na criação do job
        project_id = await create_project(user_id, "Job de Teste Estorno", "video.mp4", 60.0, status="DOWNLOADING")
        debited = await deduct_user_credits(user_id, amount=1)
        assert debited is True

        user_after_debit = await get_user_by_id(user_id)
        assert user_after_debit["credits"] == initial_credits - 1

        # 2. Falha do job e primeiro estorno automático
        await update_project_status(project_id, "FAILED", "Falha proposital de teste")
        first_refund = await refund_project_credits(project_id)
        assert first_refund is True

        user_after_refund = await get_user_by_id(user_id)
        assert user_after_refund["credits"] == initial_credits

        # 3. Segunda tentativa de estorno (idempotência: não deve estornar novamente)
        second_refund = await refund_project_credits(project_id)
        assert second_refund is False

        user_after_second = await get_user_by_id(user_id)
        assert user_after_second["credits"] == initial_credits

@pytest.mark.asyncio
async def test_get_projects_camelcase_and_aggregated_metadata():
    """
    Testa que a rota GET /projects retorna nomes em camelCase, contagem de clipes e
    primeira miniatura calculados em uma única consulta, com suporte à paginação.
    """
    async with get_client() as ac:
        email = f"projects_user_{uuid.uuid4().hex[:8]}@example.com"
        pwd = "securePassword123!"
        reg = await ac.post("/api/v1/auth/register", json={"email": email, "password": pwd})
        user_id = reg.json()["user_id"]
        login = await ac.post("/api/v1/auth/login", data={"username": email, "password": pwd})
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Cria 2 projetos com clipes
        p1 = await create_project(user_id, "Projeto Alfa", "alfa.mp4", 90.0, status="READY")
        clip1_id = str(uuid.uuid4())
        await save_single_clip(p1, {
            "id": clip1_id,
            "renderedUrl": f"clip_{clip1_id}.mp4",
            "title": "Corte 1 Alfa",
            "startTime": 0.0,
            "endTime": 15.0,
            "durationSec": 15.0,
            "viralScore": 92,
            "thumbnail_key": "thumb_alfa_1.jpg",
            "words": []
        })

        p2 = await create_project(user_id, "Projeto Beta", "beta.mp4", 120.0, status="FAILED")
        await update_project_status(p2, "FAILED", "Vídeo excede duração permitida.")

        res = await ac.get("/api/projects?limit=10", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        projects = data["projects"]
        assert len(projects) == 2

        # Valida que todos os projetos possuem campos estritamente em camelCase
        for p in projects:
            assert "id" in p
            assert "title" in p
            assert "status" in p
            assert "durationSec" in p
            assert "clipCount" in p
            assert "firstThumbnailKey" in p
            assert "errorMessage" in p
            assert "createdAt" in p
            assert "updatedAt" in p
            # Não deve vazar campos internos ou sensíveis
            assert "userId" not in p
            assert "userid" not in p
            assert "sourceFileKey" not in p
            assert "sourcefilekey" not in p

        # Alfa deve ter clipCount = 1 e firstThumbnailKey
        alfa = next(p for p in projects if p["id"] == p1)
        assert alfa["clipCount"] == 1
        assert alfa["firstThumbnailKey"] == "thumb_alfa_1.jpg"
        assert alfa["durationSec"] == 90.0
        assert alfa["status"] == "READY"

        # Beta deve ter clipCount = 0 e errorMessage preenchida
        beta = next(p for p in projects if p["id"] == p2)
        assert beta["clipCount"] == 0
        assert beta["status"] == "FAILED"
        assert "duração permitida" in beta["errorMessage"]
