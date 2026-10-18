import time
import gc
import logging
import os
import json
from dotenv import load_dotenv

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
            logger.warning("[AVISO] Rodando Whisper em CPU - isso pode ser mais lento.")
            return "cpu", "int8"
    except ImportError:
        logger.warning("[AVISO] Rodando Whisper em CPU (PyTorch nao instalado).")
        return "cpu", "int8"

def transcribe_audio(input_path: str, language: str = "pt") -> list:
    """
    Transcreve o áudio do vídeo usando Whisper.
    Auto-detecta CUDA/CPU e garante limpeza de VRAM.
    
    Retorna os segmentos como lista de dicts leves (não objetos Whisper),
    para permitir liberação imediata do modelo e seus buffers internos.
    """
    device, compute_type = _detect_device()
    logger.info(f"Transcrevendo áudio (Whisper tiny, device={device}, compute={compute_type})...")
    t0 = time.time()
    lightweight_segments = []
    model = None
    
    try:
        from faster_whisper import WhisperModel
        
        logger.info("Carregando modelo Whisper tiny...")
        cpu_threads = min(4, max(2, (os.cpu_count() or 2) // 2))
        model = WhisperModel("tiny", device=device, compute_type="int8", cpu_threads=cpu_threads)
        logger.info(f"Modelo carregado ({cpu_threads} cpu threads). Iniciando transcrição...")
        
        segments_gen, info = model.transcribe(
            input_path, 
            word_timestamps=True, 
            language=language,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500)
        )
        
        # Converter generator em lista de dicts leves imediatamente.
        # Isso permite que os objetos internos do Whisper sejam liberados com o modelo.
        for seg in segments_gen:
            seg_dict = {
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
                "words": []
            }
            if hasattr(seg, 'words') and seg.words:
                for w in seg.words:
                    seg_dict["words"].append({
                        "word": w.word,
                        "start": w.start,
                        "end": w.end
                    })
            lightweight_segments.append(seg_dict)
        
        elapsed = time.time() - t0
        logger.info(f"Transcrição concluída em {elapsed:.1f}s ({len(lightweight_segments)} segmentos)")
        
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
            
    return lightweight_segments

def format_transcript_from_segments(segments: list) -> str:
    """Formata os segmentos em um texto estruturado para o LLM."""
    parts = []
    for seg in segments:
        text = seg["text"].strip() if isinstance(seg, dict) else seg.text.strip()
        if text:
            start = seg["start"] if isinstance(seg, dict) else seg.start
            end = seg["end"] if isinstance(seg, dict) else seg.end
            parts.append(f"[{start:.1f}s - {end:.1f}s] {text}")
    return "\n".join(parts)

_LAST_LLM_META = {
    "model": None,
    "attempts": 0,
    "had_429": False,
    "source": "none"
}

def get_last_llm_meta() -> dict:
    """Retorna os metadados da última execução do LLM para auditoria e benchmark."""
    return dict(_LAST_LLM_META)

def get_viral_clips_from_llm(transcript_text: str, duration: float) -> list:
    """Envia o transcript para o Gemini e retorna a lista de clipes estruturada."""
    global _LAST_LLM_META
    _LAST_LLM_META = {
        "model": None,
        "attempts": 0,
        "had_429": False,
        "source": "fallback"
    }
    
    logger.info("Enviando transcrição para análise do LLM (Gemini)...")
    
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "COLOQUE_SUA_CHAVE_AQUI":
        logger.error("A chave GEMINI_API_KEY não foi encontrada no arquivo .env!")
        logger.info("LLM RESULTADO: modelo=None, tentativas=0, 429=False, fonte=fallback_matematico (sem api_key)")
        return _fallback_clip_boundaries(duration)
    
    # Lazy import — evita carregar gRPC/protobuf na RAM se não for necessário
    import google.generativeai as genai
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
    
    # Modelos disponíveis e verificados com a chave PRO
    models_to_try = ["gemini-3.8-flash", "gemini-flash-latest", "gemini-pro-latest"]
    total_attempts = 0
    had_429 = False
    
    for model_name in models_to_try:
        for attempt in range(3):
            total_attempts += 1
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
                logger.debug(f"Resposta do Gemini ({model_name}): {raw_json[:300]}...")
                
                clips = json.loads(raw_json)
                
                clip_boundaries = []
                for c in clips:
                    st = float(c.get("start_time", 0.0))
                    en = float(c.get("end_time", duration))
                    ti = c.get("title", "Clipe Viral")
                    ho = c.get("hook_text", "")
                    try:
                        vs = int(c.get("viral_score", 85))
                    except (ValueError, TypeError):
                        vs = 85
                    vs = max(0, min(100, vs))
                    clip_boundaries.append({
                        "start": st,
                        "end": en,
                        "title": ti,
                        "hook": ho,
                        "viral_score": vs
                    })
                    
                _LAST_LLM_META = {
                    "model": model_name,
                    "attempts": total_attempts,
                    "had_429": had_429,
                    "source": "gemini"
                }
                logger.info(
                    f"LLM RESULTADO: modelo={model_name}, tentativas={total_attempts}, "
                    f"429={had_429}, fonte=Gemini ({len(clip_boundaries)} clipes gerados)"
                )
                return clip_boundaries
                
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "quota" in err_str.lower() or "resourceexhausted" in err_str.lower():
                    had_429 = True
                    logger.warning(f"LLM 429 Quota Exceeded com {model_name} (tentativa {attempt+1}/3)")
                else:
                    logger.warning(f"Tentativa {attempt+1} falhou com {model_name}: {err_str[:100]}")
                
                if "503" in err_str or "UNAVAILABLE" in err_str or "overloaded" in err_str.lower():
                    wait_time = (attempt + 1) * 10
                    logger.info(f"API sobrecarregada. Aguardando {wait_time}s antes de nova tentativa...")
                    time.sleep(wait_time)
                    continue
                
                if "404" in err_str or "NOT_FOUND" in err_str:
                    logger.warning(f"Modelo {model_name} não disponível. Tentando próximo...")
                    break
                    
                time.sleep(5)
    
    _LAST_LLM_META = {
        "model": "nenhum (todos falharam)",
        "attempts": total_attempts,
        "had_429": had_429,
        "source": "fallback_matematico"
    }
    logger.error(
        f"LLM RESULTADO: modelo=nenhum, tentativas={total_attempts}, "
        f"429={had_429}, fonte=fallback_matematico (acionado após esgotar retentativas)"
    )
    return _fallback_clip_boundaries(duration)

def _fallback_clip_boundaries(duration: float) -> list:
    """Fallback matemático caso a API do Gemini falhe."""
    logger.warning("Usando fallback matemático para gerar cortes.")
    clip_boundaries = []
    clip_duration = 75.0
    if duration <= clip_duration:
        clip_boundaries.append({
            "start": 0.0,
            "end": duration,
            "title": "Clipe Completo",
            "hook": "Gancho inicial",
            "viral_score": 85
        })
    else:
        num_clips = min(int(duration // clip_duration) or 1, 6)
        step = (duration - clip_duration) / max(1, num_clips - 1) if num_clips > 1 else 0
        for i in range(num_clips):
            start = i * step
            end = min(start + clip_duration, duration)
            score = max(50, 95 - i * 8)
            clip_boundaries.append({
                "start": start,
                "end": end,
                "title": f"Momento {i+1}",
                "hook": "Trecho relevante",
                "viral_score": score
            })
    return clip_boundaries
