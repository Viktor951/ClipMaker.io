# Como rodar o projeto

Este projeto utiliza processamento em segundo plano para extração de clipes usando Huey. Para que o projeto funcione corretamente (e os clipes sejam gerados), você **precisa rodar dois processos simultaneamente**:

1. **API (FastAPI)**: Recebe os vídeos e interage com o frontend.
2. **Worker (Huey)**: Processa os vídeos pesados (Whisper, ffmpeg, etc) em background.

### Executando com o script automático (Recomendado no Windows)

Para facilitar, criamos um script que inicia os dois processos automaticamente:
Basta executar o script `start_all.ps1` no PowerShell:

```powershell
.\start_all.ps1
```

### Executando manualmente

Se preferir rodar manualmente em terminais separados, execute:

**Terminal 1 (API):**
```bash
uvicorn backend.main:app --reload
```

**Terminal 2 (Worker):**
```bash
python huey_consumer.py backend.worker.huey -w 1
```