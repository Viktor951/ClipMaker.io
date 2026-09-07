import time
import gc
import logging
import os
import json
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

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
        
        segments_gen, info = model.transcribe(
            input_path, 
            word_timestamps=True, 
            language=language,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )
        
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

def format_transcript_from_segments(segments: list) -> str:
    """Formata os segmentos gerados pelo Whisper em um texto estruturado para o LLM."""
    transcript = []
    for seg in segments:
        text = seg.text.strip()
        if text:
            transcript.append(f"[{seg.start:.1f}s - {seg.end:.1f}s] {text}")
    return "\n".join(transcript)

def get_viral_clips_from_llm(transcript_text: str, duration: float) -> list:
    """Envia o transcript para o Gemini e retorna a lista de clipes estruturada."""
    logger.info("Enviando transcrição para análise do LLM (Gemini)...")
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "COLOQUE_SUA_CHAVE_AQUI":
        logger.error("A chave GEMINI_API_KEY não foi encontrada no arquivo .env!")
        # Fallback de segurança para não quebrar a aplicação caso a chave falte
        return _fallback_clip_boundaries(duration)
        
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""Você é um Produtor Sênior de Vídeos Virais para TikTok, Reels e Shorts (como o OpusClip).
Sua missão é analisar a transcrição de um vídeo e extrair de 4 a 6 clipes ALTAMENTE VIRAIS.

REGRAS RÍGIDAS:
1. Cada clipe deve ter sentido semântico completo (narrativa com início, meio e fim).
2. A duração matemática (end_time - start_time) de cada clipe deve ser ESTRITAMENTE entre 60 e 90 segundos.
3. O 'start_time' deve iniciar imediatamente onde uma fala forte começa.
4. O 'end_time' deve ser após a conclusão do raciocínio.
5. Selecione ganchos incrivelmente chamativos para a primeira frase ('hook_text').
6. Retorne puramente um array de objetos JSON, sem formatação Markdown ao redor do JSON (nada de ```json).
7. Se o vídeo inteiro for menor que 60 segundos, retorne apenas 1 clipe do início ao fim.

O esquema JSON OBRIGATÓRIO por item:
{{
  "title": "Um título muito chamativo e polêmico",
  "start_time": 12.5,
  "end_time": 85.0,
  "viral_score": 95,
  "hook_text": "A primeira frase forte do clipe"
}}

TRANSCRIÇÃO DO VÍDEO:
{transcript_text}
"""
    
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json"
            )
        )
        
        clips = json.loads(response.text)
        
        # Converter para o formato (start, end, title, hook) esperado pelo engine
        clip_boundaries = []
        for c in clips:
            st = float(c.get("start_time", 0.0))
            en = float(c.get("end_time", duration))
            ti = c.get("title", "Clipe Viral")
            ho = c.get("hook_text", "")
            clip_boundaries.append((st, en, ti, ho))
            
        logger.info(f"{len(clip_boundaries)} clipe(s) retornado(s) pelo LLM.")
        return clip_boundaries
        
    except Exception as e:
        logger.error(f"Erro ao processar LLM: {str(e)}")
        return _fallback_clip_boundaries(duration)

def _fallback_clip_boundaries(duration: float) -> list:
    """Fallback matemático caso a API do Gemini falhe."""
    clip_boundaries = []
    clip_duration = 75.0 
    if duration <= clip_duration:
        clip_boundaries.append((0.0, duration, "Clipe Inicial", "Gancho padrão"))
    else:
        num_clips = min(int(duration // clip_duration) or 1, 6)
        step = (duration - clip_duration) / max(1, num_clips - 1) if num_clips > 1 else 0
        for i in range(num_clips):
            start = i * step
            end = min(start + clip_duration, duration)
            clip_boundaries.append((start, end, f"Momento {i+1}", "Análise primária"))
    return clip_boundaries
