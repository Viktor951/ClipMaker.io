from huey import SqliteHuey
import os
import logging
import traceback

# Configurar logging para ser visível no Huey consumer
logging.basicConfig(
    level=logging.DEBUG,
    format="[%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("clipmaker.worker")

# Configura a fila usando SQLite (funciona perfeitamente no Windows)
huey = SqliteHuey(filename=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'huey_queue.db'))

@huey.task()
def process_video_task(project_id: str, input_path: str, temp_dir: str):
    logger.info(f"Iniciando processamento para o projeto: {project_id}")
    logger.info(f"Input: {input_path}")
    try:
        # Import local para evitar problemas de dependência circular
        from backend.engine import process_video_full_pipeline
        
        # Executa o pipeline de IA
        clips = process_video_full_pipeline(input_path, temp_dir)
        logger.info(f"Sucesso! Clipes gerados para {project_id}: {len(clips)}")
        
        # Salva no banco de dados
        import asyncio
        from backend.services.db_service import save_project_results
        asyncio.run(save_project_results(project_id, clips))
        logger.info(f"Resultados salvos no banco para {project_id}")
        
    except Exception as e:
        logger.error(f"Erro ao processar projeto {project_id}: {e}")
        traceback.print_exc()
        
        # Atualiza o status do projeto para FAILED no banco
        import asyncio
        from backend.services.db_service import update_project_status
        asyncio.run(update_project_status(project_id, "FAILED", str(e)))
        logger.info(f"Status do projeto {project_id} atualizado para FAILED")
        
    finally:
        # 1. Limpeza de VRAM (CRÍTICO para evitar OutOfMemory no próximo job)
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("VRAM liberada com sucesso (torch).")
        except ImportError:
            # torch não instalado, ignora empty_cache
            pass
            
        # 2. Deleta o vídeo original
        if os.path.exists(input_path):
            try:
                os.remove(input_path)
                logger.info(f"Arquivo temporário removido: {input_path}")
            except OSError:
                pass
