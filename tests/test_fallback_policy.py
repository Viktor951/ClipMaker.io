import os
import pytest
from unittest.mock import patch

@pytest.mark.asyncio
async def test_sqlite_fallback_denied_without_flag():
    from backend.app.db.db_service import get_backend, _backends
    import asyncio

    # Força remoção do backend atual do loop para testar nova inicialização
    loop = asyncio.get_running_loop()
    old_backend = _backends.pop(loop, None)

    try:
        with patch.dict(os.environ, {"ALLOW_SQLITE_FALLBACK": "false", "ENVIRONMENT": "production"}):
            with pytest.raises(RuntimeError) as exc_info:
                await get_backend()
            assert "indisponível" in str(exc_info.value).lower() or "não configurada" in str(exc_info.value).lower()
    finally:
        if old_backend:
            _backends[loop] = old_backend
