# ClipMakerAI — Deploy de Produção (Docker + disco D:)

## 1. Primeira execução

```powershell
# 1) Cria D:\docker-data\clipmaker\{videos,cache,logs,redis,caddy} e gera .env com segredos fortes
#    (se já existir um .env antigo, renomeie-o antes: ele tem SECRET_KEY fraca)
powershell -ExecutionPolicy Bypass -File scripts\setup-prod.ps1

# 2) Edite .env: DOMAIN (localhost para teste) e GEMINI_API_KEY

# 3) Validar, buildar e subir
docker compose -f docker-compose.prod.yml config -q
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps        # todos "healthy" (migrate = Exited 0)
docker compose -f docker-compose.prod.yml logs -f api worker
```

Acesse `https://localhost` (certificado interno: aceite o aviso) ou seu domínio (Let's Encrypt automático; portas 80/443 devem estar abertas).

## 2. Testar persistência no D:

```powershell
# Dados aparecem no D:
dir D:\docker-data\clipmaker\videos ; dir D:\docker-data\clipmaker\redis

# Prova de persistência: derruba tudo e sobe de novo, dados devem continuar
"teste" | Out-File D:\docker-data\clipmaker\videos\persist.txt
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec api ls /app/backend/temp_videos   # persist.txt presente
```

Verificações de segurança:
```powershell
docker compose -f docker-compose.prod.yml exec api id          # uid=10001(appuser)
docker compose -f docker-compose.prod.yml exec db psql -U $env:POSTGRES_USER -d $env:POSTGRES_DB -c "\dt"
docker stats --no-stream                                         # limites de memória/CPU
curl.exe -k -I https://localhost                                 # HSTS, nosniff...
```

## 3. Postgres e o disco D:

Bind mount do Postgres em NTFS (`D:/...`) via Docker Desktop/WSL2 costuma falhar no `initdb` (permissões `chmod`/`chown` não suportadas) e é lento. Por isso o Postgres usa **volume nomeado**, que vive dentro do `docker_data.vhdx` do Docker Desktop. Com esse disco no D: (seção 4), o banco também fica no D:. Todo o resto (vídeos, cache de modelos, Redis, certificados) já está em bind mounts no D:.

Backup lógico do banco para o D:
```powershell
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U $env:POSTGRES_USER $env:POSTGRES_DB > D:\docker-data\backups\clipmaker_$(Get-Date -f yyyyMMdd).sql
```

## 4. Mover o disco do Docker Desktop de C: para D:

**Método recomendado (validado):** *Settings → Resources → Advanced → Disk image location* → `D:\docker-data` → Apply & Restart. O Docker copia os discos sozinho (leva alguns minutos) e cria a pasta `DockerDesktopWSL` dentro do caminho escolhido:

```
D:\docker-data\DockerDesktopWSL\disk\docker_data.vhdx   # imagens, volumes, build cache (~11 GB)
D:\docker-data\DockerDesktopWSL\main\ext4.vhdx          # distro docker-desktop
```

Validação:
```powershell
Get-ChildItem D:\docker-data\DockerDesktopWSL -Recurse -Filter *.vhdx | Select FullName,@{n='GB';e={[math]::Round($_.Length/1GB,2)}}
Get-ChildItem "$env:LOCALAPPDATA\Docker" -Recurse -Filter *.vhdx   # deve retornar vazio
docker images                                                       # imagens preservadas
```

> **Não use `wsl --export/--import` para isso.** Nas versões atuais, esse comando só move a distro `docker-desktop` (~90 MB). O `docker_data.vhdx`, que ocupa o espaço de verdade, não é uma distro registrada e não é alcançado por ele.

Alternativa manual (se a opção não existir nas Settings): feche o Docker Desktop, rode `wsl --shutdown`, copie `%LOCALAPPDATA%\Docker\wsl\disk` para o D: com `robocopy /E`, renomeie a pasta original para `disk.bak`, crie um junction com `New-Item -ItemType Junction` apontando para a cópia no D:, abra o Docker, confira `docker images` e só então apague o `disk.bak`.

Compactar o vhdx depois de limpezas: `docker system prune -af --volumes` (**cuidado: apaga volumes não usados**), `wsl --shutdown`, `Optimize-VHD -Path <docker_data.vhdx> -Mode Full` (Hyper-V) ou `diskpart` → `compact vdisk`.

## 5. Operação

| Tarefa | Comando |
|---|---|
| Atualizar | `git pull; docker compose -f docker-compose.prod.yml up -d --build` (migrações rodam sozinhas) |
| Nova migração | criar `migrations/002_descricao.sql` (idempotente) |
| Logs | `docker compose -f docker-compose.prod.yml logs -f --tail=100 api` (JSON em stdout) |
| Parar | `docker compose -f docker-compose.prod.yml down` (sem `-v`!) |
| Testes | `pip install -r backend/requirements.txt -r backend/requirements-dev.txt; pytest -v` |

## 6. Pendências recomendadas (não alteradas por risco de regressão sem testes)

- Atualizar dependências com CVEs conhecidas: `python-multipart` (≥0.0.9), `python-jose` (≥3.4), `fastapi/starlette`, `opencv-python-headless` (≥4.8.1.78), `numpy`.
- `video.py`: `/upload-url/` usa `subprocess.run` bloqueante (até 30 min) dentro de endpoint `async` — trava o event loop; mover o download para a task Huey. Também validar o host da URL contra SSRF (IPs privados/localhost).
- Mensagens `detail=f"...{str(e)}"` vazam erros internos ao cliente.
- `slowapi` usa memória local: use `storage_uri=REDIS_URL` se escalar para >1 worker da API.
- Tags `<video src="/api/v1/video/download/...">` não enviam o header `Authorization`; o download exige Bearer token (verifique se o player funciona).
- Para brotli, Caddy requer build customizado (`caddy add-package`); zstd/gzip já estão ativos.
