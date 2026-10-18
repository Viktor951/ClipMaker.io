# ClipMakerAI — Deploy de Produção (Docker + disco D:)

## 1. Primeira execução

```powershell
# 1) Cria D:\docker-data\clipmaker\{videos,cache,logs,redis,caddy} e gera .env com segredos fortes
#    (se já existir um .env antigo, renomeie-o antes: ele tem SECRET_KEY fraca)
powershell -ExecutionPolicy Bypass -File scripts\setup-prod.ps1

# 2) Edite .env: DOMAIN (localhost para teste) e GEMINI_API_KEY

# 3) Validar e subir os containers:

# ── Modo SEM GPU (Padrão CPU):
docker compose -f docker-compose.prod.yml config -q
docker compose -f docker-compose.prod.yml up -d --build

# ── Modo COM GPU (NVIDIA CUDA + NVENC):
docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml config -q
docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml up -d --build

# 4) Verificar status dos containers
docker compose -f docker-compose.prod.yml ps        # todos "healthy" (migrate = Exited 0)
docker compose -f docker-compose.prod.yml logs -f api worker
```

Acesse `http://localhost` (porta 80) para desenvolvimento e testes locais. Para ambientes de produção com domínio público, consulte a seção 3 abaixo para configuração de TLS/HTTPS via proxy externo.

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
curl.exe -I http://localhost                                     # nosniff, X-Frame-Options...
```

## 3. TLS / HTTPS e Terminação SSL em Produção

O `docker-compose.prod.yml` expõe o serviço de frontend (Nginx) na porta **80 (HTTP)**. O suporte a HTTPS e certificados SSL deve ser gerenciado na camada de **proxy reverso externo de borda**:

1. **Opções Recomendadas para TLS:**
   - **Cloudflare (Proxy / Cloudflare Tunnel):** modo SSL *Full (Strict)* com HSTS e redirecionamento HTTPS ativados diretamente no painel Cloudflare.
   - **AWS Application Load Balancer (ALB) ou GCP HTTPS Load Balancer:** terminação SSL na porta 443 com certificado ACM e target group apontando para a porta 80 da instância.
   - **Proxy Reverso no Host (Caddy, Traefik ou Nginx + Certbot):** instalado diretamente no host Linux/Windows, gerenciando certificados Let's Encrypt automáticos nas portas 80/443 públicas e fazendo `proxy_pass http://127.0.0.1:80`.

2. **Por que manter HTTP no Compose?**
   - Evita acoplamento e overhead desnecessário de containers intermediários (ex.: Caddy em frente ao Nginx).
   - Não interfere no desenvolvimento ou testes locais onde certificados válidos não existem.
   - Segue as boas práticas de microsserviços (Twelve-Factor App): a terminação TLS pertence à infraestrutura de borda (Ingress).

3. **Política de HSTS:**
   - O cabeçalho `Strict-Transport-Security` (HSTS) só deve ser injetado quando houver TLS real (pelo proxy de terminação externa). O Nginx interno na porta 80 não envia HSTS para evitar rejeições ou quebras em conexões locais HTTP (RFC 6797).

## 4. Postgres e o disco D:

Bind mount do Postgres em NTFS (`D:/...`) via Docker Desktop/WSL2 costuma falhar no `initdb` (permissões `chmod`/`chown` não suportadas) e é lento. Por isso o Postgres usa **volume nomeado**, que vive dentro do `docker_data.vhdx` do Docker Desktop. Com esse disco no D: (seção 5), o banco também fica no D:. Todo o resto (vídeos, cache de modelos, Redis) já está em bind mounts no D:.

Backup lógico do banco para o D:
```powershell
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U $env:POSTGRES_USER $env:POSTGRES_DB > D:\docker-data\backups\clipmaker_$(Get-Date -f yyyyMMdd).sql
```

## 5. Mover o disco do Docker Desktop de C: para D:

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

## 6. Operação

| Tarefa | Comando |
|---|---|
| Atualizar (CPU) | `git pull; docker compose -f docker-compose.prod.yml up -d --build` |
| Atualizar (GPU) | `git pull; docker compose -f docker-compose.prod.yml -f docker-compose.gpu.yml up -d --build` |
| Nova migração | criar `migrations/00X_nome.sql` (idempotente) |
| Logs | `docker compose -f docker-compose.prod.yml logs -f --tail=100 api` (JSON em stdout) |
| Parar | `docker compose -f docker-compose.prod.yml down` (sem `-v`!) |
| Testes | `python -m pytest -v` |

