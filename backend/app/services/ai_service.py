import time
import gc
import logging
import os
import json
import re
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

# ============================================================
# Whisper — Gerenciamento de Modelo e Cache Global
# ============================================================

_WHISPER_CACHE = {
    "model": None,
    "model_name": None,
    "device": None,
    "compute_type": None,
    "last_used": 0.0,
}

def _detect_device() -> tuple:
    """Detecta se CUDA está disponível via ctranslate2. Fallback seguro para CPU."""
    try:
        import ctranslate2
        cuda_count = ctranslate2.get_cuda_device_count()
        if cuda_count > 0:
            logger.info(f"GPU detectada via CTranslate2 ({cuda_count} dispositivo(s) CUDA). Usando float16.")
            return "cuda", "float16"
        else:
            logger.info("Nenhuma GPU CUDA detectada via CTranslate2. Usando CPU (int8).")
            return "cpu", "int8"
    except Exception as e:
        logger.warning(f"[AVISO] Falha ao verificar CTranslate2 para CUDA ({e}). Rodando Whisper em CPU (int8).")
        return "cpu", "int8"

def _get_target_model_name(device: str) -> str:
    """Determina o nome do modelo Whisper com base na configuração e dispositivo."""
    configured = os.getenv("WHISPER_MODEL", "auto").strip().lower()
    if configured and configured != "auto":
        return configured
    return "small" if device == "cuda" else "base"

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


def get_whisper_model():
    """Retorna o modelo Whisper mantido em cache global, respeitando o timeout de ociosidade."""
    global _WHISPER_CACHE
    device, compute_type = _detect_device()
    target_model_name = _get_target_model_name(device)
    idle_timeout_sec = int(os.getenv("WHISPER_IDLE_TIMEOUT_MINUTES", "15")) * 60
    now = time.time()

    # Verificar se o cache existente expirou por inatividade ou se mudou de configuração
    if _WHISPER_CACHE["model"] is not None:
        is_idle_expired = (now - _WHISPER_CACHE["last_used"]) > idle_timeout_sec
        is_config_changed = (
            _WHISPER_CACHE["model_name"] != target_model_name
            or _WHISPER_CACHE["device"] != device
            or _WHISPER_CACHE["compute_type"] != compute_type
        )
        if is_idle_expired or is_config_changed:
            motivo = "tempo ocioso expirado" if is_idle_expired else "configuração alterada"
            logger.info(f"Descarregando modelo Whisper da memória ({motivo}).")
            del _WHISPER_CACHE["model"]
            _WHISPER_CACHE["model"] = None
            gc.collect()

    # Se não está em cache, carregar
    if _WHISPER_CACHE["model"] is None:
        from faster_whisper import WhisperModel
        cpu_threads = min(4, max(1, int(get_cgroup_cpu_limit())))
        logger.info(
            f"Carregando modelo Whisper '{target_model_name}' "
            f"(device={device}, compute_type={compute_type}, threads={cpu_threads if device == 'cpu' else 'GPU'})..."
        )
        download_root = os.getenv("HF_HOME")
        model = WhisperModel(
            target_model_name,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads if device == "cpu" else 0,
            download_root=download_root,
        )
        _WHISPER_CACHE["model"] = model
        _WHISPER_CACHE["model_name"] = target_model_name
        _WHISPER_CACHE["device"] = device
        _WHISPER_CACHE["compute_type"] = compute_type
        logger.info(f"Modelo Whisper '{target_model_name}' carregado e retido em cache global.")

    _WHISPER_CACHE["last_used"] = time.time()
    return _WHISPER_CACHE["model"]

def preload_whisper_model():
    """Pré-carrega o modelo Whisper na inicialização para evitar latência no primeiro job."""
    try:
        logger.info("Executando pré-carregamento do modelo Whisper...")
        get_whisper_model()
    except Exception as e:
        logger.warning(f"Não foi possível pré-carregar o modelo Whisper na inicialização: {e}")

def transcribe_audio(input_path: str, language: str = "pt") -> list:
    """
    Transcreve o áudio do vídeo usando o modelo Whisper em cache.
    Retorna os segmentos como lista de dicts leves.
    """
    t0 = time.time()
    lightweight_segments = []

    try:
        model = get_whisper_model()
        device = _WHISPER_CACHE["device"]
        model_name = _WHISPER_CACHE["model_name"]
        compute_type = _WHISPER_CACHE["compute_type"]

        logger.info(f"Iniciando transcrição de áudio (modelo='{model_name}', device={device}, compute={compute_type})...")
        segments_gen, info = model.transcribe(
            input_path,
            word_timestamps=True,
            language=language,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        for seg in segments_gen:
            seg_dict = {
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
                "words": [],
            }
            if hasattr(seg, "words") and seg.words:
                for w in seg.words:
                    seg_dict["words"].append({
                        "word": w.word,
                        "start": w.start,
                        "end": w.end,
                    })
            lightweight_segments.append(seg_dict)

        elapsed = time.time() - t0
        logger.info(f"Transcrição concluída em {elapsed:.1f}s ({len(lightweight_segments)} segmentos)")

    except Exception as e:
        logger.error(f"FALHA na transcrição Whisper: {str(e)}", exc_info=True)
        raise RuntimeError(f"FALHA na transcrição Whisper: {str(e)}")
    finally:
        gc.collect()

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

def _get_clip_target_and_durations(duration: float):
    """
    Calcula dinamicamente a quantidade de clipes e durações mínima/máxima coerentes com o vídeo.
    Evita que o LLM entre em loops de raciocínio com restrições contraditórias (ex: 5 clipes de 60s em vídeo de 20s).
    """
    if duration <= 30.0:
        target_count = 1
        min_dur = min(5.0, duration * 0.4)
        max_dur = duration
    elif duration <= 60.0:
        target_count = 2
        min_dur = 10.0
        max_dur = duration
    elif duration <= 120.0:
        target_count = 3
        min_dur = 20.0
        max_dur = min(60.0, duration)
    else:
        target_count = TARGET_CLIPS_COUNT
        min_dur = MIN_DURATION_SEC
        max_dur = MAX_DURATION_SEC
    return target_count, min_dur, max_dur


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
    
    target_count, min_dur, max_dur = _get_clip_target_and_durations(duration)

    prompt = f"""Você é um Produtor Sênior de Vídeos Virais para TikTok, Reels e Shorts (como o OpusClip).
Sua missão é analisar a transcrição de um vídeo de {duration:.1f} segundos e extrair EXATAMENTE {target_count} clipe(s) ALTAMENTE VIRAIS.

REGRAS RÍGIDAS:
1. Você deve retornar ESTRITAMENTE {target_count} corte(s).
2. A duração matemática (end_time - start_time) de CADA clipe deve ser de no mínimo {min_dur:.1f} segundos e no máximo {max_dur:.1f} segundos. 
3. Não crie clipes que ultrapassem {duration:.1f} segundos e garanta início e fim dentro dos limites do vídeo.
4. Priorize frases completas e raciocínios que façam sentido isoladamente (começo, meio e fim).
5. O 'start_time' deve iniciar imediatamente onde uma fala forte começa.
6. O 'end_time' deve ser após a conclusão do raciocínio.
7. Selecione ganchos incrivelmente chamativos para a primeira frase ('hook_text').
8. Retorne puramente um array de objetos JSON, sem formatação Markdown (nada de ```json).

O esquema JSON OBRIGATÓRIO por item:
{{
  "title": "Um título muito chamativo e polêmico",
  "start_time": 0.0,
  "end_time": {max_dur:.1f},
  "viral_score": 95,
  "hook_text": "A primeira frase forte do clipe"
}}

TRANSCRIÇÃO DO VÍDEO:
{transcript_text}
"""
    
    # Modelos configuráveis via variável de ambiente GEMINI_MODELS
    raw_models = os.getenv("GEMINI_MODELS", "gemini-3.8-flash,gemini-flash-latest,gemini-pro-latest")
    models_to_try = [m.strip() for m in raw_models.split(",") if m.strip()]
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
                if not isinstance(clips, list) or len(clips) == 0:
                    logger.warning(f"Resposta vazia ou inválida do Gemini ({model_name}).")
                    break
                
                clip_boundaries = []
                for c in clips:
                    st = max(0.0, float(c.get("start_time", 0.0)))
                    en = min(duration, float(c.get("end_time", duration)))
                    if en <= st:
                        en = min(duration, st + min_dur)
                    if en <= st:
                        continue
                    ti = c.get("title", "Clipe Viral")
                    ho = c.get("hook_text", "")
                    try:
                        vs = int(c.get("viral_score", 85))
                    except (ValueError, TypeError):
                        vs = 85
                    vs = max(0, min(100, vs))
                    clip_boundaries.append({
                        "start": round(st, 2),
                        "end": round(en, 2),
                        "title": ti,
                        "hook": ho,
                        "viral_score": vs
                    })
                
                if len(clip_boundaries) == 0:
                    logger.warning("Nenhum corte válido após sanitização dos dados do Gemini.")
                    break

                _LAST_LLM_META = {
                    "model": model_name,
                    "attempts": total_attempts,
                    "had_429": had_429,
                    "source": "gemini",
                    "ai_cuts_fallback": False
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
                    logger.warning(f"LLM 429 Quota Exceeded com modelo '{model_name}'.")
                    delay_match = re.search(r"retry.*?(\d+(?:\.\d+)?)\s*s", err_str, re.IGNORECASE)
                    retry_delay = float(delay_match.group(1)) if delay_match else 0.0
                    if 0.0 < retry_delay < 10.0:
                        logger.info(f"Retry-delay viável detectado ({retry_delay:.1f}s < 10s). Aguardando {retry_delay:.1f}s...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        logger.warning(f"Sem retry-delay menor que 10s para {model_name}. NÃO tentando novamente este modelo. Avançando para o próximo...")
                        break
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
                    
                time.sleep(3)
    
    _LAST_LLM_META = {
        "model": "nenhum (todos falharam)",
        "attempts": total_attempts,
        "had_429": had_429,
        "source": "fallback_matematico",
        "ai_cuts_fallback": True
    }
    logger.error(
        f"LLM RESULTADO: modelo=nenhum, tentativas={total_attempts}, "
        f"429={had_429}, fonte=fallback_matematico (acionado após esgotar modelos)"
    )
    return _fallback_clip_boundaries(duration)


def _fallback_clip_boundaries(duration: float) -> list:
    """Fallback matemático caso a API do Gemini falhe."""
    logger.warning("Usando fallback matemático para gerar cortes.")
    clip_boundaries = []
    if duration <= 45.0:
        clip_boundaries.append({
            "start": 0.0,
            "end": duration,
            "title": "Destaque Principal",
            "hook": "Melhor momento do vídeo",
            "viral_score": 90
        })
    elif duration <= 90.0:
        half = round(duration / 2.0, 1)
        clip_boundaries.append({
            "start": 0.0,
            "end": half,
            "title": "Parte 1 - Momento Viral",
            "hook": "Gancho inicial",
            "viral_score": 92
        })
        clip_boundaries.append({
            "start": half,
            "end": duration,
            "title": "Parte 2 - Conclusão",
            "hook": "Desfecho impactante",
            "viral_score": 88
        })
    else:
        clip_duration = min(75.0, duration / 3.0)
        num_clips = min(int(duration // clip_duration) or 1, 5)
        step = (duration - clip_duration) / max(1, num_clips - 1) if num_clips > 1 else 0
        for i in range(num_clips):
            start = round(i * step, 1)
            end = min(round(start + clip_duration, 1), duration)
            score = max(50, 95 - i * 5)
            clip_boundaries.append({
                "start": start,
                "end": end,
                "title": f"Momento {i+1}",
                "hook": "Trecho relevante",
                "viral_score": score
            })
    return clip_boundaries

