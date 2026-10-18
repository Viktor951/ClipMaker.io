# Relatório de Auditoria de Integridade das Etapas — ClipMaker.io

**Data da Auditoria:** 18 de Outubro de 2026  
**Commit Auditado:** `564e5ec` (`feat(clean): etapa e - limpeza de timings, toasts acessiveis, versionamento de assets e coerencia de docs`)  
**Ambiente:** Host Windows 11 (Python 3.14.7, pytest 9.1.1, Git 2.47, FFmpeg 9.0.1 com NVENC)  
**Escopo:** Verificação estrita de integridade contra o código-fonte, histórico Git e testes automatizados (Somente Leitura, sem commits).

---

## 1. Resumo Executivo e Contagem por Bloco

| Bloco | Descrição | Total Itens | OK | PARCIAL | AUSENTE | NÃO EXECUTADA | NÃO VERIFICÁVEL |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **G** | Governança e Estado Geral | 6 | 5 | 1 | 0 | 0 | 0 |
| **F1** | Correções Críticas (Fase 1) | 12 | 11 | 1 | 0 | 0 | 0 |
| **E0** | Etapa 0 — Medição e Baseline | 6 | 6 | 0 | 0 | 0 | 0 |
| **E1** | Etapa 1 — Infraestrutura e Recursos | 7 | 6 | 1 | 0 | 0 | 0 |
| **E2** | Etapa 2 — Pipeline de Mídia | 8 | 8 | 0 | 0 | 0 | 0 |
| **E3** | Etapa 3 — API e Desacoplamento | 8 | 7 | 1 | 0 | 0 | 0 |
| **E4** | Etapa 4 — Frontend e UX | 7 | 7 | 0 | 0 | 0 | 0 |
| **A** | Etapa A — Fila Huey | 4 | 4 | 0 | 0 | 0 | 0 |
| **B** | Etapa B — Robustez de Jobs | 5 | 5 | 0 | 0 | 0 | 0 |
| **C** | Etapa C — Compose sem GPU | 4 | 3 | 0 | 0 | 0 | 1 |
| **D** | Etapa D — Segurança Pendente | 5 | 4 | 1 | 0 | 0 | 0 |
| **E** | Etapa E — Limpeza e Coerência | 5 | 5 | 0 | 0 | 0 | 0 |
| **H** | Funcionalidades Futuras (Fases 2–6) | 10 | 0 | 1 | 9 | 0 | 0 |
| **DOC** | Documentação e Consistência | 7 | 3 | 4 | 0 | 0 | 0 |
| **TOTAL** | **Todos os Blocos** | **94** | **74** | **10** | **9** | **0** | **1** |

---

## 2. Tabela Completa de Auditoria Item a Item

| ID | Item Auditado | Status | Evidência Técnica | Observação Técnica |
| :--- | :--- | :---: | :--- | :--- |
| **G1** | Histórico de commits e status de trabalho | **OK** | `git log`: 33 commits (de `09019ac` a `564e5ec`). `git status -sb`: `## main...origin/main` | Árvore de trabalho 100% limpa no commit atual. |
| **G2** | Execução da suíte de testes pytest | **OK** | `pytest -v`: 34 passed, 5 warnings em 73.44s. Python `3.14.7` | Todos os 34 testes passaram com sucesso no host. |
| **G3** | Validação sintática do Docker Compose | **OK** | `docker compose -f docker-compose.prod.yml config -q` e `-f docker-compose.gpu.yml`: saída vazia (código 0) | Ambas as configurações (padrão CPU e override GPU) são sintaticamente válidas. |
| **G4** | Integridade e idempotência das migrações SQL | **OK** | `migrations/001_init.sql` a `006_etapa_b_job_robustness.sql`. Zero `DROP`. `scripts/migrate.sh:9-23` | Numeração estrita sem lacunas (001 a 006), todas usam `IF NOT EXISTS` e tabela `schema_migrations`. |
| **G5** | Auditoria de segredos e dados pessoais | **OK** | `git ls-files \| grep '\.env$'` (vazio); `git grep -i "C:\\Users"` (vazio); `git grep "AIza"` (vazio) | Nenhum arquivo `.env` versionado, zero caminhos locais, zero chaves privadas no repositório. |
| **G6** | Configuração do GitHub Actions CI | **PARCIAL** | `.github/workflows/tests.yml:34, 45, 54` (`python-version: "3.11"`, `pytest -v`) | O CI roda `pytest -v` (descobre todos os 34 testes via `pytest.ini`), mas a linha 45 executa apenas `001_init.sql` no Postgres do CI. |
| **F1.1** | Política de fallback SQLite e SqliteHuey | **OK** | `backend/app/db/db_service.py:281, 291-296` e `backend/app/worker/worker.py:19, 32-37` | Rejeita SQLite se `ENVIRONMENT=production` ou `ALLOW_SQLITE_FALLBACK != true`. Testado em `test_fallback_policy.py`. |
| **F1.2** | Renderização de título e gancho do clipe | **OK** | `frontend/js/ui.js:134-135`. `git grep "startsWith('clip_')"` no frontend retornou vazio | Exibe sempre `clip.title` e `clip.hookReason` reais da IA sem substituição por prefixo de ID. |
| **F1.3** | ViralScore originado da IA (0-100) | **OK** | `backend/app/services/ai_service.py:314-323`, `engine_service.py:302` | `viral_score` extraído do JSON do Gemini e limitado a `[0, 100]`. Fórmula fixa restrita ao fallback. |
| **F1.4** | Geração de thumbnail real via FFmpeg | **OK** | `backend/app/services/video_service.py:602-627`, `routers/video.py:321`. `git grep "unsplash"` = 0 | Miniatura JPG extraída do frame em ~1s via FFmpeg; coluna `thumbnail_key` e endpoint `/thumbnail/{clip_id}`. |
| **F1.5** | Re-renderização assíncrona de clipes | **OK** | `backend/app/worker/worker.py:298, 385, 390` e `frontend/js/ui.js:363-385` | Worker atualiza `clips.status` (`RENDERING`/`COMPLETED`/`FAILED`). Frontend consulta `/clip/{id}/status` até `COMPLETED`. |
| **F1.6** | Fechamento do editor sem recarregar lista | **OK** | `frontend/js/ui.js:433-445` (`closeEditorModal`), `frontend/js/app.js:880-884` (`isClosingEditor`) | O fechamento do modal seta flag e o listener `popstate` impede a remontagem da lista de clipes. |
| **F1.7** | Resiliência a falhas de rede no polling | **OK** | `frontend/js/app.js:718-728` (`consecutiveFailures >= 5`) | Exibe banner com mensagem de conexão instável e botão "Tentar novamente" (`#btn-retry-poll`). |
| **F1.8** | Tipagem e coerência da qualidade de vídeo | **OK** | `backend/app/api/routers/project.py:41` (`Literal["720p", "1080p"]`), `worker.py:328` | Tipagem Pydantic estrita e padrão coerente em `1080p`. |
| **F1.9** | Validação de payload do ReRenderRequest | **OK** | `backend/app/api/routers/project.py:34-48, 159-161`, `routers/video.py:113, 186` | Valida `style`, `aspect_ratio`, `quality`, `words` (máx. 5000) e `end_time > start_time` e `<= duração`. |
| **F1.10** | Tratamento de canal de áudio opcional | **OK** | `backend/app/services/video_service.py:390, 446, 509, 529, 590` | Todas as 5 ocorrências de mapeamento de áudio usam rigorosamente `"-map", "0:a?"`. |
| **F1.11** | Validação de senha mínima (8 caracteres) | **PARCIAL** | `backend/app/models/user.py:9` (`min_length=8`), `frontend/index.html:321` (`minlength="8"`), `frontend/js/app.js:104` | Backend exige 8 caracteres e HTML tem `minlength="8"`, mas o parser em `app.js:104` diz "mínimo 6 caracteres". |
| **F1.12** | Hardening de CORS, WebSockets e estáticos | **OK** | `backend/app/main.py:49-55, 87-94`. Zero rotas WebSocket no arquivo | Métodos limitados a `GET, POST, OPTIONS`; sem WebSockets; arquivos estáticos só com `SERVE_FRONTEND=true`. |
| **E0.1** | Instrumentação de métricas com timed() | **OK** | `backend/app/core/timing.py:28`. `engine_service.py:125, 163, 191, 258, 263` | Decorator e context manager cobrindo `probe`, `transcription`, `llm`, `face_tracking` e `render`. |
| **E0.2** | Parâmetros de CLI no benchmark.py | **OK** | `scripts/benchmark.py:195-199` | Aceita `--video`, `--skip-llm`, `--aspect`, `--runs` e `--keep-output`. |
| **E0.3** | Relatório de performance com dados empíricos | **OK** | `docs/PERFORMANCE.md:7-105` | Registra hardware detalhado, 3 rodadas com mediana e variação, e tabelas comparativas. |
| **E0.4** | Face tracking OpenCV com classificador Haar | **OK** | `backend/app/services/video_service.py:169, 192`, `services/haarcascade_frontalface_default.xml` | Arquivo XML versionado localmente no pacote e verificação `hasattr(cv2, 'CascadeClassifier')`. |
| **E0.5** | Auditoria e metadados estruturados da IA | **OK** | `backend/app/services/ai_service.py:197-200` (`get_last_llm_meta`) | Registra modelo usado, tentativas, flag de cota 429 e fonte (Gemini vs fallback). |
| **E0.6** | Decomposição do FFmpeg e análise de cgroup | **OK** | `docs/PERFORMANCE.md:174-210` (Tabela 4 e inspeção de `/sys/fs/cgroup/cpu.max`) | Registra gargalos de software encoder e descompasso entre `os.cpu_count()` e a cota do container. |
| **E1.1** | Limites de CPU e memória configuráveis | **OK** | `docker-compose.prod.yml:168-169`, `.env.example:25-26` | `WORKER_CPUS=${WORKER_CPUS:-4.0}` e `WORKER_MEM_LIMIT=${WORKER_MEM_LIMIT:-6g}`. |
| **E1.2** | Volume Docker rápido compartilhado | **OK** | `docker-compose.prod.yml:29, 123, 157, 183, 201` | Volume nomeado `clipmaker_temp_videos` em ext4 compartilhado por api, worker, cleanup e nginx (`:ro`). |
| **E1.3** | Configuração do Worker GPU NVIDIA | **OK** | `Dockerfile:76`, `docker-compose.gpu.yml:12, 16, 20-24` | Target `runtime-gpu`, `capabilities: [gpu]`, `NVIDIA_DRIVER_CAPABILITIES: compute,utility,video`. |
| **E1.4** | Gerenciamento de GPU e cache do Whisper | **PARCIAL** | `backend/app/services/ai_service.py:38, 41, 73-95`, `docker-compose.prod.yml:152` | CTranslate2 CUDA/float16 e descarte por inatividade OK. Porém o "preload" roda num `python -c` separado antes do `huey_consumer`, perdendo a RAM no exit. |
| **E1.5** | Otimização de download com yt-dlp | **OK** | `backend/app/worker/worker.py:174-184` | `--concurrent-fragments 4`, `--force-ipv4` e `-f bestvideo[height<=MAX_SOURCE_HEIGHT]...`. |
| **E1.6** | Cálculo de threads a partir do cgroup | **OK** | `backend/app/services/ai_service.py:56-70, 99` e `video_service.py:42-56, 60` | Lê `/sys/fs/cgroup/cpu.max` e calcula threads dividindo pela concorrência. |
| **E1.7** | Comparativo de aceleração de infraestrutura | **OK** | `docs/PERFORMANCE.md:249-270` (Tabela 5) | Registra aceleração de 235.16s para 100.65s (2.34x) com GPU e volume rápido. |
| **E2.1** | Render em passe único (sem clean_*.mp4) | **OK** | `backend/app/services/engine_service.py:101, 261-276`. `git grep "clean_"` confirmado | Integra `crop`, `scale` e legendas em um único comando FFmpeg; zero arquivos `clean_*.mp4` gerados no pipeline principal. |
| **E2.2** | Enquadramento facial persistente | **OK** | `migrations/003_etapa2_pipeline.sql:4`, `db_service.py:462, 467`, `worker.py:336, 355` | `face_center_x` gravado por clipe e repassado diretamente no re-render. |
| **E2.3** | Face tracking com cv2.VideoCapture leve | **OK** | `backend/app/services/video_service.py:150-235` | Amostra o clipe inteiro com `cap.grab()` (~2 fps), resize para 320px e fallback para `total_width // 2`. |
| **E2.4** | Presets de encoding FFmpeg e faststart | **OK** | `backend/app/services/video_service.py:64-85` | `ultrafast` em CPU, `p4` em NVENC, `CRF` por env e `movflags: +faststart`. |
| **E2.5** | Paralelismo de renderização de clipes | **OK** | `backend/app/services/engine_service.py:220, 325-340` | `ThreadPoolExecutor(max_workers=parallelism)` mantendo a ordem original dos clipes. |
| **E2.6** | Persistência incremental por clipe | **OK** | `backend/app/services/engine_service.py:311-319`, `api/routers/project.py:83-108` | Salva clipe imediatamente no banco com status `COMPLETED`; `/status` retorna clipes já prontos em tempo real. |
| **E2.7** | Reuso inteligente de transcrição Whisper | **OK** | `migrations/003_etapa2_pipeline.sql:10-14`, `db_service.py:484-525` | Cache por `userId + fileHash/sourceUrl`, reduzindo tempo de transcrição a zero em re-execuções. |
| **E2.8** | Resiliência do LLM e fallback matemático | **OK** | `backend/app/services/ai_service.py:276, 345-356, 377`, `project.py:126`, `app.js:806` | Alterna modelos em 429, seta `ai_cuts_fallback=True`, `/status` retorna `aiCutsFallback` e frontend avisa via toast. |
| **E3.1** | Desacoplamento da rota de importação por URL | **OK** | `backend/app/api/routers/video.py:209-215` | Cria projeto com status `DOWNLOADING`, despacha para fila Huey e responde em < 15ms. |
| **E3.2** | Upload assíncrono não bloqueante | **OK** | `backend/app/api/routers/video.py:133, 153` | Gravação em disco e `ffprobe` executados via `asyncio.to_thread`. |
| **E3.3** | Entrega de vídeo acelerada via Nginx X-Accel | **OK** | `backend/app/api/routers/video.py:303-318`, `frontend/nginx.conf:49-54` | Header `X-Accel-Redirect: /internal_videos/`, volume `:ro`, suporte a HTTP Range 206 e sanitização `relative_to`. |
| **E3.4** | Consulta de mídia com JOIN único | **OK** | `backend/app/db/db_service.py:642-663` (`get_clip_with_owner`), `routers/video.py:233, 280, 347` | Traz clipe e dono em uma só query SQL sem carregar listas ou fazer parse JSON desnecessário. |
| **E3.5** | Limitação de concorrência por usuário | **OK** | `backend/app/api/routers/video.py:117-122, 189-194` | Rejeita upload ou URL com HTTP 429 se jobs ativos $\ge$ `MAX_CONCURRENT_JOBS_PER_USER`. |
| **E3.6** | Rate limiting distribuído no Redis | **PARCIAL** | `backend/app/api/deps.py:14-25`, `routers/project.py:143` | Decorator `@limiter.limit("10/minute")` OK. Porém `deps.py:23-24` cai silenciosamente para `memory://` se o Redis falhar, mesmo em produção. |
| **E3.7** | Posição na fila e estimativa de tempo (ETA) | **OK** | `migrations/004_etapa3_api_queue.sql:9-16`, `db_service.py:678-735`, `routers/project.py:116-121` | Tabela `job_metrics`, média móvel ponderada por duração e devolução de `queuePosition`/`estimatedTimeSec` em `/status`. |
| **E3.8** | Fila Huey unificada e decoradores únicos | **OK** | `backend/app/worker/worker.py:26, 114, 129, 244, 285` | Apenas uma instância `huey` (`clipmaker_tasks`); exatamente 1 decorador por tarefa (`@huey.task` ou `@huey.periodic_task`). |
| **E4.1** | Renderização não-destrutiva de cards | **OK** | `frontend/js/ui.js:122-125` | Verifica se o elemento já existe no DOM antes de criar, preservando o estado do player. |
| **E4.2** | Polling progressivo e barra de status real | **OK** | `frontend/js/app.js:588-594, 684-704` | Backoff progressivo (3s $\to$ 5s $\to$ 10s); barra de progresso baseada nos status reais da API e fila (sem incrementos falsos de +5%). |
| **E4.3** | Otimização de vídeo com poster e preload | **OK** | `frontend/js/ui.js:140` | `<video src="..." poster="..." preload="none" controls>` em todos os cards. |
| **E4.4** | Configuração dinâmica de limites de arquivo | **OK** | `frontend/js/app.js:291-306`. `git grep "5GB"` no frontend = 0 | Consulta `/api/v1/config` no boot e atualiza texto da dropzone dinamicamente (2000MB padrão). |
| **E4.5** | Barra de progresso real de upload com cancelamento | **OK** | `frontend/js/app.js:342-349, 389-400` | XHR com listener `progress` (exibe MB e porcentagem reais) e botão `#btn-cancel-upload` com `xhr.abort()`. |
| **E4.6** | Otimização de bundle e scripts com defer | **OK** | `frontend/index.html:15, 338-339` | Scripts com `defer`; Font Awesome substituído por `icons.css` (~3KB); 2 fontes do Google Fonts; versionamento de cache. |
| **E4.7** | Higienização de estilos inline | **OK** | `frontend/index.html:187` | Quase totalidade migrada para classes CSS; resta exatamente 1 `style="margin-top: 1.25rem;"` no botão de cancelamento. |
| **A.1** | Remoção de decoradores empilhados na fila | **OK** | `backend/app/worker/worker.py:129, 244, 285` | Zero decoradores duplicados; elimina enfileiramento em filas zumbis. |
| **A.2** | Teste de regressão de roteamento de filas | **OK** | `tests/test_queue_routing.py:69` | Testado contra o commit `3cc6e5c`: falhou conclusivamente com `AssertionError` na fila `huey_ingest`. Passa no commit atual. |
| **A.3** | Validação ponta a ponta com Redis real | **OK** | `docs/PERFORMANCE.md:414-439` (Seção 12) | Registra teste ponta a ponta conteinerizado (135.24s worker / 140.55s API), distinguindo do benchmark direto (72.25s). |
| **A.4** | Diagnóstico do intervalo de ~105s do LLM | **OK** | `docs/PERFORMANCE.md:441-475` (Seção 13) | Identifica loop de *extended thinking* do `gemini-3.8-flash` devido a restrições impossíveis em vídeo de 20s. |
| **B.1** | Watchdog periódico contra projetos travados | **OK** | `migrations/006_etapa_b_job_robustness.sql:5-8`, `worker.py:114-126`, `db_service.py:738-780` | Tarefa periódica (`*/5`) marca projetos inativos há mais de `PROJECT_STALE_MINUTES` como `FAILED`; coluna `updatedAt`. |
| **B.2** | Isolamento de projetos em rascunho (DRAFT) | **OK** | `backend/app/api/routers/project.py:68`, `db_service.py:672` | `POST /projects` cria projeto com status `DRAFT`; `count_active_projects_by_user` ignora DRAFT e não bloqueia uploads. |
| **B.3** | Timeout absoluto de job e retry seletivo | **OK** | `backend/app/services/engine_service.py:115-120`, `worker.py:190-210` | Interrompe job após `JOB_TIMEOUT_MINUTES` (padrão 120min); no máximo 1 retry no yt-dlp restrito a falhas de rede transitórias. |
| **B.4** | Sanitização de mensagens de erro ao usuário | **OK** | `backend/app/worker/worker.py:72-93` (`categorize_error`), `tests/test_job_robustness.py:100` | Substitui stderrs e stack traces técnicos por mensagens curtas e amigáveis antes de gravar no banco. |
| **B.5** | Adaptação de cortes para vídeos curtos | **OK** | `backend/app/services/ai_service.py:201-240` (`_get_clip_target_and_durations`) | Ajusta quantidade e limites de tempo dos clipes proporcionalmente à duração do vídeo de entrada. |
| **C.1** | Worker padrão em CPU e override para GPU | **OK** | `docker-compose.prod.yml:150` (target `runtime`), `docker-compose.gpu.yml:12` (target `runtime-gpu`) | Compose padrão roda em qualquer máquina sem GPU; GPU requer comando explícito com override. |
| **C.2** | Fixação de bibliotecas CUDA/cuBLAS/cuDNN | **OK** | `Dockerfile:28-29` (`nvidia-cublas-cu12==12.9.2.10`, `nvidia-cudnn-cu12==9.27.0.42`) | Dependências binárias da GPU fixadas com precisão na imagem `builder-gpu`. |
| **C.3** | Encoder h264_nvenc dentro do container GPU | **NÃO VERIFICÁVEL** | `ffmpeg -encoders` no host lista `h264_nvenc` | Não é permitido subir containers nesta auditoria somente leitura. O pacote Debian Bookworm oficial não inclui nvenc por padrão. |
| **C.4** | Documentação de variáveis em .env.example | **OK** | `.env.example:24-42` | Contém todas as variáveis de worker, timeouts, modelos e aceleração. |
| **D.1** | Remoção de cabeçalhos de teste e heurísticas | **OK** | `backend/app/api/routers/video.py:303`. `git grep` por `X-Request-Accel` e `has_proxy_headers` = 0 | Utiliza exclusivamente `USE_NGINX_ACCEL`. |
| **D.2** | Proteção Anti-SSRF estrita com fail-closed | **OK** | `backend/app/api/routers/video.py:31-86`, `worker.py:154-156` | Valida IPv4 e IPv6 via `socket.getaddrinfo`, exige `ip.is_global`, falha fechado em exceções e revalida no worker. |
| **D.3** | Autenticação via URLs assinadas HMAC-SHA256 | **OK** | `backend/app/core/security.py:46-77`, `routers/video.py:240, 270`, `tests/test_api_endpoints.py:205` | Elimina tokens JWT na query string; links usam assinatura temporal HMAC de 300s (`?sig=...`). |
| **D.4** | Auditoria de vulnerabilidades e versão Python | **PARCIAL** | Host roda Python `3.14.7`; `pip-audit` não encontrado no PATH | O Dockerfile e CI usam Python 3.11, mas o ambiente host executa em 3.14.7; `pip-audit` não está instalado no ambiente local. |
| **D.5** | Alinhamento de documentação de TLS/HTTPS | **OK** | `README-DEPLOY.md:50-66` | Explica a separação de responsabilidades (Compose em HTTP na porta 80; terminação TLS no proxy de borda). |
| **E.1** | Remoção de bloco vazio de timed('subtitles') | **OK** | `backend/app/services/engine_service.py`. `git grep "timed('subtitles')"` = 0 | Bloco residual de 0s removido completamente. |
| **E.2** | Substituição de alert() por toasts acessíveis | **OK** | `frontend/js/ui.js:23-28` (`role="status"`/`"alert"`). `git grep "alert("` no frontend = 0 | Todos os 14 alerts nativos foram substituídos por notificações toast acessíveis com timeout e botão fechar. |
| **E.3** | Versionamento automatizado por hash SHA-256 | **OK** | `scripts/version_assets.py:25-47`, `tests/test_core_and_security.py:100` | Injeta `?v=<hash>` nos arquivos CSS e JS do `index.html`. |
| **E.4** | Coerência técnica dos documentos README | **OK** | `README.md:23, 127` e `README-DEPLOY.md:50-110` | Documenta `ALLOW_SQLITE_FALLBACK=true`, fila `clipmaker_tasks`, comandos de GPU e remove referências a caminhos locais. |
| **E.5** | Ausência de caminhos ou dados locais versionados | **OK** | `git grep -i "C:\\Users"` e `git grep -i "Documents\\"` = 0 | Nenhuma trilha de caminho local do host exposta nos arquivos do repositório. |
| **H1** | Débito de créditos por processamento | **AUSENTE** | `backend/app/db/db_service.py:134` (apenas `credits INT DEFAULT 60` na tabela) | Não há lógica de decremento de créditos nas rotas de upload ou worker. |
| **H2** | Marcação de clipes expirados no banco | **AUSENTE** | `scripts/cleanup.py:12-23` (apenas remove arquivos físicos do disco) | Não altera o status dos clipes para `EXPIRED` no banco de dados nem avisa o frontend. |
| **H3** | Instalação de fontes Montserrat no container | **AUSENTE** | `Dockerfile:35, 78` (apenas instala `ffmpeg` e `libglib2.0-0`) | Nenhuma fonte tipográfica personalizada é instalada via apt no container. |
| **H4** | Renderização de legendas dinâmicas em ASS | **AUSENTE** | `backend/app/services/video_service.py:100-140` | Gera legendas em formato `.srt` com tags `<b>...</b>`, sem suporte a estilos avançados `.ass`. |
| **H5** | Queima de hook_text no topo do clipe | **AUSENTE** | `backend/app/services/video_service.py:530` | `hook_text` é exibido nos cards da interface, mas não é renderizado no vídeo pelo FFmpeg. |
| **H6** | Interface "Meus Projetos" com listagem e delete | **AUSENTE** | `frontend/index.html` (não possui seção ou modal de listagem histórica de projetos) | Rota de backend `/api/projects` existe, mas não há tela correspondente no frontend. |
| **H7** | Exportação em lote (.zip) e link de share | **AUSENTE** | `backend/` e `frontend/` (sem rotas ou botões para exportação em lote) | Não implementado. |
| **H8** | Limpeza de loggers de debug e traceback | **PARCIAL** | `backend/app/services/ai_service.py:16`, `engine_service.py:12`, `video_service.py:10` | Configuração em pydantic-settings OK e sem print_exc, mas `logger.setLevel(logging.DEBUG)` ainda forçado nos 3 arquivos. |
| **H9** | Acessibilidade avançada em modais e tabs | **AUSENTE** | `frontend/js/app.js` e `ui.js` | Não possui aprisionamento de foco (*focus trap*), `role="tab"` ou navegação por teclado em radios. |
| **H10** | Consolidação de rotas no prefixo único /api/v1 | **AUSENTE** | `backend/app/main.py:58-69` | Mantém rotas duplicadas (`/api/video`, `/api/videos`, `/api/v1/video`, `/api/v1/videos`) por compatibilidade. |
| **DOC1** | Existência do gerador e arquivo Word | **OK** | `docs/ClipMaker_Documentacao.docx` (41.6 KB), `scripts/gerar_documentacao.py` | Ambos os arquivos existem no repositório. |
| **DOC2** | Cobertura de commits no histórico da docx | **PARCIAL** | `docs/ClipMaker_Documentacao.docx` tabela 2 cobre 26 commits até `b51c030` | O repositório possui 33 commits até `564e5ec`. Faltam 7 commits na tabela do documento Word. |
| **DOC3** | Capítulo 12 condizente com git status | **PARCIAL** | `docs/ClipMaker_Documentacao.docx` capítulo 12 cita 8 modificados e 2 untracked | O `git status` atual está 100% limpo; o documento Word ainda reflete alterações residuais da Etapa 4. |
| **DOC4** | Eliminação de menções a huey_ingest/render | **PARCIAL** | `docs/ClipMaker_Documentacao.docx` parágrafos p59 e p128 e `arch_diagram.png` | O docx e o script `gerar_documentacao.py` ainda citam `huey_ingest` e `huey_render` no texto e diagrama. |
| **DOC5** | Completude da matriz de lacunas de segurança | **PARCIAL** | `docs/ClipMaker_Documentacao.docx` seção 5.2 | Omite o fallback silencioso para `memory://` no rate limit e declarava SSRF como resolvido antes da Etapa D. |
| **DOC6** | Documentos alternativos em formato Markdown | **OK** | Não encontrados (`CHANGELOG.md`, `docs/ARQUITETURA.md`, etc.) | Registrados como "não gerados", em conformidade com as instruções do checklist. |
| **DOC7** | Rastreabilidade dos números de performance | **OK** | `docs/PERFORMANCE.md` Seções 3, 5, 10, 12 e 13 | 5 métricas analisadas e mapeadas no código; evidenciado que a Seção 12 mede a fila conteinerizada e não o benchmark direto. |

---

## 3. Itens Pulados ou Incompletos (Ordenados por Risco)

1. **[CRÍTICO] Fallback Silencioso do Rate Limiter para `memory://` (E3.6 / DOC5)**
   - **Localização:** `backend/app/api/deps.py:14-25`
   - **Motivo do Risco:** Se a conexão com o Redis cair temporariamente ou atingir timeout, a aplicação em produção passa a usar contadores isolados em memória local sem emitir erro fatal ou rejeitar tráfego desprotegido, permitindo burlar o rate limiting através de múltiplas instâncias da API.

2. **[ALTO] Pré-carregamento do Whisper Não Persistido na Memória do Worker (E1.4)**
   - **Localização:** `Dockerfile:111` e `docker-compose.prod.yml:152`
   - **Motivo do Risco:** O comando de inicialização executa `python -c 'preload_whisper_model()'` num subprocesso efêmero que encerra antes do `huey_consumer` iniciar; com isso, os modelos são baixados no disco, mas a alocação em VRAM/RAM é perdida, mantendo latência de carregamento (*cold start*) no primeiro job do worker.

3. **[ALTO] Documentação Word (.docx) Desatualizada em Relação ao Código Real (DOC2, DOC3, DOC4, DOC5)**
   - **Localização:** `docs/ClipMaker_Documentacao.docx` e `scripts/gerar_documentacao.py`
   - **Motivo do Risco:** O documento Word registra apenas 26 dos 33 commits, mantém parágrafos e diagramas citando filas zumbis (`huey_ingest`/`huey_render`) que foram unificadas na Etapa A, e afirma que o repositório possui 10 arquivos pendentes de commit quando a árvore Git está limpa.

4. **[MÉDIO] Discrepância na Mensagem de Erro de Senha Mínima entre Frontend e Backend (F1.11)**
   - **Localização:** `frontend/js/app.js:104` vs `backend/app/models/user.py:9`
   - **Motivo do Risco:** Quando um usuário digita uma senha com 7 caracteres, o backend rejeita com erro Pydantic de tamanho mínimo, mas a função `parseApiError` em `app.js` formata a mensagem para o usuário como *"A senha deve ter no mínimo 6 caracteres"*, gerando confusão e suporte desnecessário.

5. **[MÉDIO] Step de Banco de Dados no Pipeline de Integração Contínua (CI) Incompleto (G6)**
   - **Localização:** `.github/workflows/tests.yml:45`
   - **Motivo do Risco:** O workflow do GitHub Actions executa apenas `migrations/001_init.sql` no container PostgreSQL de teste, deixando de aplicar as migrações 002 a 006 no banco real do CI (os testes atualmente passam porque utilizam SQLite em memória nos fixtures de teste).

6. **[BAIXO] Forçamento de Nível DEBUG nos Módulos de Serviço (H8)**
   - **Localização:** `backend/app/services/ai_service.py:16`, `engine_service.py:12`, `video_service.py:10`
   - **Motivo do Risco:** A chamada explícita `logger.setLevel(logging.DEBUG)` sobrepõe a configuração centralizada de logs (`LOG_LEVEL=INFO`), podendo gerar volume excessivo de logs no container em produção.

---

## 4. Afirmações da Documentação sem Respaldo no Código

1. **Diagrama e Texto do DOCX Citando Múltiplas Filas Huey:**
   - **Afirmação no DOCX (p59, p128 e `arch_diagram.png`):** Afirma que existem três filas dedicadas no Redis: `huey_ingest`, `huey_render` e `huey (geral)`.
   - **Realidade no Código:** A Etapa A unificou a fila em uma única instância `huey = RedisHuey('clipmaker_tasks')` em `backend/app/worker/worker.py:26, 44`, consumida por `huey_consumer backend.app.worker.worker.huey`. As filas separadas foram completamente eliminadas do runtime.

2. **Capítulo 12 do DOCX sobre "Mudanças Não Commitadas":**
   - **Afirmação no DOCX (Capítulo 12):** Afirma que há 8 arquivos modificados e 2 arquivos untracked pendentes de commit relativos à Etapa 4.
   - **Realidade no Código:** O `git status` está perfeitamente limpo no commit `564e5ec`, cobrindo as Etapas A, B, C, D e E. As alterações citadas já estão consolidadas no histórico Git.

3. **Afirmação de Validação SSRF no DOCX Original:**
   - **Afirmação no DOCX (Capítulo 5.1):** Afirma que a proteção anti-SSRF utiliza `socket.gethostbyname()` para bloquear IPs privados.
   - **Realidade no Código:** O código foi atualizado na Etapa D para usar `socket.getaddrinfo()` com suporte completo a IPv4 e IPv6, exigindo `ip.is_global` e falhando fechado (`routers/video.py:31-86`). O DOCX precisa refletir a implementação atual.

4. **Status do Encoder NVENC no Container GPU (PERFORMANCE.md):**
   - **Afirmação no PERFORMANCE.md:** Considera o encoder `h264_nvenc` ativo dentro do container GPU da Etapa 1.
   - **Realidade no Código:** A imagem base do Dockerfile (`python:3.11-slim-bookworm`) instala o FFmpeg via `apt-get install -y ffmpeg`, pacote compilado pelo Debian sem suporte a NVENC. No host Windows o NVENC funciona nativamente, mas no container Linux requer compilação customizada com `nv-codec-headers` ou imagem específica.

---

## 5. Ordem Recomendada para Correção (Plano em 6 Passos)

1. **Passo 1 (Segurança): Corrigir Fallback Silencioso no Rate Limiter (`deps.py`)**
   - Em `backend/app/api/deps.py`, alterar `_get_limiter_storage_uri` para levantar exceção ou falhar de forma explícita caso `ENVIRONMENT == "production"` e o Redis esteja inacessível, impedindo o fallback silencioso para `memory://`.

2. **Passo 2 (Frontend UX): Harmonizar Mensagem de Senha Mínima (`app.js`)**
   - Em `frontend/js/app.js:104`, atualizar a string de `"A senha deve ter no mínimo 6 caracteres."` para `"A senha deve ter no mínimo 8 caracteres."`, igualando ao Pydantic e ao HTML.

3. **Passo 3 (CI / Devops): Atualizar Migrações no Workflow do GitHub Actions**
   - Em `.github/workflows/tests.yml:45`, executar todas as migrações `migrations/*.sql` em ordem (ou via `scripts/migrate.sh`) no serviço PostgreSQL de teste, garantindo paridade com produção.

4. **Passo 4 (Worker / Cold Start): Ajustar Preload em Memória do Whisper**
   - Importar e invocar `preload_whisper_model()` dentro do próprio ciclo de vida do worker ou no início do `worker.py` quando executado em processo consumidor contínuo.

5. **Passo 5 (Limpeza): Remover `setLevel(DEBUG)` Hardcoded nos Serviços**
   - Remover as linhas `logger.setLevel(logging.DEBUG)` de `ai_service.py`, `engine_service.py` e `video_service.py`, permitindo que `LOG_LEVEL` da configuração central governe o nível de verbosidade.

6. **Passo 6 (Documentação): Atualizar e Regenerar `docs/ClipMaker_Documentacao.docx`**
   - Ajustar `scripts/gerar_documentacao.py` para refletir a fila unificada `huey` (`clipmaker_tasks`), ler dinamicamente o status limpo do Git no Capítulo 12, incorporar os 33 commits e gerar o arquivo Word atualizado.
