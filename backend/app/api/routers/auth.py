from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm

from backend.app.api.deps import limiter, get_current_user
from backend.app.models.user import UserCreate
from backend.app.core.security import verify_password, get_password_hash, create_access_token
from backend.app.db.db_service import get_user_by_email, create_user_safe

router = APIRouter(tags=["auth"])


def _normalize_email(email: str) -> str:
    # Sem normalizar, "A@x.com" e "a@x.com" virariam contas diferentes.
    return email.strip().lower()


@router.post("/register")
@limiter.limit("5/minute")
async def register(request: Request, user: UserCreate):
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
    if not user or not verify_password(form_data.password, user["passwordhash"]):
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

