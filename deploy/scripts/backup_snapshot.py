#!/usr/bin/env python3
"""创建一致的 SQLite 快照，并只复制数据库关联的有效公开 PDF。"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--uploads-dir", required=True, type=Path)
    parser.add_argument("--backend-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database = args.database.resolve(strict=True)
    uploads_dir = args.uploads_dir.resolve(strict=True)
    backend_dir = args.backend_dir.resolve(strict=True)
    output_dir = args.output_dir.resolve()

    if output_dir.exists():
        raise RuntimeError("输出目录必须不存在")
    output_dir.mkdir(mode=0o700, parents=True)
    snapshot_path = output_dir / "site.db"
    snapshot_uploads = output_dir / "uploads"
    snapshot_uploads.mkdir(mode=0o700)

    sys.path.insert(0, str(backend_dir))
    from file_storage import public_pdf_filename  # noqa: PLC0415

    source = sqlite3.connect(database)
    destination = sqlite3.connect(snapshot_path)
    try:
        checkpoint = source.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if checkpoint is None or checkpoint[0] != 0:
            raise RuntimeError("SQLite WAL checkpoint 未完成")
        source.backup(destination)
    finally:
        destination.close()
        source.close()

    snapshot = sqlite3.connect(snapshot_path)
    snapshot.row_factory = sqlite3.Row
    try:
        integrity = snapshot.execute("PRAGMA integrity_check").fetchall()
        if [row[0] for row in integrity] != ["ok"]:
            raise RuntimeError("SQLite 快照完整性检查失败")
        rows = snapshot.execute(
            "SELECT * FROM courseware WHERE pdf_path <> '' ORDER BY id"
        ).fetchall()
    finally:
        snapshot.close()

    pdf_entries: list[dict[str, object]] = []
    copied: set[str] = set()
    for row in rows:
        filename = public_pdf_filename(row, uploads_dir=uploads_dir)
        if filename is None or filename in copied:
            continue
        source_path = uploads_dir / filename
        destination_path = snapshot_uploads / filename
        shutil.copy2(source_path, destination_path, follow_symlinks=False)
        if destination_path.is_symlink():
            raise RuntimeError("快照中不得包含符号链接")
        pdf_entries.append(
            {
                "filename": filename,
                "bytes": destination_path.stat().st_size,
                "sha256": file_sha256(destination_path),
            }
        )
        copied.add(filename)

    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": {
            "filename": "site.db",
            "bytes": snapshot_path.stat().st_size,
            "sha256": file_sha256(snapshot_path),
        },
        "pdf_count": len(pdf_entries),
        "pdfs": pdf_entries,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
