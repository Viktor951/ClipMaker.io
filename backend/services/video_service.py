import os
import time
import subprocess
import logging
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

def get_encoding_params() -> dict:
    if is_nvenc_available():
        return {
            "vcodec": "h264_nvenc",
            "preset": "p4",
            "rc": "vbr",
            "cq": "23",
            "b:v": "5M",
            "maxrate": "8M",
            "acodec": "aac",
            "b:a": "128k",
            "threads": "0",
        }
    else:
        return {
            "vcodec": "libx264",
            "preset": "ultrafast",
            "crf": "23",
            "acodec": "aac",
            "b:a": "128k",
            "threads": "4",
        }

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

def calculate_smooth_face_center(video_path: str, start_sec: float, end_sec: float, alpha: float = 0.15, max_frames: int = 300) -> int:
    logger.info(f"Face tracking: {start_sec:.1f}s -> {end_sec:.1f}s (max {max_frames} frames)")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.warning("Não foi possível abrir o vídeo para face tracking. Usando centro padrão.")
        return 960

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    start_frame = int(start_sec * fps)
    end_frame = min(int(end_sec * fps), start_frame + max_frames)
    total_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    current_center_x = total_width // 2
    smoothed_center_x = float(current_center_x)
    frames_processed = 0
    faces_found = 0

    try:
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        if os.path.exists(cascade_path):
            face_cascade = cv2.CascadeClassifier(cascade_path)
            current_frame = start_frame
            while current_frame <= end_frame:
                ret, frame = cap.read()
                if not ret:
                    break
                if current_frame % 3 == 0:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60))
                    if len(faces) > 0:
                        largest_face = max(faces, key=lambda rect: rect[2] * rect[3])
                        x, y, w, h = largest_face
                        smoothed_center_x = alpha * (x + w // 2) + (1.0 - alpha) * smoothed_center_x
                        faces_found += 1
                frames_processed += 1
                current_frame += 1
        else:
            logger.warning("Haar cascade file não encontrado. Usando centro padrão.")
    except Exception as e:
        logger.warning(f"Erro no face tracking: {e}")
    finally:
        cap.release()

    logger.info(f"Face tracking concluído: {frames_processed} frames, {faces_found} detecções.")
    return int(smoothed_center_x)

def format_timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def generate_word_level_srt(segments, start_offset: float, end_offset: float, output_srt_path: str) -> list:
    words_ui = []
    try:
        with open(output_srt_path, "w", encoding="utf-8") as f:
            idx = 1
            for segment in segments:
                if not hasattr(segment, 'words') or segment.words is None:
                    continue
                for word in segment.words:
                    if word.end < start_offset:
                        continue
                    if word.start > end_offset:
                        break

                    s_clip = max(0, word.start - start_offset)
                    e_clip = max(0.1, word.end - start_offset)

                    f.write(f"{idx}\n")
                    f.write(f"{format_timestamp(s_clip)} --> {format_timestamp(e_clip)}\n")

                    text = word.word.strip().upper()
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

def escape_ffmpeg_path(path: str) -> str:
    escaped = os.path.abspath(path)
    escaped = escaped.replace("\\", "/")
    escaped = escaped.replace(":", "\\:")
    return escaped

def render_clip(input_path: str, output_path: str, srt_path: str, start_sec: float, end_sec: float, orig_w: int, orig_h: int, face_center_x: int, has_subtitles: bool) -> float:
    target_crop_h = orig_h
    target_crop_w = int(target_crop_h * (9 / 16))
    if target_crop_w > orig_w:
        target_crop_w = orig_w
        target_crop_h = int(target_crop_w * (16 / 9))

    target_crop_w = target_crop_w - (target_crop_w % 2)
    target_crop_h = target_crop_h - (target_crop_h % 2)

    crop_x = face_center_x - (target_crop_w // 2)
    crop_x = max(0, min(crop_x, orig_w - target_crop_w))
    crop_y = (orig_h - target_crop_h) // 2

    encoding_params = get_encoding_params()
    srt_escaped = escape_ffmpeg_path(srt_path)
    sub_style = "FontSize=20,PrimaryColour=&H0000FFFF&,Alignment=2,Bold=1,MarginV=15,Outline=2,Shadow=1"

    filter_complex = f"[0:v]crop={target_crop_w}:{target_crop_h}:{crop_x}:{crop_y},scale=1080:1920"
    if has_subtitles:
        filter_complex += f",subtitles='{srt_escaped}':force_style='{sub_style}'"
    filter_complex += "[v]"

    base_cmd = [
        "ffmpeg", "-y",
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
        result = subprocess.run(base_cmd, capture_output=True, text=True)

        if result.returncode != 0:
            if encoding_params.get("vcodec") == "h264_nvenc":
                cpu_params = {
                    "vcodec": "libx264",
                    "preset": "ultrafast",
                    "crf": "23",
                    "acodec": "aac",
                    "b:a": "128k",
                    "threads": "4",
                }
                fallback_cmd = [
                    "ffmpeg", "-y",
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
                
                result_cpu = subprocess.run(fallback_cmd, capture_output=True, text=True)
                
                if result_cpu.returncode != 0:
                    raise RuntimeError(f"FFmpeg falhou com CPU. Erro:\n{result_cpu.stderr[-1000:]}")
            else:
                raise RuntimeError(f"FFmpeg falhou. Erro:\n{result.stderr[-1000:]}")
    except Exception as e:
        raise RuntimeError(f"Erro ao renderizar clipe: {str(e)}")
        
    return time.time() - t1
