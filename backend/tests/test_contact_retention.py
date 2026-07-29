import asyncio
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

os.environ["APP_ENV"] = "test"
os.environ["ADMIN_PASSWORD"] = "a-strong-test-password"
os.environ["ADMIN_SESSION_TTL_SECONDS"] = "7200"
os.environ["TRUSTED_ORIGINS"] = "https://test.example"
os.environ["DATABASE_PATH"] = str(
    Path(tempfile.gettempdir()) / "summercamp-import-only.db"
)
os.environ["UPLOADS_DIR"] = str(
    Path(tempfile.gettempdir()) / "summercamp-import-uploads"
)
os.environ["COURSEWARE_TEMP_DIR"] = str(
    Path(tempfile.gettempdir()) / "summercamp-import-temp"
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI
from fastapi.testclient import TestClient

import routes.contact as contact_routes
from abuse_protection import VisitorIdentityMiddleware
from auth import AdminSession, require_admin, require_admin_write
from contact_retention import (
    ContactRetentionWorker,
    classify_contact_timestamp,
    format_sqlite_utc,
    purge_expired_contacts,
)


def create_contact_database(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE contact_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            contact_info TEXT DEFAULT '',
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    conn.close()


class ContactRetentionBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp_context = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_context.name) / "contacts.db"
        create_contact_database(self.database)

        def get_test_db():
            conn = sqlite3.connect(self.database)
            conn.row_factory = sqlite3.Row
            return conn

        self.get_test_db = get_test_db

    def tearDown(self):
        self.temp_context.cleanup()

    def insert(self, created_at: object, name: str = "昵称") -> int:
        conn = self.get_test_db()
        cursor = conn.execute(
            "INSERT INTO contact_submissions "
            "(name, contact_info, message, created_at) VALUES (?, '', ?, ?)",
            (name, "内容线索", created_at),
        )
        conn.commit()
        item_id = cursor.lastrowid
        conn.close()
        return item_id

    def test_exact_utc_boundary_is_expired(self):
        now = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)
        exact = now - timedelta(days=90)
        newer = exact + timedelta(seconds=1)
        self.insert(format_sqlite_utc(exact), "exact")
        self.insert(format_sqlite_utc(newer), "newer")

        deleted = purge_expired_contacts(
            now=now,
            connection_factory=self.get_test_db,
        )
        self.assertEqual(deleted, 1)
        conn = self.get_test_db()
        remaining = conn.execute(
            "SELECT name FROM contact_submissions"
        ).fetchall()
        conn.close()
        self.assertEqual([row["name"] for row in remaining], ["newer"])

    def test_invalid_timestamp_is_visible_and_not_auto_deleted(self):
        now = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)
        invalid_values = (
            "2026-04-01T00:00:00Z",
            "2026-04-01 00:00:00+00:00",
            "2026-04-01 00:00:00.000",
            " 2026-04-01 00:00:00",
            "2026-04-01 00:00:00 ",
            "2026-02-30 00:00:00",
            "",
            None,
            20260401000000,
        )
        invalid_ids = [
            self.insert(value, f"invalid-{index}")
            for index, value in enumerate(invalid_values)
        ]
        for value in invalid_values:
            with self.subTest(value=value):
                view = classify_contact_timestamp(value, now=now)
                self.assertEqual(
                    view.retention_status,
                    "invalid_timestamp",
                )
                self.assertTrue(view.is_visible)
                self.assertIsNone(view.expires_at)

        purge_expired_contacts(
            now=now,
            connection_factory=self.get_test_db,
        )
        conn = self.get_test_db()
        remaining_ids = {
            row["id"]
            for row in conn.execute(
                "SELECT id FROM contact_submissions"
            ).fetchall()
        }
        conn.close()
        self.assertEqual(remaining_ids, set(invalid_ids))

    def test_strict_valid_timestamp_is_parsed_and_expired(self):
        now = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)
        expired_id = self.insert("2026-04-01 00:00:00", "strict-valid")
        view = classify_contact_timestamp(
            "2026-04-01 00:00:00",
            now=now,
        )
        self.assertEqual(view.retention_status, "active")
        self.assertFalse(view.is_visible)
        self.assertEqual(
            purge_expired_contacts(
                now=now,
                connection_factory=self.get_test_db,
            ),
            1,
        )
        conn = self.get_test_db()
        self.assertIsNone(
            conn.execute(
                "SELECT id FROM contact_submissions WHERE id = ?",
                (expired_id,),
            ).fetchone()
        )
        conn.close()

    def test_purge_does_not_delete_record_changed_after_read(self):
        now = datetime(2026, 7, 29, 12, 0, 0, tzinfo=timezone.utc)
        item_id = self.insert("2026-04-01 00:00:00", "changed")

        class RacingConnection:
            def __init__(self, connection):
                self.connection = connection
                self.changed = False

            def execute(self, sql, parameters=()):
                if sql.lstrip().startswith("DELETE") and not self.changed:
                    self.connection.execute(
                        "UPDATE contact_submissions SET created_at = ? "
                        "WHERE id = ?",
                        ("2026-07-29 11:59:59", item_id),
                    )
                    self.changed = True
                return self.connection.execute(sql, parameters)

            def commit(self):
                self.connection.commit()

            def rollback(self):
                self.connection.rollback()

            def close(self):
                self.connection.close()

        deleted = purge_expired_contacts(
            now=now,
            connection_factory=lambda: RacingConnection(self.get_test_db()),
        )
        self.assertEqual(deleted, 0)
        conn = self.get_test_db()
        row = conn.execute(
            "SELECT created_at FROM contact_submissions WHERE id = ?",
            (item_id,),
        ).fetchone()
        conn.close()
        self.assertEqual(row["created_at"], "2026-07-29 11:59:59")


class ContactRouteRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp_context = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_context.name) / "contacts.db"
        create_contact_database(self.database)

        def get_test_db():
            conn = sqlite3.connect(self.database)
            conn.row_factory = sqlite3.Row
            return conn

        self.get_test_db = get_test_db
        self.app = FastAPI()
        self.app.add_middleware(VisitorIdentityMiddleware)
        self.app.include_router(contact_routes.router)
        session = AdminSession(
            role="admin",
            expires_at=time.time() + 300,
            csrf_token="test-csrf-token",
        )
        self.app.dependency_overrides[require_admin] = lambda: session
        self.app.dependency_overrides[require_admin_write] = lambda: session
        self.db_patch = patch.object(
            contact_routes,
            "get_db",
            self.get_test_db,
        )
        self.db_patch.start()
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.db_patch.stop()
        self.temp_context.cleanup()

    def insert(self, created_at: str, name: str) -> int:
        conn = self.get_test_db()
        cursor = conn.execute(
            "INSERT INTO contact_submissions "
            "(name, contact_info, message, created_at) VALUES (?, '', '线索', ?)",
            (name, created_at),
        )
        conn.commit()
        item_id = cursor.lastrowid
        conn.close()
        return item_id

    def test_admin_list_hides_expired_but_keeps_invalid(self):
        now = contact_routes.utc_now()
        self.insert(
            format_sqlite_utc(now - timedelta(days=91)),
            "expired",
        )
        self.insert(
            format_sqlite_utc(now - timedelta(days=1)),
            "active",
        )
        invalid_id = self.insert("invalid", "invalid")

        response = self.client.get("/api/contact/submissions")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual({item["name"] for item in body}, {"active", "invalid"})
        invalid = next(item for item in body if item["id"] == invalid_id)
        self.assertEqual(invalid["retention_status"], "invalid_timestamp")
        self.assertIsNone(invalid["expires_at"])

    def test_invalid_record_can_be_deleted_manually(self):
        invalid_id = self.insert("2026-04-01T00:00:00Z", "invalid")
        response = self.client.delete(
            f"/api/contact/submissions/{invalid_id}"
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(
            self.client.delete(
                f"/api/contact/submissions/{invalid_id}"
            ).status_code,
            404,
        )

    def test_cleanup_failure_does_not_block_new_submission(self):
        cleanup_attempted = threading.Event()

        def failing_cleanup():
            cleanup_attempted.set()
            raise sqlite3.OperationalError("simulated cleanup failure")

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            worker = ContactRetentionWorker(
                purge=failing_cleanup,
                next_expiry=lambda: None,
            )
            app.state.contact_retention_worker = worker
            worker.start()
            try:
                yield
            finally:
                await worker.stop()

        app = FastAPI(lifespan=lifespan)
        app.add_middleware(VisitorIdentityMiddleware)
        app.include_router(contact_routes.router)
        with TestClient(app) as client:
            self.assertTrue(cleanup_attempted.wait(timeout=1))
            response = client.post(
                "/api/contact/submit",
                json={
                    "name": "新昵称",
                    "contact_info": "",
                    "message": "新留言",
                },
            )
        self.assertEqual(response.status_code, 200)
        conn = self.get_test_db()
        count = conn.execute(
            "SELECT COUNT(*) FROM contact_submissions"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)


class ContactRetentionWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_retries_and_stops_without_leaking_task(self):
        attempts = 0

        def purge():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise sqlite3.OperationalError("simulated")
            return 0

        worker = ContactRetentionWorker(
            purge=purge,
            next_expiry=lambda: None,
        )
        worker.start()
        for _ in range(20):
            if attempts >= 1:
                break
            await asyncio.sleep(0)
        worker.notify_changed()
        for _ in range(20):
            if attempts >= 2:
                break
            await asyncio.sleep(0)
        await worker.stop()

        self.assertGreaterEqual(attempts, 2)
        self.assertIsNone(worker._task)
