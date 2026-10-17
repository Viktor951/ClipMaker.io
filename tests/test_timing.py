import time
import asyncio
import logging
import pytest
from backend.app.core.timing import timed, get_stage_timings, reset_stage_timings


def test_timed_context_manager(caplog):
    caplog.set_level(logging.INFO)
    reset_stage_timings()

    with timed("test_context_stage"):
        time.sleep(0.05)

    timings = get_stage_timings()
    assert len(timings) == 1
    assert timings[0]["stage"] == "test_context_stage"
    assert timings[0]["seconds"] >= 0.04
    assert any("TIMING stage=test_context_stage seconds=" in record.message for record in caplog.records)


def test_timed_decorator_sync(caplog):
    caplog.set_level(logging.INFO)
    reset_stage_timings()

    @timed("test_sync_stage")
    def sample_func():
        time.sleep(0.05)
        return "result"

    res = sample_func()
    assert res == "result"
    timings = get_stage_timings()
    assert len(timings) == 1
    assert timings[0]["stage"] == "test_sync_stage"
    assert any("TIMING stage=test_sync_stage seconds=" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_timed_decorator_async(caplog):
    caplog.set_level(logging.INFO)
    reset_stage_timings()

    @timed("test_async_stage")
    async def sample_async_func():
        await asyncio.sleep(0.05)
        return 42

    res = await sample_async_func()
    assert res == 42
    timings = get_stage_timings()
    assert len(timings) == 1
    assert timings[0]["stage"] == "test_async_stage"
    assert any("TIMING stage=test_async_stage seconds=" in record.message for record in caplog.records)
