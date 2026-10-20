from huey import RedisHuey, SqliteHuey, crontab
import os
import sys
import gc
import logging
import traceback
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# INFO em vez de DEBUG — evita acumular strings de log na RAM
from backend.app.core.logging_config import setup_logging
setup_logging()
logger = logging.getLogger("clipmaker.worker")

# Configuração da fila: Redis (produção) ou SQLite (desenvolvimento local / testes com flag explícita)
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
allow_sqlite = os.getenv("ALLOW_SQLITE_FALLBACK", "false").lower() in ("true", "1") and os.getenv("ENVIRONMENT") != "production"
_use_redis = True

if redis_url.startswith("sqlite"):
    if not allow_sqlite:
        raise RuntimeError("REDIS_URL SQLite detectada, mas ALLOW_SQLITE_FALLBACK não está ativada.")
    _use_redis = False
else:
    try:
        import redis
        client = redis.from_url(redis_url, socket_connect_timeout=2.0)
        client.ping()
    except Exception as e:
        if not allow_sqlite:
            logger.critical(f"Falha crítica: Redis indisponível ({e}).")
            raise RuntimeError(
                f"Redis indisponível ({e}). Em produção ou sem permissão explícita, "
                f"a fila de tarefas falha imediatamente. Para testes/dev local sem Redis, use ALLOW_SQLITE_FALLBACK=true."
            ) from e
        logger.warning(
            f"[AVISO] Redis indisponível ({e}). ALLOW_SQLITE_FALLBACK=true ativado: alternando para SqliteHuey (huey_queue.db) local."
        )
        _use_redis = False

if _use_redis:
    huey = RedisHuey('clipmaker_tasks', url=redis_url)
    huey_ingest = huey
    huey_render = huey
    logger.info("Fila Huey unificada (clipmaker_tasks) inicializada com Redis com sucesso.")
else:
    import tempfile
    queue_dir = Path(__file__).resolve().parent.parent.parent.parent
    db_path = queue_dir / "huey_queue.db"
    if not os.access(queue_dir, os.W_OK):
        db_path = Path(tempfile.gettempdir()) / "huey_queue.db"
    huey = SqliteHuey('clipmaker_tasks', filename=str(db_path))
    huey_ingest = huey
    huey_render = huey
    logger.warning("[AVISO] Fila Huey unificada inicializada com SqliteHuey local.")


@huey.on_startup()
def preload_models_on_worker_startup():
    """Pré-carrega o modelo Whisper dentro do processo do worker para reutilização entre jobs."""
    try:
        from backend.app.services.ai_service import preload_whisper_model
        logger.info("[WORKER] Executando pré-carregamento do modelo Whisper no startup do worker...")
        preload_whisper_model()
        logger.info("[WORKER] Modelo Whisper inicializado no processo do worker com sucesso.")
    except Exception as e:
        logger.warning(f"[WORKER] Falha ao pré-carregar modelo Whisper no startup: {e}")


def _cleanup_runtime():
    """Limpeza agressiva de RAM e VRAM após qualquer task pesada."""
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            logger.info("VRAM e RAM liberadas com sucesso.")
    except ImportError:
        pass


def categorize_error(e: Exception) -> str:
    """
    Gera uma mensagem de erro curta e genérica por categoria para gravação no banco de dados.
    O erro técnico completo deve ser registrado exclusivamente nos logs da aplicação via logger.exception.
    """
    err_str = str(e).lower()
    if isinstance(e, TimeoutError) or "tempo limite" in err_str or "timeout" in err_str:
        return "O processamento excedeu o tempo limite. Tente novamente."
    if "download" in err_str or "yt-dlp" in err_str or "url" in err_str:
        return "Falha ao baixar o vídeo. Verifique se o link é válido e público."
    if "whisper" in err_str or "transcri" in err_str:
        return "Falha na transcrição do áudio do vídeo."
    if "gemini" in err_str or "llm" in err_str or "análise" in err_str or "analise" in err_str:
        return "Falha na análise dos melhores momentos com IA."
    if "render" in err_str or "ffmpeg" in err_str:
        return "Falha na renderização do clipe."
    if "duração máxima" in err_str or "limite de duração" in err_str or "excede" in err_str:
        return "O vídeo excede os limites de duração permitidos."
    if "arquivo" in err_str and ("vazio" in err_str or "não encontrado" in err_str or "corrompido" in err_str):
        return "Arquivo de vídeo não encontrado ou corrompido."
    return "Ocorreu um erro no processamento do vídeo. Tente novamente."


def _is_network_transient_error(stderr_text: str) -> bool:
    """Detecta se uma falha do yt-dlp foi puramente de rede (elegível para 1 retry)."""
    err_lower = stderr_text.lower()
    non_retryable = [
        "private video", "video unavailable", "sign in", "removed by the uploader",
        "copyright", "http error 404", "http error 403", "members-only",
        "account has been terminated"
    ]
    if any(nr in err_lower for nr in non_retryable):
        return False
    network_indicators = [
        "timed out", "timeout", "connection reset", "connection refused",
        "network is unreachable", "temporary failure", "incompleteread",
        "remotedisconnected", "unable to download webpage", "connection error",
        "errno 104", "errno 110", "errno 111"
    ]
    return any(ni in err_lower for ni in network_indicators)


@huey.periodic_task(crontab(minute='*/5'))
def watchdog_stale_projects_task():
    """Tarefa periódica do Huey que identifica e finaliza projetos travados a cada 5 minutos."""
    from backend.app.core.loop import run_sync
    from backend.app.db.db_service import fail_stale_projects
    from backend.app.core.config import settings
    stale_min = int(getattr(settings, "PROJECT_STALE_MINUTES", 60))
    try:
        count = run_sync(fail_stale_projects(stale_minutes=stale_min))
        if count > 0:
            logger.warning(f"[WATCHDOG] {count} projeto(s) travado(s) marcado(s) como FAILED por inatividade > {stale_min}min.")
    except Exception as e:
        logger.exception(f"[WATCHDOG] Falha ao executar varredura de projetos travados: {e}")


@huey.task()
def download_and_process_url_task(project_id: str, url: str, temp_dir: str, aspect_ratio: str = "9:16"):
    """
    Task assíncrona de ingestão via URL:
    1. Probe de metadados e duração via yt-dlp sem travar o event loop da API.
    2. Download otimizado do vídeo com yt-dlp.
    3. Atualização do projeto com o arquivo gravado.
    4. Execução do pipeline completo (transcrição, momentos, render).
    """
    import time
    import subprocess
    from backend.app.core.config import settings
    from backend.app.core.loop import run_sync
    from backend.app.db.db_service import update_project_status, update_project_source, record_job_metric
    from backend.app.services.video_service import get_video_info
    from backend.app.services.engine_service import process_video_full_pipeline

    t_start = time.time()
    logger.info(f"[INGEST] Iniciando download por URL para projeto {project_id}: {url}")
    safe_filename = f"{project_id}.mp4"
    input_path = os.path.join(temp_dir, safe_filename)
    max_duration_sec = settings.MAX_DURATION_SEC

    try:
        # Validação Anti-SSRF antes do yt-dlp para mitigar risco de DNS rebinding
        from backend.app.api.routers.video import _is_safe_public_url
        if not _is_safe_public_url(url):
            raise ValueError("URL não permitida ou insegura.")

        run_sync(update_project_status(project_id, "DOWNLOADING"))

        # 1. Probe prévio com timeout controlado
        probe_cmd = [sys.executable, "-m", "yt_dlp", "--force-ipv4", "--no-playlist", "--print", "duration", "--", url]
        probe_res = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=60)
        video_duration = 0.0
        if probe_res.returncode == 0:
            try:
                video_duration = float(probe_res.stdout.strip() or "0")
            except ValueError:
                pass

        if video_duration > max_duration_sec:
            raise ValueError(f"O vídeo excede o limite máximo permitido de {max_duration_sec} segundos.")

        # 2. Download otimizado com no máximo 1 retry apenas para falhas de rede transitórias
        max_height = getattr(settings, "MAX_SOURCE_HEIGHT", 1080)
        max_file_size_mb = getattr(settings, "MAX_FILE_SIZE_MB", 500)
        download_cmd = [
            sys.executable, "-m", "yt_dlp",
            "--force-ipv4",
            "--no-playlist",
            "--max-filesize", f"{max_file_size_mb}M",
            "--concurrent-fragments", "4",
            "--quiet", "--no-progress",
            "-f", f"bestvideo[height<={max_height}][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "-o", input_path,
            "--", url
        ]
        
        max_download_attempts = 2
        dl_success = False
        last_dl_err = ""
        
        for attempt in range(max_download_attempts):
            try:
                dl_res = subprocess.run(download_cmd, capture_output=True, text=True, timeout=1800)
                if dl_res.returncode == 0 and os.path.exists(input_path) and os.path.getsize(input_path) > 0:
                    dl_success = True
                    break
                stderr_text = dl_res.stderr or ""
                last_dl_err = stderr_text[-500:]
                logger.warning(f"[INGEST] Tentativa {attempt + 1} de download falhou para {project_id}: {last_dl_err}")
                
                if attempt == 0 and _is_network_transient_error(stderr_text):
                    logger.info(f"[INGEST] Erro de rede detectado. Tentando novamente (máx. 1 retry)...")
                    time.sleep(3)
                    continue
                else:
                    break
            except subprocess.TimeoutExpired:
                last_dl_err = "Download excedeu o tempo limite de 1800s via yt-dlp"
                if attempt == 0:
                    logger.info(f"[INGEST] Timeout de download. Tentando novamente (máx. 1 retry)...")
                    continue
                break

        if not dl_success:
            raise RuntimeError(f"Falha no download via yt-dlp: {last_dl_err}")

        if not os.path.exists(input_path) or os.path.getsize(input_path) == 0:
            raise RuntimeError("O arquivo de vídeo baixado está vazio ou não foi gravado.")

        # 3. Probe real no arquivo baixado
        _, _, actual_duration = get_video_info(input_path)
        if actual_duration > max_duration_sec:
            raise ValueError(f"O vídeo excede a duração máxima permitida ({actual_duration:.1f}s > {max_duration_sec}s).")

        run_sync(update_project_source(project_id, safe_filename, actual_duration))
        logger.info(f"[INGEST] Download concluído para {project_id}: {safe_filename} ({actual_duration:.1f}s)")

        # 4. Execução do pipeline completo
        clips = process_video_full_pipeline(input_path, temp_dir, project_id, aspect_ratio, source_url=url)
        elapsed = time.time() - t_start
        run_sync(record_job_metric(project_id, actual_duration, elapsed))
        logger.info(f"Sucesso! Projeto {project_id} finalizado em {elapsed:.1f}s ({len(clips)} clipes).")

    except Exception as e:
        logger.exception(f"Erro técnico no processamento por URL para {project_id}: {e}")
        friendly_error = categorize_error(e)
        run_sync(update_project_status(project_id, "FAILED", friendly_error))
        if os.path.exists(input_path):
            try: os.remove(input_path)
            except OSError: pass
    finally:
        _cleanup_runtime()


@huey.task()
def process_video_task(project_id: str, input_path: str, temp_dir: str, aspect_ratio: str = "9:16"):
    import time
    t_start = time.time()
    logger.info(f"Iniciando processamento para o projeto: {project_id} (proporção: {aspect_ratio})")
    logger.info(f"Input: {input_path}")
    try:
        from backend.app.services.engine_service import process_video_full_pipeline
        
        clips = process_video_full_pipeline(input_path, temp_dir, project_id, aspect_ratio)
        logger.info(f"Sucesso! Clipes gerados para {project_id}: {len(clips)}")
        
        from backend.app.core.loop import run_sync
        from backend.app.db.db_service import save_project_results, record_job_metric
        from backend.app.services.video_service import get_video_info

        run_sync(save_project_results(project_id, clips))
        logger.info(f"Resultados salvos no banco para {project_id}")

        elapsed = time.time() - t_start
        try:
            _, _, dur = get_video_info(input_path)
            run_sync(record_job_metric(project_id, dur, elapsed))
        except Exception:
            pass
        
    except Exception as e:
        logger.exception(f"Erro técnico ao processar projeto {project_id}: {e}")
        friendly_error = categorize_error(e)
        from backend.app.core.loop import run_sync
        from backend.app.db.db_service import update_project_status
        run_sync(update_project_status(project_id, "FAILED", friendly_error))
        logger.info(f"Status do projeto {project_id} atualizado para FAILED ({friendly_error})")
        
    finally:
        _cleanup_runtime()
        
        if os.path.exists(input_path):
            logger.info(f"Vídeo original preservado para edições: {input_path}")


@huey.task()
def re_render_clip_task(clip_id: str, payload_dict: dict):
    from backend.app.core.loop import run_sync
    from backend.app.db.db_service import get_clip, get_project_with_clips, update_clip_render_details, update_clip_status
    from backend.app.services.video_service import generate_srt_from_words, extract_and_crop_clip, re_render_clip
    import uuid, shutil, json

    clip = run_sync(get_clip(clip_id))
    if not clip: return
    project = run_sync(get_project_with_clips(clip.get("projectid")))
    if not project: return

    # Atualiza status inicial do re-render
    run_sync(update_clip_status(clip_id, "RENDERING"))

    from backend.app.core.config import settings
    temp_dir = str(settings.TEMP_DIR)
    
    rendered_url = clip.get("renderedurl")
    if not rendered_url:
        run_sync(update_clip_status(clip_id, "FAILED", "Arquivo renderizado de origem não encontrado."))
        return
        
    clip_uuid = rendered_url.replace("clip_", "").replace(".mp4", "")
    clean_clip_filename = f"clean_{clip_uuid}.mp4"
    output_clean_path = os.path.join(temp_dir, clean_clip_filename)
    output_path = os.path.join(temp_dir, rendered_url)
    srt_path = os.path.join(temp_dir, f"sub_rerender_{uuid.uuid4().hex}.srt")
    source_filename = project.get("sourcefilekey", "")
    source_video_path = os.path.join(temp_dir, source_filename) if source_filename else ""
    
    current_start = float(clip.get("starttime") or 0.0)
    current_end = float(clip.get("endtime") or clip.get("durationsec") or 0.0)
    new_start = payload_dict.get("start_time") if payload_dict.get("start_time") is not None else current_start
    new_end = payload_dict.get("end_time") if payload_dict.get("end_time") is not None else current_end
    current_aspect = clip.get("aspectratio", "9:16")
    
    aspect_ratio = payload_dict.get("aspect_ratio", "9:16")
    if aspect_ratio not in ("9:16", "1:1", "16:9"):
        aspect_ratio = "9:16"

    style = payload_dict.get("style", "Yellow")
    raw_quality = str(payload_dict.get("quality", "1080p")).lower()
    quality = "720p" if raw_quality == "720p" else "1080p"
    add_subtitles = payload_dict.get("add_subtitles", True)
    words = payload_dict.get("words", [])

    needs_full_render = False
    if aspect_ratio != current_aspect: needs_full_render = True
    if abs(new_start - current_start) > 0.5 or abs(new_end - current_end) > 0.5: needs_full_render = True
        
    face_center_x = clip.get("face_center_x") if clip.get("face_center_x") is not None else clip.get("facecenterx")
    temp_render_out = os.path.join(temp_dir, f"temp_render_{uuid.uuid4().hex}.mp4")

    try:
        generate_srt_from_words(words, srt_path)
        has_source = bool(source_video_path and os.path.exists(source_video_path))
        
        if has_source:
            logger.info(f"Re-renderizando clipe {clip_id} em passe único a partir do vídeo fonte: {source_video_path} (face_center_x={face_center_x})")
            extract_and_crop_clip(
                source_path=source_video_path,
                output_path=temp_render_out,
                srt_path=srt_path,
                start_sec=new_start,
                end_sec=new_end,
                aspect_ratio=aspect_ratio,
                add_subtitles=add_subtitles,
                style_name=style,
                quality=quality,
                face_center_x=face_center_x,
            )
        else:
            logger.warning(
                f"[AVISO] Vídeo fonte não encontrado em {source_video_path}. "
                f"Usando o clipe final anterior {output_path} como fonte."
            )
            if not os.path.exists(output_path):
                raise FileNotFoundError(f"Nem o vídeo fonte nem o clipe anterior existem no disco: {output_path}")
            re_render_clip(
                input_clean_path=output_path,
                output_path=temp_render_out,
                srt_path=srt_path,
                style_name=style,
                add_subtitles=add_subtitles,
                quality=quality,
                aspect_ratio=aspect_ratio,
            )

        if os.path.exists(temp_render_out):
            shutil.move(temp_render_out, output_path)

        # Sucesso: atualiza dados e define status COMPLETED
        run_sync(update_clip_render_details(
            clip_id=clip_id,
            words_json=json.dumps(words),
            caption_config=style,
            aspect_ratio=aspect_ratio,
            start_time=new_start,
            end_time=new_end,
            status="COMPLETED"
        ))
        logger.info(f"Re-render do clipe {clip_id} concluído com sucesso.")
    except Exception as e:
        logger.exception(f"Erro técnico no re-render do clipe {clip_id}: {e}")
        run_sync(update_clip_status(clip_id, "FAILED", "Falha na renderização do clipe."))
        raise
    finally:
        if os.path.exists(srt_path):
            try: os.remove(srt_path)
            except OSError: pass
        _cleanup_runtime()
