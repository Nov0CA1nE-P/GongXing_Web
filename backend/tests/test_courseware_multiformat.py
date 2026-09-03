import io
import os
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

os.environ["APP_ENV"] = "test"
os.environ["ADMIN_PASSWORD"] = "a-strong-test-password"
os.environ["ADMIN_SESSION_TTL_SECONDS"] = "7200"
os.environ["TRUSTED_ORIGINS"] = "https://test.example"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI
from fastapi.testclient import TestClient

import database
import routes.courseware as courseware_routes
import routes.files as files_routes
from auth import AdminSession, require_admin_write


def valid_docx() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>',
        )
    return output.getvalue()


def valid_jpg() -> bytes:
    return bytes.fromhex(
        "ffd8ffe000104a46494600010100000100010000"
        "ffc00011080001000103011100021100031100"
        "ffc40014000100000000000000000000000000000000"
        "ffda0008010100003f00ffd9"
    )


class MultiFormatCoursewareTests(unittest.TestCase):
    def setUp(self):
        self.temp_context = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_context.name)
        self.database = self.root / "site.db"
        self.uploads = self.root / "uploads"
        self.temp = self.root / "tmp"
        self.uploads.mkdir()
        with patch.object(database, "DATABASE_PATH", str(self.database)):
            database.init_db()

        def get_db():
            conn = sqlite3.connect(self.database)
            conn.row_factory = sqlite3.Row
            return conn

        self.patches = [
            patch.object(courseware_routes, "UPLOADS_DIR", str(self.uploads)),
            patch.object(courseware_routes, "COURSEWARE_TEMP_DIR", str(self.temp)),
            patch.object(courseware_routes, "get_db", get_db),
            patch.object(files_routes, "UPLOADS_DIR", str(self.uploads)),
            patch.object(files_routes, "get_db", get_db),
        ]
        for active_patch in self.patches:
            active_patch.start()
        self.app = FastAPI()
        self.app.include_router(courseware_routes.router)
        self.app.include_router(files_routes.router)
        self.app.dependency_overrides[require_admin_write] = lambda: AdminSession(
            role="admin", expires_at=9999999999, csrf_token="test"
        )
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        for active_patch in reversed(self.patches):
            active_patch.stop()
        self.temp_context.cleanup()

    def test_upload_and_download_each_public_format(self):
        files = (
            ("slides.pptx", b"", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
            ("notes.docx", valid_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            ("photo.jpg", valid_jpg(), "image/jpeg"),
        )
        # 使用最小合法 PPTX，与现有文件存储测试保持相同内容结构。
        pptx = io.BytesIO()
        with zipfile.ZipFile(pptx, "w") as archive:
            archive.writestr(
                "[Content_Types].xml",
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/></Types>',
            )
            archive.writestr(
                "ppt/presentation.xml",
                '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>',
            )
        files = ((files[0][0], pptx.getvalue(), files[0][2]), *files[1:])
        for name, content, mime in files:
            response = self.client.post(
                "/api/courseware/upload",
                data={"title": name},
                files={"file": (name, content, mime)},
            )
            self.assertEqual(response.status_code, 200, response.text)

        listing = self.client.get("/api/courseware/list")
        self.assertEqual(listing.status_code, 200)
        by_type = {item["file_type"]: item for item in listing.json()}
        self.assertEqual(set(by_type), {"pptx", "docx", "jpg"})
        for file_type, item in by_type.items():
            download = self.client.get("/data/uploads/" + item["file_path"])
            self.assertEqual(download.status_code, 200)
            self.assertIn(
                "inline" if file_type == "jpg" else "attachment",
                download.headers["content-disposition"].lower(),
            )
            self.assertEqual(download.headers["x-content-type-options"], "nosniff")

    def test_docx_jpg_content_mismatch_is_rejected_without_file(self):
        for name, mime in (("bad.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"), ("bad.jpg", "image/jpeg")):
            response = self.client.post(
                "/api/courseware/upload",
                data={"title": name},
                files={"file": (name, b"plain text", mime)},
            )
            self.assertEqual(response.status_code, 400)
        self.assertEqual(list(self.uploads.iterdir()), [])

    def test_generic_columns_are_used_and_old_schema_migration_is_idempotent(self):
        response = self.client.post(
            "/api/courseware/upload",
            data={"title": "notes"},
            files={
                "file": (
                    "notes.docx",
                    valid_docx(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        self.assertEqual(response.status_code, 200)
        conn = sqlite3.connect(self.database)
        row = conn.execute(
            "SELECT file_path, file_type, pdf_path, pptx_path FROM courseware"
        ).fetchone()
        conn.close()
        self.assertTrue(row[0].endswith(".docx"))
        self.assertEqual(row[1], "docx")
        self.assertEqual(row[2:], ("", ""))

    def test_old_courseware_schema_migrates_without_losing_rows(self):
        old_database = self.root / "old.db"
        conn = sqlite3.connect(old_database)
        conn.execute(
            "CREATE TABLE courseware (id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
            "date TEXT NOT NULL, description TEXT DEFAULT '', tags TEXT DEFAULT '', "
            "pdf_path TEXT DEFAULT '', pptx_path TEXT DEFAULT '', created_at TIMESTAMP)"
        )
        conn.execute(
            "INSERT INTO courseware (id, title, date, pdf_path) VALUES (1, '旧记录', '2026-08-01', 'old.pdf')"
        )
        conn.commit()
        conn.close()
        with patch.object(database, "DATABASE_PATH", str(old_database)):
            database.init_db()
            database.init_db()
        conn = sqlite3.connect(old_database)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(courseware)")}
        row = conn.execute("SELECT title, pdf_path FROM courseware WHERE id = 1").fetchone()
        conn.close()
        self.assertTrue({"file_path", "file_type"}.issubset(columns))
        self.assertEqual(row, ("旧记录", "old.pdf"))


if __name__ == "__main__":
    unittest.main()
