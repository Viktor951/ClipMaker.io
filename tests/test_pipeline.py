import os
import sys
import time
import subprocess

# Adicionar a pasta backend ao sys.path para importar o app
sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))

from fastapi.testclient import TestClient
from backend.main import app, TEMP_DIR

client = TestClient(app)

def run_test():
    video_path = os.path.join("backend", "test_video.mp4")
    
    if not os.path.exists(video_path):
        print("Erro: Arquivo test_video.mp4 nao encontrado!")
        sys.exit(1)
        
    print(f"Limpando diretorio {TEMP_DIR}...")
    import shutil
    if os.path.exists(TEMP_DIR):
        for f in os.listdir(TEMP_DIR):
            try:
                os.remove(os.path.join(TEMP_DIR, f))
            except:
                pass
                
    print(f"Iniciando Teste E2E (Simulando request para /upload-and-process/ com {video_path})")
    
    # 1. Enviar arquivo para a API
    with open(video_path, "rb") as f:
        t0 = time.time()
        print("Enviando video...")
        response = client.post("/upload-and-process/", files={"file": ("test_video.mp4", f, "video/mp4")})
        t1 = time.time()
        
    print(f"Request concluido em {t1 - t0:.2f}s")
    
    if response.status_code != 200:
        print(f"Erro na API (Status {response.status_code}): {response.text}")
        sys.exit(1)
        
    data = response.json()
    if data.get("status") != "success":
        print(f"Resposta inesperada: {data}")
        sys.exit(1)
        
    clips = data.get("clips", [])
    print(f"Sucesso! Foram gerados {len(clips)} clipe(s).")
    
    # 2. Verificar arquivos residuais no diretorio TEMP_DIR
    print("Verificando limpeza de arquivos temporarios...")
    all_files = os.listdir(TEMP_DIR)
    
    clip_ids = [c["id"] for c in clips]
    
    residual_files = [f for f in all_files if f not in clip_ids and not f.endswith(".mp4")] # We assume all non-mp4 files shouldn't be there, and original mp4 should be deleted
    
    # Actually, original uploaded video should be deleted but it might not be implemented in main.py yet
    print(f"Arquivos presentes no temp_dir: {all_files}")
    
    # Verificar se ha videos originais (uuid aleatorio .mp4) e .srt residuais
    has_srt = any(f.endswith(".srt") for f in all_files)
    has_original = any(f.endswith(".mp4") and f not in clip_ids for f in all_files)
    
    if has_srt:
        print("Vazamento detectado: Arquivos .srt residuais nao foram limpos!")
    else:
        print("Arquivos .srt limpos corretamente.")
        
    if has_original:
        print("Vazamento detectado: Video original (input) nao foi deletado do temp_dir!")
    else:
        print("Video original deletado com sucesso.")
        
    if has_srt or has_original:
        print("TESTE FALHOU DEVIDO A VAZAMENTO DE RECURSOS/ARQUIVOS.")
        sys.exit(1)
        
    print("TESTE E2E CONCLUIDO COM SUCESSO!")

if __name__ == "__main__":
    run_test()
