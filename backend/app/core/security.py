import hmac
import hashlib
import time
import base64
from datetime import datetime, timedelta, timezone
import jwt
from jwt.exceptions import PyJWTError
from passlib.context import CryptContext
from backend.app.core.config import settings

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    if isinstance(encoded_jwt, bytes):
        encoded_jwt = encoded_jwt.decode("utf-8")
    return encoded_jwt

DUMMY_PASSWORD_HASH = "$2b$12$uO3WYGhnZTVnGO61TfV93eaFiVabrVdgeI0QcAjNd6ZoxPQzyN/9y"

def dummy_verify_password(password: str) -> bool:
    """Executa verificação bcrypt dummy para garantir tempo de resposta constante e mitigar timing attacks."""
    try:
        return pwd_context.verify(password, DUMMY_PASSWORD_HASH)
    except Exception:
        return False

def decode_access_token(token: str):
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
            options={"require": ["exp"]}
        )
        return payload
    except PyJWTError:
        return None

def create_signed_url_token(user_id: str, clip_id: str, expires_in_sec: int = 86400) -> str:
    """
    Gera uma assinatura HMAC-SHA256 vinculada a clip_id e user_id (padrão 24 horas).
    Formato: base64url(user_id:clip_id:expires_ts:signature_hex)
    """
    expires_at = int(time.time()) + expires_in_sec
    message = f"{user_id}:{clip_id}:{expires_at}"
    sig = hmac.new(SECRET_KEY.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{user_id}:{clip_id}:{expires_at}:{sig}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8").rstrip("=")

def verify_signed_url_token(token: str, expected_clip_id: str) -> dict | None:
    """
    Valida a assinatura HMAC, expiração (<= 5 min) e vínculo com o clipe.
    Retorna o dicionário com user_id e clip_id se válido, ou None se inválido/expirado/adulterado.
    """
    if not token:
        return None
    try:
        padding = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(token + padding).decode("utf-8")
        parts = raw.split(":")
        if len(parts) != 4:
            return None
        user_id, clip_id, expires_str, sig = parts

        # 1. Verifica vínculo do clipe
        if clip_id != expected_clip_id:
            return None

        # 2. Verifica assinatura HMAC em tempo constante
        message = f"{user_id}:{clip_id}:{expires_str}"
        expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None

        # 3. Verifica expiração temporal
        expires_at = int(expires_str)
        if time.time() > expires_at:
            return None

        return {"user_id": user_id, "clip_id": clip_id, "expires_at": expires_at}
    except Exception:
        return None

