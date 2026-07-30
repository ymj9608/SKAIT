import unittest
from unittest.mock import patch

import open as launcher


class ExistingServerStartupTests(unittest.TestCase):
    def test_existing_backend_is_not_reused(self) -> None:
        processes = []

        with patch.object(launcher, "backend_is_ready", return_value=True):
            with self.assertRaises(launcher.OpenError) as context:
                launcher.start_backend({}, processes)

        self.assertIn("이전 버전을 재사용하지 않도록", str(context.exception))
        self.assertEqual(processes, [])

    def test_shutdown_unloads_the_configured_ollama_model(self) -> None:
        completed = type("Completed", (), {"returncode": 0})()
        with (
            patch.object(launcher.shutil, "which", return_value="/opt/homebrew/bin/ollama"),
            patch.object(launcher, "ollama_is_ready", return_value=True),
            patch.object(launcher.subprocess, "run", return_value=completed) as run,
        ):
            unloaded = launcher.unload_ollama_model(
                {
                    "LLM_PROVIDER": "ollama",
                    "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
                    "OLLAMA_MODEL": "qwen3:8b",
                }
            )

        self.assertTrue(unloaded)
        self.assertEqual(run.call_args.args[0], ["/opt/homebrew/bin/ollama", "stop", "qwen3:8b"])
        self.assertEqual(
            run.call_args.kwargs["env"]["OLLAMA_HOST"],
            "http://127.0.0.1:11434",
        )

    def test_shutdown_does_not_touch_ollama_for_another_provider(self) -> None:
        with patch.object(launcher.shutil, "which") as which:
            unloaded = launcher.unload_ollama_model(
                {"LLM_PROVIDER": "huggingface"}
            )

        self.assertFalse(unloaded)
        which.assert_not_called()

    def test_existing_frontend_is_not_reused(self) -> None:
        processes = []

        with patch.object(launcher, "frontend_is_ready", return_value=True):
            with self.assertRaises(launcher.OpenError) as context:
                launcher.start_frontend(processes)

        self.assertIn("이전 버전을 재사용하지 않도록", str(context.exception))
        self.assertEqual(processes, [])


if __name__ == "__main__":
    unittest.main()
