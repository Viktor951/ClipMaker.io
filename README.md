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
- ⚡ **Processamento Assíncrono:** Fila de tarefas pesadas com **Huey** (Redis em produção e fallback para SQLite local em desenvolvimento).
- 📱 **Editor de Clipes Integrado:** Ajuste fino de palavras, timing, estilo de legenda e aspect ratio direto no navegador.
- 🛡️ **Segurança por Padrão:** Autenticação JWT com Bcrypt, queries parametrizadas (AsyncPG), proteção estrita contra SSRF em URLs externas, rate limiting e containers com usuário não-root.

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
                         (Dados e Projetos)               (Fila de Tarefas)
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

### Opção 1: Execução com Docker (Recomendada para Produção)

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
   > No Windows (PowerShell), você pode executar `powershell -ExecutionPolicy Bypass -File scripts\setup-prod.ps1` para gerar chaves criptográficas fortes e criar as pastas persistentes automaticamente.

3. **Inicie os containers:**
   ```bash
   docker compose -f docker-compose.prod.yml up -d --build
   ```

4. **Acesse a aplicação:**
   - Web: [http://localhost](http://localhost)
   - Verificação de Saúde da API: [http://localhost/api/health](http://localhost/api/health)

---

### Opção 2: Desenvolvimento Local (sem Docker)

O backend possui suporte a fallback para SQLite em desenvolvimento, permitindo testar e desenvolver rapidamente sem precisar subir PostgreSQL ou Redis:

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

3. **Configure o `.env`:**
   ```bash
   cp .env.example .env
   # Preencha a GEMINI_API_KEY no arquivo .env
   ```

4. **Inicie a API:**
   ```bash
   uvicorn backend.app.main:app --reload --port 8000
   ```
   > Em modo local, acesse [http://localhost:8000](http://localhost:8000). O FastAPI serve a interface estática automaticamente.

5. **(Opcional) Inicie o worker de processamento:**
   ```bash
   huey_consumer backend.app.worker.worker.huey -w 1 -k thread
   ```

---

## 🧪 Testes Automatizados

A suíte de testes valida rotas da API, autenticação, persistência e verificações de segurança:

```bash
pytest -v
```

---

## ⚙️ Variáveis de Ambiente

| Variável | Descrição | Padrão |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | Chave de API do Google Gemini (análise e ranqueamento de clipes) | Obrigatório |
| `SECRET_KEY` | Chave secreta para assinatura dos tokens JWT | Obrigatório |
| `ENVIRONMENT` | Ambiente de execução (`production` ou `development`) | `production` |
| `DOMAIN` | Domínio configurado para o proxy Nginx | `localhost` |
| `DATA_ROOT` | Caminho de armazenamento persistente para vídeos e cache | `D:/docker-data/clipmaker` |
| `POSTGRES_USER` / `PASSWORD` | Credenciais de acesso ao PostgreSQL | `clipmaker` |
| `REDIS_PASSWORD` | Senha de autenticação do Redis | Obrigatório |

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