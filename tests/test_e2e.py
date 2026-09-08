import asyncio
import httpx
import os
import time

API_URL = "http://127.0.0.1:8000"

async def test_e2e():
    print("Iniciando Teste E2E...")
    
    # 1. Registrar um usuario de teste
    test_email = f"test_{int(time.time())}@example.com"
    test_password = "password123"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("Registrando usuario...")
        reg_res = await client.post(f"{API_URL}/auth/register", json={
            "email": test_email,
            "password": test_password,
            "name": "Test User"
        })
        if reg_res.status_code not in (200, 201, 400):
            print(f"Erro ao registrar: {reg_res.text}")
            return
            
        print("Fazendo login...")
        login_res = await client.post(f"{API_URL}/auth/login", data={
            "username": test_email,
            "password": test_password
        })
        token = login_res.json().get("access_token")
        if not token:
            print("Falha ao logar")
            return
            
        headers = {"Authorization": f"Bearer {token}"}
        
        # 2. Enviar um video por URL para testar yt-dlp e fila
        url_to_test = "https://www.youtube.com/watch?v=jNQXAC9IVRw" # Me at the zoo (19 sec)
        print(f"Enviando URL: {url_to_test}")
        
        upload_res = await client.post(f"{API_URL}/upload-url/", data={"url": url_to_test}, headers=headers)
        if upload_res.status_code != 200:
            print(f"Upload falhou: {upload_res.text}")
            return
            
        project_id = upload_res.json()["project_id"]
        print(f"Upload OK. Project ID: {project_id}")
        
        # 3. Polling
        print("Aguardando processamento na fila...")
        max_attempts = 120 # 6 minutos
        
        for i in range(max_attempts):
            status_res = await client.get(f"{API_URL}/project/{project_id}/status", headers=headers)
            if status_res.status_code == 200:
                data = status_res.json()
                status = data.get("status")
                
                print(f"[{i}] Status: {status}")
                if status == "READY":
                    print("Processamento concluido!")
                    print(f"Clips gerados: {len(data.get('clips', []))}")
                    break
                elif status == "FAILED":
                    print(f"Processamento FALHOU: {data.get('error')}")
                    break
            else:
                print(f"Erro no polling: {status_res.status_code}")
                
            await asyncio.sleep(3)
            
if __name__ == "__main__":
    asyncio.run(test_e2e())
