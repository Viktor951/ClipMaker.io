import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath("."))

from scripts.security.canary_server import start_canary_server, canary_hits
import ffmpeg

def test_ffmpeg_protocol_whitelist():
    print("[*] Iniciando teste S3.2: Protocol Whitelist no FFprobe/FFmpeg...")
    canary_port = 8888
    server = start_canary_server(port=canary_port)
    time.sleep(0.5)

    temp_test_dir = Path("scripts/security/scratch")
    temp_test_dir.mkdir(parents=True, exist_ok=True)
    m3u8_file = temp_test_dir / "exploit_canary.mp4"

    # Criar playlist HLS que aponta para o canary local
    m3u8_content = f"""#EXTM3U
#EXT-X-TARGETDURATION:10
#EXTINF:10,
http://127.0.0.1:{canary_port}/canary_ffmpeg_probe_ssrf
"""
    m3u8_file.write_text(m3u8_content, encoding="utf-8")

    initial_hits = len(canary_hits)
    print(f"  [+] Arquivo canario criado em {m3u8_file}. Hits iniciais no canario: {initial_hits}")

    # Executa ffmpeg.probe sem protocol_whitelist (como esta hoje no video_service.py)
    probe_triggered_hit = False
    try:
        print("  [*] Executando ffmpeg.probe() sem protocol_whitelist...")
        ffmpeg.probe(str(m3u8_file))
    except Exception as e:
        print(f"  [i] ffmpeg.probe retornou excecao esperada (m3u8 sem video real): {type(e).__name__}")

    time.sleep(0.5)
    new_hits = len(canary_hits) - initial_hits
    if new_hits > 0:
        probe_triggered_hit = True
        print(f"  [!] VULNERAVEL: ffprobe contatou o servidor canario local! Hits registrados: {new_hits}")
        for h in canary_hits[initial_hits:]:
            print(f"      -> Caminho requisitado pelo FFprobe: {h['path']}")
    else:
        print("  [?] Nenhum hit registrado via ffprobe.")

    # Agora testa com a mitigacao recomendada:
    # ffprobe com -protocol_whitelist "file,crypto,data"
    print("\n  [*] Testando com a mitigacao recomendada: cmd='ffprobe', extra_args=['-protocol_whitelist', 'file,crypto,data']...")
    mitigated_hits_before = len(canary_hits)
    try:
        # ffmpeg-python suporta passar argumentos adicionais para o probe
        import subprocess
        res = subprocess.run(
            ["ffprobe", "-protocol_whitelist", "file,crypto,data", "-show_format", str(m3u8_file)],
            capture_output=True,
            text=True,
            timeout=5
        )
        print(f"  [i] Saida do ffprobe com whitelist:\n      STDERR: {res.stderr.strip()[:200]}")
    except Exception as e:
        print(f"  [i] Excecao: {e}")

    time.sleep(0.5)
    mitigated_new_hits = len(canary_hits) - mitigated_hits_before
    if mitigated_new_hits == 0:
        print(f"  [+] MITIGACAO EFICAZ: ffprobe bloqueou acesso HTTP/externo com '-protocol_whitelist file,crypto,data'!")
    else:
        print(f"  [-] Mitigacao falhou, ainda gerou hit.")

    # Limpeza
    try:
        m3u8_file.unlink()
    except Exception:
        pass

    return {
        "vulnerable_without_whitelist": probe_triggered_hit,
        "mitigated_with_whitelist": (mitigated_new_hits == 0)
    }

if __name__ == "__main__":
    test_ffmpeg_protocol_whitelist()
