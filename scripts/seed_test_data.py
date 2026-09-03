"""生成可识别、可清理的本地仿真内容；严禁用于 production 数据库。"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import os
import random
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))


MESSAGE_TEXTS = (
    "第一次参加夏令营，想提前了解机械方向平时会做哪些项目。",
    "如果喜欢拆装东西但数学一般，适合从哪些专业开始了解？",
    "杭州的校区交通方便吗？活动期间需要准备什么？",
    "我对机器人和编程都感兴趣，不知道该先学哪一块。",
    "想听听学长学姐大学里最有意思的一门课。",
    "材料专业是不是只做实验，也会接触设计和计算机吗？",
    "第一次做科普分享有点紧张，有没有简单的准备方法？",
    "谢谢实践团的活动安排，期待现场交流！",
)
REPLY_TEXTS = (
    "可以从一个小项目入手，先观察自己更享受搭建、调试还是解释原理。",
    "不用先给自己贴标签，夏令营里多体验几种活动再比较会更准确。",
    "具体安排会在活动通知里说明，带上笔记本和轻便衣物即可。",
    "不用紧张，先把想讲的一件小事说明白，现场会有同学一起练习。",
    "欢迎到现场继续提问，我们会结合体验项目分享真实感受。",
    "机械、材料和计算机之间有很多交叉方向，动手体验最容易找到感觉。",
    "可以先记录问题和观察，再把它们整理成三分钟的小分享。",
    "谢谢你的期待，期待在活动现场见到你。",
)
QUESTION_TEXTS = (
    "计算机科学和软件工程在课程与就业方向上有什么主要区别？",
    "材料科学专业会学习哪些基础课程，和化学专业有什么联系？",
    "如果以后想做机器人，本科阶段应该重点准备哪些能力？",
    "机械工程学生平时会不会使用编程和数据分析工具？",
    "对新闻传播感兴趣但也喜欢技术，能选择哪些交叉方向？",
    "大学里如何判断一个专业是否真的适合自己？",
)


def _timestamp(rng: random.Random, start: datetime, end: datetime) -> str:
    seconds = int((end - start).total_seconds())
    return (start + timedelta(seconds=rng.randrange(seconds + 1))).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _call_ai(call: Callable[[str], Awaitable[str] | str], prompt: str) -> str:
    value = call(prompt)
    if inspect.isawaitable(value):
        value = asyncio.run(value)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("模拟内容生成失败")
    result = value.strip()
    if result.startswith(("API Key 未配置", "大模型服务暂时不可用", "响应解析失败")):
        raise RuntimeError("DeepSeek 内容生成失败，测试批次未写入")
    return result


def seed_database(
    database: Path,
    *,
    batch_id: str,
    seed: int = 20260803,
    ai_call: Callable[[str], Awaitable[str] | str],
) -> tuple[int, int]:
    """在一次数据库事务中写入留言、回复和待审核 AI 问答。"""
    if not batch_id or not batch_id.isascii() or not batch_id.replace("-", "").isalnum():
        raise ValueError("batch_id 只能使用 ASCII 字母、数字和连字符")
    database = database.resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    rng = random.Random(seed)
    start = datetime(2026, 8, 2, tzinfo=timezone.utc)
    end = datetime(2026, 9, 1, 23, 59, 59, tzinfo=timezone.utc)
    end_naive = end.replace(tzinfo=None)
    student = f"示例学生（测试）·{batch_id}"
    team = f"实践团答疑（测试）·{batch_id}"
    try:
        existing = conn.execute(
            "SELECT 1 FROM messages WHERE author IN (?, ?) LIMIT 1",
            (student, team),
        ).fetchone()
        if existing is not None:
            raise RuntimeError("该测试批次已存在，请更换 batch_id 或先清理")
        existing = conn.execute(
            "SELECT 1 FROM questions WHERE author = ? LIMIT 1", (student,)
        ).fetchone()
        if existing is not None:
            raise RuntimeError("该测试批次已存在，请更换 batch_id 或先清理")

        ai_answers = [_call_ai(ai_call, text) for text in QUESTION_TEXTS]
        message_rows: list[tuple[str, str, int | None, str]] = []
        for index, text in enumerate(MESSAGE_TEXTS):
            created = _timestamp(rng, start, end - timedelta(days=1))
            message_rows.append((student, text, None, created))
            reply_time = datetime.strptime(created, "%Y-%m-%d %H:%M:%S") + timedelta(
                minutes=rng.randint(5, 180)
            )
            if reply_time > end_naive:
                reply_time = end_naive
            message_rows.append((team, REPLY_TEXTS[index], index, reply_time.strftime("%Y-%m-%d %H:%M:%S")))

        conn.execute("BEGIN")
        top_ids: list[int] = []
        for author, content, parent_index, created_at in message_rows:
            if parent_index is None:
                cursor = conn.execute(
                    "INSERT INTO messages (author, content, created_at) VALUES (?, ?, ?)",
                    (author, content, created_at),
                )
                top_ids.append(int(cursor.lastrowid))
            else:
                conn.execute(
                    "INSERT INTO messages (author, content, parent_id, created_at) VALUES (?, ?, ?, ?)",
                    (author, content, top_ids[parent_index], created_at),
                )

        question_times: list[str] = []
        for text, answer in zip(QUESTION_TEXTS, ai_answers):
            question_time = _timestamp(rng, start, end - timedelta(hours=2))
            answer_time = datetime.strptime(question_time, "%Y-%m-%d %H:%M:%S") + timedelta(
                minutes=rng.randint(2, 90)
            )
            if answer_time > end_naive:
                answer_time = end_naive
            question_times.append(question_time)
            cursor = conn.execute(
                "INSERT INTO questions (author, content, created_at) VALUES (?, ?, ?)",
                (student, text, question_time),
            )
            conn.execute(
                "INSERT INTO answers (question_id, content, is_ai_generated, status, created_at) VALUES (?, ?, 1, 'pending', ?)",
                (cursor.lastrowid, answer, answer_time.strftime("%Y-%m-%d %H:%M:%S")),
            )
        conn.commit()
        return len(MESSAGE_TEXTS) * 2, len(QUESTION_TEXTS)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def cleanup_batch(database: Path, batch_id: str) -> tuple[int, int]:
    database = database.resolve()
    student = f"示例学生（测试）·{batch_id}"
    team = f"实践团答疑（测试）·{batch_id}"
    conn = sqlite3.connect(database)
    try:
        conn.execute("BEGIN")
        questions = conn.execute(
            "SELECT id FROM questions WHERE author = ?", (student,)
        ).fetchall()
        question_ids = [row[0] for row in questions]
        for question_id in question_ids:
            conn.execute("DELETE FROM answers WHERE question_id = ?", (question_id,))
        conn.execute("DELETE FROM questions WHERE author = ?", (student,))
        messages = conn.execute(
            "SELECT id FROM messages WHERE author IN (?, ?)", (student, team)
        ).fetchall()
        conn.execute("DELETE FROM messages WHERE author IN (?, ?)", (student, team))
        conn.commit()
        return len(messages), len(question_ids)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成隔离的夏令营测试内容")
    parser.add_argument("--database", required=True, help="明确指定的测试 SQLite 数据库")
    parser.add_argument("--confirm-test-data", action="store_true")
    parser.add_argument("--batch-id", default="demo-20260903")
    parser.add_argument("--seed", type=int, default=20260803)
    parser.add_argument("--cleanup-batch", action="store_true")
    return parser.parse_args()


def main() -> int:
    if os.getenv("APP_ENV") not in {"test", "development"}:
        print("拒绝执行：仿真数据工具只允许 APP_ENV=test 或 development。", file=sys.stderr)
        return 2
    args = parse_args()
    if not args.confirm_test_data:
        print("拒绝执行：必须显式传入 --confirm-test-data。", file=sys.stderr)
        return 2
    database = Path(args.database)
    if not database.is_absolute():
        print("拒绝执行：--database 必须是绝对路径。", file=sys.stderr)
        return 2
    try:
        import database as database_module

        database_module.DATABASE_PATH = str(database.resolve())
        database_module.init_db()
        if args.cleanup_batch:
            messages, questions = cleanup_batch(database, args.batch_id)
            print(f"已清理测试批次：留言 {messages} 条，问题 {questions} 条")
            return 0
        # 只有通过环境和参数门禁后才导入应用配置及 DeepSeek 客户端。
        from config import DEEPSEEK_API_KEY

        if not DEEPSEEK_API_KEY:
            raise RuntimeError("未配置 DeepSeek API Key，未生成测试批次")
        from services.ai_service import ask_deepseek

        messages, questions = seed_database(
            database,
            batch_id=args.batch_id,
            seed=args.seed,
            ai_call=ask_deepseek,
        )
        print(f"已生成测试批次：留言及回复 {messages} 条，待审核问题 {questions} 条")
        return 0
    except (OSError, sqlite3.Error, RuntimeError, ValueError) as exc:
        print(f"仿真数据操作失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
