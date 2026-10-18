#!/usr/bin/env python3
"""
ClipMakerAI — Script de Versionamento Automático de Assets (Cache Busteing)

Lê frontend/index.html, calcula o hash SHA-256 do conteúdo de cada arquivo
CSS e JavaScript referenciado e injeta '?v=<hash>' para garantir invalidação
imediata de cache no navegador (onde o Nginx cacheia assets por 1 ano).

Uso:
    python scripts/version_assets.py           # Atualiza frontend/index.html
    python scripts/version_assets.py --check   # Apenas valida se os hashes estão atualizados
"""

import sys
import os
import re
import hashlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
INDEX_HTML = FRONTEND_DIR / "index.html"


def compute_file_hash(filepath: Path, length: int = 8) -> str:
    """Calcula o hash SHA-256 do conteúdo de um arquivo estático."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()[:length]


def update_asset_versions(check_only: bool = False) -> bool:
    if not INDEX_HTML.exists():
        print(f"[ERRO] Arquivo não encontrado: {INDEX_HTML}")
        sys.exit(1)

    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        content = f.read()

    # Padrões para CSS (href="css/...") e JS (src="js/...")
    # Grupo 1: prefixo (href=" ou src=")
    # Grupo 2: caminho do asset (ex.: css/components.css)
    # Grupo 3: query string existente opcional (?v=...)
    # Grupo 4: aspa de fechamento
    pattern = re.compile(r'((?:href|src)=["\'])(css/[^"\'?#]+|js/[^"\'?#]+)(?:\?[^"\'#]*)?(["\'])')

    changes = []

    def replacer(match):
        prefix = match.group(1)
        rel_path = match.group(2)
        quote = match.group(3)

        asset_file = FRONTEND_DIR / rel_path
        if not asset_file.exists():
            print(f"[AVISO] Asset não encontrado em disco: {asset_file}")
            return match.group(0)

        file_hash = compute_file_hash(asset_file)
        new_tag = f"{prefix}{rel_path}?v={file_hash}{quote}"
        changes.append((rel_path, file_hash))
        return new_tag

    new_content = pattern.sub(replacer, content)

    print("=" * 60)
    print("      CLIPMAKER.IO — ATUALIZAÇÃO DE ASSETS DO FRONTEND")
    print("=" * 60)
    for rel_path, file_hash in changes:
        print(f"  • {rel_path:<25} -> ?v={file_hash}")
    print("=" * 60)

    is_modified = (new_content != content)

    if check_only:
        if is_modified:
            print("[CHECK FALHOU] frontend/index.html possui hashes desatualizados. Execute: python scripts/version_assets.py")
            return False
        print("[CHECK OK] Todos os assets em frontend/index.html estão com hashes válidos.")
        return True

    if is_modified:
        with open(INDEX_HTML, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"[SUCESSO] {len(changes)} referências atualizadas com sucesso em frontend/index.html.")
    else:
        print("[INFO] Todos os hashes já estavam atualizados. Nenhuma alteração necessária.")

    return True


def main():
    check_mode = "--check" in sys.argv
    success = update_asset_versions(check_only=check_mode)
    if not success and check_mode:
        sys.exit(1)


if __name__ == "__main__":
    main()
