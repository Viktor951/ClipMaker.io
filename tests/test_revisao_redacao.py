import uuid
import pytest
from scripts.revisao.gerar_pacote import SecretRedactor, SecurityLeakException


def test_redact_jwt_and_bearer():
    redactor = SecretRedactor()
    # Gera tokens sintéticos puramente em tempo de execução
    dummy_jwt = f"eyJ{uuid.uuid4().hex[:15]}.eyJ{uuid.uuid4().hex[:20]}.{uuid.uuid4().hex[:25]}"
    dummy_bearer = f"Bearer {uuid.uuid4().hex}{uuid.uuid4().hex}"

    raw_text = f"Auth Header: {dummy_bearer}\nToken: {dummy_jwt}"
    redacted, stats = redactor.redact_text(raw_text)

    assert dummy_jwt not in redacted
    assert dummy_bearer not in redacted
    assert "<REDACTED_JWT_TOKEN>" in redacted
    assert "<REDACTED_BEARER_TOKEN>" in redacted
    assert stats["jwt"] >= 1
    assert stats["bearer_token"] >= 1

    # Confirma que o fail-safe aprova o texto redigido
    assert len(redactor.scan_for_unredacted_secrets(redacted)) == 0


def test_redact_api_keys_and_connection_urls():
    redactor = SecretRedactor()
    dummy_aiza = "AI" + "za" + uuid.uuid4().hex + "a"
    dummy_sk = "sk-" + uuid.uuid4().hex + uuid.uuid4().hex
    dummy_aq = "AQ." + uuid.uuid4().hex + uuid.uuid4().hex
    dummy_pwd = uuid.uuid4().hex
    user_tag = uuid.uuid4().hex[:4]

    redis_url = f"redis://:{dummy_pwd}@redis-host:6379/0"
    pg_url = f"postgresql://appuser_{user_tag}:{dummy_pwd}@postgres-host:5432/clipdb"

    text = f"""
    GOOGLE_KEY={dummy_aiza}
    OPENAI_KEY={dummy_sk}
    GEMINI_KEY={dummy_aq}
    REDIS_URL={redis_url}
    DATABASE_URL={pg_url}
    """

    redacted, stats = redactor.redact_text(text)

    assert dummy_aiza not in redacted
    assert dummy_sk not in redacted
    assert dummy_aq not in redacted
    assert dummy_pwd not in redacted
    assert "<REDACTED_API_KEY>" in redacted
    assert "redis://:<REDACTED_PASSWORD>@" in redacted
    assert ":<REDACTED_PASSWORD>@" in redacted
    assert stats["api_key"] >= 3
    assert stats["url_password"] >= 2

    # Fail-safe passa limpo
    violations = redactor.scan_for_unredacted_secrets(redacted)
    assert len(violations) == 0


def test_redact_config_secrets_and_paths():
    redactor = SecretRedactor()
    secret_val = uuid.uuid4().hex + uuid.uuid4().hex
    raw_text = f'''
    SECRET_KEY = "{secret_val}"
    POSTGRES_PASSWORD: '{secret_val}'
    Arquivo em C:\\Users\\TestDevUser\\Projects\\ClipMakerAI\\main.py
    '''

    redacted, stats = redactor.redact_text(raw_text)

    assert secret_val not in redacted
    assert "<REDACTED_SECRET>" in redacted
    assert "TestDevUser" not in redacted
    assert "C:\\Users\\<usuario>\\" in redacted
    assert stats["config_secret"] >= 2
    assert stats["local_path"] >= 1

    violations = redactor.scan_for_unredacted_secrets(redacted)
    assert len(violations) == 0


def test_redact_real_emails_preserves_example():
    redactor = SecretRedactor()
    real_email = f"user_{uuid.uuid4().hex[:6]}@corporativo.com.br"
    safe_email = "tester@example.com"

    text = f"Contato real: {real_email} e contato de teste: {safe_email}"
    redacted, stats = redactor.redact_text(text)

    assert real_email not in redacted
    assert "<usuario>@example.com" in redacted
    assert safe_email in redacted
    assert stats["email"] == 1


def test_fail_safe_detects_leaks():
    """Valida que o detector fail-safe identifica segredos não mascarados."""
    redactor = SecretRedactor()
    leaked_jwt = f"eyJ{uuid.uuid4().hex[:15]}.eyJ{uuid.uuid4().hex[:20]}.{uuid.uuid4().hex[:25]}"
    leaked_aiza = "AI" + "za" + uuid.uuid4().hex + "1"
    leaked_redis = f"redis://:{uuid.uuid4().hex}@host:6379/0"

    # Não passa pelo redact_text de propósito
    leaked_text = f"Log acidental: {leaked_jwt} e chave {leaked_aiza} e {leaked_redis}"
    violations = redactor.scan_for_unredacted_secrets(leaked_text)

    assert len(violations) >= 3
    # Confirma que nenhuma violação imprime o valor do segredo
    for v in violations:
        assert leaked_jwt not in v
        assert leaked_aiza not in v
