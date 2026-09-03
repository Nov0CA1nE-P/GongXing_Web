import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

os.environ["APP_ENV"] = "test"
os.environ["ADMIN_PASSWORD"] = "a-strong-test-password"
os.environ["ADMIN_SESSION_TTL_SECONDS"] = "7200"
os.environ["TRUSTED_ORIGINS"] = "https://test.example"
os.environ["TRUSTED_PROXY_IPS"] = ""
os.environ["PYTHON_DOTENV_DISABLED"] = "1"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

import database
from seed_public_content import (
    CURATED_AUTHOR,
    CURATED_QA,
    PROFESSIONAL_AUTHOR,
    PROFESSIONAL_QUESTIONS,
    TEAM_AUTHOR,
    seed_database,
)


class PublicContentSeedTests(unittest.TestCase):
    def setUp(self):
        self.temp_context = tempfile.TemporaryDirectory()
        self.database = Path(self.temp_context.name) / "isolated" / "site.db"
        with patch.object(database, "DATABASE_PATH", str(self.database)):
            database.init_db()

    def tearDown(self):
        self.temp_context.cleanup()

    def _rows(self):
        conn = sqlite3.connect(self.database)
        conn.row_factory = sqlite3.Row
        try:
            return (
                conn.execute(
                    "SELECT author, content, created_at FROM questions ORDER BY id"
                ).fetchall(),
                conn.execute(
                    """SELECT a.content, a.is_ai_generated, a.status,
                              a.reviewed_by, a.created_at, q.author AS question_author
                       FROM answers a JOIN questions q ON q.id = a.question_id
                       ORDER BY a.id"""
                ).fetchall(),
            )
        finally:
            conn.close()

    def test_writes_team_content_and_pending_ai_answers_with_current_timestamps(self):
        calls: list[str] = []
        before = datetime.now(timezone.utc)

        def fake_ai(prompt: str) -> str:
            calls.append(prompt)
            return f"## 团队审核稿\n\n这是针对问题的测试回答 {len(calls)}。"

        counts = seed_database(self.database, ai_call=fake_ai)
        after = datetime.now(timezone.utc)
        self.assertEqual(counts, (8, 6))
        self.assertEqual(len(calls), 6)
        self.assertTrue(all("问题：" in prompt for prompt in calls))

        questions, answers = self._rows()
        self.assertEqual(len(questions), 14)
        self.assertEqual(len(answers), 14)
        self.assertEqual([row["author"] for row in questions[:8]], [CURATED_AUTHOR] * 8)
        self.assertEqual(
            [row["author"] for row in questions[8:]], [PROFESSIONAL_AUTHOR] * 6
        )
        for row in questions:
            timestamp = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
            self.assertGreaterEqual(timestamp, before.replace(microsecond=0))
            self.assertLessEqual(timestamp, after)
        for row in answers:
            timestamp = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
            self.assertGreaterEqual(timestamp, before.replace(microsecond=0))
            self.assertLessEqual(timestamp, after)

        self.assertEqual([row["status"] for row in answers[:8]], ["published"] * 8)
        self.assertEqual([row["reviewed_by"] for row in answers[:8]], [TEAM_AUTHOR] * 8)
        self.assertEqual([row["is_ai_generated"] for row in answers[8:]], [1] * 6)
        self.assertEqual([row["status"] for row in answers[8:]], ["pending"] * 6)
        self.assertTrue(all(row["reviewed_by"] is None for row in answers[8:]))

    def test_ai_failure_rolls_back_entire_batch(self):
        calls = 0

        def failing_ai(_prompt: str) -> str:
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError("模拟 DeepSeek 失败")
            return "不会写入"

        with self.assertRaises(RuntimeError):
            seed_database(self.database, ai_call=failing_ai)
        questions, answers = self._rows()
        self.assertEqual(questions, [])
        self.assertEqual(answers, [])

    def test_duplicate_content_is_rejected_before_second_ai_call(self):
        calls = 0

        def fake_ai(_prompt: str) -> str:
            nonlocal calls
            calls += 1
            return "测试回答"

        seed_database(self.database, ai_call=fake_ai)
        with self.assertRaisesRegex(RuntimeError, "已存在"):
            seed_database(self.database, ai_call=fake_ai)
        self.assertEqual(calls, 6)

    def test_production_guard_rejects_before_database_creation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "should-not-exist" / "site.db"
            env = os.environ.copy()
            env.update({"APP_ENV": "production", "PYTHONPATH": str(BACKEND_DIR)})
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "seed_public_content.py"),
                    "--database",
                    str(target),
                    "--confirm-public-content",
                ],
                cwd=PROJECT_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertFalse(target.exists())
            self.assertIn("只允许", result.stderr)


if __name__ == "__main__":
    unittest.main()
