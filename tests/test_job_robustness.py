import uuid
import pytest
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.db.db_service import (
    get_backend,
    create_user_safe,
    create_project,
    get_project_with_clips,
    count_active_projects_by_user,
    fail_stale_projects,
)
from backend.app.worker.worker import (
    categorize_error,
    _is_network_transient_error,
    watchdog_stale_projects_task,
)
from backend.app.services.ai_service import (
    _get_clip_target_and_durations,
    _fallback_clip_boundaries,
)
from backend.app.core.security import create_access_token


def get_client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_watchdog_stale_projects():
    """Item 1: Projeto com updatedAt estagnado passa a FAILED com mensagem amigável."""
    user = await create_user_safe(f"stale_{uuid.uuid4().hex[:8]}@test.com", "hash123")
    user_id = str(user["id"])

    project_id = await create_project(
        user_id=user_id,
        title="Projeto Travado Teste",
        source_file_key="stale.mp4",
        duration_sec=30.0,
        status="TRANSCRIBING"
    )

    db = await get_backend()
    # Retrocede updatedAt para 90 minutos no passado
    past_time = (datetime.now(timezone.utc) - timedelta(minutes=90)).strftime("%Y-%m-%d %H:%M:%S")
    await db.execute("UPDATE projects SET updatedAt = $1 WHERE id = $2", past_time, project_id)

    # Executa o watchdog com limite de 60 minutos
    affected = await fail_stale_projects(stale_minutes=60)
    assert affected >= 1

    # Verifica status e mensagem amigável no banco
    updated = await get_project_with_clips(project_id)
    assert updated["status"] == "FAILED"
    assert updated["errormessage"] == "O processamento excedeu o tempo limite. Tente novamente."


@pytest.mark.asyncio
async def test_draft_projects_do_not_block_concurrency():
    """Item 2: Projetos DRAFT não entram na contagem de ativos e não bloqueiam uploads."""
    email = f"draft_{uuid.uuid4().hex[:8]}@test.com"
    user = await create_user_safe(email, "hash123")
    user_id = str(user["id"])
    token = create_access_token(data={"sub": email})
    headers = {"Authorization": f"Bearer {token}"}

    async with get_client() as ac:
        # Cria 2 projetos via POST /api/projects
        for i in range(2):
            res_draft = await ac.post(
                "/api/projects",
                json={"title": f"Rascunho {i+1}", "duration_sec": 0.0},
                headers=headers
            )
            assert res_draft.status_code == 200
            data = res_draft.json()
            assert data["status_name"] == "DRAFT"

        # Concorrência ativa deve ser 0
        active_count = await count_active_projects_by_user(user_id)
        assert active_count == 0

        # Usuário com 2 projetos DRAFT ainda consegue enviar vídeo com sucesso
        fake_video_bytes = b"\x00" * 1024
        files = {"file": ("test_upload.mp4", fake_video_bytes, "video/mp4")}
        data = {"aspect_ratio": "9:16"}
        res_upload = await ac.post("/api/videos/upload-and-process", files=files, data=data, headers=headers)
        
        # Não pode receber 429 (limite de concorrência)
        assert res_upload.status_code != 429
        assert res_upload.status_code in (200, 400)


@pytest.mark.asyncio
async def test_status_endpoint_returns_clean_error():
    """Item 4: Endpoint /projects/{id}/status não contém Traceback, caminhos nem stderr."""
    email = f"status_{uuid.uuid4().hex[:8]}@test.com"
    user = await create_user_safe(email, "hash123")
    user_id = str(user["id"])
    token = create_access_token(data={"sub": email})
    headers = {"Authorization": f"Bearer {token}"}

    # Simula erro capturado e sanitizado
    err = Exception("Command 'ffmpeg -i /app/temp_videos/source.mp4' Traceback (most recent call last)")
    clean_msg = categorize_error(err)

    project_id = await create_project(
        user_id=user_id,
        title="Projeto com Erro",
        source_file_key="err.mp4",
        duration_sec=10.0,
        status="FAILED"
    )
    db = await get_backend()
    await db.execute("UPDATE projects SET errorMessage = $1 WHERE id = $2", clean_msg, project_id)

    async with get_client() as ac:
        res = await ac.get(f"/api/projects/{project_id}/status", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "FAILED"
        assert "Traceback" not in (data.get("error") or "")
        assert "/app/" not in (data.get("error") or "")
        assert "ffmpeg" not in (data.get("error") or "")


def test_categorize_error_and_no_leakage():
    """Item 4: Testa que mensagens de erro são sanitizadas e não contêm paths ou tracebacks."""
    raw_ffmpeg_err = Exception("Command '['ffmpeg', '-i', '/app/backend/temp_videos/abc.mp4']' returned non-zero exit status 1: Error in /usr/lib/x86_64-linux-gnu/libavcodec.so")
    msg1 = categorize_error(raw_ffmpeg_err)
    assert msg1 == "Falha na renderização do clipe."
    assert "/app/" not in msg1
    assert "ffmpeg" not in msg1

    raw_ytdlp_err = Exception("Falha no download via yt-dlp: ERROR: [youtube] 12345: Video unavailable (yt_dlp/extractor/youtube.py:345)")
    msg2 = categorize_error(raw_ytdlp_err)
    assert msg2 == "Falha ao baixar o vídeo. Verifique se o link é válido e público."
    assert "yt_dlp" not in msg2
    assert "ERROR:" not in msg2

    raw_timeout = TimeoutError("Job exceeded maximum allowed duration of 90 minutes")
    msg3 = categorize_error(raw_timeout)
    assert msg3 == "O processamento excedeu o tempo limite. Tente novamente."


def test_yt_dlp_retry_discrimination():
    """Item 3: Apenas falhas transitórias de rede disparam retry no yt-dlp."""
    assert _is_network_transient_error("Connection reset by peer (errno 104)") is True
    assert _is_network_transient_error("Temporary failure in name resolution") is True
    assert _is_network_transient_error("Read timed out after 30 seconds") is True

    # Não deve retentar vídeos indisponíveis, privados ou removidos
    assert _is_network_transient_error("ERROR: Video unavailable") is False
    assert _is_network_transient_error("Private video. Sign in if you've been granted access") is False
    assert _is_network_transient_error("HTTP Error 404: Not Found") is False


def test_short_video_clip_generation_boundaries():
    """Item 5: Vídeos curtos recebem alvos e limites de corte coerentes."""
    # Vídeo de 20 segundos
    target_count, min_dur, max_dur = _get_clip_target_and_durations(20.0)
    assert target_count == 1
    assert max_dur == 20.0
    assert min_dur <= 10.0

    fallback_clips = _fallback_clip_boundaries(20.0)
    assert len(fallback_clips) == 1
    assert fallback_clips[0]["start"] == 0.0
    assert fallback_clips[0]["end"] == 20.0

    # Vídeo de 180 segundos (longo)
    target_count_long, min_dur_long, max_dur_long = _get_clip_target_and_durations(180.0)
    assert target_count_long == 5
    assert min_dur_long == 60.0
    assert max_dur_long == 90.0
