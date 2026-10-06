import os
import gc
import uuid
import shutil
import time
import logging

logger = logging.getLogger("clipmaker.engine")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)

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

def process_video_full_pipeline(input_path: str, temp_dir: str, project_id: str = None, aspect_ratio: str = "9:16") -> list:
    """
    Pipeline completo otimizado para baixo consumo de RAM:
    1. Probe do vídeo
    2. Transcrição (Whisper) com liberação estrita de VRAM
    3. Detecção de momentos (Gemini)
    4. Geração de clipes, legendas e crop configurável (FFmpeg)
    
    Otimizações de memória aplicadas:
    - Segmentos Whisper convertidos em dicts leves (ai_service já faz isso)
    - transcript_text liberado após enviar para LLM
    - gc.collect() entre etapas pesadas
    """
    input_path = os.path.abspath(input_path)
    temp_dir = os.path.abspath(temp_dir)

    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Arquivo de input não encontrado: {input_path}")

    file_size_mb = os.path.getsize(input_path) / (1024 * 1024)
    logger.info(f"Iniciando para: {os.path.basename(input_path)} ({file_size_mb:.1f} MB)")

    # 1. Probe
    logger.info("Etapa 1/4: Analisando vídeo (ffprobe)...")
    orig_w, orig_h, duration = video_service.get_video_info(input_path)
    logger.info(f"Vídeo: {orig_w}x{orig_h}, duração: {duration:.1f}s")

    # 2. Transcrição
    logger.info("Etapa 2/4: Transcrevendo áudio (Whisper)...")
    if project_id:
        _update_status(project_id, "TRANSCRIBING")
        
    segments = ai_service.transcribe_audio(input_path)
    logger.info(f"Transcrição finalizada: {len(segments)} segmentos obtidos.")

    # 3. Geração de boundaries via LLM
    logger.info("Etapa 3/4: Calculando melhores momentos...")
    if project_id:
        _update_status(project_id, "ANALYZING")
        
    transcript_text = ai_service.format_transcript_from_segments(segments)
    clip_boundaries = ai_service.get_viral_clips_from_llm(transcript_text, duration)
    
    # Liberar o texto da transcrição — pode ser grande para vídeos longos
    del transcript_text
    gc.collect()

    # 4. Renderização
    logger.info(f"Etapa 4/4: Renderizando {len(clip_boundaries)} clipe(s)...")
    if project_id and clip_boundaries:
        _update_status(project_id, "RENDERING")
        
    generated_clips_ui = []
    total_clips = len(clip_boundaries)
    
    for i, (start_sec, end_sec, title, hook) in enumerate(clip_boundaries):
        clip_num = i + 1
        logger.info(f"[CLIPE {clip_num}/{total_clips}] Processando ({start_sec:.1f}s -> {end_sec:.1f}s)...")

        clip_uuid = str(uuid.uuid4())
        clip_filename = f"clip_{clip_uuid}.mp4"
        clean_clip_filename = f"clean_{clip_uuid}.mp4"
        output_clean_path = os.path.join(temp_dir, clean_clip_filename)
        output_path = os.path.join(temp_dir, clip_filename)
        srt_path = os.path.join(temp_dir, f"sub_{uuid.uuid4().hex}.srt")

        has_subtitles = False
        words_ui = []
        if segments:
            logger.info(f"[CLIPE {clip_num}] Gerando legendas SRT...")
            words_ui = video_service.generate_word_level_srt(segments, start_sec, end_sec, srt_path)
            if words_ui:
                has_subtitles = True
            
        logger.info(f"[CLIPE {clip_num}] Tracking facial (OpenCV)...")
        face_center_x = video_service.calculate_smooth_face_center(input_path, start_sec, end_sec)

        logger.info(f"[CLIPE {clip_num}] Renderizando vídeo limpo com FFmpeg...")
        try:
            render_time = video_service.render_clip(
                input_path=input_path,
                output_path=output_clean_path,
                srt_path=None,
                start_sec=start_sec,
                end_sec=end_sec,
                orig_w=orig_w,
                orig_h=orig_h,
                face_center_x=face_center_x,
                has_subtitles=False,
                aspect_ratio=aspect_ratio
            )
            
            if has_subtitles:
                logger.info(f"[CLIPE {clip_num}] Aplicando subtitles no vídeo limpo...")
                video_service.re_render_clip(output_clean_path, output_path, srt_path, "Yellow", aspect_ratio=aspect_ratio)
            else:
                shutil.copy(output_clean_path, output_path)
                
            logger.info(f"[CLIPE {clip_num}] OK! Renderizado em {render_time:.1f}s -> {clip_filename}")
        except Exception as e:
            raise RuntimeError(f"Erro inesperado ao renderizar clipe {clip_num}: {str(e)}")
        finally:
            try:
                if os.path.exists(srt_path):
                    os.remove(srt_path)
            except OSError:
                pass

        generated_clips_ui.append({
            "id": clip_uuid,
            "renderedUrl": clip_filename,
            "title": title,
            "duration": format_duration(end_sec - start_sec),
            "durationSec": round(end_sec - start_sec, 2),
            "startTime": round(start_sec, 2),
            "endTime": round(end_sec, 2),
            "aspectRatio": aspect_ratio,
            "viralScore": 95 - i * 5,
            "hookReason": hook,
            "words": words_ui,
            "thumbnail": f"https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=600&auto=format&fit=crop&q=80",
        })
        
        # GC entre clipes para devolver memória do face tracking e render anterior
        gc.collect()

    logger.info(f"Concluido! {len(generated_clips_ui)} clipe(s) gerado(s).")
    return generated_clips_ui
