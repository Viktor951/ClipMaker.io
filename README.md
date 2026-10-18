# 🎬 ClipMaker.io

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&style=for-the-badge" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-0.104-009688?logo=fastapi&style=for-the-badge" alt="FastAPI" />
  <img src="https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql&style=for-the-badge" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&style=for-the-badge" alt="Redis" />
  <img src="https://img.shields.io/badge/Nginx-1.25-009639?logo=nginx&style=for-the-badge" alt="Nginx" />
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&style=for-the-badge" alt="Docker" />
</p>

O **ClipMaker.io** é uma plataforma alimentada por Inteligência Artificial projetada para transformar vídeos longos (do YouTube ou uploads locais) em clipes curtos verticais (9:16) ou quadrados (1:1), altamente dinâmicos e prontos para publicação no TikTok, Instagram Reels e YouTube Shorts.

A plataforma automatiza todo o pipeline de pós-produção: transcrição de áudio, detecção de ganchos virais com IA, reenquadramento facial inteligente (face tracking) e renderização de legendas dinâmicas sincronizadas palavra por palavra.

---

## ✨ Principais Funcionalidades

- 🧠 **Detecção Inteligente de Momentos Virais:** Transcrição veloz com **Faster-Whisper** e ranqueamento contextual de ganchos virais via **Google Gemini**.
- 🎯 **Face Tracking Automático:** Detecção facial com **OpenCV** para manter o interlocutor centralizado no enquadramento vertical (9:16).
- 💬 **Legendas Dinâmicas Sincronizadas:** Renderização de legendas palavra por palavra com estilos personalizáveis diretamente no vídeo via **FFmpeg**.
- ⚡ **Processamento Assíncrono:** Fila mestre única de tarefas com **Huey** (`clipmaker_tasks`) sobre Redis em produção. Em desenvolvimento local fora do Docker, suporta fallback seguro para SQLite caso `ALLOW_SQLITE_FALLBACK=true` e `ENVIRONMENT != "production"`.
- 📱 **Editor de Clipes Integrado:** Ajuste fino de palavras, timing, estilo de legenda e aspect ratio direto no navegador com toasts acessíveis.
- 🛡️ **Segurança por Padrão:** Autenticação JWT com Bcrypt, queries parametrizadas (AsyncPG), proteção estrita contra SSRF com resolução DNS global, rate limiting distribuído no Redis e containers sem privilégios root.

---

## 🎨 Identidade Visual & Design System

A interface do ClipMaker.io adota a identidade **Studio Engine**, com estética técnica cinematográfica de alto contraste e foco no desempenho:

### Marca Unificada
- **Nome:** **ClipMaker.io**
- **Símbolo:** Ícone vetorial com enquadramento horizontal widescreen transicionado para corte vertical 9:16 em Studio Lime com marcador play.
- **Assets de Marca:** Favicon SVG escalável, PNGs multi-resolução (`16x16`, `32x32`), `apple-touch-icon.png` (180x180) e Social Card `og-image.png` (1200x630).

### Paleta de Cores e Tokens (`frontend/css/tokens.css`)
| Token | Cor Hex | Uso Principal |
| :--- | :--- | :--- |
| `--surface-0` | `#090A0D` | Fundo principal da página (Deep Carbon) |
| `--surface-1` | `#111318` | Superfície de cartões, modais e rodapé |
| `--surface-2` | `#181B22` | Entradas de formulário, pills e containers secundários |
| `--surface-3` | `#222631` | Trilhas de progresso e estados de hover sutil |
| `--accent-ai` | `#00F076` | Destaque principal (Studio Lime) — CTAs, progresso, badges virais |
| `--text-100` | `#F4F6F9` | Títulos e texto de máxima ênfase (contraste 18.28:1) |
| `--text-200` | `#C2C8D2` | Subtítulos, descrições e ganchos (contraste 11.05:1) |
| `--text-300` | `#8E96A6` | Metadados e placeholders legíveis (contraste 5.80:1) |
| `--color-error` | `#EF4444` | Alertas e toasts de erro |
| `--accent-warn` | `#F59E0B` | Scores virais médios (<90) |

### Tipografia
- **Títulos e Display:** `Space Grotesk` (Google Fonts, pesos 600/700, tracking `-0.015em`, espaçamento calibrado sem sobreposição de caracteres).
- **Interface e Corpo:** `Inter` (Google Fonts, pesos 400/500/600, alta legibilidade em todas as densidades de tela).
- **Métricas e Dados:** `JetBrains Mono` (Google Fonts, pesos 500/600/700, utilizado em scores virais, durações, timestamps e badges técnicos).

### Sistema de Ícones Vetoriais
- **Zero Dependências Pesadas:** Ícones via máscaras CSS (`mask-image: url(...)`) em SVG monocromático (`frontend/css/icons.css`), eliminando o carregamento de arquivos pesados de fontes (~500 KB economizados).

### Acessibilidade (WCAG 2.1 AA)
- **Contraste Auditado:** 100% dos pares texto/fundo aprovados no critério AA, com títulos e textos primários atingindo nível AAA.
- **Navegação por Teclado:** Foco acessível global com anel de destaque em Studio Lime (`:focus-visible { outline: 2px solid var(--accent-ai); outline-offset: 2px; }`).
- **Semântica:** Abas com `role="tablist"` / `role="tab"` / `aria-selected`, seletores de proporção com `tabindex="0"`, toasts com `role="status"` ou `role="alert"`.

---

## 🏗️ Arquitetura do Sistema

```text
                        [ Cliente / Navegador ]
                                  │
                                  ▼
                     [ Reverse Proxy (Nginx) ]
                    Porta 80 / Gzip / Security Headers
                                  │
                 ┌────────────────┴────────────────┐
                 ▼                                 ▼
         / (Frontend SPA)                 /api/* (Proxy HTTP)
        [ HTML5 / CSS / JS ]                       │
                                                   ▼
                                       [ API FastAPI (Uvicorn) ]
                                                   │
                                   ┌───────────────┴───────────────┐
                                   ▼                               ▼
                          [ PostgreSQL 15 ]                   [ Redis 7 ]
                         (Dados e Projetos)            (Fila Única: Huey)
                                                                   │
                                                                   ▼
                                                         [ Worker Huey ]
                                                   (Whisper + OpenCV + FFmpeg)
```

---

## 🚀 Como Executar

### Pré-requisitos
- [Docker](https://www.docker.com/) e Docker Compose (para execução em containers) **OU**
- [Python 3.10+](https://www.python.org/) e [FFmpeg](https://ffmpeg.org/) (para execução local)
- Chave de API do [Google AI Studio](https://aistudio.google.com/) (Gemini)

---

### Opção 1: Execução com Docker (Produção)

1. **Clone o repositório:**
   ```bash
   git clone https://github.com/Viktor951/ClipMaker.io.git
   cd ClipMaker.io
   ```

2. **Configure as variáveis de ambiente:**
   Copie o arquivo de exemplo e preencha sua chave do Gemini:
   ```bash
   cp .env.example .env
   ```
   > No Windows (PowerShell), você pode executar `powershell -ExecutionPolicy Bypass -File scripts\setup-prod.ps1` para gerar chaves criptográficas fortes e criar as pastas persistentes (`D:\docker-data\clipmaker\{videos,cache,logs,redis}`) automaticamente.

3. **Inicie os containers:**
   - **Modo Padrão em CPU (sem GPU dedicada):**
     ```bash
     docker compose -f docker-compose.prod.yml up -d --build
     ```
   - **Modo com Aceleração por GPU NVIDIA (CUDA + NVENC):**
     ```bash
     docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml up -d --build
     ```

4. **Acesse a aplicação e portas:**
   - **Frontend e API (Nginx):** [http://localhost](http://localhost) (porta **80**, com entrega acelerada `X-Accel-Redirect` em `/internal_videos/`).
   - **Saúde da Aplicação:** [http://localhost/api/health](http://localhost/api/health)
   - **Configurações e Limites Dinâmicos:** [http://localhost/api/config](http://localhost/api/config) (fornece tamanho máximo de upload e duração permitida ao frontend).

5. **Versionamento e Invalidação de Cache (Assets Frontend):**
   O Nginx aplica cache longo (1 ano) em arquivos `.css` e `.js`. Ao alterar o frontend, execute:
   ```bash
   python scripts/version_assets.py
   ```
   O script injeta automaticamente hashes do conteúdo (`?v=<hash>`) no `index.html`.

---

### Opção 2: Desenvolvimento Local (sem Docker)

O backend possui suporte a fallback para SQLite exclusivamente em desenvolvimento:

1. **Crie e ative um ambiente virtual:**
   ```bash
   python -m venv venv
   # Linux/macOS:
   source venv/bin/activate
   # Windows:
   .\venv\Scripts\activate
   ```

2. **Instale as dependências:**
   ```bash
   pip install -r backend/requirements.txt
   pip install -r requirements-dev.txt
   ```

3. **Configure o `.env` para fallback:**
   ```dotenv
   ENVIRONMENT=development
   ALLOW_SQLITE_FALLBACK=true
   GEMINI_API_KEY=sua_chave_aqui
   SECRET_KEY=sua_chave_secreta_local
   ```
   > **Atenção:** Se `ENVIRONMENT=production` ou se `ALLOW_SQLITE_FALLBACK` não for `true`, o fallback é estritamente bloqueado para evitar uso inadvertido de SQLite em produção.

4. **Inicie a API:**
   ```bash
   uvicorn backend.app.main:app --reload --port 8000
   ```
   > Em modo local direto, acesse [http://localhost:8000](http://localhost:8000). O FastAPI serve a interface estática automaticamente.

5. **(Opcional) Inicie o worker de processamento na fila única:**
   ```bash
   huey_consumer backend.app.worker.worker.huey -w 1 -k thread
   ```

---

## 🧪 Testes Automatizados

A suíte de testes valida rotas da API, autenticação JWT, integridade de tarefas, watchdog, proteção SSRF, dimensionamento de corte e versionamento de assets:

```bash
python -m pytest -v
```

---

## ⚙️ Variáveis de Ambiente

| Variável | Descrição | Padrão |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | Chave de API do Google Gemini (análise e ranqueamento de clipes) | Obrigatório |
| `SECRET_KEY` | Chave secreta para assinatura dos tokens JWT | Obrigatório |
| `ENVIRONMENT` | Ambiente de execução (`production` ou `development`) | `production` |
| `ALLOW_SQLITE_FALLBACK` | Permite banco SQLite local se Postgres/Redis indisponíveis (apenas em dev) | `false` |
| `DOMAIN` | Domínio configurado para o proxy Nginx | `localhost` |
| `DATA_ROOT` | Caminho de armazenamento persistente para cache e Redis | `D:/docker-data/clipmaker` |
| `POSTGRES_USER` / `PASSWORD` | Credenciais de acesso ao PostgreSQL | `clipmaker` |
| `REDIS_PASSWORD` | Senha de autenticação do Redis | Obrigatório |
| `WORKER_CPUS` | Cota de núcleos de CPU para o container worker | `4.0` |
| `WORKER_MEM_LIMIT` | Limite de memória RAM para o container worker | `6g` |
| `WHISPER_MODEL` | Modelo Whisper (`small` para GPU, `base` para CPU, `tiny`) | `small` (GPU) / `base` (CPU) |
| `FFMPEG_PRESET` | Preset de encoding FFmpeg (`ultrafast` em CPU; `p4` em NVENC) | `ultrafast` |
| `FFMPEG_CRF` | Fator de taxa constante / qualidade visual do FFmpeg | `23` |
| `RENDER_PARALLELISM` | Paralelismo de renderização de clipes | `2` |
| `MAX_CONCURRENT_JOBS_PER_USER` | Máximo de processamentos simultâneos por usuário | `2` |
| `PROJECT_STALE_MINUTES` | Limite de inatividade para watchdog marcar projeto como FAILED | `60` |
| `JOB_TIMEOUT_MINUTES` | Tempo limite máximo de execução de um job | `120` |
| `USE_NGINX_ACCEL` | Ativa envio acelerado de vídeo via cabeçalho `X-Accel-Redirect` | `true` em prod, `false` local |

---

## 📂 Estrutura do Projeto

```text
.
├── backend/
│   ├── app/
│   │   ├── api/routers/      # Endpoints REST (auth, projects, videos)
│   │   ├── core/             # Configurações, JWT e logging estruturado
│   │   ├── db/               # Camada de dados (AsyncPG e fallback SQLite)
│   │   ├── models/           # Schemas Pydantic v2
│   │   ├── services/         # Serviços de IA (Whisper/Gemini), OpenCV e FFmpeg
│   │   └── worker/           # Tasks assíncronas do Huey Consumer
│   └── requirements.txt      # Dependências do backend
├── frontend/                 # Interface Web (HTML5, CSS moderno e Vanilla JS)
├── migrations/               # Migrações SQL idempotentes do banco de dados
├── scripts/                  # Scripts de automação (setup, limpeza)
├── tests/                    # Suíte de testes automatizados com pytest
├── docker-compose.prod.yml   # Orquestração completa de produção
└── README-DEPLOY.md          # Guia operacional avançado (backup, disco host, etc.)
```

---

## 📄 Licença

Distribuído sob a licença [MIT](LICENSE).