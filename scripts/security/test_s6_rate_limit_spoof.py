import os
import sys
import asyncio
from starlette.requests import Request
from slowapi.util import get_remote_address
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

async def dummy_app(scope, receive, send):
    pass

def test_rate_limit_ip_extraction():
    print("[*] Testando extracao de IP pelo slowapi e ProxyHeadersMiddleware...")

    # Nginx config:
    # proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    # Se o cliente enviar: X-Forwarded-For: 200.200.200.200
    # Nginx concatena o IP real (ex: 189.10.10.10):
    # Header final enviado ao Uvicorn: X-Forwarded-For: 200.200.200.200, 189.10.10.10

    m = ProxyHeadersMiddleware(dummy_app, trusted_hosts="*")
    scope = {
        "type": "http",
        "client": ("172.18.0.3", 45678), # IP do container Nginx
        "headers": [
            (b"host", b"localhost"),
            (b"x-forwarded-for", b"200.200.200.200, 189.10.10.10"),
            (b"x-real-ip", b"189.10.10.10"),
        ],
    }

    asyncio.run(m(scope, None, None))
    parsed_client = scope.get("client")
    req = Request(scope)
    detected_ip = get_remote_address(req)

    print(f"  [i] Cliente original antes do middleware: ('172.18.0.3', 45678)")
    print(f"  [i] Cliente parseado pelo Uvicorn: {parsed_client}")
    print(f"  [i] IP utilizado pelo SlowAPI: {detected_ip}")

    # Verifica se o IP parseado foi o IP forjado pelo atacante (200.200.200.200) ou o real
    if detected_ip == "200.200.200.200":
        print("  [!] VULNERAVEL: O Uvicorn adotou o PRIMEIRO IP do cabeçalho X-Forwarded-For!")
        print("      Um atacante pode forjar 'X-Forwarded-For: <IP_aleatorio>' a cada requisicao e burlar 100% do rate limiting!")
    elif detected_ip == "189.10.10.10":
        print("  [+] O Uvicorn adotou o ultimo IP confiado da cadeia (189.10.10.10).")
    elif detected_ip == "172.18.0.3":
        print("  [!] PROBLEMA: O rate limiter usou o IP do Nginx (172.18.0.3). Todos os usuarios compartilham o mesmo contador!")
    else:
        print(f"  [?] Outro IP detectado: {detected_ip}")

if __name__ == "__main__":
    test_rate_limit_ip_extraction()
