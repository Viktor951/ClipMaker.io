# 🎬 ClipMaker.io

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-blue?logo=python&style=for-the-badge" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-0.104-009688?logo=fastapi&style=for-the-badge" alt="FastAPI" />
  <img src="https://img.shields.io/badge/PostgreSQL-15-336791?logo=postgresql&style=for-the-badge" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis&style=for-the-badge" alt="Redis" />
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&style=for-the-badge" alt="Docker" />
</p>

O **ClipMaker.io** é uma plataforma SaaS alimentada por Inteligência Artificial projetada para transformar vídeos longos do YouTube (ou uploads locais) em clipes curtos, dinâmicos e altamente virais, prontos para o TikTok, Reels e Shorts. 

O sistema orquestra tecnologias de ponta para analisar contexto, rastrear rostos e aplicar legendas dinâmicas, operando de forma assíncrona para garantir alta disponibilidade.

---

## ✨ Principais Funcionalidades

- 🧠 **Detecção de Virais com IA:** Utiliza **Faster-Whisper** para gerar transcrições ultrarrápidas do áudio e o **Google Gemini 1.5** para identificar e justificar (hook_reason) os momentos de maior retenção.
- 🎯 **Face Tracking Automático:** Integra **OpenCV** para rastrear rostos e manter a ação sempre centralizada na transição do vídeo horizontal (16:9) para vertical (9:16).
- 💬 **Legendas Dinâmicas Embutidas:** Engine própria usando **FFmpeg** que sincroniza palavras exatas extraídas do Whisper diretamente no vídeo renderizado.
- 🚀 **Arquitetura Assíncrona:** Fila baseada em **Redis e Huey**, permitindo processamento massivo de vídeos pesados em _background_ sem travar a interface.

---

## 🏗️ Arquitetura do Sistema

O projeto segue princípios de **Clean Architecture**, dividindo responsabilidades claras entre serviços:

1. **Frontend (Nginx / VanillaJS):** Roda na porta `3000` isolado, oferecendo uma UI responsiva e se comunicando com o backend através do proxy do Nginx para evitar falhas de CORS.
2. **API (FastAPI):** Exposta na porta `8000`, valida tokens JWT, recebe uploads gigantes em _chunks_, salva no banco de dados e delega a renderização.
3. **Task Queue (Redis):** Gerencia a fila de processamento de vídeos, essencial para não estourar a memória (VRAM/RAM) do servidor.
4. **Worker (Huey Consumer):** Processo dedicado que retira tarefas da fila, orquestra o Pipeline de IA (Whisper -> Gemini -> OpenCV -> FFmpeg) e devolve o vídeo finalizado.
5. **Database (PostgreSQL):** Mantém as sessões, usuários, e o histórico persistente do status de processamento de cada projeto.

---

## 📂 Estrutura de Diretórios

```text
/
├── backend/
│   ├── app/
│   │   ├── api/routers/  # Endpoints RESTful separados (auth.py, video.py)
│   │   ├── core/         # Configuração (.env) e segurança (JWT)
│   │   ├── db/           # Conexão AsyncPG com o PostgreSQL
│   │   ├── models/       # Definições de Schemas Pydantic
│   │   ├── services/     # Lógica de IA, Video e Engine Core
│   │   └── worker/       # Configuração da fila e Huey Tasks
│   └── main.py           # Entrypoint da API
├── frontend/             # Vanilla JS, CSS e arquivo nginx.conf
├── scripts/              # Scripts utilitários (ex: inicializar o banco)
└── docker-compose.yml    # Orquestração do ambiente de desenvolvimento
```

---

## 🛠️ Pré-requisitos

Para rodar o projeto de forma impecável, você só precisa de:
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (ou Docker + Docker Compose) instalado.
- Conta e Chave de API do [Google Gemini (Google AI Studio)](https://aistudio.google.com/).

---

## ⚡ Início Rápido (Quickstart)

Siga os passos abaixo para subir a arquitetura completa em seu computador:

### 1. Configure as Variáveis de Ambiente
Copie o template de segurança e preencha a sua chave do Gemini. As demais senhas e credenciais (como o Postgres e o Redis) já vêm pré-preenchidas para funcionar magicamente via Docker Compose local.
```bash
cp backend/.env.example backend/.env
```
👉 *Abra o arquivo recém-criado `backend/.env` e troque o campo `GEMINI_API_KEY` pela sua chave real.*

### 2. Suba a Infraestrutura (Docker)
Construa e inicie todos os containers (Postgres, Redis, API, Worker e Frontend):
```bash
docker-compose up -d --build
```

### 3. Inicialize as Tabelas do Banco de Dados
Apenas na **primeira vez** que você rodar o projeto, será necessário criar as tabelas do PostgreSQL. Basta executar:
```bash
docker-compose exec api python scripts/init_db.py
```

### 4. Acesso ao SaaS
Pronto! Tudo está no ar:
- **Painel do Usuário (SaaS):** Acesse [http://localhost:3000](http://localhost:3000) no seu navegador.
- **Documentação da API:** Acesse [http://localhost:8000/docs](http://localhost:8000/docs) para ver a interface interativa do Swagger FastAPI.

---

## 🔍 Troubleshooting (Solução de Problemas)

### Quero acompanhar o processamento do vídeo, onde vejo?
Como o vídeo é processado de forma assíncrona pelo **Worker**, você precisa olhar os logs do container do worker para ver o progresso (FFmpeg, Whisper, LLM):
```bash
docker-compose logs -f worker
```

### Ocorreu um erro de "Out Of Memory (VRAM)" na IA
O **Faster-Whisper** consome recursos da Placa de Vídeo. Certifique-se de que nenhum outro programa pesado está aberto concorrentemente, ou ajuste o modelo no código (`backend/app/services/ai_service.py`) de `large-v2` para `base` ou `small`.

### Quero parar a aplicação e limpar o banco
Para interromper a infraestrutura e destruir os volumes persistentes do banco de dados (apagando usuários e clipes):
```bash
docker-compose down -v
```

---

<p align="center">Desenvolvido com ☕ e focado na estabilidade!</p>