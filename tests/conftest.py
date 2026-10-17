import os
import pytest

# Para a suíte de testes local, permite explicitamente o fallback SQLite
os.environ["ALLOW_SQLITE_FALLBACK"] = "true"
os.environ["ENVIRONMENT"] = "test"
os.environ["SECRET_KEY"] = "test_secret_key_1234567890_test_suite_key"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
