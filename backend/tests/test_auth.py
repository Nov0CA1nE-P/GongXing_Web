import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

os.environ["APP_ENV"] = "test"
os.environ["ADMIN_PASSWORD"] = "a-strong-test-password"
os.environ["ADMIN_SESSION_TTL_SECONDS"] = "7200"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

try:
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient
except ModuleNotFoundError as exc:
    raise unittest.SkipTest(
        "需要先安装 backend/requirements.txt 中的现有后端依赖"
    ) from exc

import auth
import routes.admin as admin_routes
import routes.contact as contact_routes
import routes.courseware as courseware_routes
import routes.guestbook as guestbook_routes
import routes.qanda as qanda_routes
from auth import AdminSession, AdminSessionStore, require_admin


class MutableClock:
    def __init__(self, value: float = 1000.0) -> None:
        self.value = value
        self.lock = threading.Lock()

    def __call__(self) -> float:
        with self.lock:
            return self.value

    def advance(self, seconds: float) -> None:
        with self.lock:
            self.value += seconds


class SessionStoreTests(unittest.TestCase):
    def test_independent_sessions_and_logout(self):
        store = AdminSessionStore(7200)
        first_token, _ = store.create()
        second_token, _ = store.create()

        store.revoke(first_token)

        self.assertIsNone(store.validate(first_token))
        self.assertIsNotNone(store.validate(second_token))

    def test_absolute_expiry_and_restart(self):
        clock = MutableClock()
        store = AdminSessionStore(300, clock)
        token, session = store.create()
        clock.advance(299)
        self.assertEqual(store.validate(token), session)
        clock.advance(1)
        self.assertIsNone(store.validate(token))

        restarted_store = AdminSessionStore(300, clock)
        self.assertIsNone(restarted_store.validate(token))

    def test_random_and_truncated_tokens_are_rejected(self):
        store = AdminSessionStore(7200)
        token, _ = store.create()

        self.assertIsNone(store.validate("random-token"))
        self.assertIsNone(store.validate(token[:-1]))

    def test_concurrent_create_validate_cleanup_and_revoke(self):
        clock = MutableClock()
        store = AdminSessionStore(300, clock)

        def exercise(index: int) -> None:
            token, _ = store.create()
            self.assertIsNotNone(store.validate(token))
            if index % 2 == 0:
                store.revoke(token)
            if index % 10 == 0:
                clock.advance(1)
                store.count()

        with ThreadPoolExecutor(max_workers=12) as executor:
            list(executor.map(exercise, range(200)))

        self.assertGreaterEqual(store.count(), 0)


class AdminRouteTests(unittest.TestCase):
    def setUp(self):
        self.store = AdminSessionStore(7200)
        self.app = FastAPI()
        self.app.include_router(admin_routes.router)

        @self.app.get("/api/protected")
        def protected(_session: AdminSession = Depends(require_admin)):
            return {"ok": True}

        self.store_patches = [
            patch.object(auth, "admin_session_store", self.store),
            patch.object(admin_routes, "admin_session_store", self.store),
            patch.object(auth, "ADMIN_AUTH_CONFIGURED", True),
            patch.object(auth, "ADMIN_PASSWORD", "a-strong-test-password"),
            patch.object(auth, "ADMIN_COOKIE_SECURE", False),
        ]
        for active_patch in self.store_patches:
            active_patch.start()
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        for active_patch in reversed(self.store_patches):
            active_patch.stop()

    def test_login_session_and_logout_cookie_contract(self):
        response = self.client.post(
            "/api/admin/login",
            json={"password": "a-strong-test-password"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["authenticated"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)
        self.assertIn("path=/api", cookie)
        self.assertNotIn("max-age", cookie)
        self.assertNotIn("expires", cookie)
        self.assertNotIn("a-strong-test-password", cookie)

        session_response = self.client.get("/api/admin/session")
        self.assertEqual(session_response.status_code, 200)
        self.assertEqual(session_response.headers["cache-control"], "no-store")
        logout = self.client.post("/api/admin/logout")
        self.assertEqual(logout.status_code, 204)
        self.assertEqual(logout.headers["cache-control"], "no-store")
        self.assertIn("path=/api", logout.headers["set-cookie"].lower())
        self.assertEqual(
            self.client.get("/api/admin/session").status_code,
            401,
        )
        self.assertEqual(self.client.post("/api/admin/logout").status_code, 204)

    def test_wrong_password_does_not_set_cookie(self):
        response = self.client.post(
            "/api/admin/login",
            json={"password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("set-cookie", response.headers)

    def test_unconfigured_authentication_returns_503(self):
        with patch.object(auth, "ADMIN_AUTH_CONFIGURED", False):
            response = self.client.post(
                "/api/admin/login",
                json={"password": "any-password"},
            )
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("set-cookie", response.headers)

    def test_production_cookie_uses_secure_on_set_and_delete(self):
        with patch.object(auth, "ADMIN_COOKIE_SECURE", True):
            login = self.client.post(
                "/api/admin/login",
                json={"password": "a-strong-test-password"},
            )
            logout = self.client.post("/api/admin/logout")

        login_cookie = login.headers["set-cookie"].lower()
        logout_cookie = logout.headers["set-cookie"].lower()
        self.assertIn("secure", login_cookie)
        self.assertIn("path=/api", login_cookie)
        self.assertIn("secure", logout_cookie)
        self.assertIn("path=/api", logout_cookie)

    def test_valid_non_admin_session_returns_403(self):
        token, _ = self.store.create(role="viewer")
        self.client.cookies.set("admin_session", token, path="/api")
        response = self.client.get("/api/protected")
        self.assertEqual(response.status_code, 403)


class ProtectedEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = FastAPI()
        app.include_router(courseware_routes.router)
        app.include_router(qanda_routes.router)
        app.include_router(guestbook_routes.router)
        app.include_router(contact_routes.router)
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def test_all_admin_endpoints_reject_missing_cookie(self):
        requests = [
            (
                "post",
                "/api/courseware/upload",
                {
                    "data": {
                        "title": "test",
                        "date": "2026-01-01",
                    },
                    "files": {
                        "file": ("test.pdf", b"test", "application/pdf")
                    },
                },
            ),
            ("delete", "/api/courseware/1", {}),
            ("get", "/api/qanda/questions/pending", {}),
            (
                "put",
                "/api/qanda/answers/1/review",
                {"json": {"status": "published"}},
            ),
            ("delete", "/api/qanda/questions/1", {}),
            ("get", "/api/qanda/admin/all", {}),
            ("get", "/api/qanda/follow-ups/pending", {}),
            (
                "put",
                "/api/qanda/follow-ups/1/review",
                {"json": {"status": "published"}},
            ),
            ("delete", "/api/qanda/follow-ups/1", {}),
            ("delete", "/api/guestbook/messages/1", {}),
            ("get", "/api/contact/submissions", {}),
        ]
        for method, path, kwargs in requests:
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(path, **kwargs)
                self.assertEqual(response.status_code, 401)

    def test_public_status_query_cannot_select_pending_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "test.db"
            conn = sqlite3.connect(database_path)
            conn.execute(
                "CREATE TABLE questions "
                "(id INTEGER PRIMARY KEY, author TEXT, content TEXT, created_at TEXT)"
            )
            conn.execute(
                "CREATE TABLE answers "
                "(id INTEGER PRIMARY KEY, question_id INTEGER, content TEXT, "
                "status TEXT, likes INTEGER)"
            )
            conn.execute(
                "INSERT INTO questions VALUES (1, '公开', '公开问题', '2026-01-01')"
            )
            conn.execute(
                "INSERT INTO questions VALUES (2, '待审核', '私密问题', '2026-01-02')"
            )
            conn.execute(
                "INSERT INTO answers VALUES (1, 1, '公开回答', 'published', 0)"
            )
            conn.execute(
                "INSERT INTO answers VALUES (2, 2, '待审核回答', 'pending', 0)"
            )
            conn.commit()
            conn.close()

            def get_test_db():
                test_conn = sqlite3.connect(database_path)
                test_conn.row_factory = sqlite3.Row
                return test_conn

            with patch.object(qanda_routes, "get_db", get_test_db):
                response = self.client.get(
                    "/api/qanda/questions?status=pending"
                )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["questions"][0]["content"], "公开问题")


if __name__ == "__main__":
    unittest.main()
