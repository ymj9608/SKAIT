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

    def test_existing_frontend_is_not_reused(self) -> None:
        processes = []

        with patch.object(launcher, "frontend_is_ready", return_value=True):
            with self.assertRaises(launcher.OpenError) as context:
                launcher.start_frontend(processes)

        self.assertIn("이전 버전을 재사용하지 않도록", str(context.exception))
        self.assertEqual(processes, [])


if __name__ == "__main__":
    unittest.main()
