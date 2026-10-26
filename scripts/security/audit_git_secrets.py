import subprocess
import re
import sys

# Masking helper
def mask_secret(val: str) -> str:
    if not val:
        return ""
    if len(val) <= 8:
        return "****"
    return val[:4] + "****" + val[-4:]

PATTERNS = [
    ("Google/Gemini API Key", re.compile(r"AIza[0-9A-Za-z\-_]{35}")),
    ("JWT Token", re.compile(r"eyJ[A-Za-z0-9\-_]{20,}\.eyJ[A-Za-z0-9\-_]{20,}\.[A-Za-z0-9\-_]+")),
    ("AWS Access Key", re.compile(r"(?:A3T[A-Z0-9]|AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{16}")),
    ("Generic Private Key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("Hardcoded Password in assignments", re.compile(r"(?:SECRET_KEY|POSTGRES_PASSWORD|REDIS_PASSWORD|GEMINI_API_KEY)\s*=\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)),
]

FALSE_POSITIVE_HINTS = [
    "COLOQUE_SUA_CHAVE_AQUI",
    "change_this_to_a_super_secret_key_in_production_32bytes",
    "your_gemini_api_key_here",
    "clipmaker_prod_secret_token_fixed_key",
    "example",
    "dummy",
    "fake",
    "test_key",
    "test_secret"
]

def scan_git_history():
    print("[*] Iniciando varredura de histórico Git completo (git log -p)...")
    try:
        proc = subprocess.Popen(
            ["git", "log", "-p", "--all"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
    except Exception as e:
        print(f"[-] Erro ao executar git log: {e}")
        return

    commit_hash = "unknown"
    commit_author = "unknown"
    commit_date = "unknown"
    current_file = "unknown"
    line_num = 0

    findings = []
    false_positives = []

    for raw_line in proc.stdout:
        line = raw_line.rstrip("\r\n")
        if line.startswith("commit "):
            commit_hash = line.split()[1]
        elif line.startswith("Author: "):
            commit_author = line[8:]
        elif line.startswith("Date: "):
            commit_date = line[6:].strip()
        elif line.startswith("diff --git "):
            parts = line.split()
            if len(parts) >= 4:
                current_file = parts[3].lstrip("b/")
        elif line.startswith("+") and not line.startswith("+++"):
            added_content = line[1:]
            for pat_name, regex in PATTERNS:
                matches = regex.findall(added_content)
                for m in matches:
                    secret_val = m if isinstance(m, str) else m[0]
                    is_fp = any(fp.lower() in secret_val.lower() for fp in FALSE_POSITIVE_HINTS)
                    item = {
                        "type": pat_name,
                        "commit": commit_hash[:8],
                        "file": current_file,
                        "masked": mask_secret(secret_val),
                        "is_fp": is_fp
                    }
                    if is_fp:
                        false_positives.append(item)
                    else:
                        findings.append(item)

    proc.wait()
    print(f"\n[+] Varredura concluida. Achados suspeitos: {len(findings)}, Falsos positivos descartados: {len(false_positives)}")
    if findings:
        print("\n--- ACHADOS SUSPEITOS NO GIT ---")
        for f in findings:
            print(f"- Tipo: {f['type']} | Commit: {f['commit']} | Arquivo: {f['file']} | Valor: {f['masked']}")
    else:
        print("[+] Nenhum segredo real ativo encontrado no historico git!")

    if false_positives:
        print("\n--- FALSOS POSITIVOS DESCARTADOS (exemplos/placeholders) ---")
        for fp in false_positives[:10]:
            print(f"- [FP] Tipo: {fp['type']} | Arquivo: {fp['file']} | Valor: {fp['masked']}")

if __name__ == "__main__":
    scan_git_history()
