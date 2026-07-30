import io
import os
import sqlite3
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

os.environ["APP_ENV"] = "test"
os.environ["ADMIN_PASSWORD"] = "a-strong-test-password"
os.environ["ADMIN_SESSION_TTL_SECONDS"] = "7200"
os.environ["COURSEWARE_MAX_UPLOAD_MB"] = "50"
os.environ["TRUSTED_ORIGINS"] = "https://test.example"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.datastructures import Headers, UploadFile

import file_storage
import database as database_module
import routes.courseware as courseware_routes
import routes.files as files_routes
import routes.qanda as qanda_routes
from auth import AdminSession, require_admin, require_admin_write
from file_storage import (
    UnsafeStoredPath,
    classify_stored_path,
    cleanup_stale_temporary_files,
    resolve_upload_path,
    serialize_courseware_row,
    public_pdf_filename,
    store_validated_upload,
)


def valid_pdf() -> bytes:
    return b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def valid_pptx(extra_entries: int = 0) -> bytes:
    output = io.BytesIO()
    content_types = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        b'content-types"><Override PartName="/ppt/presentation.xml" '
        b'ContentType="application/vnd.openxmlformats-officedocument.'
        b'presentationml.presentation.main+xml"/></Types>'
    )
    presentation = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<p:presentation xmlns:p="http://schemas.openxmlformats.org/'
        b'presentationml/2006/main"/>'
    )
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("ppt/presentation.xml", presentation)
        for index in range(extra_entries):
            archive.writestr(f"ppt/slides/slide{index}.xml", b"<slide/>")
    return output.getvalue()


def upload_file(name: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=name,
        headers=Headers({"content-type": content_type}),
    )


def create_database(path: Path) -> None:
    # 复用真实初始化逻辑，但强制指向隔离临时数据库。
    with patch.object(database_module, "DATABASE_PATH", str(path)):
        database_module.init_db()


class PathCompatibilityTests(unittest.TestCase):
    def test_new_windows_and_posix_paths_map_to_basename(self):
        self.assertEqual(
            classify_stored_path("a" * 32 + ".pdf"),
            ("new", "a" * 32 + ".pdf"),
        )
        self.assertEqual(
            classify_stored_path(r"E:\old\data\uploads\旧课件.ppt")[1],
            "旧课件.ppt",
        )
        self.assertEqual(
            classify_stored_path("/srv/app/data/uploads/slides.pptx")[1],
            "slides.pptx",
        )

    def test_mixed_traversal_and_outside_paths_are_rejected(self):
        unsafe_values = (
            r"E:\old/data/uploads/a.pdf",
            "/srv/data/uploads/../a.pdf",
            "/srv/private/a.pdf",
            r"C:\private\a.pdf",
            "../a.pdf",
        )
        for value in unsafe_values:
            with self.subTest(value=value):
                with self.assertRaises(UnsafeStoredPath):
                    classify_stored_path(value)

    def test_serializer_never_exposes_unsafe_absolute_path(self):
        row = {
            "id": 1,
            "pdf_path": "/private/site.db.pdf",
            "pptx_path": r"E:\old\data\uploads\safe.pptx",
        }
        serialized = serialize_courseware_row(row)
        self.assertEqual(serialized["pdf_path"], "")
        self.assertEqual(serialized["pptx_path"], "safe.pptx")

    def test_resolver_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "uploads"
            root.mkdir()
            link = root / "link.pdf"
            link.write_bytes(valid_pdf())
            original_is_symlink = Path.is_symlink

            def reports_target_as_symlink(path: Path) -> bool:
                return path == link or original_is_symlink(path)

            with patch.object(
                Path,
                "is_symlink",
                autospec=True,
                side_effect=reports_target_as_symlink,
            ):
                with self.assertRaises(UnsafeStoredPath):
                    resolve_upload_path(
                        "link.pdf",
                        uploads_dir=root,
                        require_exists=True,
                    )


class PublicPdfSignatureTests(unittest.TestCase):
    def setUp(self):
        self.temp_context = tempfile.TemporaryDirectory()
        self.uploads = Path(self.temp_context.name)
        self.row = {
            "id": 1,
            "title": "PDF",
            "description": "",
            "tags": "测试",
            "pdf_path": "document.pdf",
        }

    def tearDown(self):
        self.temp_context.cleanup()

    def test_empty_and_unreadable_pdf_are_not_public(self):
        target = self.uploads / "document.pdf"
        target.write_bytes(b"")
        self.assertIsNone(
            public_pdf_filename(self.row, uploads_dir=self.uploads)
        )

        target.write_bytes(valid_pdf())
        original_open = Path.open

        def fail_target_open(path, *args, **kwargs):
            if path == target:
                raise PermissionError("simulated")
            return original_open(path, *args, **kwargs)

        with patch.object(
            Path,
            "open",
            autospec=True,
            side_effect=fail_target_open,
        ):
            self.assertIsNone(
                public_pdf_filename(self.row, uploads_dir=self.uploads)
            )

    def test_file_disappearing_after_signature_check_is_not_public(self):
        target = self.uploads / "document.pdf"
        target.write_bytes(valid_pdf())

        def remove_after_check(path):
            path.unlink()
            return True

        with patch.object(
            file_storage,
            "has_pdf_content_signature",
            side_effect=remove_after_check,
        ):
            self.assertIsNone(
                public_pdf_filename(self.row, uploads_dir=self.uploads)
            )


class UploadValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_pdf_and_pptx_get_unique_server_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            uploads = root / "uploads"
            temporary = root / "tmp"
            first_name, first_path = await store_validated_upload(
                upload_file("same.pdf", valid_pdf(), "application/pdf"),
                uploads_dir=uploads,
                temp_dir=temporary,
            )
            second_name, second_path = await store_validated_upload(
                upload_file("same.pdf", valid_pdf(), "application/pdf"),
                uploads_dir=uploads,
                temp_dir=temporary,
            )
            pptx_name, pptx_path = await store_validated_upload(
                upload_file(
                    "slides.pptx",
                    valid_pptx(),
                    "application/vnd.openxmlformats-officedocument."
                    "presentationml.presentation",
                ),
                uploads_dir=uploads,
                temp_dir=temporary,
            )
            self.assertNotEqual(first_name, second_name)
            self.assertRegex(first_name, r"^[0-9a-f]{32}\.pdf$")
            self.assertRegex(pptx_name, r"^[0-9a-f]{32}\.pptx$")
            self.assertTrue(first_path.exists())
            self.assertTrue(second_path.exists())
            self.assertTrue(pptx_path.exists())

    async def test_empty_oversize_bad_mime_and_bad_signatures_are_rejected(self):
        cases = (
            ("empty.pdf", b"", "application/pdf", 100, 400),
            ("large.pdf", valid_pdf(), "application/pdf", 4, 413),
            ("fake.pdf", valid_pdf(), "application/octet-stream", 100, 400),
            ("fake.pdf", b"not a pdf", "application/pdf", 100, 400),
            (
                "fake.pptx",
                b"not a zip",
                "application/vnd.openxmlformats-officedocument."
                "presentationml.presentation",
                100,
                400,
            ),
            (
                "fake.ppt",
                b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
                "application/vnd.ms-powerpoint",
                100,
                400,
            ),
        )
        for name, content, mime, limit, status in cases:
            with self.subTest(name=name, mime=mime):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    with self.assertRaisesRegex(Exception, "") as raised:
                        await store_validated_upload(
                            upload_file(name, content, mime),
                            uploads_dir=root / "uploads",
                            temp_dir=root / "tmp",
                            max_bytes=limit,
                        )
                    self.assertEqual(raised.exception.status_code, status)
                    self.assertEqual(
                        list((root / "tmp").glob("*")),
                        [],
                    )
                    self.assertEqual(
                        list((root / "uploads").glob("*")),
                        [],
                    )

    async def test_pptx_limits_and_dangerous_zip_paths_are_rejected(self):
        cases = []
        with patch.object(file_storage, "MAX_PPTX_ENTRIES", 2):
            cases.append(valid_pptx(extra_entries=1))
            with tempfile.TemporaryDirectory() as temp_dir:
                with self.assertRaises(Exception) as raised:
                    await store_validated_upload(
                        upload_file(
                            "many.pptx",
                            cases[-1],
                            "application/vnd.openxmlformats-officedocument."
                            "presentationml.presentation",
                        ),
                        uploads_dir=Path(temp_dir) / "uploads",
                        temp_dir=Path(temp_dir) / "tmp",
                    )
                self.assertEqual(raised.exception.status_code, 400)

        dangerous = io.BytesIO()
        with zipfile.ZipFile(dangerous, "w") as archive:
            archive.writestr("[Content_Types].xml", b"<Types/>")
            archive.writestr("ppt/presentation.xml", b"<presentation/>")
            archive.writestr("../escape", b"x")
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(Exception) as raised:
                await store_validated_upload(
                    upload_file(
                        "danger.pptx",
                        dangerous.getvalue(),
                        "application/vnd.openxmlformats-officedocument."
                        "presentationml.presentation",
                    ),
                    uploads_dir=Path(temp_dir) / "uploads",
                    temp_dir=Path(temp_dir) / "tmp",
                )
            self.assertEqual(raised.exception.status_code, 400)

    async def test_pptx_xml_and_total_uncompressed_limits_are_enforced(self):
        mime = (
            "application/vnd.openxmlformats-officedocument."
            "presentationml.presentation"
        )
        limits = (
            ("MAX_CONTENT_TYPES_BYTES", 32),
            ("MAX_PRESENTATION_XML_BYTES", 32),
            ("MAX_PPTX_UNCOMPRESSED_BYTES", 64),
        )
        for setting, value in limits:
            with self.subTest(setting=setting):
                with tempfile.TemporaryDirectory() as temp_dir:
                    with patch.object(file_storage, setting, value):
                        with self.assertRaises(Exception) as raised:
                            await store_validated_upload(
                                upload_file(
                                    "limited.pptx",
                                    valid_pptx(),
                                    mime,
                                ),
                                uploads_dir=Path(temp_dir) / "uploads",
                                temp_dir=Path(temp_dir) / "tmp",
                            )
                    self.assertEqual(raised.exception.status_code, 400)


class TemporaryCleanupTests(unittest.TestCase):
    def test_only_module_files_older_than_24_hours_are_removed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            now = time.time()
            old_part = root / f".upload-{'a' * 32}.part"
            exact_part = root / f".upload-{'b' * 32}.part"
            recent_delete = root / f".delete-{'c' * 32}-1.delete"
            old_recovery = root / f".recover-{'d' * 32}-1.hold"
            unrelated = root / ".upload-not-generated.part"
            for path in (
                old_part,
                exact_part,
                recent_delete,
                old_recovery,
                unrelated,
            ):
                path.write_bytes(b"x")
            os.utime(old_part, (now - 86401, now - 86401))
            os.utime(exact_part, (now - 86400, now - 86400))
            os.utime(recent_delete, (now - 60, now - 60))
            os.utime(old_recovery, (now - 90000, now - 90000))
            os.utime(unrelated, (now - 90000, now - 90000))

            cleanup_stale_temporary_files(temp_dir=root, now=now)

            self.assertFalse(old_part.exists())
            self.assertTrue(exact_part.exists())
            self.assertTrue(recent_delete.exists())
            self.assertTrue(old_recovery.exists())
            self.assertTrue(unrelated.exists())

    def test_cleanup_failure_does_not_escape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(
                Path,
                "iterdir",
                autospec=True,
                side_effect=OSError("simulated"),
            ):
                cleanup_stale_temporary_files(temp_dir=temp_dir)


class DownloadRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_context = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_context.name)
        self.uploads = self.root / "uploads"
        self.database = self.root / "test.db"
        self.uploads.mkdir()
        create_database(self.database)

        def get_test_db():
            conn = sqlite3.connect(self.database)
            conn.row_factory = sqlite3.Row
            return conn

        self.app = FastAPI()
        self.app.include_router(files_routes.router)
        self.patches = [
            patch.object(files_routes, "UPLOADS_DIR", str(self.uploads)),
            patch.object(files_routes, "get_db", get_test_db),
            patch.object(qanda_routes, "UPLOADS_DIR", str(self.uploads)),
            patch.object(qanda_routes, "get_db", get_test_db),
        ]
        for active_patch in self.patches:
            active_patch.start()
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        for active_patch in reversed(self.patches):
            active_patch.stop()
        self.temp_context.cleanup()

    def test_only_registered_pdf_is_public(self):
        (self.uploads / "document.pdf").write_bytes(valid_pdf())
        (self.uploads / "slides.ppt").write_bytes(b"download-only")
        (self.uploads / "slides.pptx").write_bytes(valid_pptx())
        conn = sqlite3.connect(self.database)
        conn.executemany(
            "INSERT INTO courseware "
            "(title, date, pdf_path, pptx_path) VALUES (?, ?, ?, ?)",
            (
                ("PDF", "2026-07-28", "document.pdf", ""),
                ("PPT", "2026-07-28", "", "slides.ppt"),
                ("PPTX", "2026-07-28", "", "slides.pptx"),
            ),
        )
        conn.commit()
        conn.close()

        response = self.client.get("/data/uploads/document.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertTrue(
            response.headers["content-disposition"].startswith("inline")
        )
        self.assertEqual(
            response.headers["x-content-type-options"],
            "nosniff",
        )
        self.assertEqual(
            self.client.get("/data/uploads/slides.ppt").status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/data/uploads/slides.pptx").status_code,
            404,
        )

    def test_orphan_pdf_is_not_public(self):
        (self.uploads / "orphan.pdf").write_bytes(valid_pdf())
        self.assertEqual(
            self.client.get("/data/uploads/orphan.pdf").status_code,
            404,
        )

    def test_pdf_disappearing_after_public_check_returns_404(self):
        target = self.uploads / "disappearing.pdf"
        target.write_bytes(valid_pdf())
        conn = sqlite3.connect(self.database)
        conn.execute(
            "INSERT INTO courseware "
            "(title, date, pdf_path) VALUES (?, ?, ?)",
            ("disappearing", "2026-07-29", target.name),
        )
        conn.commit()
        conn.close()

        def remove_after_public_check(_row, *, uploads_dir):
            self.assertEqual(Path(uploads_dir), self.uploads)
            target.unlink()
            return target.name

        with patch.object(
            files_routes,
            "public_pdf_filename",
            side_effect=remove_after_public_check,
        ):
            response = self.client.get(
                f"/data/uploads/{target.name}"
            )
        self.assertEqual(response.status_code, 404)

    def test_internal_and_unsafe_paths_are_not_exposed(self):
        internal = Path(self.temp_context.name) / "site.db"
        internal.write_bytes(b"secret")
        for path in (
            "/data/site.db",
            "/data/uploads/missing.pdf",
            "/data/uploads/file.txt",
            "/data/uploads/..%2Fsite.db",
            "/data/uploads/%5C%5Cserver%5Cfile.pdf",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)


class CoursewareRouteIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_context = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_context.name)
        self.uploads = self.root / "uploads"
        self.temporary = self.root / "tmp"
        self.database = self.root / "test.db"
        self.uploads.mkdir()
        create_database(self.database)

        def get_test_db():
            conn = sqlite3.connect(self.database)
            conn.row_factory = sqlite3.Row
            return conn

        self.patches = [
            patch.object(courseware_routes, "UPLOADS_DIR", str(self.uploads)),
            patch.object(
                courseware_routes,
                "COURSEWARE_TEMP_DIR",
                str(self.temporary),
            ),
            patch.object(courseware_routes, "get_db", get_test_db),
            patch.object(files_routes, "UPLOADS_DIR", str(self.uploads)),
            patch.object(files_routes, "get_db", get_test_db),
            patch.object(qanda_routes, "UPLOADS_DIR", str(self.uploads)),
            patch.object(qanda_routes, "get_db", get_test_db),
        ]
        for active_patch in self.patches:
            active_patch.start()

        self.app = FastAPI()
        self.app.include_router(courseware_routes.router)
        self.app.include_router(files_routes.router)
        self.app.include_router(qanda_routes.router)
        self.app.dependency_overrides[require_admin_write] = lambda: AdminSession(
            role="admin",
            expires_at=time.time() + 300,
            csrf_token="test-csrf-token",
        )
        self.app.dependency_overrides[require_admin] = lambda: AdminSession(
            role="admin",
            expires_at=time.time() + 300,
            csrf_token="test-csrf-token",
        )
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        for active_patch in reversed(self.patches):
            active_patch.stop()
        self.temp_context.cleanup()

    def test_upload_list_download_and_delete_use_safe_filename(self):
        response = self.client.post(
            "/api/courseware/upload",
            data={"title": "../危险标题", "date": "2026-07-28"},
            files={"file": ("../../same.pdf", valid_pdf(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(self.uploads.iterdir()), [])

        response = self.client.post(
            "/api/courseware/upload",
            data={"title": "../危险标题", "date": "2026-07-28"},
            files={"file": ("same.pdf", valid_pdf(), "application/pdf")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        item_id = response.json()["id"]
        listing = self.client.get("/api/courseware/list").json()
        stored_name = listing[0]["pdf_path"]
        self.assertRegex(stored_name, r"^[0-9a-f]{32}\.pdf$")
        self.assertNotIn(str(self.root), str(listing))

        download = self.client.get(f"/data/uploads/{stored_name}")
        self.assertEqual(download.status_code, 200)
        deleted = self.client.delete(f"/api/courseware/{item_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse((self.uploads / stored_name).exists())

    def test_public_and_admin_lists_have_distinct_file_boundaries(self):
        (self.uploads / "public.pdf").write_bytes(valid_pdf())
        (self.uploads / "legacy.pptx").write_bytes(valid_pptx())
        conn = sqlite3.connect(self.database)
        conn.executemany(
            "INSERT INTO courseware "
            "(title, date, pdf_path, pptx_path, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                ("PDF", "2026-07-28", "public.pdf", "", "2026-07-28 10:00:00"),
                ("PPTX", "2026-07-28", "", "legacy.pptx", "2026-07-28 11:00:00"),
            ),
        )
        conn.commit()
        pptx_id = conn.execute(
            "SELECT id FROM courseware WHERE title = 'PPTX'"
        ).fetchone()[0]
        conn.close()

        public_list = self.client.get("/api/courseware/list").json()
        self.assertEqual([item["title"] for item in public_list], ["PDF"])
        self.assertNotIn("date", public_list[0])
        self.assertNotIn("pptx_path", public_list[0])
        self.assertEqual(
            self.client.get(f"/api/courseware/{pptx_id}").status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/api/qanda/stats").json()["total_courseware"],
            1,
        )

        admin_list = self.client.get("/api/courseware/admin/list").json()
        self.assertEqual(
            [item["title"] for item in admin_list],
            ["PPTX", "PDF"],
        )
        deleted = self.client.delete(f"/api/courseware/{pptx_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse((self.uploads / "legacy.pptx").exists())

    def test_tampered_and_empty_pdf_are_excluded_everywhere(self):
        files = {
            "valid.pdf": valid_pdf(),
            "tampered.pdf": b"ordinary text pretending to be a PDF",
            "empty.pdf": b"",
        }
        for filename, content in files.items():
            (self.uploads / filename).write_bytes(content)

        conn = sqlite3.connect(self.database)
        conn.executemany(
            "INSERT INTO courseware "
            "(title, date, tags, pdf_path) VALUES (?, ?, ?, ?)",
            (
                ("valid", "2026-07-28", "physics", "valid.pdf"),
                ("tampered", "2026-07-28", "physics", "tampered.pdf"),
                ("empty", "2026-07-28", "physics", "empty.pdf"),
            ),
        )
        conn.commit()
        ids = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT title, id FROM courseware"
            ).fetchall()
        }
        conn.close()

        for path in ("/api/courseware/list", "/api/courseware/list?tag=physics"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    [item["title"] for item in response.json()],
                    ["valid"],
                )

        stats = self.client.get("/api/qanda/stats")
        self.assertEqual(stats.status_code, 200)
        self.assertEqual(stats.json()["total_courseware"], 1)

        self.assertEqual(
            self.client.get(f"/api/courseware/{ids['valid']}").status_code,
            200,
        )
        self.assertEqual(
            self.client.get("/data/uploads/valid.pdf").status_code,
            200,
        )
        for title in ("tampered", "empty"):
            with self.subTest(title=title):
                self.assertEqual(
                    self.client.get(
                        f"/api/courseware/{ids[title]}"
                    ).status_code,
                    404,
                )
                self.assertEqual(
                    self.client.get(
                        f"/data/uploads/{title}.pdf"
                    ).status_code,
                    404,
                )

    def test_upload_without_date_uses_stable_created_order(self):
        for title in ("first", "second"):
            response = self.client.post(
                "/api/courseware/upload",
                data={"title": title},
                files={
                    "file": (
                        f"{title}.pdf",
                        valid_pdf(),
                        "application/pdf",
                    )
                },
            )
            self.assertEqual(response.status_code, 200, response.text)

        conn = sqlite3.connect(self.database)
        conn.execute(
            "UPDATE courseware SET created_at = '2026-07-28 12:00:00'"
        )
        conn.commit()
        dates = conn.execute(
            "SELECT date FROM courseware"
        ).fetchall()
        conn.close()
        self.assertTrue(all(date[0] for date in dates))

        listing = self.client.get("/api/courseware/list").json()
        self.assertEqual(
            [item["title"] for item in listing],
            ["second", "first"],
        )

    def test_unsafe_legacy_delete_returns_409_without_changes(self):
        outside = self.root / "outside.pdf"
        outside.write_bytes(valid_pdf())
        conn = sqlite3.connect(self.database)
        cursor = conn.execute(
            "INSERT INTO courseware "
            "(title, date, pdf_path, pptx_path) VALUES (?, ?, ?, ?)",
            ("unsafe", "2026-07-28", str(outside), ""),
        )
        conn.commit()
        item_id = cursor.lastrowid
        conn.close()

        response = self.client.delete(f"/api/courseware/{item_id}")
        self.assertEqual(response.status_code, 409)
        conn = sqlite3.connect(self.database)
        remaining = conn.execute(
            "SELECT COUNT(*) FROM courseware WHERE id = ?",
            (item_id,),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(remaining, 1)
        self.assertEqual(outside.read_bytes(), valid_pdf())

    def test_missing_file_record_can_be_deleted(self):
        conn = sqlite3.connect(self.database)
        cursor = conn.execute(
            "INSERT INTO courseware "
            "(title, date, pdf_path, pptx_path) VALUES (?, ?, ?, ?)",
            ("missing", "2026-07-28", "missing.pdf", ""),
        )
        conn.commit()
        item_id = cursor.lastrowid
        conn.close()
        self.assertEqual(
            self.client.delete(f"/api/courseware/{item_id}").status_code,
            200,
        )

    def test_unauthenticated_upload_creates_nothing(self):
        override = self.app.dependency_overrides.pop(require_admin_write)
        try:
            response = self.client.post(
                "/api/courseware/upload",
                data={"title": "unauthorized", "date": "2026-07-28"},
                files={
                    "file": ("unauthorized.pdf", valid_pdf(), "application/pdf")
                },
            )
        finally:
            self.app.dependency_overrides[require_admin_write] = override
        self.assertEqual(response.status_code, 401)
        self.assertEqual(list(self.uploads.iterdir()), [])
        conn = sqlite3.connect(self.database)
        count = conn.execute("SELECT COUNT(*) FROM courseware").fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)

    def test_database_commit_failure_removes_final_file(self):
        class FailingConnection:
            def __init__(self, connection):
                self.connection = connection

            def execute(self, *args, **kwargs):
                return self.connection.execute(*args, **kwargs)

            def commit(self):
                raise sqlite3.OperationalError("simulated")

            def rollback(self):
                self.connection.rollback()

            def close(self):
                self.connection.close()

        def get_failing_db():
            connection = sqlite3.connect(self.database)
            connection.row_factory = sqlite3.Row
            return FailingConnection(connection)

        with patch.object(
            courseware_routes,
            "get_db",
            get_failing_db,
        ):
            response = self.client.post(
                "/api/courseware/upload",
                data={"title": "failure", "date": "2026-07-28"},
                files={"file": ("failure.pdf", valid_pdf(), "application/pdf")},
            )
        self.assertEqual(response.status_code, 500)
        self.assertEqual(list(self.uploads.iterdir()), [])
        self.assertEqual(list(self.temporary.glob("*")), [])

    def test_windows_legacy_path_maps_to_current_upload_for_delete(self):
        legacy_file = self.uploads / "legacy.pdf"
        legacy_file.write_bytes(valid_pdf())
        conn = sqlite3.connect(self.database)
        cursor = conn.execute(
            "INSERT INTO courseware "
            "(title, date, pdf_path, pptx_path) VALUES (?, ?, ?, ?)",
            (
                "legacy",
                "2026-07-28",
                r"E:\old-project\data\uploads\legacy.pdf",
                "",
            ),
        )
        conn.commit()
        item_id = cursor.lastrowid
        conn.close()

        listing = self.client.get("/api/courseware/list").json()
        self.assertEqual(listing[0]["pdf_path"], "legacy.pdf")
        self.assertEqual(
            self.client.delete(f"/api/courseware/{item_id}").status_code,
            200,
        )
        self.assertFalse(legacy_file.exists())

    def test_delete_commit_failure_restores_quarantined_file(self):
        stored_file = self.uploads / "restore.pdf"
        stored_file.write_bytes(valid_pdf())
        conn = sqlite3.connect(self.database)
        cursor = conn.execute(
            "INSERT INTO courseware "
            "(title, date, pdf_path, pptx_path) VALUES (?, ?, ?, ?)",
            ("restore", "2026-07-28", "restore.pdf", ""),
        )
        conn.commit()
        item_id = cursor.lastrowid
        conn.close()

        class FailingConnection:
            def __init__(self, connection):
                self.connection = connection

            def execute(self, *args, **kwargs):
                return self.connection.execute(*args, **kwargs)

            def commit(self):
                raise sqlite3.OperationalError("simulated")

            def rollback(self):
                self.connection.rollback()

            def close(self):
                self.connection.close()

        def get_failing_db():
            connection = sqlite3.connect(self.database)
            connection.row_factory = sqlite3.Row
            return FailingConnection(connection)

        with patch.object(
            courseware_routes,
            "get_db",
            get_failing_db,
        ):
            response = self.client.delete(f"/api/courseware/{item_id}")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(stored_file.read_bytes(), valid_pdf())
        self.assertEqual(list(self.temporary.glob("*")), [])
        conn = sqlite3.connect(self.database)
        remaining = conn.execute(
            "SELECT COUNT(*) FROM courseware WHERE id = ?",
            (item_id,),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(remaining, 1)

    def test_commit_and_restore_failure_preserves_recovery_hold(self):
        stored_file = self.uploads / "manual-recovery.pdf"
        stored_file.write_bytes(valid_pdf())
        conn = sqlite3.connect(self.database)
        cursor = conn.execute(
            "INSERT INTO courseware "
            "(title, date, pdf_path, pptx_path) VALUES (?, ?, ?, ?)",
            (
                "manual recovery",
                "2026-07-28",
                "manual-recovery.pdf",
                "",
            ),
        )
        conn.commit()
        item_id = cursor.lastrowid
        conn.close()

        class FailingConnection:
            def __init__(self, connection):
                self.connection = connection

            def execute(self, *args, **kwargs):
                return self.connection.execute(*args, **kwargs)

            def commit(self):
                raise sqlite3.OperationalError("simulated")

            def rollback(self):
                self.connection.rollback()

            def close(self):
                self.connection.close()

        def get_failing_db():
            connection = sqlite3.connect(self.database)
            connection.row_factory = sqlite3.Row
            return FailingConnection(connection)

        real_replace = os.replace

        def replace_with_restore_failure(source, destination):
            if (
                Path(source).name.startswith(".recover-")
                and Path(destination) == stored_file
            ):
                raise OSError("simulated restore failure")
            return real_replace(source, destination)

        with (
            patch.object(
                courseware_routes,
                "get_db",
                get_failing_db,
            ),
            patch.object(
                courseware_routes.os,
                "replace",
                side_effect=replace_with_restore_failure,
            ),
        ):
            response = self.client.delete(f"/api/courseware/{item_id}")

        self.assertEqual(response.status_code, 500)
        self.assertFalse(stored_file.exists())
        recovery_holds = list(self.temporary.glob(".recover-*.hold"))
        self.assertEqual(len(recovery_holds), 1)
        self.assertEqual(recovery_holds[0].read_bytes(), valid_pdf())
        conn = sqlite3.connect(self.database)
        remaining = conn.execute(
            "SELECT COUNT(*) FROM courseware WHERE id = ?",
            (item_id,),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(remaining, 1)

        old_time = time.time() - 90000
        os.utime(recovery_holds[0], (old_time, old_time))
        cleanup_stale_temporary_files(
            temp_dir=self.temporary,
            now=time.time(),
        )
        self.assertTrue(recovery_holds[0].exists())

    def test_committed_delete_cleanup_failure_is_cleaned_later(self):
        stored_file = self.uploads / "cleanup-later.pdf"
        stored_file.write_bytes(valid_pdf())
        conn = sqlite3.connect(self.database)
        cursor = conn.execute(
            "INSERT INTO courseware "
            "(title, date, pdf_path, pptx_path) VALUES (?, ?, ?, ?)",
            (
                "cleanup later",
                "2026-07-28",
                "cleanup-later.pdf",
                "",
            ),
        )
        conn.commit()
        item_id = cursor.lastrowid
        conn.close()

        real_unlink = Path.unlink

        def fail_immediate_delete(path, *args, **kwargs):
            if path.name.startswith(".delete-"):
                raise OSError("simulated cleanup failure")
            return real_unlink(path, *args, **kwargs)

        with patch.object(
            Path,
            "unlink",
            autospec=True,
            side_effect=fail_immediate_delete,
        ):
            response = self.client.delete(f"/api/courseware/{item_id}")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(stored_file.exists())
        cleanable_files = list(self.temporary.glob(".delete-*.delete"))
        self.assertEqual(len(cleanable_files), 1)
        conn = sqlite3.connect(self.database)
        remaining = conn.execute(
            "SELECT COUNT(*) FROM courseware WHERE id = ?",
            (item_id,),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(remaining, 0)

        old_time = time.time() - 90000
        os.utime(cleanable_files[0], (old_time, old_time))
        cleanup_stale_temporary_files(
            temp_dir=self.temporary,
            now=time.time(),
        )
        self.assertFalse(cleanable_files[0].exists())


if __name__ == "__main__":
    unittest.main()
