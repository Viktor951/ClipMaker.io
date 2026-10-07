# 🎬 ClipMaker.io

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-blue?logo=python&style=for-the-badge" alt="Python" />
  <img src="https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql&style=for-the-badge" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&style=for-the-badge" alt="Redis" />
  <img src="https://img.shields.io/badge/Nginx-1.25-009639?logo=nginx&style=for-the-badge" alt="Nginx" />
  <img src="https://img.shields.io/badge/Docker-Production_Ready-2496ED?logo=docker&style=for-the-badge" alt="Docker" />
</p>

O **ClipMaker.io** é uma plataforma SaaS alimentada por Inteligência Artificial projetada para transformar vídeos longos do YouTube (ou uploads locais) em clipes curtos, dinâmicos e altamente virais, prontos para TikTok, Reels e Shorts.

O sistema orquestra tecnologias de ponta para analisar contexto, rastrear rostos via visão computacional e aplicar legendas dinâmicas sincronizadas palavra por palavra, operando de forma assíncrona para garantir alta performance e resiliência em produção.

---

## ✨ Principais Funcionalidades

- 🧠 **Detecção de Virais com IA:** Transcrição veloz com **Faster-Whisper** e inteligência de ganchos (hook reason/viral score) via **Google Gemini**.
- 🎯 **Face Tracking Automático:** Integração com **OpenCV** para identificar rostos e manter o sujeito centralizado na conversão para formato vertical (9:16) ou quadrado (1:1).
- 💬 **Legendas Dinâmicas Embutidas:** Engine própria com **FFmpeg** que gera e queima legendas estilizadas palavra por palavra sincronizadas com o áudio.
- 🚀 **Arquitetura Assíncrona & Worker Dedicado:** Fila gerenciada com **Redis e Huey**, permitindo processamento pesado sem bloquear requisições da API.
- 🔒 **Segurança Corporativa:**
  - Autenticação JWT com senhas hasheadas em Bcrypt.
  - Rate Limiting integrado contra abusos.
  - Proteção estrita contra SSRF em downloads por URL.
  - CORS restrito, headers HTTP defensivos (nosniff, DENY framing).
  - Execução segura em containers Docker com usuário não-root (`appuser`, UID 10001) e privilégios rebaixados (`cap_drop: ALL`).

---

## 🏗️ Arquitetura do Sistema

```
                        [ Cliente / Navegador ]
                                  │
                                  ▼
                 [ Reverse Proxy & Web / Nginx: 80 ]
                  (Gzip, Headers Defensivos, SPA)
                                  │
                  ┌───────────────┴───────────────┐
                  ▼                               ▼
         / (Frontend Estático)            /api/* (Proxy HTTP)
        [ VanillaJS & HTML5 ]                     │
                    ▼
         / (Frontend Estático)            /api/* (Proxy HTTP)
        [ VanillaJS & HTML5 ]                     │
                                                  ▼
                                      [ API FastAPI (Uvicorn) ]
                                      (Porta 8000 Interna)
                                                  │
                                  ┌───────────────┴───────────────┐
                                  ▼                               ▼
                        [ PostgreSQL 15 ]                  [ Redis 7 ]
                      (Migrações Automáticas)            (Fila de Tarefas AOF)
                                                                  ▲
                                                                  │
                                                      [ Worker Huey Consumer ]
                                                      (Whisper + OpenCV + FFmpeg)
```

---

## 📂 Estrutura de Diretórios

```text
.
├── backend/
│   ├── app/
│   │   ├── api/routers/      # Endpoints REST (auth.py, video.py, project.py)
│   │   ├── core/             # Configurações centralizadas, logging JSON e segurança JWT
│   │   ├── db/               # Conexões assíncronas com AsyncPG e queries seguras
│   │   ├── models/           # Schemas tipados com Pydantic v2
│   │   ├── services/         # IA (Whisper/Gemini), Visão Computacional e FFmpeg
│   │   └── worker/           # Tasks assíncronas do Huey Consumer
│   └── requirements.txt      # Dependências pinadas de produção
├── frontend/                 # Interface Web Vanilla (HTML5, CSS moderno, JS)
├── migrations/               # Scripts SQL versionados e idempotentes (001_init.sql)
├── scripts/                  # Automação de setup, migração e rotinas de limpeza
├── tests/                    # Suíte de testes automatizados e segurança
├── Dockerfile                # Multi-stage build otimizado com usuário não-root
├── docker-compose.prod.yml   # Stack completa de produção com limites e saúde
└── README-DEPLOY.md          # Guia operacional detalhado (incluindo persistência no Disco D:)
```

---

## ⚡ Início Rápido (Produção)

### 1. Inicialize as Variáveis de Ambiente e Pastas
Execute o script de automação para gerar credenciais criptográficas fortes e criar as pastas persistentes:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-prod.ps1
```

> Edite o arquivo `.env` gerado para inserir sua chave `GEMINI_API_KEY` do Google AI Studio e ajustar o `DOMAIN` (padrão: `localhost`).

### 2. Suba a Stack Completa
```powershell
docker compose -f docker-compose.prod.yml up -d --build
```

O compose executa automaticamente:
1. Subida do PostgreSQL e Redis com healthchecks ativos.
2. Execução transacional das migrações de banco (`migrations/001_init.sql`).
3. Inicialização da API FastAPI, Worker de IA, Container de Limpeza e Frontend/Reverse Proxy Nginx.

### 3. Acesso à Aplicação
- **Aplicação Web:** Acesse [http://localhost](http://localhost) (ou seu domínio configurado).
- **Verificação de Saúde:** [http://localhost/api/health](http://localhost/api/health) ou [http://localhost/health](http://localhost/health)

---

## 🛡️ Matriz de Segurança e Proteções Ativas

| Vetor de Ataque / Risco | Mecanismo de Mitigação | Componente / Arquivo |
| :--- | :--- | :--- |
| **SSRF (Server-Side Request Forgery)** | Validação de scheme (`http`/`https`), bloqueio de IPs privados/loopback/cloud metadata e bloqueio de DNS para nomes de containers Docker internos. | [`backend/app/api/routers/video.py`](file:///c:/Users/Jo%C3%A3o%20Victor/Documents/Antigravity%20Projects/ClipMakerAI/backend/app/api/routers/video.py) |
| **Injeção de Comandos (CLI Injection)** | Argumentos do `yt-dlp` e `ffmpeg` passados como lista sanitizada com separador de parâmetros `--` para impedir injeção de flags maliciosas. | [`backend/app/services/video_service.py`](file:///c:/Users/Jo%C3%A3o%20Victor/Documents/Antigravity%20Projects/ClipMakerAI/backend/app/services/video_service.py) |
| **SQL Injection (SQLi)** | Consultas 100% parametrizadas via `AsyncPG` (`$1, $2, ...`) e blocos transacionais controlados. Sem interpolação de strings. | [`backend/app/db/db_service.py`](file:///c:/Users/Jo%C3%A3o%20Victor/Documents/Antigravity%20Projects/ClipMakerAI/backend/app/db/db_service.py) |
| **Path Traversal / LFI** | Nomes de arquivos gerados como UUIDv4 e uso estrito de `os.path.basename()` em endpoints de download. | [`backend/app/api/routers/video.py`](file:///c:/Users/Jo%C3%A3o%20Victor/Documents/Antigravity%20Projects/ClipMakerAI/backend/app/api/routers/video.py) |
| **XSS (Cross-Site Scripting)** | Higienização de strings dinâmicas no frontend antes da injeção no DOM com `escapeHtml()`. | [`frontend/js/ui.js`](file:///c:/Users/Jo%C3%A3o%20Victor/Documents/Antigravity%20Projects/ClipMakerAI/frontend/js/ui.js) |
| **Força Bruta / Abuso de Recursos** | Rate Limiting em memória/Redis gerenciado via `slowapi` (`5 req/min` em rotas de auth e processamento). | [`backend/app/api/deps.py`](file:///c:/Users/Jo%C3%A3o%20Victor/Documents/Antigravity%20Projects/ClipMakerAI/backend/app/api/deps.py) |
| **Vazamento de Segredos** | Auditoria de `.gitignore` cobrindo todas as variantes de `.env`, bancos SQLite e arquivos temporários. | [`.gitignore`](file:///c:/Users/Jo%C3%A3o%20Victor/Documents/Antigravity%20Projects/ClipMakerAI/.gitignore) |
| **Ataques a Nível de Container** | Execução com usuário sem privilégios (`appuser:10001`), remoção de capabilities Linux (`cap_drop: ALL`) e banco isolado em rede interna. | [`docker-compose.prod.yml`](file:///c:/Users/Jo%C3%A3o%20Victor/Documents/Antigravity%20Projects/ClipMakerAI/docker-compose.prod.yml) |
| **Clickjacking & MIME-sniffing** | Headers de segurança `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` e proteção XSS injetados pelo Nginx. | [`frontend/nginx.conf`](file:///c:/Users/Jo%C3%A3o%20Victor/Documents/Antigravity%20Projects/ClipMakerAI/frontend/nginx.conf) |


---

## 🧪 Testes Automatizados

A suíte cobre autenticação, ciclo de vida de JWT, proteção anti-SSRF, proporções de vídeo e formatação de legendas.

### Executar Localmente com Pytest:
```bash
pip install -r backend/requirements.txt
pip install -r requirements-dev.txt
pytest -v
```

### Executar no Container Docker (com imagem de produção):
```bash
docker run --rm -v "${PWD}:/app" clipmakerai:prod python -c "

from tests.test_core_and_security import (
    test_password_hashing,
    test_jwt_token_lifecycle,
    test_anti_ssrf_url_validation,
    test_video_crop_and_scale_dimensions,
    test_srt_timestamp_formatting
)
test_password_hashing()
test_jwt_token_lifecycle()
test_anti_ssrf_url_validation()
test_video_crop_and_scale_dimensions()
test_srt_timestamp_formatting()
print('✅ Todos os testes de segurança e processamento passaram com sucesso!')
"
```

---

## 💾 Persistência de Dados no Disco D:
O projeto está configurado para salvar arquivos pesados (vídeos enviados, clipes renderizados, cache de modelos Whisper e persistência do Redis) diretamente no diretório:
- `D:\docker-data\clipmaker\`

Consulte o [README-DEPLOY.md](README-DEPLOY.md) para detalhes sobre backup, recuperação e movimentação do disco de dados do Docker Desktop.

---

<p align="center">Construído com excelência técnica e foco em produção 🚀</p>