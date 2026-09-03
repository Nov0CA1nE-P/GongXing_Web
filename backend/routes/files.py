from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from config import UPLOADS_DIR
from database import get_db
from file_storage import (
    DOWNLOAD_MIME_TYPES,
    UnsafeStoredPath,
    courseware_file_reference,
    is_safe_basename,
    public_pdf_filename,
    public_courseware_reference,
    resolve_upload_path,
)

router = APIRouter(tags=["courseware-files"])


@router.get("/data/uploads/{filename}")
def download_courseware_file(filename: str):
    """只公开数据库关联、内容有效且位于上传目录内的课件文件。"""
    if not is_safe_basename(filename):
        raise HTTPException(status_code=404, detail="文件不存在")

    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM courseware").fetchall()
    finally:
        conn.close()

    matching_row = None
    matching_reference = None
    for row in rows:
        if Path(filename).suffix.lower() == ".pdf":
            pdf_name = public_pdf_filename(row, uploads_dir=UPLOADS_DIR)
            reference = (pdf_name, ".pdf") if pdf_name else None
            if reference is None:
                reference = public_courseware_reference(
                    row, uploads_dir=UPLOADS_DIR
                )
        else:
            reference = public_courseware_reference(row, uploads_dir=UPLOADS_DIR)
        if reference is not None and reference[0] == filename:
            matching_row = row
            matching_reference = reference
            break
    if matching_row is None:
        raise HTTPException(status_code=404, detail="文件不存在") from None

    try:
        reference = matching_reference or courseware_file_reference(matching_row)
        if reference is None or reference[0] != filename:
            raise UnsafeStoredPath("unmatched")
        file_path = resolve_upload_path(
            filename,
            uploads_dir=UPLOADS_DIR,
            require_exists=True,
        )
    except (UnsafeStoredPath, FileNotFoundError, OSError, RuntimeError):
        raise HTTPException(status_code=404, detail="文件不存在") from None

    extension = Path(filename).suffix.lower()
    disposition = "inline" if extension in {".pdf", ".jpg"} else "attachment"
    encoded_name = quote(filename, safe="")
    return FileResponse(
        file_path,
        media_type=DOWNLOAD_MIME_TYPES[extension],
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{encoded_name}",
            "X-Content-Type-Options": "nosniff",
        },
    )
