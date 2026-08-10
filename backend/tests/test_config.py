from pathlib import Path
import unittest

from app.config import Settings


class DatabaseFileSettingsTests(unittest.TestCase):
    def test_default_database_uses_skait_filename(self) -> None:
        settings = Settings(_env_file=None)

        self.assertEqual(settings.database_file, Path("data/skait.sqlite3"))

    def test_legacy_database_filename_is_automatically_normalized(self) -> None:
        settings = Settings(
            _env_file=None,
            database_file=Path("/tmp/skait-test/reclass.sqlite3"),
        )

        self.assertEqual(
            settings.database_file,
            Path("/tmp/skait-test/skait.sqlite3"),
        )

    def test_custom_database_filename_is_preserved(self) -> None:
        settings = Settings(
            _env_file=None,
            database_file=Path("/tmp/skait-test/custom.sqlite3"),
        )

        self.assertEqual(
            settings.database_file,
            Path("/tmp/skait-test/custom.sqlite3"),
        )

    def test_default_ollama_model_uses_qwen_3_5_4b(self) -> None:
        settings = Settings(_env_file=None)

        self.assertEqual(settings.ollama_model, "qwen3.5:4b-q4_K_M")


if __name__ == "__main__":
    unittest.main()
