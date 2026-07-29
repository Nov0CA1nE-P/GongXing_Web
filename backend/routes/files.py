from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from config import UPLOADS_DIR
from database import get_db
from file_storage import (
    DOWNLOAD_MIME_TYPES,
    is_safe_basename,
    public_pdf_filename,
    resolve_upload_path,
)

router = APIRouter(tags=["courseware-files"])


@router.get("/data/uploads/{filename}")
def download_courseware_file(filename: str):
    """只公开数据库关联且当前可安全访问的PDF。"""
    if (
        not is_safe_basename(filename)
        or Path(filename).suffix.lower() != ".pdf"
    ):
        raise HTTPException(status_code=404, detail="文件不存在")

    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM courseware WHERE pdf_path <> ''"
        ).fetchall()
    finally:
        conn.close()
    matching_row = next(
        (
            row for row in rows
            if public_pdf_filename(row, uploads_dir=UPLOADS_DIR) == filename
        ),
        None,
    )
    if matching_row is None:
        raise HTTPException(status_code=404, detail="文件不存在") from None

    file_path = resolve_upload_path(
        matching_row["pdf_path"],
        uploads_dir=UPLOADS_DIR,
        require_exists=True,
    )
    encoded_name = quote(filename, safe="")
    return FileResponse(
        file_path,
        media_type=DOWNLOAD_MIME_TYPES[".pdf"],
        headers={
            "Content-Disposition": (
                f"inline; filename*=UTF-8''{encoded_name}"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )
