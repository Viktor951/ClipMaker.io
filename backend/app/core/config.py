from pydantic_settings import BaseSettings
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "ClipMaker.io"
    VERSION: str = "3.0"
    
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "password")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "clipmaker_db")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/clipmaker_db")
    
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    SECRET_KEY: str = os.getenv("SECRET_KEY", "chave_secreta_padrao_apenas_para_desenvolvimento")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))
    
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    ALLOWED_ORIGINS: str = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://localhost")

    # Diretório compartilhado entre API e worker (uploads, clipes renderizados)
    TEMP_DIR: str = os.getenv("TEMP_DIR", str(_BACKEND_DIR / "temp_videos"))
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "2000"))
    MAX_DURATION_SEC: int = int(os.getenv("MAX_DURATION_SEC", "14400"))
    
    model_config = {
        "env_file": ".env",
        "extra": "ignore"
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.ENVIRONMENT == "production" and self.SECRET_KEY == "chave_secreta_padrao_apenas_para_desenvolvimento":
            raise RuntimeError("CRITICAL SECURITY ERROR: SECRET_KEY is using the default value in production!")
        if self.ENVIRONMENT == "production" and len(self.SECRET_KEY) < 32:
            raise RuntimeError("CRITICAL SECURITY ERROR: SECRET_KEY must have at least 32 characters in production!")

settings = Settings()
