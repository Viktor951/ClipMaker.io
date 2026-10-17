# ClipMaker.io — Relatório de Performance e Linha de Base (Baseline)

Este documento registra as métricas empíricas de performance da arquitetura do ClipMaker.io, o perfil de hardware do ambiente de execução e a identificação dos principais gargalos do pipeline.

---

## 1. Perfil de Hardware e Ambiente de Execução

### Hardware Host (Windows 11)
- **Processador (CPU):** 13th Gen Intel(R) Core(TM) i5-13420H (8 núcleos físicos: 4 P-cores + 4 E-cores, 12 threads lógicas)
- **Memória RAM Física:** 24.00 GB DDR4/DDR5
- **GPU Dedicada:** NVIDIA GeForce RTX 3050 Laptop GPU (6 GB VRAM GDDR6)
  - **Driver NVIDIA:** 617.42
  - **Versão CUDA:** 13.4 (WDDM 3.2)
  - **Aceleração Hardware FFmpeg:** NVENC disponível (`h264_nvenc`)

### Ambiente Docker Desktop / WSL2
- **Kernel WSL2:** `6.18.33.2-microsoft-standard-WSL2`
- **CPUs alocadas à VM:** 12
- **RAM Total alocada à VM WSL2:** 11.54 GiB (~50% da RAM física)
- **Limites de Memória por Container (`docker stats`):**
  - `clipmaker-prod-worker-1`: 3.0 GiB
  - `clipmaker-prod-api-1`: 768 MiB
  - `clipmaker-prod-db-1`: 512 MiB
  - `clipmaker-prod-redis-1`: 192 MiB
  - `clipmaker-prod-frontend-1`: 128 MiB
  - `clipmaker-prod-cleanup-1`: 64 MiB

> **Nota Operacional:** No host Windows com FFmpeg nativo, o NVENC é detectado e acelera o encoding. Dentro do container padrão do worker, o toolkit da NVIDIA não está montado, fazendo o container recorrer ao encoding CPU (`libx264`).

---

## 2. Metodologia de Benchmark (Etapa 0)

- **Script de Benchmark:** `scripts/benchmark.py`
- **Instrumentação:** Decorator e Context Manager `timed("nome_da_etapa")` em `backend/app/core/timing.py`.
- **Vídeo de Teste:**
  - Arquivo: `backend/temp_videos/87e2634a-75a5-4f26-b18a-079fe423f7b5.mp4`
  - Resolução: `1920x1080` (Full HD, 30 fps)
  - Duração: `406.16s` (~6.77 minutos)
  - Tamanho: `256.56 MB`
  - Aspect Ratio de saída: `9:16` (1080x1920)
  - Clipes gerados: `5` clipes (75.0s cada)

---

## 3. Linha de Base — Resultados Medidos

### Tabela 1: Linha de Base de Computação Local (`--skip-llm`)
Isola a performance do hardware e do pipeline de processamento (probe, áudio/Whisper, OpenCV e FFmpeg) sem influência de latência ou limites de cota de APIs externas.

| Fase do Pipeline | Tempo (s) | % do Total | Observações |
| :--- | :---: | :---: | :--- |
| **1. Probe (ffprobe)** | 0.04s | 0.0% | Metadados do vídeo via ffprobe |
| **2. Transcrição (Whisper)** | 18.01s | 21.4% | Whisper `tiny`, CPU int8, 4 threads |
| **3. LLM (Detecção Momentos)** | 0.00s | 0.0% | Fallback matemático rápido |
| **4. Face Tracking (OpenCV)** | 0.00s | 0.0% | Fallback centro padrão (sem haar xml) |
| **5. Render Vídeo (FFmpeg)** | 32.60s | 38.8% | Corte 9:16 do vídeo limpo (5 clipes x ~6.5s) |
| **6. Legendas Burn-in (FFmpeg)** | 32.32s | 38.5% | Re-render completo com filtro `subtitles` |
| **7. Overhead / E/S / Thumbnails** | 1.05s | 1.3% | Thumbnails, GC e I/O de disco |
| **TEMPO TOTAL PIPELINE** | **84.02s** | **100.0%** | **5 clipes 9:16 gerados (1m 24s)** |

---

### Tabela 2: Linha de Base com Chamada de LLM (`Gemini API`)

| Fase do Pipeline | Tempo (s) | % do Total | Observações |
| :--- | :---: | :---: | :--- |
| **1. Probe (ffprobe)** | 0.04s | 0.0% | Metadados do vídeo |
| **2. Transcrição (Whisper)** | 21.17s | 14.3% | Whisper `tiny`, CPU int8 |
| **3. LLM (Detecção Momentos)** | 60.61s | 40.9% | Tentativas e backoff de quota (429) |
| **4. Face Tracking (OpenCV)** | 0.00s | 0.0% | Centro padrão |
| **5. Render Vídeo (FFmpeg)** | 32.76s | 22.1% | Render do vídeo limpo |
| **6. Legendas Burn-in (FFmpeg)** | 32.45s | 21.9% | Re-render com legendas |
| **7. Overhead / E/S / Thumbnails** | 1.11s | 0.7% | Thumbnails e limpeza |
| **TEMPO TOTAL PIPELINE** | **148.14s** | **100.0%** | **5 clipes gerados (2m 28s)** |

---

## 4. As 3 Etapas Mais Pesadas do Pipeline

Com base nos dados reais do benchmark, os 3 maiores gargalos do sistema são:

### 1º Render Vídeo Limpo (FFmpeg): 32.60s (38.8% do tempo de computação)
- Cada clipe de 75s leva cerca de **6.5s** para ser cortado, cropado para 9:16 e codificado em H.264.
- Para 5 clipes sequenciais, o tempo escala linearmente (5 x 6.5s = 32.6s).

### 2º Queima de Legendas / Re-render (FFmpeg): 32.32s (38.5% do tempo de computação)
- O pipeline atual renderiza o vídeo **duas vezes**: primeiro gera `clean_<uuid>.mp4`, e depois executa um segundo processo do FFmpeg (`re_render_clip`) para queimar o arquivo SRT sobre o vídeo limpo, gerando `clip_<uuid>.mp4`.
- Somados, **Render + Legendas consom 64.92s (77.3% de todo o tempo de computação)**. Uma única passagem combinada ou otimização de filtro pode cortar quase metade desse tempo.

### 3º Transcrição de Áudio (Whisper): 18.01s – 21.17s (21.4% do tempo de computação)
- A transcrição de 6.77 minutos de áudio levou ~18 segundos usando o modelo `tiny` com 4 threads na CPU.
- Para modelos maiores (`base`, `small`) ou vídeos de 10-30 minutos, o tempo cresce substancialmente se não houver aceleração por GPU/CUDA ou otimização de pré-extração de áudio em 16kHz mono.
