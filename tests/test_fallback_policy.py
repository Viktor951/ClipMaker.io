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


