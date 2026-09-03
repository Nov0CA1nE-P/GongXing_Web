"""初始化可公开的团队整理问答内容（只允许隔离的 test/development 数据库）。

本工具不会伪装真实学生，也不会生成历史发布时间：所有记录使用执行时的
UTC 时间。正式生产库的初始化需要另行审批，本脚本在 production 环境硬性拒绝。
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))


# 明确标注为团队整理，避免把内容伪装成真实学生发言。
CURATED_QA: tuple[tuple[str, str], ...] = (
    (
        "夏令营主要会安排哪些活动，第一次参加需要准备什么？",
        "活动通常会把专业介绍、动手体验和交流分享结合起来。提前准备好笔记本、水杯和记录问题的清单即可，最重要的是带着好奇心来体验。",
    ),
    (
        "喜欢拆装和动手实践，可以重点了解哪些专业？",
        "机械、材料、自动化等方向都重视实践，但侧重点不同。可以比较课程和项目，再通过一次小制作感受自己更喜欢设计、加工还是调试。",
    ),
    (
        "对编程感兴趣但没有基础，应该从哪里开始？",
        "先用 Python 做几个很小的项目，例如计算器、文字小游戏或数据可视化。把重点放在理解变量、条件、循环和调试过程，不必一开始追求复杂框架。",
    ),
    (
        "材料科学和化学专业有什么区别？",
        "化学更关注物质组成、反应和规律，材料科学还会追问怎样把这些规律变成更结实、更轻或更耐用的材料。两者有交叉，最终可按自己更喜欢基础研究还是工程应用来比较。",
    ),
    (
        "选择大学专业时只看就业率可以吗？",
        "就业情况值得参考，但不能替代对课程内容、学习方式和个人兴趣的了解。把就业信息、专业培养方案和自己的长期投入意愿放在一起看，判断会更稳妥。",
    ),
    (
        "高中阶段怎样判断自己是否适合一个专业？",
        "可以先看该专业的核心课程，再找一个入门项目亲自做一遍。记录自己在遇到困难时是否愿意继续改进，比只凭专业名称想象更可靠。",
    ),
    (
        "参加科普体验活动能收获什么？",
        "一次活动不一定让你立刻确定志愿，但能把抽象的专业变成可观察、可操作的体验。你可以带走对课程、学习方法和校园生活的具体问题，再继续查证。",
    ),
    (
        "现场有没听懂的问题，活动结束后还可以继续提问吗？",
        "当然可以。先把没听懂的关键词和自己的困惑写下来，活动后在问答区继续提问；实践团会尽量用清楚、可验证的方式补充说明。",
    ),
)


PROFESSIONAL_QUESTIONS: tuple[str, ...] = (
    "计算机科学、软件工程和人工智能本科方向在课程结构与能力培养上如何区分？",
    "材料科学与工程本科通常怎样连接物理、化学和工程应用，适合怎样的学习兴趣？",
    "如果希望在大学阶段进入机器人方向，高中到本科可以分阶段准备哪些数学、编程和实践能力？",
    "机械工程学习中会怎样使用编程、数据分析和数字化制造工具，学生应如何建立交叉能力？",
    "对技术产品和内容传播都感兴趣，大学里有哪些跨学科探索路径，如何避免两边都学得不扎实？",
    "判断一个专业是否适合自己时，如何结合课程体验、实践反馈和职业信息做出可复盘的决定？",
)

CURATED_AUTHOR = "学生常见问题（团队整理）"
PROFESSIONAL_AUTHOR = "专业问题（团队整理）"
TEAM_AUTHOR = "躬行启杭实践团"


def _now_text() -> str:
    """返回实际执行时的 UTC 时间，不生成随机或历史时间。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _call_ai(call: Callable[[str], Awaitable[str] | str], prompt: str) -> str:
    value = call(prompt)
    if inspect.isawaitable(value):
        value = asyncio.run(value)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("DeepSeek 内容生成失败，未写入公开内容")
    result = value.strip()
    if result.startswith(("API Key 未配置", "大模型服务暂时不可用", "响应解析失败")):
        raise RuntimeError("DeepSeek 内容生成失败，未写入公开内容")
    return result


def _ai_prompt(question: str) -> str:
    return (
        "请为躬行启杭交流平台的高中生写一份专业、准确、易懂的中文回答。"
        "围绕课程内容、学习方式、实践建议和可能的发展方向展开，避免编造学校或个人经历，"
        "使用 Markdown，控制在 500-900 字，并明确说明专业选择需要结合个人实践。\n\n"
        f"问题：{question}"
    )


def _existing_content(conn: sqlite3.Connection, contents: tuple[str, ...]) -> bool:
    placeholders = ",".join("?" for _ in contents)
    row = conn.execute(
        f"SELECT 1 FROM questions WHERE content IN ({placeholders}) LIMIT 1",
        contents,
    ).fetchone()
    return row is not None


def seed_database(
    database: Path,
    *,
    ai_call: Callable[[str], Awaitable[str] | str],
) -> tuple[int, int]:
    """原子写入 8 条已发布团队问答和 6 条待审核 AI 问答。

    调用方应先通过 ``database.init_db()`` 初始化项目数据库。重复执行会因问题
    内容已存在而拒绝，避免产生无法识别的重复批次。
    """
    database = database.resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    all_questions = tuple(text for text, _ in CURATED_QA) + PROFESSIONAL_QUESTIONS

    conn = sqlite3.connect(database)
    try:
        if _existing_content(conn, all_questions):
            raise RuntimeError("公开内容已存在，未重复写入")
    finally:
        conn.close()

    # 先完成所有外部调用，再开始数据库事务；任意失败都不会留下半批记录。
    generated_answers: list[str] = []
    for question in PROFESSIONAL_QUESTIONS:
        generated_answers.append(_call_ai(ai_call, _ai_prompt(question)))

    conn = sqlite3.connect(database)
    try:
        conn.execute("BEGIN")
        # 事务开始后再次检查，避免并发执行造成重复内容。
        if _existing_content(conn, all_questions):
            raise RuntimeError("公开内容已存在，未重复写入")

        for question, answer in CURATED_QA:
            question_time = _now_text()
            cursor = conn.execute(
                "INSERT INTO questions (author, content, created_at) VALUES (?, ?, ?)",
                (CURATED_AUTHOR, question, question_time),
            )
            conn.execute(
                """INSERT INTO answers
                   (question_id, content, is_ai_generated, status, reviewed_by, created_at)
                   VALUES (?, ?, 0, 'published', ?, ?)""",
                (cursor.lastrowid, answer, TEAM_AUTHOR, _now_text()),
            )

        for question, answer in zip(PROFESSIONAL_QUESTIONS, generated_answers):
            question_time = _now_text()
            cursor = conn.execute(
                "INSERT INTO questions (author, content, created_at) VALUES (?, ?, ?)",
                (PROFESSIONAL_AUTHOR, question, question_time),
            )
            conn.execute(
                """INSERT INTO answers
                   (question_id, content, is_ai_generated, status, created_at)
                   VALUES (?, ?, 1, 'pending', ?)""",
                (cursor.lastrowid, answer, _now_text()),
            )
        conn.commit()
        return len(CURATED_QA), len(PROFESSIONAL_QUESTIONS)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="初始化隔离的公开团队问答内容")
    parser.add_argument("--database", required=True, help="明确指定的隔离 SQLite 数据库")
    parser.add_argument("--confirm-public-content", action="store_true")
    return parser.parse_args()


def main() -> int:
    # 环境门禁必须早于后端配置、数据库打开和 DeepSeek 客户端导入。
    if os.getenv("APP_ENV") not in {"test", "development"}:
        print(
            "拒绝执行：公开内容初始化只允许 APP_ENV=test 或 development。",
            file=sys.stderr,
        )
        return 2

    args = parse_args()
    if not args.confirm_public_content:
        print("拒绝执行：必须显式传入 --confirm-public-content。", file=sys.stderr)
        return 2
    database = Path(args.database)
    if not database.is_absolute():
        print("拒绝执行：--database 必须是绝对路径。", file=sys.stderr)
        return 2

    try:
        import database as database_module

        database_module.DATABASE_PATH = str(database.resolve())
        database_module.init_db()

        from config import DEEPSEEK_API_KEY

        if not DEEPSEEK_API_KEY:
            raise RuntimeError("未配置 DeepSeek API Key，未写入公开内容")
        from services.ai_service import ask_deepseek

        curated_count, professional_count = seed_database(
            database,
            ai_call=ask_deepseek,
        )
        print(
            f"已初始化公开内容：团队整理 {curated_count} 条，待审核专业问答 {professional_count} 条"
        )
        return 0
    except (OSError, sqlite3.Error, RuntimeError, ValueError) as exc:
        print(f"公开内容初始化失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
