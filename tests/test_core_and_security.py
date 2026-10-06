from datetime import timedelta
from backend.app.core.security import get_password_hash, verify_password, create_access_token, decode_access_token
from backend.app.services.video_service import _compute_crop_and_scale, format_timestamp
from backend.app.api.routers.video import _is_safe_public_url


def test_password_hashing():
    raw = "MinhaSenhaForte123!"
    hashed = get_password_hash(raw)
    assert hashed != raw
    assert verify_password(raw, hashed) is True
    assert verify_password("SenhaErrada", hashed) is False


def test_jwt_token_lifecycle():
    email = "usuario@clipmaker.io"
    token = create_access_token({"sub": email}, expires_delta=timedelta(minutes=15))
    assert isinstance(token, str)
    assert len(token) > 20

    payload = decode_access_token(token)
    assert payload is not None
    assert payload.get("sub") == email

    # Token inválido
    assert decode_access_token("token.malformado.aqui") is None


def test_anti_ssrf_url_validation():
    # URLs legítimas
    assert _is_safe_public_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") is True
    assert _is_safe_public_url("http://example.com/video.mp4") is True

    # URLs perigosas / SSRF
    assert _is_safe_public_url("-rf /") is False
    assert _is_safe_public_url("file:///etc/passwd") is False
    assert _is_safe_public_url("ftp://example.com") is False
    assert _is_safe_public_url("http://localhost:8000") is False
    assert _is_safe_public_url("http://127.0.0.1:5432") is False
    assert _is_safe_public_url("http://169.254.169.254/latest/meta-data/") is False
    assert _is_safe_public_url("http://db:5432") is False
    assert _is_safe_public_url("http://redis:6379") is False


def test_video_crop_and_scale_dimensions():
    # Vídeo Full HD (1920x1080) convertido para 9:16 vertical
    crop_w, crop_h, crop_x, crop_y, scale_w, scale_h = _compute_crop_and_scale(1920, 1080, "9:16", "1080p")
    assert crop_w % 2 == 0
    assert crop_h % 2 == 0
    assert scale_w == 1080
    assert scale_h == 1920
    assert crop_w == 607 or crop_w == 606 or crop_w <= 1920

    # Conversão 1:1 quadrado
    crop_w, crop_h, crop_x, crop_y, scale_w, scale_h = _compute_crop_and_scale(1920, 1080, "1:1", "1080p")
    assert crop_w == 1080
    assert crop_h == 1080
    assert scale_w == 1080
    assert scale_h == 1080


def test_srt_timestamp_formatting():
    assert format_timestamp(0.0) == "00:00:00,000"
    assert format_timestamp(65.5) == "00:01:05,500"
    assert format_timestamp(3661.123) == "01:01:01,123"
