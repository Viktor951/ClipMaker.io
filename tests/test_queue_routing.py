import os
import re
from pathlib import Path
import pytest

# Ensure SQLite fallback is allowed for unit testing
os.environ["ALLOW_SQLITE_FALLBACK"] = "true"
os.environ["REDIS_URL"] = "sqlite:///:memory:"
os.environ["ENVIRONMENT"] = "development"


def test_tasks_enqueued_to_configured_compose_consumer():
    """
    Verifica que cada tarefa enfileirada no worker cai em uma instância
    do Huey cujo consumidor está configurado em docker-compose.prod.yml.
    """
    compose_path = Path(__file__).resolve().parent.parent / "docker-compose.prod.yml"
    if not compose_path.exists():
        compose_path = Path("/app/docker-compose.prod.yml")
    if not compose_path.exists():
        pytest.skip("docker-compose.prod.yml não encontrado neste ambiente de execução")

    
    compose_content = compose_path.read_text(encoding="utf-8")
    
    # Extrai os nomes das instâncias do Huey consumidas no compose em linhas ativas (não comentadas)
    # Exemplo de comando: huey_consumer backend.app.worker.worker.huey -w 1 -k thread
    active_lines = [line for line in compose_content.splitlines() if not line.strip().startswith("#")]
    active_content = "\n".join(active_lines)
    consumer_matches = re.findall(r"huey_consumer\s+[\w\.]+\.([\w]+)", active_content)
    assert consumer_matches, "Nenhum huey_consumer ativo encontrado no docker-compose.prod.yml"
    configured_queues = set(consumer_matches)
    
    from backend.app.worker import worker

    # Esvazia filas antes do teste
    for q_name in ("huey", "huey_ingest", "huey_render"):
        if hasattr(worker, q_name):
            q = getattr(worker, q_name)
            if hasattr(q, "flush"):
                q.flush()

    # Enfileira as 3 tarefas
    task1 = worker.download_and_process_url_task("proj-test-1", "https://example.com/video.mp4", "temp")
    task2 = worker.process_video_task("proj-test-2", "temp/test.mp4", "temp")
    task3 = worker.re_render_clip_task("clip-test-1", {})

    # Para cada tarefa, verifica em qual fila ela foi enfileirada
    tasks_and_names = [
        ("download_and_process_url_task", task1),
        ("process_video_task", task2),
        ("re_render_clip_task", task3),
    ]

    for name, task_result in tasks_and_names:
        # Descobre a fila pela propriedade huey da task
        task_obj = getattr(worker, name)
        # O objeto Task do Huey aponta para task_obj.huey
        task_huey_instance = getattr(task_obj, "huey", None)
        assert task_huey_instance is not None, f"Tarefa {name} não possui instância do Huey associada"
        
        # Encontra o nome da variável no módulo worker que corresponde a essa instância
        matched_attr = None
        for attr in ("huey", "huey_ingest", "huey_render"):
            if getattr(worker, attr, None) is task_huey_instance:
                matched_attr = attr
                break

        assert matched_attr in configured_queues, (
            f"A tarefa {name} foi enfileirada na fila '{matched_attr}', "
            f"mas o docker-compose.prod.yml apenas consome as seguintes filas: {configured_queues}. "
            f"O job ficará pendente indefinidamente!"
        )
        
        # Verifica também que a fila correspondente realmente tem itens enfileirados
        assert len(task_huey_instance) > 0, f"A fila '{matched_attr}' deveria ter tarefas enfileiradas."
