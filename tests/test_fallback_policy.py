import os
import pytest
from unittest.mock import patch

@pytest.mark.asyncio
async def test_sqlite_fallback_denied_without_flag(monkeypatch):
    from backend.app.core.config import settings
    from backend.app.db.db_service import get_backend, _backends
    import asyncio

    # Força remoção do backend atual do loop para testar nova inicialização
    loop = asyncio.get_running_loop()
    old_backend = _backends.pop(loop, None)

    try:
        monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://invalid_host_12345:5432/clipmaker")
        monkeypatch.setenv("ALLOW_SQLITE_FALLBACK", "false")
        monkeypatch.setenv("ENVIRONMENT", "production")
        with pytest.raises(RuntimeError) as exc_info:
            await get_backend()
        assert "indisponível" in str(exc_info.value).lower() or "não configurada" in str(exc_info.value).lower()
    finally:
        if old_backend:
            _backends[loop] = old_backend


def test_rate_limiter_storage_fallback_policy(monkeypatch):
    """Testa que _get_limiter_storage_uri falha em produção sem Redis e usa memory:// fora de produção."""
    from backend.app.api.deps import _get_limiter_storage_uri

    # 1. Em produção, se o Redis falhar, deve levantar RuntimeError com mensagem clara
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("REDIS_URL", "redis://invalid_host_redis_12345:6379/0")
    with pytest.raises(RuntimeError) as exc_info:
        _get_limiter_storage_uri()
    assert "redis indisponível para rate limiting em produção" in str(exc_info.value).lower()

    # 2. Fora de produção (development), deve permitir fallback para memory://
    monkeypatch.setenv("ENVIRONMENT", "development")
    uri = _get_limiter_storage_uri()
    assert uri == "memory://"



