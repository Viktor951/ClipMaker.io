from typing import Optional
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm

from backend.app.api.deps import limiter, get_current_user
from backend.app.models.user import UserCreate
from backend.app.core.config import settings
from backend.app.core.security import verify_password, get_password_hash, create_access_token, dummy_verify_password
from backend.app.db.db_service import get_user_by_email, create_user_safe, delete_user_account

router = APIRouter(tags=["auth"])


def _normalize_email(email: str) -> str:
    # Sem normalizar, "A@x.com" e "a@x.com" virariam contas diferentes.
    return email.strip().lower()


async def _verify_turnstile(token: Optional[str], client_ip: Optional[str] = None) -> bool:
    """Valida token do Cloudflare Turnstile anti-bot. Em desenvolvimento/testes ou sem chave configurada, permite bypass."""
    if not settings.TURNSTILE_SECRET_KEY or settings.ENVIRONMENT in ("development", "test"):
        return True
    if not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={
                    "secret": settings.TURNSTILE_SECRET_KEY,
                    "response": token,
                    "remoteip": client_ip or ""
                }
            )
            data = res.json()
            return bool(data.get("success", False))
    except Exception:
        return False


@router.post("/register")
@limiter.limit("5/minute")
async def register(request: Request, user: UserCreate):
    client_ip = request.client.host if request.client else None
    if not await _verify_turnstile(user.turnstile_token, client_ip):
        raise HTTPException(status_code=400, detail="Validação anti-bot inválida ou expirada")

    email = _normalize_email(user.email)
    if await get_user_by_email(email):
        raise HTTPException(status_code=400, detail="Email já cadastrado")
    hashed = get_password_hash(user.password)
    new_user = await create_user_safe(email, hashed, user.name)
    return {"status": "success", "user_id": str(new_user["id"])}


@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    user = await get_user_by_email(_normalize_email(form_data.username))
    if not user:
        # Executa hash dummy para manter tempo de resposta constante e mitigar timing attacks (S1.3)
        dummy_verify_password(form_data.password)
        raise HTTPException(status_code=400, detail="Email ou senha incorretos")

    if not verify_password(form_data.password, user["passwordhash"]):
        raise HTTPException(status_code=400, detail="Email ou senha incorretos")

    access_token = create_access_token(data={"sub": user["email"]})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
@router.get("/me/")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Retorna os dados do perfil e saldo de créditos do usuário autenticado."""
    from backend.app.db.db_service import get_user_by_id
    user_id = str(current_user.get("id"))
    fresh_user = await get_user_by_id(user_id) or current_user
    return {
        "status": "success",
        "user": {
            "id": user_id,
            "email": fresh_user.get("email"),
            "name": fresh_user.get("name") or "",
            "credits": int(fresh_user.get("credits", 60) if fresh_user.get("credits") is not None else 60),
            "createdAt": str(fresh_user.get("createdat") or fresh_user.get("createdAt") or "")
        }
    }


@router.delete("/me")
@router.delete("/me/")
async def delete_me(current_user: dict = Depends(get_current_user)):
    """Exclui a conta do usuário autenticado e todos os seus projetos/clipes (LGPD - Direito ao Esquecimento)."""
    user_id = str(current_user.get("id"))
    success = await delete_user_account(user_id)
    if not success:
        raise HTTPException(status_code=400, detail="Não foi possível excluir a conta.")
    return {"status": "success", "message": "Conta e dados excluídos com sucesso"}


