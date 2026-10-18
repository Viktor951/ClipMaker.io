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

def get_cgroup_cpu_limit() -> float:
    """Retorna a cota real de CPU do cgroup v2 (/sys/fs/cgroup/cpu.max) ou os.cpu_count()."""
    try:
        cpu_max_path = "/sys/fs/cgroup/cpu.max"
        if os.path.exists(cpu_max_path):
            with open(cpu_max_path, "r") as f:
                parts = f.read().strip().split()
                if len(parts) >= 2 and parts[0] != "max":
                    quota = float(parts[0])
                    period = float(parts[1])
                    if period > 0:
                        return max(1.0, quota / period)
    except Exception:
        pass
    return float(os.cpu_count() or 2)

def _get_optimal_cpu_threads(parallelism: int = 1) -> str:
    """Calcula threads por processo FFmpeg dividindo a cota real de CPU pela concorrência."""
    cpu_limit = int(get_cgroup_cpu_limit())
    threads = max(1, cpu_limit // max(1, parallelism))
    return str(min(4, threads))

def get_encoding_params(parallelism: int = 1) -> dict:
    """Retorna parâmetros de encoding otimizados para velocidade e uso equilibrado de recursos."""
    crf = os.getenv("FFMPEG_CRF", "23")
    if is_nvenc_available():
        preset = os.getenv("FFMPEG_PRESET", "p4")
        return {
            "vcodec": "h264_nvenc",
            "preset": preset,
            "rc": "vbr",
            "cq": crf,
            "b:v": "6M",
            "maxrate": "10M",
            "acodec": "aac",
            "b:a": "128k",
            "threads": _get_optimal_cpu_threads(parallelism),
            "movflags": "+faststart",
        }
    else:
        # Padrão ultrafast em CPU (não trocar para veryfast)
        preset = os.getenv("FFMPEG_PRESET", "ultrafast")
        return {
            "vcodec": "libx264",
            "preset": preset,
            "crf": crf,
            "acodec": "aac",
            "b:a": "128k",
            "threads": _get_optimal_cpu_threads(parallelism),
            "movflags": "+faststart",
        }

def _get_fallback_cpu_params(parallelism: int = 1) -> dict:
    """Parâmetros de fallback em CPU com multithreading equilibrado."""
    preset = os.getenv("FFMPEG_PRESET", "ultrafast")
    crf = os.getenv("FFMPEG_CRF", "23")
    return {
        "vcodec": "libx264",
        "preset": preset,
        "crf": crf,
        "acodec": "aac",
        "b:a": "128k",
        "threads": _get_optimal_cpu_threads(parallelism),
        "movflags": "+faststart",
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

def _find_face_cascade_path() -> str:
    """Procura o XML de Haar cascade em caminhos padrão do OpenCV e locais do projeto."""
    candidates = []
    if hasattr(cv2, 'data') and hasattr(cv2.data, 'haarcascades'):
        candidates.append(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    candidates.append(os.path.join(os.path.dirname(__file__), 'haarcascade_frontalface_default.xml'))
    candidates.append('/opt/venv/lib/python3.11/site-packages/cv2/data/haarcascade_frontalface_default.xml')
    for p in candidates:
        if p and os.path.exists(p):
            return p
    return ""

def calculate_smooth_face_center(video_path: str, start_sec: float, end_sec: float, alpha: float = 0.15) -> int:
    """
    Detecta o centro do rosto predominante no trecho de vídeo de forma leve:
    - Abre o vídeo fonte diretamente com cv2.VideoCapture (sem sub-clipe temporário e sem ffmpeg)
    - Posiciona no início com CAP_PROP_POS_MSEC
    - Amostra ~2 frames por segundo ao longo de TODO o trecho usando grab() para pular frames sem decodificar
    - Reduz cada frame amostrado para ~320px de largura antes da detecção Haar
    - Suaviza o resultado com média móvel exponencial
    - Fallback dinâmico para a metade da largura real do vídeo (total_width // 2)
    """
    cascade_path = _find_face_cascade_path()
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.warning(f"Não foi possível abrir o vídeo {video_path} para face tracking. Usando centro 960.")
        return 960

    total_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920)
    total_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1080)
    fallback_center_x = total_width // 2

    if not cascade_path or not hasattr(cv2, 'CascadeClassifier'):
        cap.release()
        logger.info(f"Face tracking: Haar cascade indisponível. Usando centro padrão ({fallback_center_x}).")
        return fallback_center_x

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    start_ms = max(0.0, float(start_sec)) * 1000.0
    cap.set(cv2.CAP_PROP_POS_MSEC, start_ms)

    clip_duration = max(1.0, float(end_sec) - float(start_sec))
    total_clip_frames = int(clip_duration * fps)

    # Amostrar ~2 frames por segundo (ex: a cada 15 frames em vídeo de 30fps)
    sample_interval = max(1, int(round(fps / 2.0)))
    target_process_width = 320
    scale_factor = target_process_width / total_width if total_width > target_process_width else 1.0

    current_center_x = fallback_center_x
    smoothed_center_x = float(current_center_x)
    frames_processed = 0
    frames_sampled = 0
    faces_found = 0

    face_cascade = cv2.CascadeClassifier(cascade_path)

    try:
        current_frame = 0
        while current_frame < total_clip_frames:
            if current_frame % sample_interval == 0:
                grabbed = cap.grab()
                if not grabbed:
                    break
                ret, frame = cap.retrieve()
                if not ret or frame is None:
                    break

                frames_sampled += 1
                if scale_factor < 1.0:
                    small_frame = cv2.resize(frame, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_AREA)
                else:
                    small_frame = frame

                gray = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(20, 20))

                if len(faces) > 0:
                    largest_face = max(faces, key=lambda rect: rect[2] * rect[3])
                    x, y, w, h = largest_face
                    real_center_x = (x + w // 2) / scale_factor
                    smoothed_center_x = alpha * real_center_x + (1.0 - alpha) * smoothed_center_x
                    faces_found += 1

                del gray, faces
                if scale_factor < 1.0:
                    del small_frame
                del frame
            else:
                # Pula frames rapidamente sem decodificar na CPU
                if not cap.grab():
                    break

            current_frame += 1
            frames_processed += 1

            if frames_sampled % 50 == 0:
                gc.collect()

    except Exception as e:
        logger.warning(f"Erro durante face tracking direto: {e}")
    finally:
        cap.release()
        del cap
        del face_cascade
        gc.collect()

    detection_rate = (faces_found / frames_sampled * 100.0) if frames_sampled > 0 else 0.0
    target_crop_w = int(total_height * 9 / 16) if total_height else 608
    target_crop_w -= (target_crop_w % 2)
    final_crop_x = max(0, min(int(smoothed_center_x) - (target_crop_w // 2), total_width - target_crop_w))

    logger.info(
        f"Face tracking concluído: {frames_sampled} frames amostrados (de {frames_processed} analisados), "
        f"{faces_found} detecções (taxa de detecção: {detection_rate:.1f}%), "
        f"crop_x final={final_crop_x} (center_x={int(smoothed_center_x)})."
    )
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

def _run_ffmpeg_with_fallback(primary_cmd: list, filter_complex: str, start_sec: float, end_sec: float, input_path: str, output_path: str, parallelism: int = 1):
    """Executa FFmpeg com fallback automático para CPU se NVENC falhar."""
    result = subprocess.run(primary_cmd, capture_output=True, text=True, timeout=3600)

    if result.returncode != 0:
        encoding_params = get_encoding_params(parallelism)
        if encoding_params.get("vcodec") == "h264_nvenc":
            logger.warning("NVENC falhou, desativando NVENC e utilizando CPU com múltiplas threads...")
            global _NVENC_AVAILABLE
            _NVENC_AVAILABLE = False
            cpu_params = _get_fallback_cpu_params(parallelism)
            fallback_cmd = _ffmpeg_base() + [
                "-ss", str(start_sec),
                "-to", str(end_sec),
                "-i", input_path,
                "-filter_complex", filter_complex,
                "-map", "[v]",
                "-map", "0:a?",
            ]
            for k, v in cpu_params.items():
                fallback_cmd.extend([f"-{k}", str(v)])
            fallback_cmd.append(output_path)
            
            result_cpu = subprocess.run(fallback_cmd, capture_output=True, text=True, timeout=3600)
            if result_cpu.returncode != 0:
                raise RuntimeError(f"FFmpeg falhou com CPU. Erro:\n{result_cpu.stderr[-1000:]}")
        else:
            raise RuntimeError(f"FFmpeg falhou. Erro:\n{result.stderr[-1000:]}")


def render_clip(
    input_path: str,
    output_path: str,
    srt_path: str,
    start_sec: float,
    end_sec: float,
    orig_w: int,
    orig_h: int,
    face_center_x: int,
    has_subtitles: bool,
    aspect_ratio: str = "9:16",
    style_name: str = "Yellow",
    parallelism: int = 1
) -> float:
    """Renderiza o clipe final em UM ÚNICO PASSE (crop + scale + legendas integrados)."""
    target_crop_w, target_crop_h, crop_x, crop_y, scale_w, scale_h = _compute_crop_and_scale(orig_w, orig_h, aspect_ratio)

    # Ajustar crop_x baseado no face tracking para 9:16
    if aspect_ratio == "9:16" and face_center_x is not None:
        crop_x = face_center_x - (target_crop_w // 2)
        crop_x = max(0, min(crop_x, orig_w - target_crop_w))

    encoding_params = get_encoding_params(parallelism)
    srt_escaped = escape_ffmpeg_path(srt_path) if srt_path else ""
    colors = {
        "Yellow": "&H0000FFFF&",
        "Green": "&H0000FF00&",
        "White": "&H00FFFFFF&"
    }
    color_code = colors.get(style_name, "&H0000FFFF&")
    sub_style = f"FontName=Montserrat,FontSize=20,PrimaryColour={color_code},Alignment=2,Bold=1,MarginV=15,Outline=2,Shadow=1"

    filter_complex = f"[0:v]crop={target_crop_w}:{target_crop_h}:{crop_x}:{crop_y},scale={scale_w}:{scale_h}"
    if has_subtitles and srt_escaped and os.path.exists(srt_path) and os.path.getsize(srt_path) > 0:
        filter_complex += f",subtitles='{srt_escaped}':force_style='{sub_style}'"
    filter_complex += "[v]"

    base_cmd = _ffmpeg_base() + [
        "-ss", str(start_sec),
        "-to", str(end_sec),
        "-i", input_path,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "0:a?",
    ]
    
    for k, v in encoding_params.items():
        base_cmd.extend([f"-{k}", str(v)])
    base_cmd.append(output_path)
    
    t1 = time.time()
    try:
        _run_ffmpeg_with_fallback(base_cmd, filter_complex, start_sec, end_sec, input_path, output_path, parallelism)
    except Exception as e:
        raise RuntimeError(f"Erro ao renderizar clipe: {str(e)}")
        
    return time.time() - t1


def re_render_clip(
    input_clean_path: str,
    output_path: str,
    srt_path: str,
    style_name: str,
    add_subtitles: bool = True,
    quality: str = "1080p",
    aspect_ratio: str = "9:16",
    parallelism: int = 1
) -> float:
    t1 = time.time()
    
    colors = {
        "Yellow": "&H0000FFFF&",
        "Green": "&H0000FF00&",
        "White": "&H00FFFFFF&"
    }
    color_code = colors.get(style_name, "&H0000FFFF&")
    
    srt_escaped = escape_ffmpeg_path(srt_path) if srt_path else ""
    sub_style = f"FontName=Montserrat,FontSize=20,PrimaryColour={color_code},Alignment=2,Bold=1,MarginV=15,Outline=2,Shadow=1"
    
    scale_filter = ""
    if quality == "720p":
        if aspect_ratio == "16:9":
            scale_filter = "scale=1280:720,"
        elif aspect_ratio == "1:1":
            scale_filter = "scale=720:720,"
        else:
            scale_filter = "scale=720:1280,"
        
    filter_complex = scale_filter
    has_valid_srt = bool(srt_path and os.path.exists(srt_path) and os.path.getsize(srt_path) > 0)
    if add_subtitles and has_valid_srt:
        filter_complex += f"subtitles='{srt_escaped}':force_style='{sub_style}'"
    else:
        if filter_complex.endswith(","): filter_complex = filter_complex[:-1]
        
    vf_arg = []
    if filter_complex:
        vf_arg = ["-vf", filter_complex]
    
    encoding_params = get_encoding_params(parallelism)
    cmd = _ffmpeg_base() + [
        "-i", input_clean_path,
        *vf_arg,
        "-map", "0:v",
        "-map", "0:a?",
        "-c:a", "copy",
        "-c:v", encoding_params.get("vcodec", "libx264"),
        "-preset", encoding_params.get("preset", "ultrafast"),
        "-movflags", "+faststart",
    ]
    if encoding_params.get("vcodec") == "h264_nvenc":
        cmd.extend(["-cq", encoding_params.get("cq", "23"), "-b:v", "6M"])
    else:
        cmd.extend(["-crf", encoding_params.get("crf", "23"), "-threads", _get_optimal_cpu_threads(parallelism)])
    cmd.append(output_path)
    
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if res.returncode != 0:
            if is_nvenc_available():
                fallback_cmd = _ffmpeg_base() + [
                    "-i", input_clean_path,
                    *vf_arg,
                    "-map", "0:v",
                    "-map", "0:a?",
                    "-c:a", "copy",
                    "-c:v", "libx264",
                    "-preset", os.getenv("FFMPEG_PRESET", "ultrafast"),
                    "-crf", os.getenv("FFMPEG_CRF", "23"),
                    "-movflags", "+faststart",
                    "-threads", _get_optimal_cpu_threads(parallelism),
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


def extract_and_crop_clip(
    source_path: str,
    output_path: str,
    srt_path: str,
    start_sec: float,
    end_sec: float,
    aspect_ratio: str = "9:16",
    add_subtitles: bool = True,
    style_name: str = "Yellow",
    quality: str = "1080p",
    face_center_x: int = None,
    parallelism: int = 1
):
    """Extrai, corta, enquadra e legenda o clipe em um único passe a partir do vídeo fonte."""
    orig_w, orig_h, _ = get_video_info(source_path)
    target_crop_w, target_crop_h, crop_x, crop_y, scale_w, scale_h = _compute_crop_and_scale(orig_w, orig_h, aspect_ratio, quality)

    if aspect_ratio == "9:16" and face_center_x is not None:
        crop_x = face_center_x - (target_crop_w // 2)
        crop_x = max(0, min(crop_x, orig_w - target_crop_w))

    filter_complex = f"[0:v]crop={target_crop_w}:{target_crop_h}:{crop_x}:{crop_y},scale={scale_w}:{scale_h}"

    has_valid_srt = bool(srt_path and os.path.exists(srt_path) and os.path.getsize(srt_path) > 0)
    if add_subtitles and has_valid_srt:
        colors = {"Yellow": "&H0000FFFF&", "Green": "&H0000FF00&", "White": "&H00FFFFFF&"}
        color_code = colors.get(style_name, "&H0000FFFF&")
        srt_escaped = escape_ffmpeg_path(srt_path)
        sub_style = f"FontName=Montserrat,FontSize=20,PrimaryColour={color_code},Alignment=2,Bold=1,MarginV=15,Outline=2,Shadow=1"
        filter_complex += f",subtitles='{srt_escaped}':force_style='{sub_style}'"
    filter_complex += "[v]"
    
    encoding_params = get_encoding_params(parallelism)
    base_cmd = _ffmpeg_base() + [
        "-ss", str(start_sec),
        "-to", str(end_sec),
        "-i", source_path,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "0:a?",
    ]
    for k, v in encoding_params.items():
        base_cmd.extend([f"-{k}", str(v)])
    base_cmd.append(output_path)
    
    try:
        _run_ffmpeg_with_fallback(base_cmd, filter_complex, start_sec, end_sec, source_path, output_path, parallelism)
    except Exception as e:
        raise RuntimeError(f"Erro no extract_and_crop: {str(e)}")


def generate_thumbnail(video_path: str, timestamp_sec: float, output_thumb_path: str) -> str:
    """Extrai um frame real do vídeo com ffmpeg (~1s), redimensionado para ~480px."""
    safe_time = max(0.0, float(timestamp_sec))
    cmd = _ffmpeg_base() + [
        "-ss", str(safe_time),
        "-i", video_path,
        "-vframes", "1",
        "-vf", "scale='min(480,iw)':-1",
        "-q:v", "3",
        output_thumb_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if res.returncode != 0 or not os.path.exists(output_thumb_path) or os.path.getsize(output_thumb_path) == 0:
            fallback_cmd = _ffmpeg_base() + [
                "-ss", "0.0",
                "-i", video_path,
                "-vframes", "1",
                "-vf", "scale='min(480,iw)':-1",
                "-q:v", "3",
                output_thumb_path
            ]
            subprocess.run(fallback_cmd, capture_output=True, text=True, timeout=60)
    except Exception as e:
        logger.warning(f"Falha ao gerar thumbnail: {e}")
    return output_thumb_path
