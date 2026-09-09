import time
import gc
import logging
import os
import json
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

TARGET_CLIPS_COUNT = 5
MIN_DURATION_SEC = 60
MAX_DURATION_SEC = 90

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
            logger.warning("⚠️ Rodando Whisper em CPU — isso pode ser MUITO mais lento. Verifique se o CUDA/torch com GPU está instalado corretamente.")
            return "cpu", "int8"
    except ImportError:
        logger.warning("⚠️ Rodando Whisper em CPU (PyTorch não instalado) — isso pode ser MUITO mais lento. Verifique se o CUDA/torch com GPU está instalado corretamente.")
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
        
        segments = list(segments_gen)
        elapsed = time.time() - t0
        logger.info(f"Transcrição concluída em {elapsed:.1f}s ({len(segments)} segmentos)")
        
    except Exception as e:
        logger.error(f"FALHA na transcrição Whisper: {str(e)}", exc_info=True)
        raise RuntimeError(f"FALHA na transcrição Whisper: {str(e)}")
    finally:
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
        return _fallback_clip_boundaries(duration)
    
    genai.configure(api_key=api_key)
    
    prompt = f"""Você é um Produtor Sênior de Vídeos Virais para TikTok, Reels e Shorts (como o OpusClip).
Sua missão é analisar a transcrição de um vídeo e extrair EXATAMENTE {TARGET_CLIPS_COUNT} clipes ALTAMENTE VIRAIS.

REGRAS RÍGIDAS:
1. Você deve retornar ESTRITAMENTE entre 4 e 6 cortes.
2. A duração matemática (end_time - start_time) de CADA clipe deve ser de no mínimo {MIN_DURATION_SEC} segundos e no máximo {MAX_DURATION_SEC} segundos. 
3. Priorize frases completas e raciocínios que façam sentido isoladamente (começo, meio e fim).
4. O 'start_time' deve iniciar imediatamente onde uma fala forte começa.
5. O 'end_time' deve ser após a conclusão do raciocínio.
6. Selecione ganchos incrivelmente chamativos para a primeira frase ('hook_text').
7. Retorne puramente um array de objetos JSON, sem formatação Markdown (nada de ```json).
8. Se o vídeo inteiro for muito curto, retorne o que for possível dentro das regras.

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
    
    # Tentar vários modelos em sequência caso um esteja indisponível
    models_to_try = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]
    
    for model_name in models_to_try:
        for attempt in range(3):  # Até 3 tentativas por modelo
            try:
                logger.info(f"Tentativa {attempt+1} com modelo: {model_name}")
                model = genai.GenerativeModel(model_name)
                
                response = model.generate_content(
                    prompt,
                    generation_config=genai.GenerationConfig(
                        response_mime_type="application/json"
                    )
                )
                
                raw_json = response.text
                print(f"\n=== RESPOSTA DO GEMINI ({model_name}) ===")
                print(raw_json[:500])
                print("=================================\n")
                
                clips = json.loads(raw_json)
                
                clip_boundaries = []
                for c in clips:
                    st = float(c.get("start_time", 0.0))
                    en = float(c.get("end_time", duration))
                    ti = c.get("title", "Clipe Viral")
                    ho = c.get("hook_text", "")
                    clip_boundaries.append((st, en, ti, ho))
                    
                logger.info(f"{len(clip_boundaries)} clipe(s) retornado(s) pelo LLM ({model_name}).")
                return clip_boundaries
                
            except Exception as e:
                err_str = str(e)
                logger.warning(f"Tentativa {attempt+1} falhou com {model_name}: {err_str[:100]}")
                
                # Se for 503 (sobrecarga), esperar e tentar novamente
                if "503" in err_str or "UNAVAILABLE" in err_str or "overloaded" in err_str.lower():
                    wait_time = (attempt + 1) * 10
                    logger.info(f"API sobrecarregada. Aguardando {wait_time}s antes de nova tentativa...")
                    time.sleep(wait_time)
                    continue
                
                # Se for 404 (modelo não encontrado), tentar próximo modelo
                if "404" in err_str or "NOT_FOUND" in err_str:
                    logger.warning(f"Modelo {model_name} não disponível. Tentando próximo...")
                    break
                    
                # Outro erro: aguardar e tentar novamente
                time.sleep(5)
    
    # Todos os modelos falharam: usar fallback
    logger.error("Todos os modelos Gemini falharam. Usando fallback matemático.")
    return _fallback_clip_boundaries(duration)

def _fallback_clip_boundaries(duration: float) -> list:
    """Fallback matemático caso a API do Gemini falhe."""
    logger.warning("Usando fallback matemático para gerar cortes.")
    clip_boundaries = []
    clip_duration = 75.0
    if duration <= clip_duration:
        clip_boundaries.append((0.0, duration, "Clipe Completo", "Gancho inicial"))
    else:
        num_clips = min(int(duration // clip_duration) or 1, 6)
        step = (duration - clip_duration) / max(1, num_clips - 1) if num_clips > 1 else 0
        for i in range(num_clips):
            start = i * step
            end = min(start + clip_duration, duration)
            clip_boundaries.append((start, end, f"Momento {i+1}", "Trecho relevante"))
    return clip_boundaries
