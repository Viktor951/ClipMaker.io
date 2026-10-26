import os
import sys

os.environ["ENVIRONMENT"] = "test"
os.environ["ALLOW_SQLITE_FALLBACK"] = "true"
sys.path.insert(0, os.path.abspath("."))
from backend.app.api.routers.video import _is_safe_public_url

TEST_CASES = [
    # (URL, Expected to be safe or dangerous)
    ("http://localhost:8000", False, "localhost"),
    ("http://127.0.0.1:8000", False, "IPv4 loopback"),
    ("http://0.0.0.0", False, "0.0.0.0"),
    ("http://10.0.0.1", False, "RFC1918 10.x"),
    ("http://172.16.0.1", False, "RFC1918 172.16.x"),
    ("http://192.168.1.1", False, "RFC1918 192.168.x"),
    ("http://169.254.169.254/latest/meta-data/", False, "AWS/Cloud Link-Local Metadata"),
    ("http://[::1]", False, "IPv6 loopback"),
    ("http://[::ffff:127.0.0.1]", False, "IPv4-mapped IPv6 loopback"),
    ("http://db:5432", False, "Docker internal compose service 'db'"),
    ("http://redis:6379", False, "Docker internal compose service 'redis'"),
    ("http://api:8000", False, "Docker internal compose service 'api'"),
    ("http://worker", False, "Docker internal compose service 'worker'"),
    ("http://2130706433", False, "Decimal representation of 127.0.0.1"),
    ("http://0177.0.0.1", False, "Octal representation of 127.0.0.1"),
    ("http://0x7f000001", False, "Hex representation of 127.0.0.1"),
    ("http://user@127.0.0.1:80", False, "user@host syntax"),
    ("file:///etc/passwd", False, "file:// URI"),
    ("-i http://evil.com", False, "Leading hyphen argument injection"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", True, "Legitimate YouTube URL"),
]

def run_ssrf_tests():
    print("[*] Testando Validador Anti-SSRF (_is_safe_public_url)...")
    passed = 0
    failed = 0
    results = []

    for url, should_be_safe, desc in TEST_CASES:
        is_safe = _is_safe_public_url(url)
        # Se should_be_safe for False, esperamos is_safe == False
        # Se should_be_safe for True, esperamos is_safe == True
        ok = (is_safe == should_be_safe)
        status_str = "OK" if ok else "FALHOU"
        if not ok:
            failed += 1
            print(f"  [!] {status_str} | URL: {url} | Esperado: {'Permitido' if should_be_safe else 'Bloqueado'} | Obtido: {'Permitido' if is_safe else 'Bloqueado'} ({desc})")
        else:
            passed += 1
            print(f"  [+] {status_str} | URL: {url:45} | Bloqueado: {not is_safe:5} ({desc})")

        results.append({
            "url": url,
            "desc": desc,
            "is_safe": is_safe,
            "expected_safe": should_be_safe,
            "passed": ok
        })

    print(f"\n[+] Total de testes: {len(TEST_CASES)} | Passaram: {passed} | Falharam: {failed}")
    return results

if __name__ == "__main__":
    run_ssrf_tests()
