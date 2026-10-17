import time
import logging
import inspect
from contextlib import ContextDecorator
from functools import wraps
from typing import List, Dict, Any

logger = logging.getLogger("clipmaker.timing")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)

_STAGE_TIMINGS: List[Dict[str, Any]] = []


def get_stage_timings() -> List[Dict[str, Any]]:
    """Retorna cópia das medições coletadas até o momento."""
    return list(_STAGE_TIMINGS)


def reset_stage_timings() -> None:
    """Limpa o registro de medições."""
    _STAGE_TIMINGS.clear()


class timed(ContextDecorator):
    """
    Decorator e Context Manager para medição de performance de etapas do pipeline.
    Emite log na linha exata:
        TIMING stage=<nome> seconds=<n>
    E registra as métricas para benchmarks e auditoria.
    """

    def __init__(self, stage: str, record: bool = True):
        self.stage = stage
        self.record = record
        self.start_time: float = 0.0
        self.elapsed: float = 0.0

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.elapsed = time.perf_counter() - self.start_time
        logger.info(f"TIMING stage={self.stage} seconds={self.elapsed:.2f}")
        if self.record:
            _STAGE_TIMINGS.append({
                "stage": self.stage,
                "seconds": round(self.elapsed, 2),
            })
        return False

    def __call__(self, func):
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                with timed(self.stage, record=self.record):
                    return await func(*args, **kwargs)
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                with timed(self.stage, record=self.record):
                    return func(*args, **kwargs)
            return sync_wrapper
