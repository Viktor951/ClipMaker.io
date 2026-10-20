# Relatório de Revisão de Código Morto, Resíduos em Disco e no Docker
**Documento de Diagnóstico — Fase 3, 4 e 5**
Data: 20/10/2026 | Repositório: `ClipMakerAI`

> [!IMPORTANT]
> **REGRAS DE SEGURANÇA SEGUIDAS À RISCA:**
> - NENHUM arquivo, pasta, imagem, volume ou container foi apagado previamente.
> - O arquivo real `.env`, o volume real `clipmaker-prod_postgres_data` e o diretório `.git` estão estritamente protegidos.
> - Um backup completo do banco de dados PostgreSQL foi gerado previamente via `pg_dump`: `backups/backup_clipmaker_db_pre_limpeza.sql` (343.957 bytes).
> - Aguardando aprovação explícita ("sim", por grupo) antes de qualquer exclusão.

---

## 1. Código Python Morto e Imports Não Usados (Ruff & Vulture)

| Item | Local | Evidência de que não é usado | Classificação | Tamanho estimado |
| :--- | :--- | :--- | :--- | :--- |
| `decode_access_token` | `backend/app/api/routers/video.py:18` | Importado mas nunca referenciado no módulo (Ruff F401). | **SEGURO-APAGAR** | ~25 B |
| `get_user_by_email` | `backend/app/api/routers/video.py:23` | Importado mas nunca referenciado no módulo (Ruff F401). | **SEGURO-APAGAR** | ~20 B |
| `sys` | `backend/app/db/db_service.py:2` | Importado mas nunca referenciado no módulo (Ruff F401). | **SEGURO-APAGAR** | ~10 B |
| `_rate_limit_exceeded_handler` | `backend/app/main.py:9` | Importado mas substituído pelo handler customizado `RateLimitExceeded` (Ruff F401). | **SEGURO-APAGAR** | ~35 B |
| `shutil` | `backend/app/services/engine_service.py:4` | Importado mas nunca utilizado no arquivo (Ruff F401). | **SEGURO-APAGAR** | ~10 B |
| `Dict, Any, List` | `backend/app/services/engine_service.py:8` | Type hints importados de `typing` mas não usados nas anotações (Ruff F401). | **SEGURO-APAGAR** | ~20 B |
| `traceback` | `backend/app/worker/worker.py:6` | Importado mas não utilizado (erros logados via `logger.exception`) (Ruff F401). | **SEGURO-APAGAR** | ~15 B |
| `output_clean_path` | `backend/app/worker/worker.py:356` | Variável atribuída com caminho mas nunca lida na execução de `re_render_clip_task` (Ruff F841). | **SEGURO-APAGAR** | ~35 B |
| `needs_full_render` | `backend/app/worker/worker.py:378-380` | Flag calculada mas não consumida pelo pipeline de re-render (Ruff F841). | **SEGURO-APAGAR** | ~80 B |
| `res_c` e `res_p` | `backend/app/db/db_service.py:1077,1086` | Atribuições locais do retorno de `db.execute` sem leitura subsequente (Ruff F841). | **SEGURO-APAGAR** | ~20 B |
| `update_clip_words_and_style` | `backend/app/db/db_service.py:808` | Função antiga de atualização de palavras/estilo substituída por `update_clip_render_details`. | **PRECISA-DECISÃO** | ~750 B |
| `cleanup_old_db_records` | `backend/app/db/db_service.py:987` | Função legada não invocada pelo `scripts/cleanup.py` atual (que usa `mark_file_records_expired`). | **PRECISA-DECISÃO** | ~1.2 KB |
| `highlighted` | `backend/app/api/routers/project.py:36` | Campo opcional no modelo Pydantic `ClipResponse` para compatibilidade com frontends futuros. | **MANTER** | ~20 B |

---

## 2. Duplicações e Arquivos Redundantes

| Item | Local | Evidência de que não é usado | Classificação | Tamanho |
| :--- | :--- | :--- | :--- | :--- |
| `requirements-dev.txt` | Raiz (`requirements-dev.txt`) | Duplicado de `backend/requirements-dev.txt`. A raiz contém apenas 4 linhas com `>=`. | **PRECISA-DECISÃO** | 121 B |
| `backend/requirements-dev.txt` | `backend/requirements-dev.txt` | Contém dependências com versões pinned (`pytest==7.4.3`, etc.). Recomendado unificar na raiz e referenciar no Dockerfile se necessário. | **MANTER** | 159 B |
| `revisao_codigo.txt` | Raiz (`revisao_codigo.txt`) | Saída de diff temporário gerada durante auditoria anterior. Não versionada, não consumida por código. | **SEGURO-APAGAR** | 1.552.537 B (1,48 MB) |
| `scripts/e2e/evidencias/` | `scripts/e2e/evidencias` | Diretório vazio legado de testes e2e anteriores. | **SEGURO-APAGAR** | 0 B |
| `scripts/security/` | `scripts/security/` | Scripts de teste de estresse e segurança executados na auditoria (ex.: `test_s1_jwt.py`, `achados.json`, `canary_server.py`). | **MANTER** | 123.684 B (120 KB) |

---

## 3. Referências Obsoletas ("Caddy" e "huey_ingest/render")

| Item | Local | Evidência de obsolescência | Classificação | Tamanho |
| :--- | :--- | :--- | :--- | :--- |
| Comentários sobre Caddy | `.dockerignore:48` | Menciona `Frontend (servido pelo Caddy...)` quando a stack utiliza Nginx Alpine. | **SEGURO-APAGAR** | ~50 B |
| Regra Caddyfile | `.dockerignore:38` | `Caddyfile` não existe mais na raiz do repositório. | **SEGURO-APAGAR** | ~12 B |
| Citação de Caddy no host | `README-DEPLOY.md:57,60` | Menciona "Caddy, Traefik ou Nginx" como opções externas opcionais para TLS no host. | **MANTER** (como doc informativa de host) | - |
| Aliases `huey_ingest`, `huey_render` | `backend/app/worker/worker.py:45-46,55-56` | A fila foi unificada para `clipmaker_tasks`. Os aliases existem apenas para compatibilidade retroativa com `tests/test_queue_routing.py`. | **MANTER** (garante compatibilidade) | ~100 B |
| Menções a filas dedicadas | `scripts/gerar_documentacao.py:150,937,1219` | O gerador do docx ainda desenha diagramas com "Filas Huey: huey_ingest, huey_render". | **PRECISA-DECISÃO** | ~350 B |

---

## 4. Endpoints Backend, Aliases e Rotas

| Item / Rota | Local | Situação e Consumo | Classificação |
| :--- | :--- | :--- | :--- |
| Rotas `/api/v1/*` | `auth.py`, `project.py`, `video.py`, `main.py` | O frontend consome rotas `/api/*`. As rotas `/api/v1/*` são usadas extensivamente pela suíte automatizada `tests/test_api_endpoints.py` e servem como versionamento estável da API. | **MANTER** |
| `/api/video/upload` | `backend/app/api/routers/video.py:144` | Alias para compatibilidade com clientes que chamam `/api/video` no singular. O front usa `/api/videos/upload`. | **MANTER** |
| `/api/video/upload-url` | `backend/app/api/routers/video.py:240` | Alias para compatibilidade com clientes antigos. O front usa `/api/videos/upload-url/`. | **MANTER** |

---

## 5. Seletores CSS e Classes Dinâmicas

| Seletor | Arquivo | Situação no HTML / JS | Classificação |
| :--- | :--- | :--- | :--- |
| `.status-analyzing`, `.status-transcribing`, `.status-downloading`, `.status-rendering`, `.status-completed` | `frontend/css/components.css` | Classes dinâmicas de estados de processo de vídeo (`status-${status.toLowerCase()}`). | **MANTER** |
| `.toast-info`, `.toast-error`, `.toast-success` | `frontend/css/components.css` | Criadas dinamicamente via JS na função `showToast(msg, type)`. | **MANTER** |
| `.badge-ai` | `frontend/css/components.css` | Tag AI para marcação de clipes gerados. | **MANTER** |
| `.hero-badge`, `.pulse-glow` | `frontend/css/layout.css`, `animations.css` | Efeitos de destaque visual na landing page. | **MANTER** |
| `.desktop-only` | `frontend/css/responsive.css` | Utilitário responsivo para ocultação em mobile. | **MANTER** |

---

## 6. Variáveis de Ambiente (`.env.example` vs `config.py`)

| Variável | Em `.env.example` | Em `config.py` | Situação e Racional | Classificação |
| :--- | :--- | :--- | :--- | :--- |
| `USE_NGINX_ACCEL` | Sim | Não (lido via `os.getenv` em `video.py`) | Recomendado formalizar a variável dentro de `Settings` em `config.py` para consistência. | **PRECISA-DECISÃO** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Não | Sim (`10080`) | Recomendado documentar em `.env.example`. | **MANTER** |
| `MAX_VIDEO_DIMENSION` | Não | Sim (`2160`) | Recomendado documentar em `.env.example`. | **MANTER** |
| `TURNSTILE_SECRET_KEY` | Não | Sim (`""`) | Opcional para captcha Turnstile. | **MANTER** |
| `JOB_TIMEOUT_MINUTES` | Sim (`120`) | Sim (`90`) | Divergência de default (120 vs 90 min). Alinhar para 120 min. | **PRECISA-DECISÃO** |

---

## 7. Resíduos no Disco e Workspace (Fase 4)

| Grupo / Item | Caminho | Motivo / Descrição | Tamanho | Classificação |
| :--- | :--- | :--- | :--- | :--- |
| **Grupo Disco A**: Vídeos temporários | `backend/temp_videos/*` | Arquivos de upload e render de testes antigos fora de retenção. | **976,27 MB** | **SEGURO-APAGAR** (manter pasta vazia com `.gitkeep`) |
| **Grupo Disco B**: Scratch e testes manuais | `scratch/` | Scripts de diagnóstico temporários (`check_db.py`, `list_users.py`, etc.) criados durante investigação. | **63,81 MB** | **SEGURO-APAGAR** |
| **Grupo Disco C**: Bancos locais SQLite obsoletos | `dev.db*`, `huey*.db`, `backend/huey_queue.db*` | Bancos SQLite de desenvolvimento/testes locais criados antes da stack Docker. O stack real usa Postgres. | **4,92 MB** | **SEGURO-APAGAR** |
| **Grupo Disco D**: Caches de build e testes | `.pytest_cache/`, `.ruff_cache/`, `**/__pycache__/` | Bytecodes Python compilados e caches de ferramentas locais. | **0,75 MB** | **SEGURO-APAGAR** |
| **Grupo Disco E**: Diff temporário de auditoria | `revisao_codigo.txt` | Arquivo texto gerado para revisão de commits. | **1,48 MB** | **SEGURO-APAGAR** |
| **Grupo Disco F**: Binários de documentação | `docs/ClipMaker_Documentacao.docx`, `docs/arch_diagram.png`, `docs/AUDITORIA_SEGURANCA.docx` | Documentos compilados Word e diagramas de arquitetura versionados. | **1,81 MB** | **PRECISA-DECISÃO** (o usuário prefere manter no git ou apagar?) |
| **TOTAL LIBERÁVEL EM DISCO** | — | — | **~1.047 MB (~1,05 GB)** | — |

---

## 8. Resíduos no Docker (Fase 5)

| Grupo / Recurso | Identificador / Nome | Descrição / Pertencimento | Tamanho | Classificação |
| :--- | :--- | :--- | :--- | :--- |
| **Grupo Docker A**: Container parado | `clipmaker-prod-migrate-1` (`b203a93ae263`) | Container one-shot de migração finalizado com sucesso. | 0 B | **SEGURO-APAGAR** (`docker rm`) |
| **Grupo Docker B**: Imagens antigas/não usadas | `clipmakerai-api:latest`, `clipmakerai-worker:latest`, `caddy:2-alpine`, `mwader/static-ffmpeg:6.1`, `python:3.11-slim`, `alpine:latest`, `alpine:3.19` | Imagens de builds anteriores e Caddy obsoleto. O stack real usa `clipmakerai:prod`, `clipmakerai:prod-gpu`, `postgres:15-alpine`, `redis:7-alpine`, `nginx:alpine`. | **~5,11 GB** | **SEGURO-APAGAR** (`docker rmi`) |
| **Grupo Docker C**: Build Cache | Cache de compilação do BuildKit (`docker builder du`) | Camadas intermediárias de builds Docker acumuladas. | **30,89 GB** | **SEGURO-APAGAR** (`docker builder prune`) |
| **Grupo Docker D**: Volumes obsoletos | `clipmakerai_postgres_data`, `clipmaker_temp_videos`, volumes anônimos (`8cf4...`, `171b...`, `be31...`) | Volumes de stacks antigos ou anônimos. O volume real em uso é `clipmaker-prod_postgres_data` e `clipmaker-prod_clipmaker_temp_videos`. | **~96 MB** | **SEGURO-APAGAR** (Backup garantido com pg_dump) |
| **Grupo Docker E**: Redes obsoletas | `clipmakerai_default` (`5631def015f7`) | Rede do compose anterior `clipmakerai`. A rede real é `clipmaker-prod_default`. | 0 B | **SEGURO-APAGAR** (`docker network rm`) |
| **TOTAL LIBERÁVEL NO DOCKER** | — | — | **~36,09 GB** | — |

---

## 9. Próximos Passos e Grupos para Confirmação do Usuário

Conforme a **Regra 3**, solicitamos sua confirmação ("sim" para cada grupo ou "todos"):
1. **Grupo Código Python**: Remover os 10 imports/variáveis sem uso identificados pelo Ruff e vulture?
2. **Grupo Disco (A, B, C, D, E)**: Remover `backend/temp_videos/*` (mantendo pasta), `scratch/`, `revisao_codigo.txt`, `dev.db*`, `huey*.db` e caches `.pytest_cache`/`.ruff_cache` (~1,05 GB)?
3. **Grupo Docs (F)**: Manter ou remover `docs/ClipMaker_Documentacao.docx` e `arch_diagram.png`?
4. **Grupo Docker (A, B, C, D, E)**: Limpar container `migrate`, imagens antigas (~5,1 GB), build cache (~30,8 GB), volumes obsoletos e rede `clipmakerai_default`?
