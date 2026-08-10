from pathlib import Path
import unittest

from pydantic import ValidationError

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

    def test_ollama_performance_mode_defaults_to_balanced(self) -> None:
        settings = Settings(_env_file=None)

        self.assertEqual(settings.ollama_performance_mode, "balanced")

    def test_ollama_performance_mode_is_normalized_and_validated(self) -> None:
        settings = Settings(_env_file=None, ollama_performance_mode=" ECO ")

        self.assertEqual(settings.ollama_performance_mode, "eco")
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, ollama_performance_mode="unlimited")


if __name__ == "__main__":
    unittest.main()
