import os
import sys
import time
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.abspath("."))
from scripts.security.canary_server import start_canary_server, canary_hits

def test_ffmpeg_concat_ssrf():
    print("[*] Testando Concat Demuxer no FFmpeg...")
    canary_port = 8889
    server = start_canary_server(port=canary_port)
    time.sleep(0.3)

    scratch = Path("scripts/security/scratch")
    scratch.mkdir(parents=True, exist_ok=True)
    concat_file = scratch / "test_concat.mp4"
    concat_file.write_text(f"""ffconcat version 1.0
file http://127.0.0.1:{canary_port}/canary_hit_concat
""", encoding="utf-8")

    hits_before = len(canary_hits)
    # Executa ffmpeg sem whitelist
    res = subprocess.run(
        ["ffmpeg", "-hide_banner", "-y", "-i", str(concat_file), "-f", "null", "-"],
        capture_output=True,
        text=True,
        timeout=5
    )
    time.sleep(0.5)
    hits_after = len(canary_hits)
    print(f"  [i] FFmpeg sem whitelist -> Hits: {hits_after - hits_before}")
    if hits_after > hits_before:
        print("  [!] VULNERAVEL: FFmpeg buscou URL remota via concat file!")

    # Agora com protocol_whitelist
    hits_before_wh = len(canary_hits)
    res_wh = subprocess.run(
        ["ffmpeg", "-protocol_whitelist", "file,crypto,data", "-hide_banner", "-y", "-i", str(concat_file), "-f", "null", "-"],
        capture_output=True,
        text=True,
        timeout=5
    )
    time.sleep(0.5)
    hits_after_wh = len(canary_hits)
    print(f"  [i] FFmpeg com protocol_whitelist -> Hits: {hits_after_wh - hits_before_wh}")
    print(f"  [+] Saida do ffmpeg bloqueado: {res_wh.stderr.strip()[-200:]}")

    try:
        concat_file.unlink()
    except Exception:
        pass

if __name__ == "__main__":
    test_ffmpeg_concat_ssrf()
