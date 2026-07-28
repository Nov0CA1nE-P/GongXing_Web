"""只读审计课件路径；不会修改数据库，也不会输出原始路径。"""

import argparse
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["APP_ENV"] = "test"
os.environ["ADMIN_PASSWORD"] = "audit-tool-not-used-for-login"

from file_storage import (  # noqa: E402
    UnsafeStoredPath,
    classify_stored_path,
    resolve_upload_path,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="只读审计课件文件路径")
    parser.add_argument("--database", required=True, help="要审计的 SQLite 数据库")
    parser.add_argument("--uploads-dir", required=True, help="当前上传目录")
    return parser.parse_args()


def audit(database: Path, uploads_dir: Path) -> Counter:
    counts: Counter = Counter()
    database_uri = f"{database.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(database_uri, uri=True)
    try:
        rows = conn.execute(
            "SELECT pdf_path, pptx_path FROM courseware"
        ).fetchall()
        for row in rows:
            for stored_value in row:
                if not stored_value:
                    continue
                try:
                    kind, _ = classify_stored_path(stored_value)
                    counts[kind] += 1
                    try:
                        resolve_upload_path(
                            stored_value,
                            uploads_dir=uploads_dir,
                            require_exists=True,
                        )
                    except FileNotFoundError:
                        counts["missing"] += 1
                except UnsafeStoredPath:
                    counts["unsafe"] += 1
    finally:
        conn.close()
    return counts


def main() -> int:
    args = parse_args()
    try:
        counts = audit(Path(args.database), Path(args.uploads_dir))
    except (OSError, sqlite3.Error):
        print("审计失败：无法以只读方式检查指定数据库。", file=sys.stderr)
        return 1

    labels = (
        ("new", "新格式安全文件名"),
        ("legacy_basename", "旧版安全文件名"),
        ("windows_legacy", "Windows 历史路径"),
        ("posix_legacy", "POSIX 历史路径"),
        ("missing", "映射后文件缺失"),
        ("unsafe", "不可靠或不支持的路径"),
    )
    for key, label in labels:
        print(f"{label}: {counts[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
