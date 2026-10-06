from huey import RedisHuey
import os
import gc
import logging
import traceback
from dotenv import load_dotenv

load_dotenv()

# INFO em vez de DEBUG — evita acumular strings de log na RAM
from backend.app.core.logging_config import setup_logging
setup_logging()
logger = logging.getLogger("clipmaker.worker")

# Configura a fila usando Redis
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
huey = RedisHuey('clipmaker_tasks', url=redis_url)


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


@huey.task()
def process_video_task(project_id: str, input_path: str, temp_dir: str, aspect_ratio: str = "9:16"):
    logger.info(f"Iniciando processamento para o projeto: {project_id} (proporção: {aspect_ratio})")
    logger.info(f"Input: {input_path}")
    try:
        from backend.app.services.engine_service import process_video_full_pipeline
        
        clips = process_video_full_pipeline(input_path, temp_dir, project_id, aspect_ratio)
        logger.info(f"Sucesso! Clipes gerados para {project_id}: {len(clips)}")
        
        from backend.app.core.loop import run_sync
        from backend.app.db.db_service import save_project_results
        run_sync(save_project_results(project_id, clips))
        logger.info(f"Resultados salvos no banco para {project_id}")
        
    except Exception as e:
        logger.error(f"Erro ao processar projeto {project_id}: {e}")
        traceback.print_exc()
        
        from backend.app.core.loop import run_sync
        from backend.app.db.db_service import update_project_status
        run_sync(update_project_status(project_id, "FAILED", str(e)))
        logger.info(f"Status do projeto {project_id} atualizado para FAILED")
        
    finally:
        _cleanup_runtime()
        
        if os.path.exists(input_path):
            logger.info(f"Vídeo original preservado para edições: {input_path}")


@huey.task()
def re_render_clip_task(clip_id: str, payload_dict: dict):
    from backend.app.core.loop import run_sync
    from backend.app.db.db_service import get_clip, get_project_with_clips, update_clip_render_details
    from backend.app.services.video_service import generate_srt_from_words, extract_and_crop_clip, re_render_clip
    import uuid, shutil, json

    clip = run_sync(get_clip(clip_id))
    if not clip: return
    project = run_sync(get_project_with_clips(clip.get("projectid")))
    if not project: return

    from backend.app.core.config import settings
    temp_dir = str(settings.TEMP_DIR)
    
    rendered_url = clip.get("renderedurl")
    if not rendered_url: return
        
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
    style = payload_dict.get("style", "Yellow")
    quality = payload_dict.get("quality", "Medium")
    add_subtitles = payload_dict.get("add_subtitles", True)
    words = payload_dict.get("words", [])

    needs_full_render = False
    if aspect_ratio != current_aspect: needs_full_render = True
    if abs(new_start - current_start) > 0.5 or abs(new_end - current_end) > 0.5: needs_full_render = True
        
    try:
        generate_srt_from_words(words, srt_path)
        has_source = bool(source_video_path and os.path.exists(source_video_path))
        
        if needs_full_render or not os.path.exists(output_clean_path):
            if has_source:
                extract_and_crop_clip(
                    source_video_path, output_clean_path, None, 
                    new_start, new_end, 
                    aspect_ratio=aspect_ratio, 
                    add_subtitles=False,
                    style_name=style,
                    quality=quality
                )
            else:
                fallback_source = output_clean_path if os.path.exists(output_clean_path) else output_path
                temp_clean = os.path.join(temp_dir, f"temp_clean_{uuid.uuid4().hex}.mp4")
                clip_duration = max(0.0, new_end - new_start)
                if clip_duration <= 0.0: clip_duration = float(clip.get("durationsec") or 30.0)
                extract_and_crop_clip(
                    fallback_source, temp_clean, None, 
                    0.0, clip_duration, 
                    aspect_ratio=aspect_ratio, 
                    add_subtitles=False,
                    style_name=style,
                    quality=quality
                )
                if os.path.exists(temp_clean): shutil.move(temp_clean, output_clean_path)
            
            if add_subtitles and os.path.exists(srt_path) and os.path.getsize(srt_path) > 0:
                re_render_clip(output_clean_path, output_path, srt_path, style, True, quality, aspect_ratio)
            else:
                shutil.copyfile(output_clean_path, output_path)
        else:
            re_render_clip(output_clean_path, output_path, srt_path, style, add_subtitles, quality, aspect_ratio)
            
    except Exception as e:
        logger.error(f"Erro no re-render: {e}")
    finally:
        if os.path.exists(srt_path):
            try: os.remove(srt_path)
            except OSError: pass
        # Limpeza de RAM após re-render
        _cleanup_runtime()
                
    run_sync(update_clip_render_details(
        clip_id=clip_id,
        words_json=json.dumps(words),
        caption_config=style,
        aspect_ratio=aspect_ratio,
        start_time=new_start,
        end_time=new_end
    ))
