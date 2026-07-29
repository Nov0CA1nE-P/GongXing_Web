import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


class ConfigValidationTests(unittest.TestCase):
    def import_config(
        self,
        output_expression: str | None = None,
        **settings: str,
    ):
        env = os.environ.copy()
        for name in (
            "APP_ENV",
            "ADMIN_PASSWORD",
            "ADMIN_SESSION_TTL_SECONDS",
            "COURSEWARE_MAX_UPLOAD_MB",
            "TRUSTED_ORIGINS",
            "CORS_ALLOWED_ORIGINS",
        ):
            env.pop(name, None)
        env.update(settings)
        env["PYTHONPATH"] = str(BACKEND_DIR)
        env["PYTHON_DOTENV_DISABLED"] = "1"
        with tempfile.TemporaryDirectory() as workdir:
            command = (
                "import sys, types; "
                "dotenv = types.ModuleType('dotenv'); "
                "dotenv.load_dotenv = lambda: None; "
                "sys.modules['dotenv'] = dotenv; "
                "import config"
            )
            if output_expression:
                command += f"; print(repr({output_expression}))"
            return subprocess.run(
                [
                    sys.executable,
                    "-c",
                    command,
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
            "TRUSTED_ORIGINS": "https://test.example",
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
                        TRUSTED_ORIGINS="https://example.com",
                    ).returncode,
                    0,
                )

    def test_valid_production_config_imports(self):
        result = self.import_config(
            APP_ENV="production",
            ADMIN_PASSWORD="a-production-password-strong-enough",
            ADMIN_SESSION_TTL_SECONDS="7200",
            TRUSTED_ORIGINS="https://example.com",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_courseware_upload_limit_must_be_integer_within_bounds(self):
        base = {
            "APP_ENV": "test",
            "ADMIN_PASSWORD": "a-strong-test-password",
            "ADMIN_SESSION_TTL_SECONDS": "7200",
            "TRUSTED_ORIGINS": "https://test.example",
        }
        for value in ("abc", "0", "501"):
            with self.subTest(value=value):
                self.assertNotEqual(
                    self.import_config(
                        **base,
                        COURSEWARE_MAX_UPLOAD_MB=value,
                    ).returncode,
                    0,
                )
        self.assertEqual(
            self.import_config(
                **base,
                COURSEWARE_MAX_UPLOAD_MB="50",
            ).returncode,
            0,
        )

    def test_trusted_origins_are_required_and_strictly_validated(self):
        base = {
            "APP_ENV": "test",
            "ADMIN_PASSWORD": "a-strong-test-password",
        }
        self.assertNotEqual(self.import_config(**base).returncode, 0)
        for origin in (
            "*",
            "null",
            "https://test.example/path",
            "https://test.example?query=1",
            "https://test.example#fragment",
            "http://test.example",
            "https://user@test.example",
        ):
            with self.subTest(origin=origin):
                self.assertNotEqual(
                    self.import_config(
                        **base,
                        TRUSTED_ORIGINS=origin,
                    ).returncode,
                    0,
                )

    def test_environment_origin_rules_and_cors_subset(self):
        common = {
            "ADMIN_PASSWORD": "a-strong-test-password",
            "ADMIN_SESSION_TTL_SECONDS": "7200",
        }
        self.assertEqual(
            self.import_config(
                **common,
                APP_ENV="development",
                TRUSTED_ORIGINS="http://127.0.0.1:5173",
            ).returncode,
            0,
        )
        self.assertNotEqual(
            self.import_config(
                **common,
                APP_ENV="development",
                TRUSTED_ORIGINS="https://example.com",
            ).returncode,
            0,
        )
        self.assertNotEqual(
            self.import_config(
                **common,
                APP_ENV="production",
                TRUSTED_ORIGINS="http://example.com",
            ).returncode,
            0,
        )
        self.assertNotEqual(
            self.import_config(
                **common,
                APP_ENV="test",
                TRUSTED_ORIGINS="https://test.example",
                CORS_ALLOWED_ORIGINS="https://other.example",
            ).returncode,
            0,
        )

    def test_origins_normalize_case_and_default_ports(self):
        result = self.import_config(
            "config.TRUSTED_ORIGINS",
            APP_ENV="test",
            ADMIN_PASSWORD="a-strong-test-password",
            TRUSTED_ORIGINS=(
                "HTTPS://TEST.EXAMPLE:443,"
                "HTTP://127.0.0.1:80"
            ),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "('https://test.example', 'http://127.0.0.1')",
            result.stdout,
        )

    def test_equivalent_origins_are_duplicate(self):
        result = self.import_config(
            APP_ENV="test",
            ADMIN_PASSWORD="a-strong-test-password",
            TRUSTED_ORIGINS=(
                "https://test.example,"
                "HTTPS://TEST.EXAMPLE:443"
            ),
        )
        self.assertNotEqual(result.returncode, 0)

    def test_cors_subset_uses_normalized_origins(self):
        result = self.import_config(
            "config.CORS_ALLOWED_ORIGINS",
            APP_ENV="test",
            ADMIN_PASSWORD="a-strong-test-password",
            TRUSTED_ORIGINS="HTTPS://TEST.EXAMPLE:443",
            CORS_ALLOWED_ORIGINS="https://test.example",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("('https://test.example',)", result.stdout)


if __name__ == "__main__":
    unittest.main()
