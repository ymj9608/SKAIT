import unittest

from fastapi import BackgroundTasks

from app import main
from app.schemas import LlmModelUpdate
from app.services.study import OllamaStudyAssistant


class LlmModelSettingsTests(unittest.IsolatedAsyncioTestCase):
    def test_qwen_3_models_are_available_model_options(self) -> None:
        for model in (
            "qwen3:0.6b-q8_0",
            "qwen3:1.7b-q4_K_M",
            "qwen3:4b-q4_K_M",
            "qwen3:8b-q4_K_M",
        ):
            with self.subTest(model=model):
                self.assertEqual(LlmModelUpdate(model=model).model, model)

    async def test_model_change_switches_before_unloading_previous_model(self) -> None:
        assistant = OllamaStudyAssistant(
            "http://127.0.0.1:11434",
            "qwen3:0.6b-q8_0",
        )
        calls = []

        async def install_model(model: str) -> bool:
            calls.append(("install", model))
            return True

        async def unload_model(model: str) -> None:
            calls.append(("unload", model))

        assistant.install_model = install_model
        assistant.unload_model = unload_model
        background_tasks = BackgroundTasks()
        previous_state = dict(main.app.state._state)
        main.app.state.assistant = assistant
        main.app.state.active_ai_tasks = set()
        main.app.state.llm_model_change_in_progress = False
        try:
            response = await main.update_llm_model(
                LlmModelUpdate(model="qwen3:4b-q4_K_M"),
                background_tasks,
            )
            self.assertEqual(calls, [("install", "qwen3:4b-q4_K_M")])
            self.assertEqual(assistant.model, "qwen3:4b-q4_K_M")
            await background_tasks()
        finally:
            main.app.state._state.clear()
            main.app.state._state.update(previous_state)

        self.assertEqual(
            calls,
            [
                ("install", "qwen3:4b-q4_K_M"),
                ("unload", "qwen3:0.6b-q8_0"),
            ],
        )
        self.assertEqual(response.model, "qwen3:4b-q4_K_M")
        self.assertTrue(response.downloaded)
        self.assertEqual(assistant.model, "qwen3:4b-q4_K_M")


if __name__ == "__main__":
    unittest.main()
