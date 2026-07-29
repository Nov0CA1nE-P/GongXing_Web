import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


class ImportAndLifespanTests(unittest.TestCase):
    def test_test_import_skips_dotenv_and_paths_until_lifespan(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = root / "db" / "test.db"
            uploads = root / "uploads"
            temporary = root / "temporary"
            env = os.environ.copy()
            env.update(
                {
                    "APP_ENV": "test",
                    "ADMIN_PASSWORD": "a-strong-test-password",
                    "ADMIN_SESSION_TTL_SECONDS": "7200",
                    "TRUSTED_ORIGINS": "https://test.example",
                    "TRUSTED_PROXY_IPS": "",
                    "DATABASE_PATH": str(database),
                    "UPLOADS_DIR": str(uploads),
                    "COURSEWARE_TEMP_DIR": str(temporary),
                    "PYTHONPATH": str(BACKEND_DIR),
                }
            )
            script = textwrap.dedent(
                f"""
                import dotenv
                def forbidden_dotenv():
                    raise AssertionError("test mode must not read .env")
                dotenv.load_dotenv = forbidden_dotenv

                from fastapi.testclient import TestClient
                import main

                assert not __import__("pathlib").Path({str(database)!r}).exists()
                assert not __import__("pathlib").Path({str(uploads)!r}).exists()
                assert not __import__("pathlib").Path({str(temporary)!r}).exists()

                with TestClient(main.app):
                    assert __import__("pathlib").Path({str(database)!r}).exists()
                    assert __import__("pathlib").Path({str(uploads)!r}).exists()
                    worker = main.app.state.contact_retention_worker
                    assert worker._task is not None

                assert main.app.state.contact_retention_worker is None
                """
            )
            result = subprocess.run(
                [sys.executable, "-c", script],
                env=env,
                cwd=temp_dir,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(
                result.returncode,
                0,
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
