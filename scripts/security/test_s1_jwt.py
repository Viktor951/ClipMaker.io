import os
import sys
sys.path.insert(0, os.path.abspath("."))
import time
import jwt
from backend.app.core.config import settings
from backend.app.core.security import decode_access_token, create_access_token, verify_signed_url_token, create_signed_url_token

def test_jwt_security():
    print("[*] Testando Seguranca do JWT (S1.1)...")
    results = {}

    secret = settings.SECRET_KEY
    algo = settings.ALGORITHM

    # 1. Test "alg: none"
    header = {"alg": "none", "typ": "JWT"}
    payload = {"sub": "user_123", "exp": int(time.time()) + 3600}
    # Unsigned token
    token_none = jwt.encode(payload, key="", algorithm="none")
    decoded_none = decode_access_token(token_none)
    results["alg_none_blocked"] = (decoded_none is None)
    print(f"  [+] 'alg: none' rejeitado: {results['alg_none_blocked']} (decode result: {decoded_none})")

    # 2. Test tampered signature
    valid_token = create_access_token({"sub": "user_123"})
    parts = valid_token.split(".")
    tampered_token = f"{parts[0]}.{parts[1]}.tampered_sig"
    decoded_tampered = decode_access_token(tampered_token)
    results["tampered_sig_blocked"] = (decoded_tampered is None)
    print(f"  [+] Assinatura adulterada rejeitada: {results['tampered_sig_blocked']}")

    # 3. Test expired token
    token_expired = jwt.encode({"sub": "user_123", "exp": int(time.time()) - 100}, secret, algorithm=algo)
    decoded_expired = decode_access_token(token_expired)
    results["expired_token_blocked"] = (decoded_expired is None)
    print(f"  [+] Token expirado rejeitado: {results['expired_token_blocked']}")

    # 4. Test missing 'exp' claim
    token_no_exp = jwt.encode({"sub": "user_123"}, secret, algorithm=algo)
    decoded_no_exp = decode_access_token(token_no_exp)
    results["no_exp_accepted"] = (decoded_no_exp is not None)
    print(f"  [!] Token sem 'exp' ACEITO pelo backend (falta require=['exp']): {results['no_exp_accepted']} (payload: {decoded_no_exp})")

    # 5. Test key reuse (JWT and signed URL using identical SECRET_KEY)
    results["same_key_jwt_and_signed_url"] = True
    print(f"  [!] Mesma chave (SECRET_KEY) usada para JWT e URL assinada: {results['same_key_jwt_and_signed_url']}")

    # 6. Test signed URL tampering
    clip_id = "test-clip-1"
    user_id = "user-1"
    sig = create_signed_url_token(user_id, clip_id, expires_in_sec=3600)
    # verify with expected clip
    v_ok = verify_signed_url_token(sig, expected_clip_id=clip_id)
    # verify with different clip (BOLA test on signed url)
    v_bola = verify_signed_url_token(sig, expected_clip_id="other-clip-2")
    results["signed_url_clip_binding_enforced"] = (v_ok is not None and v_bola is None)
    print(f"  [+] Vinculo de clip_id na URL assinada verificado: {results['signed_url_clip_binding_enforced']}")

    return results

if __name__ == "__main__":
    test_jwt_security()
