import asyncio
import threading
from typing import Coroutine, Any

# Loop de eventos dedicado para o worker e threads em background
worker_loop = asyncio.new_event_loop()

def _start_loop(loop: asyncio.AbstractEventLoop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

# Inicia a thread assim que o módulo é importado
_thread = threading.Thread(target=_start_loop, args=(worker_loop,), daemon=True)
_thread.start()

def run_sync(coro: Coroutine) -> Any:
    """
    Executa uma coroutine de forma síncrona no loop de background persistente.
    Isso previne a criação de múltiplos event loops com asyncio.run(),
    evitando vazamento de pools de conexão do asyncpg no db_service.
    """
    return asyncio.run_coroutine_threadsafe(coro, worker_loop).result()
