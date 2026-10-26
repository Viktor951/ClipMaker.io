import os
import sys
import asyncio
from pathlib import Path

os.environ["ENVIRONMENT"] = "test"
os.environ["ALLOW_SQLITE_FALLBACK"] = "true"
sys.path.insert(0, os.path.abspath("."))

import uuid
from backend.app.db.db_service import get_backend, count_active_projects_by_user, create_project
from backend.app.core.config import settings

async def simulate_concurrent_job_creation():
    print("[*] Testando S2.5: Race Condition no Limite de Jobs Simultaneos...")
    user_id = str(uuid.uuid4())
    max_allowed = settings.MAX_CONCURRENT_JOBS_PER_USER # normalmente 2

    # Funcao que replica a logica atual de checagem do router video.py:
    async def try_start_job(job_num):
        # 1. Checagem nao-atomica
        active = await count_active_projects_by_user(user_id)
        # Simulando pequena latencia de I/O (ex: gravacao de upload ou validacao de URL)
        await asyncio.sleep(0.05)
        if active >= max_allowed:
            return False, f"Rejeitado: {active} jobs ativos"
        # 2. Criacao do projeto
        pid = await create_project(
            user_id=user_id,
            title=f"Job Concorrente {job_num}",
            source_file_key=f"file_{job_num}.mp4",
            duration_sec=60.0,
            status="PENDING"
        )
        return True, f"Criado com sucesso (id: {pid})"

    # Dispara 10 requisicoes simultaneas
    print(f"  [i] Disparando 10 chamadas paralelas simultaneas (Limite configurado: {max_allowed})...")
    tasks = [try_start_job(i) for i in range(10)]
    results = await asyncio.gather(*tasks)

    success_count = sum(1 for success, _ in results if success)
    print(f"  [i] Total de jobs aceitos concorrentemente: {success_count} de 10")

    if success_count > max_allowed:
        print(f"  [!] VULNERAVEL: Condicao de corrida confirmada! {success_count} jobs iniciados simultaneamente (limite era {max_allowed})!")
    else:
        print("  [+] Limite respeitado.")

    # Verifica no banco
    final_active = await count_active_projects_by_user(user_id)
    print(f"  [i] Contagem final de jobs ativos no banco: {final_active}")

    return {
        "success_count": success_count,
        "max_allowed": max_allowed,
        "bypassed": success_count > max_allowed
    }

if __name__ == "__main__":
    asyncio.run(simulate_concurrent_job_creation())
