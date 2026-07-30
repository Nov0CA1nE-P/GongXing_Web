#!/usr/bin/env python3
"""验证恢复后的数据库、manifest 和有效 PDF。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-dir", required=True, type=Path)
    args = parser.parse_args()
    root = args.snapshot_dir.resolve(strict=True)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))

    database = root / manifest["database"]["filename"]
    if file_sha256(database) != manifest["database"]["sha256"]:
        raise RuntimeError("数据库校验和不匹配")

    connection = sqlite3.connect(database)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchall()
    finally:
        connection.close()
    if [row[0] for row in integrity] != ["ok"]:
        raise RuntimeError("数据库完整性检查失败")

    pdfs = manifest["pdfs"]
    if manifest["pdf_count"] != len(pdfs):
        raise RuntimeError("PDF 数量与 manifest 不一致")
    for entry in pdfs:
        filename = entry["filename"]
        if Path(filename).name != filename or not filename.endswith(".pdf"):
            raise RuntimeError("manifest 包含不安全文件名")
        path = root / "uploads" / filename
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("PDF 缺失或是符号链接")
        if path.stat().st_size != entry["bytes"]:
            raise RuntimeError("PDF 大小不匹配")
        if file_sha256(path) != entry["sha256"]:
            raise RuntimeError("PDF 校验和不匹配")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
