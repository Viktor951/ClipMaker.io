import os
import time
import subprocess
import logging
import gc
import cv2
import ffmpeg

logger = logging.getLogger("clipmaker.video")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)

_NVENC_AVAILABLE = None

def detect_nvenc_support() -> bool:
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
        )
        return "h264_nvenc" in result.stdout
    except Exception:
        return False

def is_nvenc_available() -> bool:
    global _NVENC_AVAILABLE
    if _NVENC_AVAILABLE is None:
        _NVENC_AVAILABLE = detect_nvenc_support()
        if _NVENC_AVAILABLE:
            logger.info("NVENC (h264_nvenc) detectado — aceleração por hardware ATIVADA")
        else:
            logger.warning("NVENC não disponível — usando libx264 (CPU)")
    return _NVENC_AVAILABLE

# ============================================================
# Parâmetros de encoding centralizados (incluindo fallback)
# ============================================================

def get_encoding_params() -> dict:
    """Retorna parâmetros de encoding otimizados para baixo consumo de RAM."""
    if is_nvenc_available():
        return {
            "vcodec": "h264_nvenc",
            "preset": "p4",
            "rc": "vbr",
            "cq": "23",
            "b:v": "6M",
            "maxrate": "10M",
            "acodec": "aac",
            "b:a": "128k",
            "threads": "1",
        }
    else:
        return {
            "vcodec": "libx264",
            "preset": "ultrafast",
            "crf": "23",
            "acodec": "aac",
            "b:a": "128k",
            "threads": "1",
        }

def _get_fallback_cpu_params() -> dict:
    """Parâmetros de fallback em CPU — também limitados a 1 thread."""
    return {
        "vcodec": "libx264",
        "preset": "ultrafast",
        "crf": "23",
        "acodec": "aac",
        "b:a": "128k",
        "threads": "1",
    }

def _ffmpeg_base() -> list:
    """Prefixo padrão de todos os comandos FFmpeg: silencia logs para não encher buffers de RAM."""
    return ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]

# ============================================================
# Probe
# ============================================================

def get_video_info(input_path: str) -> tuple:
    try:
        probe = ffmpeg.probe(input_path)
    except ffmpeg.Error as e:
        stderr_msg = e.stderr.decode("utf-8", errors="ignore") if isinstance(e.stderr, bytes) else str(e.stderr) if e.stderr else ""
        raise RuntimeError(f"FFprobe falhou: {stderr_msg}")

    format_info = probe.get("format", {})
    duration = float(format_info.get("duration", 60.0))

    video_stream = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), None)
    if video_stream is None:
        raise ValueError("Nenhuma stream de vídeo encontrada no arquivo.")

    return int(video_stream["width"]), int(video_stream["height"]), duration

# ============================================================
# Face Tracking — otimizado para baixa RAM
# ============================================================

def calculate_smooth_face_center(video_path: str, start_sec: float, end_sec: float, alpha: float = 0.15, max_frames: int = 300) -> int:
    """
    Detecta o centro do rosto predominante no trecho de vídeo.
    Otimizações de memória:
    - Redimensiona frames para 480px de largura antes de processar (economia ~75% RAM por frame)
    - Deleta explicitamente todas as matrizes NumPy após uso
    - Roda gc.collect() periodicamente
    - Libera cascade classifier ao final
    """
    import tempfile

    logger.info(f"Face tracking: extraindo sub-clipe temporário {start_sec:.1f}s -> {end_sec:.1f}s...")
    
    fd, temp_clip_path = tempfile.mkstemp(suffix=".mp4")
    os.close(fd)
    
    current_center_x = 960
    smoothed_center_x = float(current_center_x)
    frames_processed = 0
    faces_found = 0

    cap = None
    face_cascade = None

    try:
        # Extrair clipe sem re-encode (muito rápido)
        cmd = _ffmpeg_base() + [
            "-ss", str(start_sec), "-to", str(end_sec),
            "-i", video_path, "-c", "copy", temp_clip_path
        ]
        subprocess.run(cmd, capture_output=True, timeout=3600)
        
        cap = cv2.VideoCapture(temp_clip_path)
        if not cap.isOpened():
            logger.warning("Não foi possível abrir o vídeo temporário para face tracking. Usando centro padrão.")
            return 960

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        end_frame = min(int((end_sec - start_sec) * fps), max_frames)
        total_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        
        current_center_x = total_width // 2
        smoothed_center_x = float(current_center_x)

        # Fator de escala para reduzir frames antes do processamento
        # Reduzir para 480px de largura economiza ~75% de RAM por frame
        target_process_width = 480
        scale_factor = target_process_width / total_width if total_width > target_process_width else 1.0

        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        if not os.path.exists(cascade_path):
            logger.warning("Haar cascade file não encontrado. Usando centro padrão.")
            return current_center_x

        face_cascade = cv2.CascadeClassifier(cascade_path)
        current_frame = 0

        while current_frame <= end_frame:
            ret, frame = cap.read()
            if not ret:
                break

            if current_frame % 5 == 0:  # A cada 5 frames (antes era 3) — reduz processamento
                # Redimensionar para resolução menor antes de converter para grayscale
                if scale_factor < 1.0:
                    small_frame = cv2.resize(frame, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_AREA)
                else:
                    small_frame = frame

                gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(30, 30))

                if len(faces) > 0:
                    largest_face = max(faces, key=lambda rect: rect[2] * rect[3])
                    x, y, w, h = largest_face
                    # Converter coordenada de volta para escala original
                    real_center_x = (x + w // 2) / scale_factor
                    smoothed_center_x = alpha * real_center_x + (1.0 - alpha) * smoothed_center_x
                    faces_found += 1

                # Liberar matrizes explicitamente
                del gray, faces
                if scale_factor < 1.0:
                    del small_frame

            # Sempre liberar o frame lido
            del frame
            frames_processed += 1
            current_frame += 1

            # GC periódico a cada 100 frames
            if frames_processed % 100 == 0:
                gc.collect()

    except Exception as e:
        logger.warning(f"Erro no face tracking: {e}")
    finally:
        if cap is not None:
            cap.release()
            del cap
        if face_cascade is not None:
            del face_cascade
        gc.collect()
        if os.path.exists(temp_clip_path):
            try:
                os.remove(temp_clip_path)
            except OSError:
                pass

    logger.info(f"Face tracking concluído: {frames_processed} frames, {faces_found} detecções.")
    return int(smoothed_center_x)

# ============================================================
# SRT Generation
# ============================================================

def format_timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def generate_word_level_srt(segments, start_offset: float, end_offset: float, output_srt_path: str) -> list:
    """Gera SRT word-level. Aceita tanto dicts leves quanto objetos Whisper."""
    words_ui = []
    try:
        with open(output_srt_path, "w", encoding="utf-8") as f:
            idx = 1
            for segment in segments:
                # Suporte a dict (novo) e objeto (legado)
                if isinstance(segment, dict):
                    seg_words = segment.get("words", [])
                else:
                    seg_words = getattr(segment, 'words', None) or []

                for word in seg_words:
                    if isinstance(word, dict):
                        w_start, w_end, w_text = word["start"], word["end"], word["word"]
                    else:
                        w_start, w_end, w_text = word.start, word.end, word.word

                    if w_end < start_offset:
                        continue
                    if w_start > end_offset:
                        break

                    s_clip = max(0, w_start - start_offset)
                    e_clip = max(0.1, w_end - start_offset)

                    f.write(f"{idx}\n")
                    f.write(f"{format_timestamp(s_clip)} --> {format_timestamp(e_clip)}\n")

                    text = w_text.strip().upper()
                    f.write(f"{text}\n\n")
                    idx += 1

                    words_ui.append({
                        "id": f"w{idx}",
                        "text": text,
                        "start": round(s_clip, 3),
                        "end": round(e_clip, 3),
                        "highlighted": False,
                    })
    except Exception as e:
        logger.error(f"ERRO ao gerar SRT: {e}")
    return words_ui

def generate_srt_from_words(words: list, output_srt_path: str):
    try:
        with open(output_srt_path, "w", encoding="utf-8") as f:
            for idx, word in enumerate(words, 1):
                f.write(f"{idx}\n")
                f.write(f"{format_timestamp(word['start'])} --> {format_timestamp(word['end'])}\n")
                
                text = word['text'].strip().upper()
                if word.get('highlighted'):
                    text = f"<b>{text}</b>"
                f.write(f"{text}\n\n")
    except Exception as e:
        logger.error(f"ERRO ao gerar SRT a partir das palavras: {e}")

def escape_ffmpeg_path(path: str) -> str:
    escaped = os.path.abspath(path)
    escaped = escaped.replace("\\", "/")
    escaped = escaped.replace(":", "\\:")
    return escaped

# ============================================================
# Cálculos de crop/scale compartilhados
# ============================================================

def _compute_crop_and_scale(orig_w: int, orig_h: int, aspect_ratio: str, quality: str = "1080p") -> tuple:
    """Retorna (target_crop_w, target_crop_h, crop_x, crop_y, scale_w, scale_h)."""
    if aspect_ratio == "16:9":
        target_ratio = 16.0 / 9.0
        scale_w = 1920 if quality == "1080p" else 1280
        scale_h = 1080 if quality == "1080p" else 720
    elif aspect_ratio == "1:1":
        target_ratio = 1.0
        scale_w = 1080 if quality == "1080p" else 720
        scale_h = 1080 if quality == "1080p" else 720
    else:  # 9:16
        target_ratio = 9.0 / 16.0
        scale_w = 1080 if quality == "1080p" else 720
        scale_h = 1920 if quality == "1080p" else 1280

    orig_ratio = orig_w / orig_h
    if orig_ratio > target_ratio:
        target_crop_h = orig_h
        target_crop_w = int(orig_h * target_ratio)
    else:
        target_crop_w = orig_w
        target_crop_h = int(orig_w / target_ratio)

    target_crop_w = min(orig_w, target_crop_w)
    target_crop_h = min(orig_h, target_crop_h)
    target_crop_w = target_crop_w - (target_crop_w % 2)
    target_crop_h = target_crop_h - (target_crop_h % 2)

    crop_x = max(0, (orig_w - target_crop_w) // 2)
    crop_y = max(0, (orig_h - target_crop_h) // 2)

    return target_crop_w, target_crop_h, crop_x, crop_y, scale_w, scale_h

# ============================================================
# Rendering — com gerenciamento de memória estritos
# ============================================================

def _run_ffmpeg_with_fallback(primary_cmd: list, filter_complex: str, start_sec: float, end_sec: float, input_path: str, output_path: str):
    """Executa FFmpeg com fallback automático para CPU se NVENC falhar."""
    result = subprocess.run(primary_cmd, capture_output=True, text=True, timeout=3600)

    if result.returncode != 0:
        encoding_params = get_encoding_params()
        if encoding_params.get("vcodec") == "h264_nvenc":
            logger.warning("NVENC falhou, tentando fallback com CPU...")
            cpu_params = _get_fallback_cpu_params()
            fallback_cmd = _ffmpeg_base() + [
                "-ss", str(start_sec),
                "-to", str(end_sec),
                "-i", input_path,
                "-filter_complex", filter_complex,
                "-map", "[v]",
                "-map", "0:a",
            ]
            for k, v in cpu_params.items():
                fallback_cmd.extend([f"-{k}", str(v)])
            fallback_cmd.append(output_path)
            
            result_cpu = subprocess.run(fallback_cmd, capture_output=True, text=True, timeout=3600)
            if result_cpu.returncode != 0:
                raise RuntimeError(f"FFmpeg falhou com CPU. Erro:\n{result_cpu.stderr[-1000:]}")
        else:
            raise RuntimeError(f"FFmpeg falhou. Erro:\n{result.stderr[-1000:]}")


def render_clip(input_path: str, output_path: str, srt_path: str, start_sec: float, end_sec: float, orig_w: int, orig_h: int, face_center_x: int, has_subtitles: bool, aspect_ratio: str = "9:16") -> float:
    target_crop_w, target_crop_h, crop_x, crop_y, scale_w, scale_h = _compute_crop_and_scale(orig_w, orig_h, aspect_ratio)

    # Ajustar crop_x baseado no face tracking para 9:16
    if aspect_ratio == "9:16" and face_center_x is not None:
        crop_x = face_center_x - (target_crop_w // 2)
        crop_x = max(0, min(crop_x, orig_w - target_crop_w))

    encoding_params = get_encoding_params()
    srt_escaped = escape_ffmpeg_path(srt_path) if srt_path else ""
    sub_style = "FontName=Montserrat,FontSize=20,PrimaryColour=&H0000FFFF&,Alignment=2,Bold=1,MarginV=15,Outline=2,Shadow=1"

    filter_complex = f"[0:v]crop={target_crop_w}:{target_crop_h}:{crop_x}:{crop_y},scale={scale_w}:{scale_h}"
    if has_subtitles and srt_escaped:
        filter_complex += f",subtitles='{srt_escaped}':force_style='{sub_style}'"
    filter_complex += "[v]"

    base_cmd = _ffmpeg_base() + [
        "-ss", str(start_sec),
        "-to", str(end_sec),
        "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "0:a",
    ]
    
    for k, v in encoding_params.items():
        base_cmd.extend([f"-{k}", str(v)])
    base_cmd.append(output_path)
    
    t1 = time.time()
    try:
        _run_ffmpeg_with_fallback(base_cmd, filter_complex, start_sec, end_sec, input_path, output_path)
    except Exception as e:
        raise RuntimeError(f"Erro ao renderizar clipe: {str(e)}")
        
    return time.time() - t1


def re_render_clip(input_clean_path: str, output_path: str, srt_path: str, style_name: str, add_subtitles: bool = True, quality: str = "1080p", aspect_ratio: str = "9:16") -> float:
    t1 = time.time()
    
    # Mapeamento de estilos (cores em formato BGR do ASS script: &Hbbggrr&)
    colors = {
        "Yellow": "&H0000FFFF&",
        "Green": "&H0000FF00&",
        "White": "&H00FFFFFF&"
    }
    color_code = colors.get(style_name, "&H0000FFFF&")
    
    srt_escaped = escape_ffmpeg_path(srt_path)
    sub_style = f"FontName=Montserrat,FontSize=20,PrimaryColour={color_code},Alignment=2,Bold=1,MarginV=15,Outline=2,Shadow=1"
    
    # Optional scaling down if clean video is 1080p but requested 720p
    scale_filter = ""
    if quality == "720p":
        if aspect_ratio == "16:9":
            scale_filter = "scale=1280:720,"
        elif aspect_ratio == "1:1":
            scale_filter = "scale=720:720,"
        else:
            scale_filter = "scale=720:1280,"
        
    filter_complex = scale_filter
    if add_subtitles:
        filter_complex += f"subtitles='{srt_escaped}':force_style='{sub_style}'"
    else:
        if filter_complex.endswith(","): filter_complex = filter_complex[:-1]
        
    vf_arg = []
    if filter_complex:
        vf_arg = ["-vf", filter_complex]
    
    # Sempre usar -hide_banner -loglevel error em todos os paths
    cmd = _ffmpeg_base() + [
        "-i", input_clean_path,
        *vf_arg,
        "-c:a", "copy",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-threads", "1",
        output_path
    ]
    
    if is_nvenc_available():
        cmd = _ffmpeg_base() + [
            "-i", input_clean_path,
            *vf_arg,
            "-c:a", "copy",
            "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23", "-b:v", "6M",
            output_path
        ]
        
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if res.returncode != 0:
            if is_nvenc_available():
                fallback_cmd = _ffmpeg_base() + [
                    "-i", input_clean_path,
                    *vf_arg,
                    "-c:a", "copy",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-threads", "1",
                    output_path
                ]
                res2 = subprocess.run(fallback_cmd, capture_output=True, text=True, timeout=3600)
                if res2.returncode != 0:
                    raise RuntimeError(f"FFmpeg re-render (fallback) falhou:\n{res2.stderr[-1000:]}")
            else:
                raise RuntimeError(f"FFmpeg re-render falhou:\n{res.stderr[-1000:]}")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"Erro no re-render: {str(e)}")
        
    return time.time() - t1


def extract_and_crop_clip(source_path: str, output_path: str, srt_path: str, start_sec: float, end_sec: float, aspect_ratio: str, add_subtitles: bool, style_name: str, quality: str):
    orig_w, orig_h, _ = get_video_info(source_path)
    target_crop_w, target_crop_h, crop_x, crop_y, scale_w, scale_h = _compute_crop_and_scale(orig_w, orig_h, aspect_ratio, quality)

    filter_complex = f"[0:v]crop={target_crop_w}:{target_crop_h}:{crop_x}:{crop_y},scale={scale_w}:{scale_h}"

    has_valid_srt = bool(srt_path and os.path.exists(srt_path) and os.path.getsize(srt_path) > 0)
    if add_subtitles and has_valid_srt:
        colors = {"Yellow": "&H0000FFFF&", "Green": "&H0000FF00&", "White": "&H00FFFFFF&"}
        color_code = colors.get(style_name, "&H0000FFFF&")
        srt_escaped = escape_ffmpeg_path(srt_path)
        sub_style = f"FontName=Montserrat,FontSize=20,PrimaryColour={color_code},Alignment=2,Bold=1,MarginV=15,Outline=2,Shadow=1"
        filter_complex += f",subtitles='{srt_escaped}':force_style='{sub_style}'"
    filter_complex += "[v]"
    
    encoding_params = get_encoding_params()
    base_cmd = _ffmpeg_base() + [
        "-ss", str(start_sec),
        "-to", str(end_sec),
        "-i", source_path,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "0:a",
    ]
    for k, v in encoding_params.items():
        base_cmd.extend([f"-{k}", str(v)])
    base_cmd.append(output_path)
    
    try:
        _run_ffmpeg_with_fallback(base_cmd, filter_complex, start_sec, end_sec, source_path, output_path)
    except Exception as e:
        raise RuntimeError(f"Erro no extract_and_crop: {str(e)}")
