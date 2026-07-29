import os
import sys
import unittest
from pathlib import Path

os.environ["APP_ENV"] = "test"
os.environ["ADMIN_PASSWORD"] = "a-strong-test-password"
os.environ["TRUSTED_ORIGINS"] = "https://test.example"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from cors_config import CORS_METHODS, configure_cors


def build_app(origins: tuple[str, ...]) -> FastAPI:
    app = FastAPI()
    configure_cors(app, origins)

    @app.get("/resource")
    def resource():
        return {"ok": True}

    @app.post("/resource")
    def update_resource():
        return {"ok": True}

    return app


class CorsTests(unittest.TestCase):
    def test_same_origin_mode_can_disable_cors(self):
        with TestClient(build_app(())) as client:
            response = client.get(
                "/resource",
                headers={"Origin": "https://test.example"},
            )
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_trusted_preflight_uses_exact_minimum_allowlist(self):
        with TestClient(build_app(("https://test.example",))) as client:
            response = client.options(
                "/resource",
                headers={
                    "Origin": "https://test.example",
                    "Access-Control-Request-Method": "DELETE",
                    "Access-Control-Request-Headers":
                        "Content-Type, X-CSRF-Token",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "https://test.example",
        )
        self.assertEqual(
            set(response.headers["access-control-allow-methods"].split(", ")),
            set(CORS_METHODS),
        )
        self.assertEqual(
            response.headers["access-control-allow-credentials"],
            "true",
        )
        self.assertNotEqual(
            response.headers["access-control-allow-origin"],
            "*",
        )

    def test_untrusted_origin_receives_no_allow_origin_header(self):
        with TestClient(build_app(("https://test.example",))) as client:
            preflight = client.options(
                "/resource",
                headers={
                    "Origin": "https://evil.example",
                    "Access-Control-Request-Method": "POST",
                },
            )
            request = client.get(
                "/resource",
                headers={"Origin": "https://evil.example"},
            )
        self.assertNotIn(
            "access-control-allow-origin",
            preflight.headers,
        )
        self.assertNotIn(
            "access-control-allow-origin",
            request.headers,
        )


if __name__ == "__main__":
    unittest.main()
