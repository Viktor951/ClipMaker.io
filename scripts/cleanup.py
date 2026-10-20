import os
import time
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMP_DIR = os.getenv("TEMP_DIR", os.path.join(BASE_DIR, "backend", "temp_videos"))
MAX_AGE_HOURS = int(os.getenv("CLEANUP_MAX_AGE_HOURS", "24"))

def cleanup_old_files():
    print("[CLEANUP] Iniciando rotina de limpeza de arquivos antigos...")
    now = time.time()
    
    # Limpa arquivos físicos do diretório
    if os.path.exists(TEMP_DIR):
        for filename in os.listdir(TEMP_DIR):
            filepath = os.path.join(TEMP_DIR, filename)
            if os.path.isfile(filepath):
                file_age = now - os.path.getmtime(filepath)
                if file_age > (MAX_AGE_HOURS * 3600):
                    try:
                        os.remove(filepath)
                        print(f"[CLEANUP] Arquivo removido: {filename}")
                    except Exception as e:
                        print(f"[CLEANUP] Erro ao remover {filename}: {e}")


def check_stale_projects_watchdog():
    """Varredura complementar de projetos travados caso cleanup tenha acesso ao banco."""
    try:
        from backend.app.core.loop import run_sync
        from backend.app.db.db_service import fail_stale_projects
        stale_min = int(os.getenv("PROJECT_STALE_MINUTES", "60"))
        count = run_sync(fail_stale_projects(stale_minutes=stale_min))
        if count > 0:
            print(f"[CLEANUP/WATCHDOG] {count} projeto(s) travado(s) marcado(s) como FAILED.")
    except Exception as e:
        print(f"[CLEANUP/WATCHDOG] Verificação ignorada ou indisponível: {e}")


def cleanup_database_retention():
    """Rotina de retenção LGPD: apaga projetos e transcrições com mais de 30 dias."""
    try:
        from backend.app.core.loop import run_sync
        from backend.app.db.db_service import cleanup_old_db_records
        max_days = int(os.getenv("RETENTION_MAX_DAYS", "30"))
        res = run_sync(cleanup_old_db_records(max_age_days=max_days))
        print(f"[CLEANUP/LGPD] Retenção concluída: {res.get('deleted_projects', 0)} projetos e {res.get('deleted_transcriptions', 0)} transcrições removidos.")
    except Exception as e:
        print(f"[CLEANUP/LGPD] Limpeza de banco ignorada ou indisponível: {e}")


if __name__ == "__main__":
    cleanup_old_files()
    check_stale_projects_watchdog()
    cleanup_database_retention()
