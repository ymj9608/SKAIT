from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import setting


class EnvironmentMigrationTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
