import asyncio
import unittest
from types import SimpleNamespace

from app.client_lifecycle import ClientConnectionTracker
from app.main import release_idle_ai_resources


class ClientConnectionTrackerTests(unittest.TestCase):
    def test_cleanup_is_claimed_ten_seconds_after_last_connection_closes(self) -> None:
        tracker = ClientConnectionTracker(idle_seconds=10)

        self.assertFalse(tracker.claim_idle_cleanup(now=100))
        tracker.connect("first")
        tracker.connect("second")
        tracker.disconnect("first", now=100)
        self.assertFalse(tracker.claim_idle_cleanup(now=120))

        tracker.disconnect("second", now=100)
        self.assertFalse(tracker.claim_idle_cleanup(now=109.9))
        self.assertTrue(tracker.claim_idle_cleanup(now=110))
        self.assertFalse(tracker.claim_idle_cleanup(now=120))

    def test_reconnection_cancels_pending_cleanup_and_starts_a_new_idle_window(self) -> None:
        tracker = ClientConnectionTracker(idle_seconds=10)
        tracker.connect("first")
        tracker.disconnect("first", now=100)
        tracker.connect("second", now=105)

        self.assertFalse(tracker.claim_idle_cleanup(now=120))

        tracker.disconnect("second", now=120)
        self.assertFalse(tracker.claim_idle_cleanup(now=129.9))
        self.assertTrue(tracker.claim_idle_cleanup(now=130))


class IdleAiCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_idle_cleanup_cancels_ai_tasks_and_unloads_the_model(self) -> None:
        cancelled = asyncio.Event()

        async def running_ai_operation() -> None:
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        task = asyncio.create_task(running_ai_operation())
        await asyncio.sleep(0)

        class FakeAssistant:
            def __init__(self) -> None:
                self.close_calls = 0

            async def close(self) -> None:
                self.close_calls += 1

        assistant = FakeAssistant()
        tracker = ClientConnectionTracker(idle_seconds=10)
        app = SimpleNamespace(
            state=SimpleNamespace(
                active_ai_tasks={task},
                assistant=assistant,
                client_connections=tracker,
            )
        )

        await release_idle_ai_resources(app)

        self.assertTrue(task.cancelled())
        self.assertTrue(cancelled.is_set())
        self.assertEqual(assistant.close_calls, 1)

    async def test_reconnected_client_prevents_cleanup(self) -> None:
        class FakeAssistant:
            def __init__(self) -> None:
                self.close_calls = 0

            async def close(self) -> None:
                self.close_calls += 1

        assistant = FakeAssistant()
        tracker = ClientConnectionTracker(idle_seconds=10)
        tracker.connect("active")
        app = SimpleNamespace(
            state=SimpleNamespace(
                active_ai_tasks=set(),
                assistant=assistant,
                client_connections=tracker,
            )
        )

        await release_idle_ai_resources(app)

        self.assertEqual(assistant.close_calls, 0)


if __name__ == "__main__":
    unittest.main()
