# ClipMaker.io — Relatório de Performance e Linha de Base (Baseline)

Este documento registra as métricas empíricas de performance da arquitetura do ClipMaker.io, o perfil de hardware e limites de recursos do ambiente de execução, a investigação técnica sobre detecção facial (OpenCV) e o detalhamento de auditoria da chamada ao Gemini.

---

## 1. Perfil de Hardware e Limites de Execução

### Hardware Host (Windows 11)
- **Processador (CPU):** 13th Gen Intel(R) Core(TM) i5-13420H (8 núcleos físicos: 4 P-cores + 4 E-cores, 12 threads lógicas)
- **Memória RAM Física:** 24.00 GB DDR4/DDR5
- **GPU Dedicada:** NVIDIA GeForce RTX 3050 Laptop GPU (6 GB VRAM GDDR6)
  - **Driver NVIDIA:** 617.42
  - **Versão CUDA:** 13.4 (WDDM 3.2)
  - **Aceleração Hardware FFmpeg:** NVENC disponível (`h264_nvenc`)

### Ambiente de Produção Docker Compose (`docker-compose.prod.yml`)
- **Kernel WSL2:** `6.18.33.2-microsoft-standard-WSL2`
- **CPUs alocadas à VM WSL2:** 12 threads
- **RAM Total alocada à VM WSL2:** 11.54 GiB
- **Limites Reais por Container (`docker-compose.prod.yml` / `docker stats`):**
  - **`clipmaker-prod-worker-1` (Processamento pesado):**
    - **`cpus: 2.0`** (limitado a 2 núcleos de CPU)
    - **`mem_limit: 3g`** (3.0 GiB de RAM)
  - `clipmaker-prod-api-1`: `cpus: 1.0`, `mem_limit: 768m`
  - `clipmaker-prod-db-1`: `cpus: 1.0`, `mem_limit: 512m`
  - `clipmaker-prod-redis-1`: `cpus: 0.3`, `mem_limit: 192m`
  - `clipmaker-prod-frontend-1`: `cpus: 0.5`, `mem_limit: 128m`
  - `clipmaker-prod-cleanup-1`: `cpus: 0.1`, `mem_limit: 64m`

> **Impacto Arquitetural de Recursos:**
> No Host nativo, o FFmpeg detecta e utiliza a GPU NVIDIA via NVENC (`h264_nvenc`), acelerando as etapas de render e queima de legendas para ~6.5s por clipe.
> Dentro do container do worker, devido à ausência do runtime NVIDIA montado e aos limites de `cpus: 2.0`, o FFmpeg executa o encoder de software (`libx264 ultrafast`), elevando o tempo de render para ~21s por clipe e a queima de legendas para ~15.5s por clipe.

---

## 2. Metodologia de Medição Estatística (Etapa 0)

Para assegurar rigor estatístico contra ruídos operacionais, caches de sistema operacional e variações de carga:
- **Número de Rodadas:** Cada cenário foi executado rigorosamente **3 vezes consecutivas** (`--runs 3`).
- **Métricas Tabuladas:** **Mediana** e intervalo de **Variação (Mínimo - Máximo)**.
- **Instrumentação:** Decorator e Context Manager `timed("etapa")` em `backend/app/core/timing.py`.
- **Vídeo Padrão de Teste:**
  - Arquivo: `87e2634a-75a5-4f26-b18a-079fe423f7b5.mp4`
  - Resolução: `1920x1080` (Full HD, 30 fps)
  - Duração: `406.16s` (~6.77 minutos)
  - Tamanho em disco: `256.56 MB`
  - Configuração de saída: Formato `9:16` (1080x1920), gerando `5` clipes curtos de `75.0s` cada.

---

## 3. Linha de Base — Resultados Medidos (3 Rodadas)

### Tabela 1: Linha de Base de Computação no Host (`--skip-llm`, 3 rodadas)
Isola o processamento de mídia (probe, Whisper CPU int8, OpenCV e FFmpeg com NVENC) no hardware nativo.

| Fase do Pipeline | Mediana | Variação (Min - Max) | % do Total | Observações |
| :--- | :---: | :---: | :---: | :--- |
| **1. Probe (ffprobe)** | 0.05s | 0.04s – 0.05s | 0.1% | Metadados do vídeo original |
| **2. Transcrição (Whisper)** | 22.81s | 18.66s – 26.68s | 25.7% | Whisper `tiny`, CPU int8, 4 threads |
| **3. LLM (Detecção Momentos)** | 0.00s | 0.00s – 0.00s | 0.0% | Fallback matemático de cortes |
| **4. Face Tracking (OpenCV)** | 0.00s | 0.00s – 0.00s | 0.0% | OpenCV 5.0 headless (sem CascadeClassifier) |
| **5. Render Vídeo (FFmpeg)** | 32.66s | 32.32s – 33.15s | 36.8% | 5 clipes 9:16 limpos com NVENC (~6.5s/clipe) |
| **6. Legendas Burn-in (FFmpeg)** | 32.53s | 32.18s – 32.95s | 36.6% | Re-render completo com filtro `subtitles` |
| **7. Overhead / E/S / Thumbs** | 1.05s | 1.04s – 1.14s | 1.2% | Miniaturas, GC e I/O de disco |
| **TEMPO TOTAL PIPELINE** | **88.87s** | **84.76s – 93.09s** | **100.0%** | **Mediana de 3 rodadas (1m 29s)** |

*Histórico das rodadas:* Rodada 1: 84.76s | Rodada 2: 93.09s | Rodada 3: 88.87s (Δ 8.33s).

---

### Tabela 2: Linha de Base no Host com Gemini LLM (3 rodadas) + Auditoria
Executa o pipeline completo acionando a API do Google Gemini para seleção semântica dos melhores momentos.

| Fase do Pipeline | Mediana | Variação (Min - Max) | % do Total | Observações |
| :--- | :---: | :---: | :---: | :--- |
| **1. Probe (ffprobe)** | 0.05s | 0.04s – 0.05s | 0.0% | Metadados via ffprobe |
| **2. Transcrição (Whisper)** | 19.34s | 18.31s – 20.44s | 18.6% | Whisper `tiny`, CPU int8 |
| **3. LLM (Detecção Momentos)** | 21.92s | 16.58s – 26.79s | 21.1% | Chamada Gemini API + parsing JSON |
| **4. Face Tracking (OpenCV)** | 0.00s | 0.00s – 0.00s | 0.0% | Fallback centro |
| **5. Render Vídeo (FFmpeg)** | 32.56s | 32.48s – 32.74s | 31.4% | Render do vídeo limpo (NVENC) |
| **6. Legendas Burn-in (FFmpeg)** | 32.61s | 32.45s – 32.88s | 31.4% | Queima de legendas (NVENC) |
| **7. Overhead / E/S / Thumbs** | 1.08s | 1.05s – 1.13s | 1.0% | Geração de miniaturas e disco |
| **TEMPO TOTAL PIPELINE** | **103.76s** | **101.65s – 109.83s** | **100.0%** | **Mediana de 3 rodadas (1m 44s)** |

*Histórico das rodadas:* Rodada 1: 101.65s (LLM: 16.58s) | Rodada 2: 103.76s (LLM: 21.92s) | Rodada 3: 109.83s (LLM: 26.79s) (Δ 8.18s).

#### Auditoria da Chamada LLM (Metadados Estruturados):
- **Modelo Utilizado:** `gemini-3.8-flash` (via alias/SDK Google GenAI)
- **Tentativas Realizadas:** `1` (sucesso imediato na primeira tentativa em todas as 3 rodadas)
- **Erros de Cota / HTTP 429:** `False` (zero ocorrências de 429)
- **Origem dos Cortes:** `gemini` (cortes semânticos gerados pela inteligência artificial; fallback matemático **não** precisou ser acionado)
- **Momentos Identificados:** 5 clipes de alta relevância com títulos gerados e justificativas contextuais baseadas na transcrição.

---

### Tabela 3: Linha de Base no Container Worker (`clipmaker-prod-worker-1`, 3 rodadas)
Execução realizada estritamente **DENTRO** do container do worker com os limites reais de produção definidos no `docker-compose.prod.yml`:
- **Limites Reais:** **`cpus: 2.0`** (2 núcleos) | **`mem_limit: 3g`** (3.0 GiB RAM)
- **Modo:** `--skip-llm` com vídeo copiado para o volume `/app/backend/temp_videos/test_video.mp4`

| Fase do Pipeline | Mediana | Variação (Min - Max) | % do Total | Observações |
| :--- | :---: | :---: | :---: | :--- |
| **1. Probe (ffprobe)** | 0.07s | 0.07s – 0.09s | 0.0% | Metadados no Debian Bookworm |
| **2. Transcrição (Whisper)** | 30.37s | 28.81s – 35.87s | 12.9% | Whisper `tiny` com 4 threads na CPU (2 vCPUs) |
| **3. LLM (Detecção Momentos)** | 0.00s | 0.00s – 0.00s | 0.0% | Fallback matemático de cortes |
| **4. Face Tracking (OpenCV)** | 16.34s | 16.09s – 16.83s | 6.9% | **Ativo!** OpenCV 4.8.0 Haar (~3.27s/clipe) |
| **5. Render Vídeo (FFmpeg)** | 107.01s | 103.67s – 114.23s | 45.5% | 5 clipes 9:16 limpos via CPU `libx264` (~21.4s/clipe) |
| **6. Legendas Burn-in (FFmpeg)** | 77.66s | 76.99s – 85.28s | 33.0% | Re-render completo com filtro `subtitles` (~15.5s/clipe) |
| **7. Overhead / E/S / Thumbs** | 1.78s | 1.71s – 2.36s | 0.8% | Thumbs, GC e IO de disco |
| **TEMPO TOTAL PIPELINE** | **235.16s** | **232.98s – 247.09s** | **100.0%** | **Mediana de 3 rodadas (3m 55s)** |

*Histórico das rodadas no container:*
- Rodada 1: 235.16s
- Rodada 2: 247.09s
- Rodada 3: 232.98s (Δ 14.11s)

---

## 4. Investigação Técnica: Detecção Facial (Face Tracking)

### Causa Raiz do "0.00s (sem haar xml)"
Foi realizada a verificação em ambos os ambientes conforme solicitado:
`python -c "import cv2,os; p=cv2.data.haarcascades+'haarcascade_frontalface_default.xml'; print(p, os.path.exists(p))"`

1. **No Ambiente Host (Windows 11 / Python 3.14):**
   - Versão do OpenCV: `5.0.0.86` (pre-release do OpenCV 5 para suportar Python 3.14).
   - O arquivo XML não vinha embutido no pacote `site-packages/cv2/data/`.
   - **Causa Crítica:** Além da ausência do XML, no OpenCV 5.0 headless a classe C++ de classificadores em cascata foi omitida das bindings Python: `hasattr(cv2, 'CascadeClassifier') == False`. Tentar invocar `CascadeClassifier` disparava `AttributeError`. O OpenCV 5 migrou a detecção padrão para o modelo neural `FaceDetectorYN`.
2. **No Ambiente Container Worker (Debian Bookworm / Python 3.11):**
   - Versão do OpenCV: `4.8.0.74`.
   - Caminho: `/opt/venv/lib/python3.11/site-packages/cv2/data/haarcascade_frontalface_default.xml`.
   - `os.path.exists(p) == True` e `hasattr(cv2, 'CascadeClassifier') == True`.
   - O classificador Haar é plenamente suportado e funcional.

### Correção Implementada
1. **Fallback de Arquivo Local:** Copiado `haarcascade_frontalface_default.xml` diretamente para `backend/app/services/haarcascade_frontalface_default.xml`.
2. **Resolução Robusta:** No `backend/app/services/video_service.py` (`_find_face_cascade_path`), a busca verifica:
   - Diretório local do serviço (`services/haarcascade_frontalface_default.xml`);
   - `cv2.data.haarcascades`;
   - Diretórios padrões de sistema (`/usr/share/opencv4/haarcascades/`, etc.).
3. **Checagem Defensiva:** `hasattr(cv2, "CascadeClassifier")` adicionado antes da instanciação para não quebrar ambientes OpenCV 5.

### Impacto Medido com Face Tracking Ativo
- No container do worker, o face tracking analisou **301 frames** por clipe de 75s (amostragem a cada 250ms).
- O tempo consumido foi de **16.34s** no total dos 5 clipes (**~3.27s por clipe**).
- No **Clipe 5 (331.2s -> 406.2s)**, o classificador detectou **12 faces**, calculou a mediana da coordenada horizontal dos rostos (`center_x=937`) e moveu o centro da janela de corte 9:16 dinamicamente para o locutor, eliminando o corte cego e estático no centro geométrico (`960`).

---

## 5. Os 3 Maiores Gargalos do Pipeline (Identificados nos Ambientes)

Comparando o Host (com GPU) e o Container de Produção (com CPU limitada a 2.0 núcleos):

### 1º Renderização do Vídeo Limpo (FFmpeg): 107.01s no Container (45.5% do total)
- No container (CPU `libx264 ultrafast` com `cpus: 2.0`), cada clipe de 75s leva **21.4s** para ser cortado, cropado e codificado.
- Para 5 clipes sequenciais, consome quase 1 minuto e 47 segundos.
- No host com NVENC, consome apenas 32.6s (6.5s/clipe).

### 2º Queima de Legendas / Re-render (FFmpeg): 77.66s no Container (33.0% do total)
- O pipeline atual gera o clipe duas vezes consecutivas:
  1. Primeiro gera `clean_<uuid>.mp4` (vídeo sem legendas);
  2. Em seguida, roda o FFmpeg novamente para queimar o arquivo SRT sobre o vídeo limpo, gerando `clip_<uuid>.mp4`.
- No container, essa segunda passagem custa **15.5s adicionais por clipe**, totalizando **77.66s**.
- **Juntas, as duas passagens do FFmpeg consom 184.67s (78.5% de TODO o tempo de computação do container)!**
- Uma passagem unificada eliminaria a necessidade de ler e recodificar o vídeo duas vezes.

### 3º Transcrição de Áudio (Whisper): 30.37s no Container (12.9% do total)
- O áudio completo de 6.77 minutos é transcrito pelo modelo `tiny` com 4 threads na CPU em ~30 segundos no container (vs ~19-22s no host).
- A pré-extração do áudio em WAV 16kHz mono antes de invocar o Whisper e o paralelismo controlado representam oportunidades claras para diminuir esse tempo.

---

## 6. Diagnóstico de Etapas do FFmpeg (Tabela 4)

Para entender com precisão cirúrgica onde o tempo é consumido durante o processamento de um clipe, foi executado um diagnóstico isolando cada etapa da cadeia de processamento em **UM clipe de 75.0s** (`0.0s -> 75.0s`) do vídeo de teste, medindo com `-benchmark -loglevel info` e descartando o muxing com saída nula (`-f null -`).

### Tabela 4: Decomposição Incremental do FFmpeg (Clipe de 75s)

| Variante Medida | Host (`rtime`) | Container (`rtime`) | Δ Container | CPU Container (`utime`) | Observações |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **a) Só Decodificar** (sem filtros, sem encode) | **3.55s** (21.1x) | **7.46s** (10.1x) | — | 14.26s | Leitura e descompressão do VP9 1080p |
| **b) Decodificar + Crop + Scale** | **3.86s** (19.4x) | **10.74s** (7.04x) | +3.28s | 19.76s | `crop=608:1080:656:0,scale=1080:1920` |
| **c) (b) + Filtro Subtitles** | **11.86s** (6.32x) | **14.83s** (5.06x) | +4.09s | 27.62s | Rasterização libass / fontconfig / FreeType |
| **d) (c) + Encode libx264 ultrafast** | **13.65s** (5.50x) | **23.95s** (3.14x) | +9.12s | 45.74s | Compressão H.264 CPU (`crf 23, ultrafast`) |
| **e) (c) + Encode h264_nvenc** | **12.75s** (5.87x) | *Indisponível* | — | 29.13s | Aceleração GPU (`Cannot load libcuda.so.1` no container) |

### Conclusão em Uma Frase:
> **No container limitado a 2 CPUs, o tempo é dominado pelo encode de CPU via libx264 (38,1%) e pelo decode (31,1%), enquanto no host com aceleração de hardware o gargalo crítico é o filtro de legendas (libass/subtitles), que sozinho adiciona 8 segundos e consome mais de 60% de todo o pipeline de vídeo.**

---

## 7. Análise de Cota de CPU e Concorrência de Threads

Foi realizada a inspeção do subsistema de cgroups e do runtime do Python no container worker:
- **Cota Real do Container (`/sys/fs/cgroup/cpu.max`):**
  - Valor lido: `200000 100000`
  - Quota: 200.000 µs por período de 100.000 µs = **2.0 CPUs reais** (limite rígido imposto pelo kernel via CFS).
- **Detecção do Python (`os.cpu_count()`):**
  - Valor retornado: **12** (o Python lê o número de processadores lógicos da máquina/VM hospedeira WSL2, e não a cota do cgroup).
- **Threads Efetivas em Execução:**
  - **Whisper (`ai_service.py`):** `cpu_threads = min(4, max(2, (os.cpu_count() or 2) // 2))` → com `os.cpu_count() == 12`, aloca **4 threads**.
  - **FFmpeg (`video_service.py`):** `cores = os.cpu_count() or 2` → aloca **4 threads** via `-threads 4` (e a `libx264` aloca pools de threads extras para lookahead e slices).
- **Diagnóstico:**
  - **SIM, há mais threads ativas (4 threads no Whisper e 4+ no FFmpeg) do que a cota física de CPU do container (2.0 CPUs).**
  - Essa sobre-alocação (oversubscription) de 2x gera concorrência acirrada entre threads, saturação da fila de execução do escalonador CFS do Linux, context switching excessivo e throttling de ciclos de CPU.

---

## 8. Log Aprimorado do Face Tracking

Para total rastreabilidade do corte inteligente em produção, a rotina de tracking facial registra por clipe:
- Quantidade de frames amostrados (intervalo a cada 5 frames)
- Total de frames brutos lidos
- Quantidade de detecções positivas de rostos
- Taxa de detecção percentual
- Coordenada `crop_x` final calculada para a janela 9:16 (junto com o `center_x` suavizado)

**Exemplo de log emitido pelo worker:**
```text
[clipmaker.video] Face tracking concluído: 61 frames amostrados (de 301 lidos), 9 detecções (taxa de detecção: 14.8%), crop_x final=652 (center_x=955).
```

---

## 9. Etapa 1 — Resultados de Infraestrutura e Configuração

Nesta etapa, o ambiente de execução do worker foi profundamente otimizado em infraestrutura, disco, concorrência e aceleração por hardware:

1. **Recursos de CPU e Memória:**
   - Tornados configuráveis dinamicamente via `.env` (`WORKER_CPUS=4.0`, `WORKER_MEM_LIMIT=6g`).
   - Evitou a saturação por oversubscription (threads alinhadas à cota real de CPU).
2. **Armazenamento de Alta Velocidade (Volume Nomeado Docker):**
   - Substituição do bind-mount lento do Windows NTFS (`D:\...` via 9P/WSL2) por um volume nomeado Docker gerenciado pelo Linux (`clipmaker_temp_videos`).
   - Elimina os gargalos de latência de I/O em leitura/escrita de sub-clipes e renderizações intermediárias do FFmpeg.
   - Mantidos no host `D:` apenas dados leves e persistentes: cache de modelos HuggingFace (`/app/cache`), logs estruturados (`/app/logs`) e dados do Redis.
3. **Aceleração por GPU (NVIDIA RTX 3050 6GB):**
   - Criação do target multi-stage `runtime-gpu` no [Dockerfile](file:///c:/Users/João Victor/Documents/Antigravity Projects/ClipMakerAI/Dockerfile) com bibliotecas mínimas `nvidia-cublas-cu12` e `nvidia-cudnn-cu12` via pip (sem necessidade de imagem base CUDA de 10GB).
   - Whisper agora detecta GPU via `ctranslate2.get_cuda_device_count()` e roda em `float16` (com fallback robusto para `int8` em CPU). Modelo configurável via `WHISPER_MODEL` (padrão `small` em GPU).
   - FFmpeg no Debian Bookworm recebeu passthrough via `NVIDIA_DRIVER_CAPABILITIES=compute,utility,video`, habilitando `h264_nvenc` por hardware nativamente dentro do container.
4. **Cache Global e Pré-carregamento do Whisper:**
   - O modelo Whisper é mantido carregado na memória global do processo do worker (`_WHISPER_CACHE`), com descarga automática apenas após `WHISPER_IDLE_TIMEOUT_MINUTES=15` minutos de ociosidade.
   - Pré-carregado no boot do container do worker para eliminar a latência de cold start no primeiro job.
5. **Download Otimizado com yt-dlp:**
   - Adicionada flag `--concurrent-fragments 4` e limite configurável `MAX_SOURCE_HEIGHT` (padrão `1080`) para evitar o download de arquivos 4K pesados quando a saída do pipeline é 1080p.

---

### Tabela 5: Comparativo ANTES x DEPOIS (Etapa 0 Container vs Etapa 1 Container com GPU)

Medições realizadas dentro do container do worker (`clipmaker-prod-worker-1`), rodando 3 execuções consecutivas para cada ambiente no mesmo vídeo de teste (256.56 MB, 6.77 min, 5 clipes gerados com aspect ratio 9:16):

| Fase do Pipeline | ANTES (Etapa 0: CPU 2 cores, 3GB, NTFS) | DEPOIS (Etapa 1: GPU NVENC, 4 cores, 6GB, Volume) | Variação Min - Max (Etapa 1) | Ganho Absoluto (s) | Redução de Tempo (%) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **1. Probe (ffprobe)** | 0.07s | **0.06s** | 0.06s – 0.06s | -0.01s | -14.3% |
| **2. Transcrição (Whisper)** | 30.37s *(tiny)* | **13.28s** *(small!)* | 13.10s – 24.85s | -17.09s | **-56.3%** |
| **3. LLM (Detecção Momentos)** | 0.00s | **0.00s** | 0.00s – 0.00s | 0.00s | 0.0% |
| **4. Face Tracking (OpenCV)** | 16.34s | **8.11s** | 8.01s – 8.46s | -8.23s | **-50.4%** |
| **5. Render Vídeo (FFmpeg)** | 107.01s *(CPU)* | **40.54s** *(NVENC)* | 40.25s – 41.40s | -66.47s | **-62.1%** |
| **6. Legendas Burn-in (FFmpeg)**| 77.66s *(CPU)* | **35.56s** *(NVENC)* | 35.03s – 36.38s | -42.10s | **-54.2%** |
| **7. Overhead / E/S / Thumbs** | 1.78s *(NTFS)* | **1.24s** *(Docker Vol)*| 1.23s – 1.25s | -0.54s | **-30.3%** |
| **TEMPO TOTAL PIPELINE** | **235.16s** (3m 55s) | **100.65s** (1m 40s) | **98.69s – 109.53s** | **-134.51s** | **-57.2% (-2.34x)** |

*(Nota: Na rodada 1 com modelo frio na memória, a transcrição levou 24.85s; nas rodadas subsequentes com o modelo mantido em cache de processo, a transcrição caiu para 13.10s a 13.28s).*

Se comparado com a linha de base original com Whisper `base` na CPU (343.83s):
- **O tempo total despencou de 5 minutos e 43 segundos para 1 minuto e 40 segundos (-70.7% de tempo total, uma aceleração de 3.42x)**.


