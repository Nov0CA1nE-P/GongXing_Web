import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


class ConfigValidationTests(unittest.TestCase):
    def import_config(self, **settings: str):
        env = os.environ.copy()
        for name in (
            "APP_ENV",
            "ADMIN_PASSWORD",
            "ADMIN_SESSION_TTL_SECONDS",
        ):
            env.pop(name, None)
        env.update(settings)
        env["PYTHONPATH"] = str(BACKEND_DIR)
        env["PYTHON_DOTENV_DISABLED"] = "1"
        with tempfile.TemporaryDirectory() as workdir:
            return subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import sys, types; "
                        "dotenv = types.ModuleType('dotenv'); "
                        "dotenv.load_dotenv = lambda: None; "
                        "sys.modules['dotenv'] = dotenv; "
                        "import config"
                    ),
                ],
                cwd=workdir,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

    def test_app_env_is_required_and_validated(self):
        self.assertNotEqual(self.import_config().returncode, 0)
        self.assertNotEqual(
            self.import_config(APP_ENV="staging").returncode,
            0,
        )

    def test_ttl_must_be_integer_within_bounds(self):
        base = {
            "APP_ENV": "test",
            "ADMIN_PASSWORD": "a-strong-test-password",
        }
        self.assertNotEqual(
            self.import_config(
                **base,
                ADMIN_SESSION_TTL_SECONDS="abc",
            ).returncode,
            0,
        )
        self.assertNotEqual(
            self.import_config(
                **base,
                ADMIN_SESSION_TTL_SECONDS="299",
            ).returncode,
            0,
        )
        self.assertNotEqual(
            self.import_config(
                **base,
                ADMIN_SESSION_TTL_SECONDS="28801",
            ).returncode,
            0,
        )

    def test_production_rejects_missing_default_placeholder_and_short_passwords(self):
        bad_passwords = (
            "",
            "admin123",
            "replace-with-a-strong-password",
            "short",
        )
        for password in bad_passwords:
            with self.subTest(password_kind="unsafe"):
                self.assertNotEqual(
                    self.import_config(
                        APP_ENV="production",
                        ADMIN_PASSWORD=password,
                        ADMIN_SESSION_TTL_SECONDS="7200",
                    ).returncode,
                    0,
                )

    def test_valid_production_config_imports(self):
        result = self.import_config(
            APP_ENV="production",
            ADMIN_PASSWORD="a-production-password-strong-enough",
            ADMIN_SESSION_TTL_SECONDS="7200",
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
