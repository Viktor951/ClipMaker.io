import os
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_AGE_HOURS = int(os.getenv("CLEANUP_MAX_AGE_HOURS", "24"))

# Diretórios temporários candidatos (inclui disco D: em produção e fallback local)
CANDIDATE_TEMP_DIRS = [
    os.getenv("TEMP_DIR"),
    os.getenv("CLIPMAKER_TEMP_VIDEOS"),
    os.path.join(BASE_DIR, "backend", "temp_videos"),
    os.path.join(os.getenv("DATA_ROOT", "D:/docker-data/clipmaker"), "temp_videos"),
    "D:/docker-data/clipmaker/temp_videos",
    "D:\\docker-data\\clipmaker\\temp_videos"
]


def cleanup_old_files():
    """Limpa arquivos de vídeo temporários e miniaturas que excederam a idade máxima permitida."""
    print("[CLEANUP] Iniciando rotina de limpeza de arquivos temporários...")
    now = time.time()
    cleaned_dirs = set()

    deleted_files = []
    for directory in CANDIDATE_TEMP_DIRS:
        if not directory or not os.path.exists(directory):
            continue
        real_dir = os.path.abspath(directory)
        if real_dir in cleaned_dirs:
            continue
        cleaned_dirs.add(real_dir)
        print(f"[CLEANUP] Varrendo diretório temporário: {real_dir}")

        for filename in os.listdir(real_dir):
            filepath = os.path.join(real_dir, filename)
            if os.path.isfile(filepath):
                file_age = now - os.path.getmtime(filepath)
                if file_age > (MAX_AGE_HOURS * 3600):
                    try:
                        os.remove(filepath)
                        deleted_files.append(filename)
                        print(f"[CLEANUP] Arquivo removido: {filename} ({file_age / 3600:.1f}h de idade)")
                    except Exception as e:
                        print(f"[CLEANUP] Erro ao remover {filename}: {e}")

    if deleted_files:
        try:
            from backend.app.core.loop import run_sync
            from backend.app.db.db_service import mark_file_records_expired
            res = run_sync(mark_file_records_expired(deleted_files))
            print(f"[CLEANUP/DB] Marcados no banco como EXPIRED: {res.get('expired_clips', 0)} clipe(s), {res.get('expired_projects', 0)} projeto(s).")
        except Exception as e:
            print(f"[CLEANUP/DB] Atualização de status no banco ignorada ou indisponível: {e}")


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
    """
    Rotina de retenção e expurgo de dados (Art. 16 da LGPD):
    Apaga projetos, clipes e transcrições com mais de 30 dias de inatividade.
    """
    print("[CLEANUP/LGPD] Iniciando expurgo de banco de dados (retenção > 30 dias - Art. 16 LGPD)...")
    try:
        from backend.app.core.loop import run_sync
        from backend.app.db.db_service import cleanup_old_db_records
        max_days = int(os.getenv("RETENTION_MAX_DAYS", "30"))
        res = run_sync(cleanup_old_db_records(max_age_days=max_days))
        deleted_p = res.get('deleted_projects', 0)
        deleted_t = res.get('deleted_transcriptions', 0)
        print(f"[CLEANUP/LGPD] Expurgo concluído com sucesso: {deleted_p} projeto(s) e {deleted_t} transcrição(ões) apagados (dados com mais de {max_days} dias).")
    except Exception as e:
        print(f"[CLEANUP/LGPD] Limpeza de banco de dados ignorada ou indisponível: {e}")


if __name__ == "__main__":
    cleanup_old_files()
    check_stale_projects_watchdog()
    cleanup_database_retention()
