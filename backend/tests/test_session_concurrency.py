import asyncio
import unittest
from uuid import uuid4

from app.main import session_pipeline


class SessionPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_session_pipeline_operations_run_in_order(self) -> None:
        session_id = uuid4().hex
        first_entered = asyncio.Event()
        release_first = asyncio.Event()
        second_entered = asyncio.Event()

        async def first_operation() -> None:
            async with session_pipeline(session_id):
                first_entered.set()
                await release_first.wait()

        async def second_operation() -> None:
            await first_entered.wait()
            async with session_pipeline(session_id):
                second_entered.set()

        first_task = asyncio.create_task(first_operation())
        second_task = asyncio.create_task(second_operation())
        await first_entered.wait()
        await asyncio.sleep(0)
        self.assertFalse(second_entered.is_set())

        release_first.set()
        await asyncio.gather(first_task, second_task)
        self.assertTrue(second_entered.is_set())

    async def test_different_sessions_do_not_block_each_other(self) -> None:
        first_session_id = uuid4().hex
        second_session_id = uuid4().hex

        async with session_pipeline(first_session_id):
            entered_second = False

            async def second_operation() -> None:
                nonlocal entered_second
                async with session_pipeline(second_session_id):
                    entered_second = True

            await asyncio.wait_for(second_operation(), timeout=0.1)
            self.assertTrue(entered_second)
