import unittest

from app import main
from app.schemas import LlmModelUpdate
from app.services.study import OllamaStudyAssistant


class LlmModelSettingsTests(unittest.IsolatedAsyncioTestCase):
    def test_qwen_3_5_0_8b_is_an_available_model_option(self) -> None:
        payload = LlmModelUpdate(model="qwen3.5:0.8b-q8_0")

        self.assertEqual(payload.model, "qwen3.5:0.8b-q8_0")

    async def test_model_change_downloads_unloads_and_switches_in_order(self) -> None:
        assistant = OllamaStudyAssistant(
            "http://127.0.0.1:11434",
            "qwen3.5:2b-q4_K_M",
        )
        calls = []

        async def install_model(model: str) -> bool:
            calls.append(("install", model))
            return True

        async def close() -> None:
            calls.append(("close", assistant.model))

        assistant.install_model = install_model
        assistant.close = close
        previous_state = dict(main.app.state._state)
        main.app.state.assistant = assistant
        main.app.state.active_ai_tasks = set()
        main.app.state.llm_model_change_in_progress = False
        try:
            response = await main.update_llm_model(
                LlmModelUpdate(model="qwen3.5:4b-q4_K_M")
            )
        finally:
            main.app.state._state.clear()
            main.app.state._state.update(previous_state)

        self.assertEqual(
            calls,
            [
                ("install", "qwen3.5:4b-q4_K_M"),
                ("close", "qwen3.5:2b-q4_K_M"),
            ],
        )
        self.assertEqual(response.model, "qwen3.5:4b-q4_K_M")
        self.assertTrue(response.downloaded)
        self.assertEqual(assistant.model, "qwen3.5:4b-q4_K_M")


if __name__ == "__main__":
    unittest.main()
