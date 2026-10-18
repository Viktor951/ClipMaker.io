import os
import gc
import uuid
import shutil
import time
import hashlib
import logging
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger("clipmaker.engine")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)

from backend.app.core.timing import timed
from backend.app.services import ai_service, video_service


def format_duration(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def _update_status(project_id: str, status: str):
    """Helper para evitar imports repetidos no pipeline."""
    from backend.app.core.loop import run_sync
    from backend.app.db.db_service import update_project_status
    run_sync(update_project_status(project_id, status))


def _normalize_url(url: Optional[str]) -> Optional[str]:
    """Normaliza URLs para busca consistente em cache."""
    if not url:
        return None
    return url.strip().lower().rstrip("/")


def _compute_fast_file_hash(filepath: str) -> Optional[str]:
    """
    Calcula hash SHA-256 rápido e determinístico de um arquivo para detecção de reuso.
    Para arquivos grandes, amostra início, meio e fim + tamanho total em ~15ms.
    """
    if not filepath or not os.path.exists(filepath):
        return None
    try:
        size = os.path.getsize(filepath)
        hasher = hashlib.sha256()
        hasher.update(f"size:{size}:".encode("utf-8"))
        chunk_size = 8 * 1024 * 1024  # 8 MB
        if size <= chunk_size * 3:
            with open(filepath, "rb") as f:
                while chunk := f.read(chunk_size):
                    hasher.update(chunk)
        else:
            with open(filepath, "rb") as f:
                # Início
                hasher.update(f.read(chunk_size))
                # Meio
                f.seek(size // 2)
                hasher.update(f.read(chunk_size))
                # Fim
                f.seek(max(0, size - chunk_size))
                hasher.update(f.read(chunk_size))
        return hasher.hexdigest()
    except Exception as e:
        logger.warning(f"Erro ao calcular hash do arquivo ({filepath}): {e}")
        return None


def _get_render_parallelism() -> int:
    """Calcula o paralelismo de renderização respeitando GPU/CPU e limites de cgroup."""
    env_p = int(os.getenv("RENDER_PARALLELISM", "0") or 0)
    if env_p > 0:
        return env_p
    if video_service.is_nvenc_available():
        return 2  # GPU com NVENC suporta múltiplas sessões com folga
    cgroup_cpus = video_service.get_cgroup_cpu_limit()
    if cgroup_cpus >= 4.0:
        return 2
    return 1


def process_video_full_pipeline(
    input_path: str,
    temp_dir: str,
    project_id: str = None,
    aspect_ratio: str = "9:16",
    skip_llm: bool = False,
    user_id: str = None,
    source_url: str = None
) -> list:
    """
    Pipeline completo otimizado para alto desempenho e baixo consumo de recursos:
    1. Probe do vídeo
    2. Transcrição com reuso em cache (Whisper pulado se já houver registro do usuário)
    3. Detecção de momentos com Gemini (respeitando retry-delay e fallback)
    4. Renderização paralela em PASSE ÚNICO (crop + scale + legendas integrados, sem clean_*.mp4)
    5. Persistência incremental imediata no banco por clipe (status COMPLETED)
    """
    input_path = os.path.abspath(input_path)
    temp_dir = os.path.abspath(temp_dir)

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Arquivo de input não encontrado: {input_path}")

    file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
    logger.info(f"Iniciando para: {os.path.basename(input_path)} ({file_size_mb:.1f} MB)")

    from backend.app.core.config import settings
    t_pipeline_start = time.time()
    max_job_sec = float(getattr(settings, "JOB_TIMEOUT_MINUTES", 90)) * 60.0

    def _check_job_timeout(stage_name: str):
        if time.time() - t_pipeline_start > max_job_sec:
            logger.error(f"Job excedeu o tempo limite total ({max_job_sec/60:.1f}min) antes da etapa: {stage_name}")
            raise TimeoutError("O processamento excedeu o tempo limite. Tente novamente.")

    # 1. Probe
    _check_job_timeout("probe")
    logger.info("Etapa 1/4: Analisando vídeo (ffprobe)...")
    with timed("probe"):
        orig_w, orig_h, duration = video_service.get_video_info(input_path)
    logger.info(f"Vídeo: {orig_w}x{orig_h}, duração: {duration:.1f}s")

    # Identificar user_id e source_url a partir do projeto se não passados
    if project_id and not user_id:
        try:
            from backend.app.core.loop import run_sync
            from backend.app.db.db_service import get_project_with_clips
            proj = run_sync(get_project_with_clips(project_id))
            if proj:
                user_id = user_id or proj.get("userid") or proj.get("user_id")
                source_url = source_url or proj.get("sourceurl") or proj.get("source_url")
        except Exception as e:
            logger.warning(f"Não foi possível obter metadados do projeto {project_id}: {e}")

    # 2. Transcrição com Reuso
    _check_job_timeout("transcription")
    norm_url = _normalize_url(source_url)
    f_hash = _compute_fast_file_hash(input_path)
    cached_transcription = None

    if user_id:
        try:
            from backend.app.core.loop import run_sync
            from backend.app.db.db_service import get_cached_transcription
            cached_transcription = run_sync(get_cached_transcription(user_id, source_url=norm_url, file_hash=f_hash))
        except Exception as e:
            logger.warning(f"Falha ao consultar cache de transcrição: {e}")

    if cached_transcription and cached_transcription.get("segments"):
        logger.info(f"Reuso de transcrição: transcrição encontrada em cache para usuário {user_id}. Pulando Whisper!")
        segments = cached_transcription["segments"]
    else:
        logger.info("Etapa 2/4: Transcrevendo áudio (Whisper)...")
        if project_id:
            _update_status(project_id, "TRANSCRIBING")
            
        with timed("transcription"):
            segments = ai_service.transcribe_audio(input_path)
        logger.info(f"Transcrição finalizada: {len(segments)} segmentos obtidos.")

        # Persistir transcrição para reuso futuro
        if project_id and segments:
            try:
                from backend.app.core.loop import run_sync
                from backend.app.db.db_service import save_transcription
                full_text = " ".join(s.get("text", "") for s in segments)
                run_sync(save_transcription(
                    project_id=project_id,
                    user_id=user_id,
                    full_text=full_text,
                    segments=segments,
                    source_url=norm_url,
                    file_hash=f_hash
                ))
                logger.info("Transcrição salva na tabela transcriptions para futuro reuso.")
            except Exception as e:
                logger.warning(f"Falha ao persistir transcrição para cache: {e}")

    # 3. Geração de boundaries via LLM
    _check_job_timeout("llm")
    logger.info("Etapa 3/4: Calculando melhores momentos...")
    if project_id:
        _update_status(project_id, "ANALYZING")
        
    with timed("llm"):
        if skip_llm:
            logger.info("skip_llm=True: usando fallback matemático de cortes (_fallback_clip_boundaries).")
            clip_boundaries = ai_service._fallback_clip_boundaries(duration)
            if project_id:
                try:
                    from backend.app.core.loop import run_sync
                    from backend.app.db.db_service import set_project_ai_fallback
                    run_sync(set_project_ai_fallback(project_id, True))
                except Exception as e:
                    logger.warning(f"Falha ao registrar ai_cuts_fallback: {e}")
        else:
            transcript_text = ai_service.format_transcript_from_segments(segments)
            clip_boundaries = ai_service.get_viral_clips_from_llm(transcript_text, duration)
            del transcript_text
            gc.collect()

            meta = ai_service.get_last_llm_meta()
            if meta.get("ai_cuts_fallback") and project_id:
                try:
                    from backend.app.core.loop import run_sync
                    from backend.app.db.db_service import set_project_ai_fallback
                    run_sync(set_project_ai_fallback(project_id, True))
                except Exception as e:
                    logger.warning(f"Falha ao registrar ai_cuts_fallback: {e}")

    # 4. Renderização Paralela em Passe Único
    _check_job_timeout("rendering")
    total_clips = len(clip_boundaries)
    parallelism = min(max(1, _get_render_parallelism()), max(1, total_clips))
    logger.info(f"Etapa 4/4: Renderizando {total_clips} clipe(s) (paralelismo={parallelism})...")
    
    if project_id and clip_boundaries:
        _update_status(project_id, "RENDERING")

    def _render_single_clip(clip_tuple):
        _check_job_timeout(f"clip_{clip_tuple[0]+1}")
        i, item = clip_tuple
        clip_num = i + 1
        if isinstance(item, dict):
            start_sec = float(item.get("start", 0.0))
            end_sec = float(item.get("end", 0.0))
            title = str(item.get("title", f"Clipe {clip_num}"))
            hook = str(item.get("hook", ""))
            viral_score = max(0, min(100, int(item.get("viral_score", 85))))
        else:
            start_sec, end_sec, title, hook = item[:4]
            viral_score = max(0, min(100, int(item[4]))) if len(item) > 4 else max(0, min(100, 95 - i * 5))

        logger.info(f"[CLIPE {clip_num}/{total_clips}] Iniciando render ({start_sec:.1f}s -> {end_sec:.1f}s)...")

        clip_uuid = str(uuid.uuid4())
        clip_filename = f"clip_{clip_uuid}.mp4"
        thumb_filename = f"thumb_{clip_uuid}.jpg"
        output_path = os.path.join(temp_dir, clip_filename)
        thumb_path = os.path.join(temp_dir, thumb_filename)
        srt_path = os.path.join(temp_dir, f"sub_{uuid.uuid4().hex}.srt")

        has_subtitles = False
        words_ui = []
        if segments:
            logger.info(f"[CLIPE {clip_num}] Gerando legendas SRT...")
            words_ui = video_service.generate_word_level_srt(segments, start_sec, end_sec, srt_path)
            if words_ui:
                has_subtitles = True
            
        logger.info(f"[CLIPE {clip_num}] Tracking facial (OpenCV com cv2.VideoCapture)...")
        with timed("face_tracking"):
            face_center_x = video_service.calculate_smooth_face_center(input_path, start_sec, end_sec)

        logger.info(f"[CLIPE {clip_num}] Renderizando em passe único com FFmpeg (face_center_x={face_center_x})...")
        try:
            with timed("render"):
                render_time = video_service.render_clip(
                    input_path=input_path,
                    output_path=output_path,
                    srt_path=srt_path if has_subtitles else None,
                    start_sec=start_sec,
                    end_sec=end_sec,
                    orig_w=orig_w,
                    orig_h=orig_h,
                    face_center_x=face_center_x,
                    has_subtitles=has_subtitles,
                    aspect_ratio=aspect_ratio,
                    parallelism=parallelism
                )
            
            logger.info(f"[CLIPE {clip_num}] OK! Renderizado em {render_time:.1f}s -> {clip_filename}")

            # Geração de thumbnail real do clipe (~1s)
            logger.info(f"[CLIPE {clip_num}] Gerando miniatura do clipe...")
            video_service.generate_thumbnail(input_path, start_sec + 1.0, thumb_path)
        except Exception as e:
            logger.exception(f"[CLIPE {clip_num}] Falha ao renderizar: {e}")
            raise RuntimeError(f"Falha na renderização do clipe {clip_num}.")
        finally:
            try:
                if os.path.exists(srt_path):
                    os.remove(srt_path)
            except OSError:
                pass

        clip_data = {
            "id": clip_uuid,
            "renderedUrl": clip_filename,
            "title": title,
            "duration": format_duration(end_sec - start_sec),
            "durationSec": round(end_sec - start_sec, 2),
            "startTime": round(start_sec, 2),
            "endTime": round(end_sec, 2),
            "aspectRatio": aspect_ratio,
            "viralScore": viral_score,
            "hookReason": hook,
            "words": words_ui,
            "thumbnail": thumb_filename,
            "thumbnail_key": thumb_filename,
            "face_center_x": face_center_x,
            "faceCenterX": face_center_x,
        }

        # Persistência incremental imediata se houver project_id
        if project_id:
            try:
                from backend.app.core.loop import run_sync
                from backend.app.db.db_service import save_single_clip
                run_sync(save_single_clip(project_id, clip_data))
                logger.info(f"[CLIPE {clip_num}] Salvo incrementalmente no banco com status COMPLETED.")
            except Exception as e:
                logger.warning(f"[CLIPE {clip_num}] Falha ao persistir incrementalmente: {e}")

        gc.collect()
        return i, clip_data

    # Execução concorrente mantendo a ordem original dos clipes
    results_map = {}
    with ThreadPoolExecutor(max_workers=parallelism) as executor:
        future_to_idx = {
            executor.submit(_render_single_clip, (i, item)): i
            for i, item in enumerate(clip_boundaries)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                i, clip_data = future.result()
                results_map[i] = clip_data
            except Exception as exc:
                logger.error(f"Erro no processamento do clipe {idx + 1}: {exc}")
                raise exc

    generated_clips_ui = [results_map[i] for i in range(total_clips)]

    if project_id:
        _update_status(project_id, "READY")
        logger.info(f"Projeto {project_id} concluído com sucesso e atualizado para READY.")

    logger.info(f"Concluído! {len(generated_clips_ui)} clipe(s) gerado(s) com sucesso.")
    return generated_clips_ui
