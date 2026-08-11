from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, call, patch

import setting


class EnvironmentMigrationTests(unittest.TestCase):
    def test_existing_qwen3_8b_alias_is_normalized(self) -> None:
        with TemporaryDirectory() as directory:
            project = Path(directory)
            backend = project / "backend"
            frontend = project / "frontend"
            backend.mkdir()
            frontend.mkdir()
            (backend / ".env").write_text(
                "OLLAMA_MODEL=qwen3:8b\nSTT_PROVIDER=demo\n",
                encoding="utf-8",
            )
            (backend / ".env.example").write_text(
                "OLLAMA_MODEL=qwen3:4b-q4_K_M\nSTT_PROVIDER=demo\n",
                encoding="utf-8",
            )
            (frontend / ".env").write_text(
                "VITE_API_BASE_URL=/api\n", encoding="utf-8"
            )
            (frontend / ".env.example").write_text(
                "VITE_API_BASE_URL=/api\n", encoding="utf-8"
            )

            with (
                patch.object(setting, "PROJECT_DIR", project),
                patch.object(setting, "BACKEND_DIR", backend),
                patch.object(setting, "FRONTEND_DIR", frontend),
            ):
                values = setting.prepare_environment_files(setting.Installer())

            self.assertEqual(values["OLLAMA_MODEL"], "qwen3:8b-q4_K_M")
            self.assertIn(
                "OLLAMA_MODEL=qwen3:8b-q4_K_M",
                (backend / ".env").read_text(encoding="utf-8"),
            )

    def test_existing_legacy_database_setting_is_updated(self) -> None:
        with TemporaryDirectory() as directory:
            project = Path(directory)
            backend = project / "backend"
            frontend = project / "frontend"
            backend.mkdir()
            frontend.mkdir()
            backend_env = backend / ".env"
            backend_example = backend / ".env.example"
            frontend_env = frontend / ".env"
            frontend_example = frontend / ".env.example"
            backend_env.write_text(
                "DATABASE_FILE=data/reclass.sqlite3\nSTT_PROVIDER=demo\n",
                encoding="utf-8",
            )
            backend_example.write_text(
                "DATABASE_FILE=data/skait.sqlite3\nSTT_PROVIDER=demo\n",
                encoding="utf-8",
            )
            frontend_env.write_text("VITE_API_BASE_URL=/api\n", encoding="utf-8")
            frontend_example.write_text("VITE_API_BASE_URL=/api\n", encoding="utf-8")

            with (
                patch.object(setting, "PROJECT_DIR", project),
                patch.object(setting, "BACKEND_DIR", backend),
                patch.object(setting, "FRONTEND_DIR", frontend),
            ):
                values = setting.prepare_environment_files(setting.Installer())

            self.assertEqual(values["DATABASE_FILE"], "data/skait.sqlite3")
            self.assertIn(
                "DATABASE_FILE=data/skait.sqlite3",
                backend_env.read_text(encoding="utf-8"),
            )


class ModelInstallationTests(unittest.TestCase):
    def test_install_models_checks_and_downloads_all_llm_options(self) -> None:
        installer = Mock(dry_run=False)
        installed_models = {
            "qwen3:0.6b-q8_0",
            "qwen3:4b-q4_K_M",
        }

        def model_is_installed(command, cwd=setting.PROJECT_DIR):
            return command[-1] in installed_models

        with (
            patch.object(setting, "start_ollama"),
            patch.object(setting.shutil, "which", return_value="/usr/local/bin/ollama"),
            patch.object(setting, "command_succeeds", side_effect=model_is_installed),
        ):
            setting.install_models(
                installer,
                Path("/tmp/python"),
                {
                    "STT_PROVIDER": "demo",
                    "LLM_PROVIDER": "ollama",
                    "OLLAMA_MODEL": "qwen3:4b-q4_K_M",
                },
            )

        self.assertEqual(
            installer.run.call_args_list,
            [
                call(["/usr/local/bin/ollama", "pull", "qwen3:1.7b-q4_K_M"]),
                call(["/usr/local/bin/ollama", "pull", "qwen3:8b-q4_K_M"]),
            ],
        )

    def test_install_models_preserves_an_extra_configured_model(self) -> None:
        installer = Mock(dry_run=False)

        with (
            patch.object(setting, "start_ollama"),
            patch.object(setting.shutil, "which", return_value="ollama"),
            patch.object(setting, "command_succeeds", return_value=False),
        ):
            setting.install_models(
                installer,
                Path("/tmp/python"),
                {
                    "STT_PROVIDER": "demo",
                    "LLM_PROVIDER": "ollama",
                    "OLLAMA_MODEL": "custom:model",
                },
            )

        pulled_models = [args[0][-1] for args, _ in installer.run.call_args_list]
        self.assertEqual(
            pulled_models,
            [*setting.OLLAMA_LLM_MODELS, "custom:model"],
        )


if __name__ == "__main__":
    unittest.main()
