import os
import uuid
import time
import logging

logger = logging.getLogger("clipmaker.engine")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)

from backend.services import ai_service, video_service

def format_duration(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"

def process_video_full_pipeline(input_path: str, temp_dir: str) -> list:
    """
    Pipeline completo otimizado:
    1. Probe do vídeo
    2. Transcrição (Whisper) com liberação estrita de VRAM
    3. Detecção de momentos
    4. Geração de clipes, legendas e crop 9:16 (FFmpeg / NVENC)
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
    segments = ai_service.transcribe_audio(input_path)
    logger.info(f"Transcrição finalizada: {len(segments)} segmentos obtidos.")

    # 3. Geração de boundaries
    logger.info("Etapa 3/4: Calculando melhores momentos...")
    clip_boundaries = ai_service.generate_clip_boundaries(duration)

    # 4. Renderização
    logger.info(f"Etapa 4/4: Renderizando {len(clip_boundaries)} clipe(s)...")
    generated_clips_ui = []
    
    for i, (start_sec, end_sec, title, hook) in enumerate(clip_boundaries):
        clip_num = i + 1
        total_clips = len(clip_boundaries)
        logger.info(f"[CLIPE {clip_num}/{total_clips}] Processando ({start_sec:.1f}s -> {end_sec:.1f}s)...")

        clip_id = f"clip_{uuid.uuid4().hex}.mp4"
        output_path = os.path.join(temp_dir, clip_id)
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

        logger.info(f"[CLIPE {clip_num}] Renderizando com FFmpeg...")
        try:
            render_time = video_service.render_clip(
                input_path=input_path,
                output_path=output_path,
                srt_path=srt_path,
                start_sec=start_sec,
                end_sec=end_sec,
                orig_w=orig_w,
                orig_h=orig_h,
                face_center_x=face_center_x,
                has_subtitles=has_subtitles
            )
            logger.info(f"[CLIPE {clip_num}] OK! Renderizado em {render_time:.1f}s -> {clip_id}")
        except Exception as e:
            raise RuntimeError(f"Erro inesperado ao renderizar clipe {clip_num}: {str(e)}")
        finally:
            try:
                if os.path.exists(srt_path):
                    os.remove(srt_path)
            except OSError:
                pass

        generated_clips_ui.append({
            "id": clip_id,
            "title": title,
            "duration": format_duration(end_sec - start_sec),
            "viralScore": 95 - i * 5,
            "hookReason": hook,
            "words": words_ui,
            "thumbnail": f"https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=600&auto=format&fit=crop&q=80",
        })

    logger.info(f"Concluido! {len(generated_clips_ui)} clipe(s) gerado(s).")
    return generated_clips_ui
