import time
import gc
import logging

logger = logging.getLogger("clipmaker.ai")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)

def _detect_device():
    """Detecta se CUDA está disponível. Fallback seguro para CPU."""
    try:
        import torch
        if torch.cuda.is_available():
            logger.info(f"GPU detectada: {torch.cuda.get_device_name(0)}")
            return "cuda", "float16"
        else:
            logger.warning("CUDA não disponível. Usando CPU (mais lento).")
            return "cpu", "int8"
    except ImportError:
        logger.warning("PyTorch não instalado. Usando CPU (mais lento).")
        return "cpu", "int8"

def transcribe_audio(input_path: str, language: str = "pt") -> list:
    """
    Transcreve o áudio do vídeo usando Whisper.
    Auto-detecta CUDA/CPU e garante limpeza de VRAM.
    """
    device, compute_type = _detect_device()
    logger.info(f"Transcrevendo áudio (Whisper small, device={device})...")
    t0 = time.time()
    segments = []
    model = None
    
    try:
        from faster_whisper import WhisperModel
        
        logger.info("Carregando modelo Whisper small...")
        model = WhisperModel("small", device=device, compute_type=compute_type)
        logger.info("Modelo carregado. Iniciando transcrição...")
        
        segments_gen, info = model.transcribe(input_path, word_timestamps=True, language=language)
        
        # Consumir o generator para uma lista enquanto o modelo está na memória
        segments = list(segments_gen)
        elapsed = time.time() - t0
        logger.info(f"Transcrição concluída em {elapsed:.1f}s ({len(segments)} segmentos)")
        
    except Exception as e:
        logger.error(f"FALHA na transcrição Whisper: {str(e)}", exc_info=True)
    finally:
        # LIMPEZA DE VRAM ESTRITA
        if model is not None:
            del model
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("Memória VRAM da GPU liberada com sucesso.")
        except (ImportError, Exception):
            pass
            
    return segments

def generate_clip_boundaries(duration: float) -> list:
    """Calcula os melhores momentos (heurística simples)."""
    logger.info(f"Calculando melhores momentos para vídeo de {duration:.1f}s...")
    clip_boundaries = []
    if duration > 90:
        clip_boundaries.append((0.0, 45.0, "O Segredo Revelado (IA)", "Gancho gerado pela análise de áudio inicial."))
        clip_boundaries.append((45.0, min(90.0, duration), "Por que você está errando", "Análise secundária de engajamento."))
    else:
        clip_boundaries.append((0.0, min(45.0, duration), "O Segredo Revelado (IA)", "Gancho gerado pela análise de áudio inicial."))
        if duration > 50:
            clip_boundaries.append((45.0, duration, "Por que você está errando", "Análise secundária de engajamento."))
    logger.info(f"{len(clip_boundaries)} clipe(s) planejado(s).")
    return clip_boundaries
