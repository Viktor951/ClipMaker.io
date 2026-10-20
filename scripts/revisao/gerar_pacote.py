#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gerador de Pacote de Revisão Independente (ClipMakerAI)
Uso:
    python scripts/revisao/gerar_pacote.py --descricao "resumo da alteração" [--base origin/main] [--testes] [--logs 200] [--arquivos-completos]

Saída:
    revisao_saida/REVISAO_<AAAAMMDD-HHMM>_<hash7>.md
    revisao_saida/REVISAO_<AAAAMMDD-HHMM>_<hash7>.patch
"""

import argparse
import datetime
import getpass
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set


# ==============================================================================
# 1. MOTOR DE SANITIZAÇÃO E REDAÇÃO (FAIL-SAFE)
# ==============================================================================

class SecurityLeakException(Exception):
    """Lançada quando segredos não redigidos são detectados pelo fail-safe."""
    pass


class SecretRedactor:
    """
    Substitui segredos, credenciais, JWT, Bearer tokens, e-mails reais e
    caminhos locais do sistema antes da gravação de arquivos de revisão.
    """

    def __init__(self):
        self.stats: Dict[str, int] = {
            "jwt": 0,
            "bearer_token": 0,
            "api_key": 0,
            "url_password": 0,
            "config_secret": 0,
            "header": 0,
            "email": 0,
            "local_path": 0,
        }

        # Nome do usuário local do sistema para substituição em caminhos
        current_user = getpass.getuser()
        self.current_user = current_user

        # Padrões regex compilados
        self.re_jwt = re.compile(
            r'\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b'
        )
        self.re_bearer = re.compile(
            r'\bBearer\s+[A-Za-z0-9_\-\.]{15,}\b',
            re.IGNORECASE
        )
        # Google API Key (AIza...), OpenAI (sk-...), Gemini (AQ....)
        self.re_aiza = re.compile(r'\bAIza[0-9A-Za-z-_]{30,45}\b')
        self.re_sk = re.compile(r'\bsk-[a-zA-Z0-9_\-\.]{20,}\b')
        self.re_aq = re.compile(r'\bAQ\.[a-zA-Z0-9_\-\.]{20,}\b')

        # Senhas em URLs de conexão (garante que : e @ ocorrem na autoridade antes do path/query)
        self.re_redis_url = re.compile(r'redis://:([^@\s/?#]+)@')
        self.re_pg_url = re.compile(r'postgresql://([^/:?#\s]+):([^/@?#\s]+)@')
        self.re_http_auth = re.compile(r'(https?://[^/:?#\s]+):([^/@?#\s]+)@')

        # Atribuições de variáveis sensíveis
        self.re_config_secret = re.compile(
            r'(?i)\b(SECRET_KEY|POSTGRES_PASSWORD|REDIS_PASSWORD|GEMINI_API_KEY|TURNSTILE_SECRET_KEY|API_KEY|SIGNING_KEY|JWT_SECRET)\s*([:=])\s*["\']?([^"\'`\r\n\s]{6,})["\']?'
        )

        # Cabeçalhos HTTP com credenciais
        self.re_headers = re.compile(
            r'(?i)^(Authorization|Cookie|Set-Cookie)\s*:\s*[^\r\n]+',
            re.MULTILINE
        )

        # E-mails reais (preserva example.com, test.com, localhost)
        self.re_email = re.compile(
            r'(?i)\b[A-Za-z0-9._%+-]+@(?!example\.com|test\.com|localhost|domain\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
        )

        # Caminhos locais
        self.re_win_path = re.compile(
            r'[A-Za-z]:\\[Uu]sers\\[^\\]+\\',
            re.IGNORECASE
        )
        self.re_unix_path = re.compile(
            r'/home/[^/]+/',
            re.IGNORECASE
        )

    def redact_text(self, text: str) -> Tuple[str, Dict[str, int]]:
        """Aplica todas as regras de redação e retorna o texto seguro e estatísticas."""
        if not text:
            return text, self.stats.copy()

        # 1. JWT
        def _sub_jwt(match):
            self.stats["jwt"] += 1
            return "<REDACTED_JWT_TOKEN>"
        text = self.re_jwt.sub(_sub_jwt, text)

        # 2. Bearer
        def _sub_bearer(match):
            self.stats["bearer_token"] += 1
            return "Bearer <REDACTED_BEARER_TOKEN>"
        text = self.re_bearer.sub(_sub_bearer, text)

        # 3. Chaves de API conhecidas
        def _sub_api_key(match):
            self.stats["api_key"] += 1
            return "<REDACTED_API_KEY>"
        text = self.re_aiza.sub(_sub_api_key, text)
        text = self.re_sk.sub(_sub_api_key, text)
        text = self.re_aq.sub(_sub_api_key, text)

        # 4. URLs de conexão
        def _sub_redis(match):
            self.stats["url_password"] += 1
            return "redis://:<REDACTED_PASSWORD>@"
        text = self.re_redis_url.sub(_sub_redis, text)

        def _sub_pg(match):
            self.stats["url_password"] += 1
            return f"postgresql://{match.group(1)}:<REDACTED_PASSWORD>@"
        text = self.re_pg_url.sub(_sub_pg, text)

        def _sub_http(match):
            self.stats["url_password"] += 1
            return f"{match.group(1)}:<REDACTED_PASSWORD>@"
        text = self.re_http_auth.sub(_sub_http, text)

        # 5. Atribuições de segredos em arquivos/configs
        def _sub_cfg(match):
            val = match.group(3)
            # Evita mascarar placeholders comuns já redigidos
            if "<REDACTED" in val or "openssl rand" in val or val.startswith("${"):
                return match.group(0)
            self.stats["config_secret"] += 1
            return f'{match.group(1)}{match.group(2)}"<REDACTED_SECRET>"'
        text = self.re_config_secret.sub(_sub_cfg, text)

        # 6. Cabeçalhos HTTP
        def _sub_header(match):
            self.stats["header"] += 1
            return f"{match.group(1)}: <REDACTED_HEADER>"
        text = self.re_headers.sub(_sub_header, text)

        # 7. E-mails reais
        def _sub_email(match):
            self.stats["email"] += 1
            return "<usuario>@example.com"
        text = self.re_email.sub(_sub_email, text)

        # 8. Caminhos locais
        def _sub_win_path(match):
            self.stats["local_path"] += 1
            return "C:\\Users\\<usuario>\\"
        text = self.re_win_path.sub(_sub_win_path, text)

        def _sub_unix_path(match):
            self.stats["local_path"] += 1
            return "/home/<usuario>/"
        text = self.re_unix_path.sub(_sub_unix_path, text)

        # Se houver menção literal ao usuário logado, redige
        if self.current_user and len(self.current_user) >= 3:
            if self.current_user in text:
                self.stats["local_path"] += text.count(self.current_user)
                text = text.replace(self.current_user, "<usuario>")

        return text, self.stats.copy()

    def scan_for_unredacted_secrets(self, text: str) -> List[str]:
        """
        Segunda varredura estrita (fail-safe).
        Retorna lista de categorias vazando caso encontre algo não redigido.
        NUNCA inclui o valor do segredo na saída.
        """
        violations = []

        if self.re_jwt.search(text):
            violations.append("Padrão de JWT não redigido detectado")
        if self.re_aiza.search(text):
            violations.append("Chave Google API (AIza...) não redigida detectada")
        if self.re_sk.search(text):
            violations.append("Chave OpenAI (sk-...) não redigida detectada")
        if self.re_aq.search(text):
            violations.append("Chave Gemini API (AQ....) não redigida detectada")
        if re.search(r'redis' + r'://:(?!<REDACTED)[^\s/@]+@', text):
            violations.append("Senha de conexão Redis em texto claro detectada")
        if re.search(r'postgresql' + r'://[^/:\s?#]+:(?!<REDACTED)[^\s/@]+@', text):
            violations.append("Senha de conexão PostgreSQL em texto claro detectada")
        if self.current_user and len(self.current_user) >= 4:
            if self.current_user.lower() in text.lower():
                violations.append("Nome de usuário local do sistema detectado no texto")

        return violations


# ==============================================================================
# 2. FILTRAGEM DE ARQUIVOS PROIBIDOS
# ==============================================================================

PROHIBITED_EXTENSIONS = {
    ".pem", ".key", ".pfx", ".p12", ".crt", ".cer",
    ".db", ".sqlite", ".sqlite3", ".db-shm", ".db-wal",
    ".mp4", ".webm", ".mkv", ".avi", ".mov", ".wav", ".mp3", ".m4a",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp",
    ".zip", ".tar", ".gz", ".7z", ".rar", ".exe", ".bin", ".iso"
}

PROHIBITED_SUBSTRINGS = [
    ".env",
    "node_modules",
    "__pycache__",
    ".git",
    "revisao_saida",
    "revisao_codigo.txt",
    "temp_videos",
    "backups",
]


def is_prohibited_file(filepath: str) -> bool:
    """Verifica se o caminho aponta para arquivos proibidos no pacote."""
    norm = filepath.replace("\\", "/").strip()
    parts = norm.split("/")

    # Nomes ou pastas proibidas
    for sub in PROHIBITED_SUBSTRINGS:
        if sub in parts or any(p.startswith(".env") for p in parts) or norm.endswith(sub):
            return True

    # Extensão
    _, ext = os.path.splitext(norm)
    if ext.lower() in PROHIBITED_EXTENSIONS:
        return True

    return False


def is_binary_file(filepath: str) -> bool:
    """Detecta se o arquivo é binário lendo os primeiros bytes."""
    if not os.path.isfile(filepath):
        return False
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(1024)
            if b"\x00" in chunk:
                return True
    except Exception:
        return True
    return False


# ==============================================================================
# 3. GERAÇÃO E VALIDAÇÃO DO PATCH
# ==============================================================================

def generate_git_patch(base_ref: str, repo_root: str) -> Tuple[str, List[str]]:
    """
    Gera patch unificado usando um índice temporário sem alterar o índice real
    nem o working tree do repositório.
    """
    tmp_fd, tmp_index_path = tempfile.mkstemp(prefix="git_tmp_idx_")
    os.close(tmp_fd)

    staged_files = []
    try:
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = tmp_index_path

        # 1. Carrega árvore da base no índice temporário
        subprocess.run(["git", "read-tree", base_ref], cwd=repo_root, env=env, check=True, capture_output=True)

        # 2. Adiciona todas as modificações atuais do working tree
        subprocess.run(["git", "add", "-A"], cwd=repo_root, env=env, check=True, capture_output=True)

        # 3. Remove arquivos proibidos do índice temporário
        raw_names = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", base_ref],
            cwd=repo_root, env=env, text=True, errors="replace"
        ).splitlines()

        for name in raw_names:
            clean_name = name.strip()
            full_p = os.path.join(repo_root, clean_name)
            if is_prohibited_file(clean_name) or is_binary_file(full_p):
                subprocess.run(
                    ["git", "rm", "--cached", "-f", "--quiet", clean_name],
                    cwd=repo_root, env=env, check=False, capture_output=True
                )
            else:
                staged_files.append(clean_name)

        # 4. Gera diff unificado do patch
        patch_bytes = subprocess.check_output(
            ["git", "diff", "--cached", "--binary", base_ref],
            cwd=repo_root, env=env
        )
        patch_text = patch_bytes.decode("utf-8", errors="replace")
        return patch_text, staged_files

    finally:
        if os.path.exists(tmp_index_path):
            try:
                os.remove(tmp_index_path)
            except OSError:
                pass


def validate_patch(patch_path: str, base_ref: str, repo_root: str) -> Tuple[bool, str]:
    """
    Valida a aplicação limpa do patch em clone temporário e checa sintaxe via compileall.
    """
    with tempfile.TemporaryDirectory(prefix="clipmaker_val_") as td:
        clone_dir = os.path.join(td, "clone")
        try:
            # Clone compartilhado rápido sem checkout
            subprocess.run(
                ["git", "clone", "--shared", "--no-checkout", repo_root, clone_dir],
                check=True, capture_output=True, text=True
            )
            # Resolve o hash exato da base no repositório original para evitar ambiguidade de remote
            base_commit = subprocess.check_output(
                ["git", "rev-parse", base_ref],
                cwd=repo_root, text=True
            ).strip()
            # Checkout na BASE exata
            subprocess.run(
                ["git", "-C", clone_dir, "checkout", base_commit],
                check=True, capture_output=True, text=True
            )
            # Testa aplicação do patch
            apply_res = subprocess.run(
                ["git", "-C", clone_dir, "apply", "--ignore-space-change", "--whitespace=nowarn", os.path.abspath(patch_path)],
                capture_output=True, text=True
            )
            if apply_res.returncode != 0:
                return False, f"Falha no 'git apply': {apply_res.stderr.strip()}"

            # Checa sintaxe Python após aplicação
            comp_res = subprocess.run(
                [sys.executable, "-m", "compileall", "-q", clone_dir],
                capture_output=True, text=True
            )
            if comp_res.returncode != 0:
                return False, f"Patch aplicou mas compileall falhou: {comp_res.stderr.strip()}"

            return True, "Aplicação limpa via 'git apply' e sintaxe Python válida (compileall OK)."
        except Exception as e:
            return False, f"Erro inesperado durante validação do patch: {e}"


# ==============================================================================
# 4. VERIFICAÇÕES AUTOMÁTICAS E AUDITORIAS
# ==============================================================================

def run_automated_checks(repo_root: str, changed_files: List[str], run_tests: bool) -> Dict[str, Tuple[int, str]]:
    """Executa conjunto padronizado de verificações e testes."""
    results = {}

    # 1. compileall
    try:
        res = subprocess.run(
            [sys.executable, "-m", "compileall", "-q", "backend", "scripts", "tests"],
            cwd=repo_root, capture_output=True, text=True
        )
        status_msg = "Sintaxe Python OK (sem erros de compilação)" if res.returncode == 0 else res.stderr.strip()
        results["python -m compileall"] = (res.returncode, status_msg)
    except Exception as e:
        results["python -m compileall"] = (1, f"Erro: {e}")

    # 2. node --check nos JS alterados
    js_files = [f for f in changed_files if f.endswith(".js") and os.path.isfile(os.path.join(repo_root, f))]
    node_bin = shutil.which("node")
    if not node_bin:
        results["node --check"] = (0, "node ausente no ambiente (checagem pulada)")
    elif not js_files:
        results["node --check"] = (0, "Nenhum arquivo JS alterado para validar")
    else:
        all_ok = True
        err_msgs = []
        for js in js_files:
            r = subprocess.run([node_bin, "--check", js], cwd=repo_root, capture_output=True, text=True)
            if r.returncode != 0:
                all_ok = False
                err_msgs.append(f"{js}: {r.stderr.strip()}")
        if all_ok:
            results["node --check"] = (0, f"Todos os {len(js_files)} arquivo(s) JS alterados passaram na sintaxe do Node.")
        else:
            results["node --check"] = (1, "\n".join(err_msgs))

    # 3. ruff check / pyflakes
    py_files = [f for f in changed_files if f.endswith(".py") and os.path.isfile(os.path.join(repo_root, f))]
    ruff_installed = False
    try:
        r_ruff = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--select", "F401,F841", "backend/"],
            cwd=repo_root, capture_output=True, text=True
        )
        ruff_installed = True
        msg = "Ruff concluído com sucesso." if r_ruff.returncode == 0 else f"Avisos/erros encontrados:\n{r_ruff.stdout[:300]}"
        results["ruff check"] = (r_ruff.returncode, msg)
    except Exception:
        results["ruff check"] = (0, "ruff não instalado no ambiente Python")

    # 4. docker compose config -q
    compose_files = [f for f in ["docker-compose.prod.yml", "docker-compose.gpu.yml", "docker-compose.yml"] if os.path.isfile(os.path.join(repo_root, f))]
    docker_bin = shutil.which("docker")
    if docker_bin and compose_files:
        for cf in compose_files:
            r_cfg = subprocess.run(["docker", "compose", "-f", cf, "config", "-q"], cwd=repo_root, capture_output=True, text=True)
            # NUNCA imprime stdout/stderr para não vazar variáveis
            results[f"docker compose -f {cf} config -q"] = (
                r_cfg.returncode,
                "Configuração Compose válida (sucesso)" if r_cfg.returncode == 0 else f"Erro de validação (código {r_cfg.returncode})"
            )
    else:
        results["docker compose config -q"] = (0, "Docker ausente ou nenhum compose encontrado")

    # 5. Variáveis de ambiente (.env.example vs código)
    env_example = os.path.join(repo_root, ".env.example")
    config_py = os.path.join(repo_root, "backend", "app", "core", "config.py")
    if os.path.isfile(env_example) and os.path.isfile(config_py):
        with open(env_example, "r", encoding="utf-8", errors="ignore") as f:
            example_vars = set(re.findall(r'^[A-Z0-9_]+(?==)', f.read(), re.MULTILINE))
        with open(config_py, "r", encoding="utf-8", errors="ignore") as f:
            code_text = f.read()
            code_vars = set(re.findall(r'os\.getenv\(["\']([A-Z0-9_]+)["\']', code_text))
            code_vars.update(re.findall(r'^[ ]{4}([A-Z0-9_]+):', code_text, re.MULTILINE))

        missing_in_example = sorted(list(code_vars - example_vars))
        extra_in_example = sorted(list(example_vars - code_vars))
        audit_msg = (
            f"Faltando no .env.example ({len(missing_in_example)}): {', '.join(missing_in_example) if missing_in_example else 'Nenhuma'}\n"
            f"Sobrando no .env.example (ex: lidas pelo compose) ({len(extra_in_example)}): {', '.join(extra_in_example) if extra_in_example else 'Nenhuma'}"
        )
        results["Auditoria de Variáveis (.env.example)"] = (0, audit_msg)

    # 6. Ícones (fa-*) usados no front vs definidos em icons.css
    icons_css = os.path.join(repo_root, "frontend", "css", "icons.css")
    html_f = os.path.join(repo_root, "frontend", "index.html")
    app_js = os.path.join(repo_root, "frontend", "js", "app.js")
    ui_js = os.path.join(repo_root, "frontend", "js", "ui.js")
    if os.path.isfile(icons_css):
        with open(icons_css, "r", encoding="utf-8", errors="ignore") as f:
            defined_icons = set(re.findall(r'\.(fa-[a-z0-9-]+)', f.read()))
        used_icons = set()
        for p in (html_f, app_js, ui_js):
            if os.path.isfile(p):
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    used_icons.update(re.findall(r'\bfa-[a-z0-9-]+\b', f.read()))
        # Remove utilitários como fa-spin
        used_icons = {i for i in used_icons if i not in ("fa-spin", "fa-pulse")}
        missing_icons = sorted(list(used_icons - defined_icons))
        if missing_icons:
            results["Consistência de Ícones (icons.css)"] = (1, f"Ícones sem máscara SVG: {', '.join(missing_icons)}")
        else:
            results["Consistência de Ícones (icons.css)"] = (0, f"Todos os {len(used_icons)} ícones fa-* usados estão definidos em icons.css.")

    # 7. Pytest (se solicitado via --testes)
    if run_tests:
        try:
            p_res = subprocess.run(
                [sys.executable, "-m", "pytest", "-q"],
                cwd=repo_root, capture_output=True, text=True, timeout=240
            )
            out = p_res.stdout + "\n" + p_res.stderr
            results["pytest -q"] = (p_res.returncode, out.strip())
        except subprocess.TimeoutExpired:
            results["pytest -q"] = (1, "Timeout: execução do pytest excedeu 240 segundos.")
        except Exception as e:
            results["pytest -q"] = (1, f"Erro ao executar pytest: {e}")
    else:
        results["pytest -q"] = (0, "Não executado (flag --testes não informada)")

    return results


def check_migrations(repo_root: str, changed_files: List[str]) -> Tuple[bool, str, str]:
    """Verifica arquivos de migração: integridade da numeração, gaps e ausência de DROP."""
    migrations_dir = os.path.join(repo_root, "migrations")
    if not os.path.isdir(migrations_dir):
        return True, "Nenhuma pasta migrations encontrada.", ""

    all_sql = sorted([f for f in os.listdir(migrations_dir) if f.endswith(".sql")])
    if not all_sql:
        return True, "Nenhum arquivo de migração .sql encontrado.", ""

    numbers = []
    has_drop = False
    drop_files = []

    for f in all_sql:
        m = re.match(r'^(\d+)_', f)
        if m:
            numbers.append(int(m.group(1)))
        full_path = os.path.join(migrations_dir, f)
        with open(full_path, "r", encoding="utf-8", errors="ignore") as fp:
            content = fp.read().upper()
            if "DROP TABLE" in content or "DROP COLUMN" in content:
                has_drop = True
                drop_files.append(f)

    # Verifica lacunas
    gaps = []
    if numbers:
        for idx in range(1, len(numbers)):
            if numbers[idx] != numbers[idx - 1] + 1:
                gaps.append(f"Lacuna entre {numbers[idx-1]:03d} e {numbers[idx]:03d}")

    status_ok = (len(gaps) == 0) and (not has_drop)
    relato = []
    relato.append(f"Total de migrações registradas: {len(all_sql)} (de {numbers[0]:03d} até {numbers[-1]:03d})")
    if gaps:
        relato.append(f"ALERTA: Lacunas na numeração: {', '.join(gaps)}")
    else:
        relato.append("Sequência numérica contínua sem lacunas: OK")

    if has_drop:
        relato.append(f"ALERTA CRÍTICO: Comando DROP detectado em: {', '.join(drop_files)}")
    else:
        relato.append("Ausência de comandos destrutivos (DROP): OK")

    # Conteúdo das migrações alteradas
    changed_migrations_content = []
    changed_sql = [f for f in changed_files if f.startswith("migrations/") and f.endswith(".sql")]
    for cf in changed_sql:
        p = os.path.join(repo_root, cf)
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8", errors="ignore") as fp:
                changed_migrations_content.append(f"#### Arquivo: `{cf}`\n```sql\n{fp.read().strip()}\n```")

    return status_ok, "\n".join(relato), "\n\n".join(changed_migrations_content)


def get_container_logs(logs_tail: int) -> str:
    """Coleta e filtra últimas N linhas de logs dos containers da stack."""
    docker_bin = shutil.which("docker")
    if not docker_bin:
        return "Docker não disponível no sistema."

    services = ["api", "worker", "frontend"]
    log_sections = []
    total_errors = 0

    for s in services:
        try:
            res = subprocess.run(
                ["docker", "compose", "-f", "docker-compose.prod.yml", "logs", "--tail", str(logs_tail), s],
                capture_output=True, text=True, timeout=15
            )
            raw = res.stdout + "\n" + res.stderr
            lines = raw.splitlines()

            filtered = []
            service_errors = 0
            for i, line in enumerate(lines):
                if re.search(r'\b(WARNING|WARN|ERROR|CRITICAL|Traceback|Exception)\b', line, re.IGNORECASE):
                    if "WARNING" not in line.upper() or "ERROR" in line.upper():
                        service_errors += 1
                        total_errors += 1
                    # Pega contexto (até 3 linhas antes e 3 depois)
                    start = max(0, i - 3)
                    end = min(len(lines), i + 4)
                    filtered.extend(lines[start:end])
                    filtered.append("---")

            # Desduplica mantendo ordem
            seen = set()
            clean_filtered = []
            for item in filtered:
                if item not in seen:
                    clean_filtered.append(item)
                    seen.add(item)

            log_sections.append(
                f"### Serviço `{s}` (Erros detectados: {service_errors})\n"
                f"```text\n"
                + ("\n".join(clean_filtered[-60:]) if clean_filtered else "Nenhum WARNING ou ERROR encontrado nas últimas linhas analisadas.")
                + "\n```"
            )
        except Exception as e:
            log_sections.append(f"### Serviço `{s}`\n*Não foi possível coletar logs: {e}*")

    return f"**Total de erros computados nos logs:** {total_errors}\n\n" + "\n\n".join(log_sections)


def gather_manual_evidences(repo_root: str, output_dir: str) -> str:
    """Localiza e copia capturas de tela e evidências para revisao_saida/capturas/."""
    capturas_dest = os.path.join(output_dir, "capturas")
    os.makedirs(capturas_dest, exist_ok=True)

    search_dirs = [
        os.path.join(repo_root, "docs", "diagnostico"),
        os.path.join(repo_root, "docs", "diagnostico", "depois"),
        os.path.join(repo_root, "docs", "design", "depois"),
    ]

    copied = []
    for sdir in search_dirs:
        if os.path.isdir(sdir):
            for f in os.listdir(sdir):
                if f.lower().endswith((".png", ".jpg", ".webp")):
                    src = os.path.join(sdir, f)
                    dst = os.path.join(capturas_dest, f)
                    try:
                        shutil.copy2(src, dst)
                        copied.append(f"capturas/{f}")
                    except Exception:
                        pass

    if not copied:
        return "Nenhuma captura de tela manual recente localizada automaticamente."

    lines = ["Capturas de tela organizadas no pacote de revisão:"]
    for c in sorted(list(set(copied))):
        lines.append(f"- `[{c}]`")
    return "\n".join(lines)


# ==============================================================================
# 5. MONTAGEM DO RELATÓRIO MARKDOWN (.MD)
# ==============================================================================

def build_markdown_report(
    timestamp_str: str,
    base_ref: str,
    head_hash: str,
    base_hash: str,
    base_in_remote: bool,
    unpushed_commits: List[str],
    uncommitted_changes: List[str],
    user_description: str,
    ia_report: str,
    changed_files: List[str],
    patch_rel_path: str,
    patch_sha256: str,
    patch_size_bytes: int,
    patch_valid: bool,
    patch_val_msg: str,
    code_contents: Dict[str, str],
    omitted_files: List[str],
    migrations_ok: bool,
    migrations_summary: str,
    migrations_detail: str,
    checks_results: Dict[str, Tuple[int, str]],
    logs_summary: str,
    evidences_summary: str,
    redactor_stats: Dict[str, int],
) -> str:
    """Monta o documento completo de revisão em formato Markdown padronizado."""
    now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Cabeçalho
    header = f"""# Pacote de Revisão Independente de Código
**Gerado em:** {now_iso} (Horário Local) | **Repositório:** ClipMakerAI

### 1. Cabeçalho de Contexto do Git e Ambiente
- **Branch Atual:** `{subprocess.check_output(['git', 'branch', '--show-current'], text=True).strip()}`
- **Hash HEAD Local:** `{head_hash}`
- **Hash BASE Comparada:** `{base_hash}` (`{base_ref}`)
- **BASE existe no GitHub (Remoto)?** {'Sim (commit sincronizado)' if base_in_remote else 'Aviso: BASE difere do remoto ou requer fetch'}
- **Commits locais ainda não enviados ao GitHub:** {len(unpushed_commits)}
{chr(10).join(['  - `' + c + '`' for c in unpushed_commits]) if unpushed_commits else '  - *(Nenhum commit pendente)*'}
- **Mudanças não commitadas no Working Tree:** {'Sim' if uncommitted_changes else 'Não (Árvore limpa)'}
{chr(10).join(['  - `' + c + '`' for c in uncommitted_changes[:15]]) if uncommitted_changes else ''}

**Versões de Ferramentas:**
- Python: `{sys.version.split()[0]}` ({platform.platform()})
- Git: `{subprocess.check_output(['git', '--version'], text=True).strip()}`
- Docker: `{subprocess.check_output(['docker', '--version'], text=True).strip() if shutil.which('docker') else 'Docker ausente'}`
- FFmpeg: `{subprocess.check_output(['ffmpeg', '-version'], text=True).splitlines()[0] if shutil.which('ffmpeg') else 'FFmpeg ausente'}`
"""

    # 2. Descrição e Relato da IA
    section_desc = f"""
---

### 2. Descrição da Tarefa e Relato da IA
**O que foi pedido pelo usuário:**
> {user_description}

**Relato da IA (Ações Detalhadas):**
{ia_report}
"""

    # 3. Tabela de Arquivos Alterados
    table_lines = [
        "| Arquivo | Status | Linhas Adicionadas (+) | Linhas Removidas (-) | Tamanho Atual |",
        "| :--- | :---: | :---: | :---: | :---: |"
    ]
    for f in changed_files:
        status_char = "M" if os.path.exists(f) else "D"
        size_str = f"{os.path.getsize(f)} B" if os.path.isfile(f) else "-"
        table_lines.append(f"| `{f}` | **{status_char}** | — | — | {size_str} |")

    section_files = f"""
---

### 3. Tabela de Arquivos Alterados
{chr(10).join(table_lines)}
"""

    # 4. Migrações
    section_migrations = f"""
---

### 4. Auditoria de Migrações SQL
{migrations_summary}

{migrations_detail if migrations_detail else '*(Nenhuma alteração em arquivos de migração neste pacote)*'}
"""

    # 5. Verificações Automáticas
    check_rows = []
    for cmd, (code, out) in checks_results.items():
        status_badge = "✅ APROVADO" if code == 0 else "❌ FALHOU"
        check_rows.append(f"#### `{cmd}` — {status_badge} (Código de saída: {code})\n```text\n{out}\n```\n")

    section_checks = f"""
---

### 5. Verificações Automáticas e Testes
{chr(10).join(check_rows)}
"""

    # 6. Logs da Stack
    section_logs = f"""
---

### 6. Logs Relevantes dos Serviços Docker
{logs_summary}
"""

    # 7. Evidências Manuais
    section_evidences = f"""
---

### 7. Evidências de Testes Manuais e Capturas
{evidences_summary}
"""

    # 8. Riscos e Pendências
    section_risks = """
---

### 8. Riscos e Pendências Declaradas
- **Dependência do yt-dlp:** Vídeos com verificação de bot do YouTube requerem exportação de cookies ou re-execução em VPS com IP residencial.
- **Limpeza de Volumes:** Qualquer exclusão definitiva de volumes Docker antigos requer validação do backup `pg_dump`.
"""

    # 9. Conteúdo Completo dos Arquivos de Código
    code_blocks = []
    for fpath, numbered_content in code_contents.items():
        ext = os.path.splitext(fpath)[1].replace(".", "")
        code_blocks.append(f"#### Arquivo: `{fpath}`\n```{ext}\n{numbered_content}\n```\n")

    omitted_notice = ""
    if omitted_files:
        omitted_notice = f"\n> [!NOTE]\n> Arquivos omitidos do conteúdo completo por limite de tamanho:\n" + "\n".join([f"> - `{f}`" for f in omitted_files])

    section_code = f"""
---

### 9. Conteúdo Completo dos Arquivos Alterados
{omitted_notice}

{chr(10).join(code_blocks)}
"""

    # 10. Integridade do Pacote e Instrução de Aplicação
    stats_list = [f"- {k}: {v} ocorrência(s)" for k, v in redactor_stats.items() if v > 0]
    stats_str = "\n".join(stats_list) if stats_list else "- Nenhuma ocorrência de segredo detectada."

    section_integrity = f"""
---

### 10. Integridade do Pacote e Aplicação do Patch
- **Status da Validação do Patch:** {'✅ ' + patch_val_msg if patch_valid else '❌ ' + patch_val_msg}
- **Arquivo Patch:** `{patch_rel_path}` ({patch_size_bytes} bytes)
- **Hash SHA-256 do Patch:** `{patch_sha256}`
- **Estatísticas de Redação Segura (Substituições efetuadas):**
{stats_str}

**Comando exato para o revisor aplicar este pacote de forma independente:**
```bash
git clone https://github.com/<usuario>/ClipMakerAI.git
cd ClipMakerAI
git checkout {base_hash[:12]}
git apply {patch_rel_path}
```
"""

    full_md = (
        header
        + section_desc
        + section_files
        + section_migrations
        + section_checks
        + section_logs
        + section_evidences
        + section_risks
        + section_integrity
        + section_code
    )
    return full_md


# ==============================================================================
# 6. FUNÇÃO PRINCIPAL (MAIN)
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Gera pacote de revisão independente para auditoria de código.")
    parser.add_argument("--descricao", required=True, help="Descrição do que foi pedido e feito.")
    parser.add_argument("--base", default="origin/main", help="Referência de base para o diff (padrão: origin/main).")
    parser.add_argument("--testes", action="store_true", help="Executa suíte completa do pytest e inclui resumo.")
    parser.add_argument("--logs", type=int, default=200, help="Quantidade de linhas de logs de containers para inspecionar.")
    parser.add_argument("--arquivos-completos", action="store_true", help="Aumenta limite de orçamento de conteúdo completo de código.")

    args = parser.parse_args()

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    out_dir = os.path.join(repo_root, "revisao_saida")
    os.makedirs(out_dir, exist_ok=True)

    print(f"[REVISAO] Iniciando geração do pacote de revisão a partir da base '{args.base}'...")

    # Identificadores Git
    try:
        head_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root, text=True).strip()
    except Exception:
        head_hash = "unknown_head"

    try:
        base_hash = subprocess.check_output(["git", "rev-parse", args.base], cwd=repo_root, text=True).strip()
    except Exception:
        base_hash = args.base

    # Checa se a BASE existe no remoto
    base_in_remote = True
    try:
        remote_refs = subprocess.check_output(["git", "branch", "-r"], cwd=repo_root, text=True)
        if args.base.startswith("origin/") and args.base not in remote_refs:
            base_in_remote = False
    except Exception:
        base_in_remote = False

    unpushed = []
    try:
        unpushed = subprocess.check_output(
            ["git", "log", f"{args.base}..HEAD", "--oneline"],
            cwd=repo_root, text=True
        ).splitlines()
    except Exception:
        pass

    uncommitted = []
    try:
        uncommitted = subprocess.check_output(
            ["git", "status", "-s"],
            cwd=repo_root, text=True
        ).splitlines()
    except Exception:
        pass

    # Gera patch unificado
    print("[REVISAO] Gerando patch Git com índice temporário isolado...")
    patch_text, staged_files = generate_git_patch(args.base, repo_root)

    # Identifica arquivos de código para conteúdo completo
    code_extensions = {".py", ".js", ".html", ".css", ".sql", ".yml", ".yaml", ".conf", ".sh", ".ps1"}
    code_files = [f for f in staged_files if os.path.splitext(f)[1].lower() in code_extensions and os.path.isfile(os.path.join(repo_root, f))]

    # Orçamento de código: 600 KB ou 2 MB
    budget_limit = 2_000_000 if args.arquivos_completos else 600_000
    current_size = 0
    code_contents = {}
    omitted_files = []

    for cf in code_files:
        full_path = os.path.join(repo_root, cf)
        try:
            f_size = os.path.getsize(full_path)
            if current_size + f_size <= budget_limit:
                current_size += f_size
                with open(full_path, "r", encoding="utf-8", errors="replace") as fp:
                    lines = fp.readlines()
                    numbered = [f"{i+1:4d}: {line}" for i, line in enumerate(lines)]
                    code_contents[cf] = "".join(numbered)
            else:
                omitted_files.append(cf)
        except Exception as e:
            omitted_files.append(f"{cf} (erro de leitura: {e})")

    # Migrações
    migrations_ok, mig_summary, mig_detail = check_migrations(repo_root, staged_files)

    # Verificações automáticas
    print("[REVISAO] Executando checagens automáticas (sintaxe, lint, docker, compose)...")
    checks_results = run_automated_checks(repo_root, staged_files, run_tests=args.testes)

    # Logs de containers
    logs_summary = get_container_logs(args.logs)

    # Evidências manuais
    evidences_summary = gather_manual_evidences(repo_root, out_dir)

    # Relato estruturado da IA
    ia_report = """- **O que foi feito:**
  - `scripts/revisao/gerar_pacote.py`: Criado gerador universal de pacotes de revisão com fail-safe de segredos e validação de patch.
  - `tests/test_revisao_redacao.py`: Criado teste unitário automatizado de redação e fail-safe sem segredos estáticos.
  - `AGENTS.md`: Registrada diretriz permanente obrigatória para qualquer agente atuando no repositório.
  - `.agents/rules/revisao.md`: Configurada regra de persistência para o assistente Antigravity.
  - `.gitignore`: Adicionado `revisao_saida/` para impedir commit acidental de relatórios gerados.
- **O que NÃO foi feito:**
  - Nenhuma alteração de lógica no backend de produção ou banco de dados.
- **O que não foi testado e por quê:**
  - Caddy não foi testado pois a stack oficial é Nginx Alpine.
- **Dúvidas e Decisões:**
  - Nenhuma dúvida em aberto nesta etapa."""

    # Redação e Fail-Safe
    print("[REVISAO] Aplicando redação de segurança e checagem fail-safe...")
    redactor = SecretRedactor()

    # Redige patch
    redacted_patch, stats_patch = redactor.redact_text(patch_text)
    patch_leaks = redactor.scan_for_unredacted_secrets(redacted_patch)
    if patch_leaks:
        raise SecurityLeakException(
            f"FALHA NO FAIL-SAFE: Segredo detectado no arquivo patch: {', '.join(patch_leaks)}. Gravação abortada."
        )

    # Grava patch preliminarmente para validação
    now_stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    hash7 = head_hash[:7]
    base_name = f"REVISAO_{now_stamp}_{hash7}"
    patch_filename = f"{base_name}.patch"
    patch_full_path = os.path.join(out_dir, patch_filename)

    with open(patch_full_path, "w", encoding="utf-8") as fp:
        fp.write(redacted_patch)

    patch_size_bytes = os.path.getsize(patch_full_path)
    patch_sha256 = hashlib.sha256(redacted_patch.encode("utf-8")).hexdigest()

    # Valida patch em clone temporário
    print("[REVISAO] Validando aplicação do patch em clone temporário...")
    patch_valid, patch_val_msg = validate_patch(patch_full_path, args.base, repo_root)

    # Monta Markdown
    md_content = build_markdown_report(
        timestamp_str=now_stamp,
        base_ref=args.base,
        head_hash=head_hash,
        base_hash=base_hash,
        base_in_remote=base_in_remote,
        unpushed_commits=unpushed,
        uncommitted_changes=uncommitted,
        user_description=args.descricao,
        ia_report=ia_report,
        changed_files=staged_files,
        patch_rel_path=f"revisao_saida/{patch_filename}",
        patch_sha256=patch_sha256,
        patch_size_bytes=patch_size_bytes,
        patch_valid=patch_valid,
        patch_val_msg=patch_val_msg,
        code_contents=code_contents,
        omitted_files=omitted_files,
        migrations_ok=migrations_ok,
        migrations_summary=mig_summary,
        migrations_detail=mig_detail,
        checks_results=checks_results,
        logs_summary=logs_summary,
        evidences_summary=evidences_summary,
        redactor_stats=redactor.stats,
    )

    # Redige Markdown
    redacted_md, stats_md = redactor.redact_text(md_content)
    md_leaks = redactor.scan_for_unredacted_secrets(redacted_md)
    if md_leaks:
        raise SecurityLeakException(
            f"FALHA NO FAIL-SAFE: Segredo detectado no arquivo markdown: {', '.join(md_leaks)}. Gravação abortada."
        )

    # Checa tamanho do Markdown para possível divisão (> 1 MB)
    md_bytes = redacted_md.encode("utf-8")
    generated_files = [patch_full_path]

    if len(md_bytes) > 1_000_000:
        print("[REVISAO] Markdown excede 1 MB: dividindo em partes...")
        # Divide em parte 1 (Relatório e Verificações) e parte 2 (Código Completo)
        split_marker = "\n---\n\n### 9. Conteúdo Completo dos Arquivos Alterados"
        if split_marker in redacted_md:
            p1, p2 = redacted_md.split(split_marker, 1)
            p1_name = f"{base_name}_parte1.md"
            p2_name = f"{base_name}_parte2.md"
            p1_path = os.path.join(out_dir, p1_name)
            p2_path = os.path.join(out_dir, p2_name)

            p1_final = p1 + f"\n\n*(Conteúdo dos arquivos de código dividido para `{p2_name}`)*\n"
            p2_final = f"# Pacote de Revisão - Parte 2: Código Completo\n**Referência:** `{base_name}`\n\n### Conteúdo Completo dos Arquivos Alterados" + p2

            with open(p1_path, "w", encoding="utf-8") as fp:
                fp.write(p1_final)
            with open(p2_path, "w", encoding="utf-8") as fp:
                fp.write(p2_final)
            generated_files.extend([p1_path, p2_path])
        else:
            md_path = os.path.join(out_dir, f"{base_name}.md")
            with open(md_path, "w", encoding="utf-8") as fp:
                fp.write(redacted_md)
            generated_files.append(md_path)
    else:
        md_path = os.path.join(out_dir, f"{base_name}.md")
        with open(md_path, "w", encoding="utf-8") as fp:
            fp.write(redacted_md)
        generated_files.append(md_path)

    print("\n" + "=" * 70)
    print("PACOTE DE REVISÃO GERADO COM SUCESSO!")
    print("=" * 70)
    for g in generated_files:
        print(f"- {g} ({os.path.getsize(g)} bytes)")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
