from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from config import UPLOADS_DIR
from file_storage import (
    DOWNLOAD_MIME_TYPES,
    UnsafeStoredPath,
    is_safe_basename,
    resolve_upload_path,
)

router = APIRouter(tags=["courseware-files"])


@router.get("/data/uploads/{filename}")
def download_courseware_file(filename: str):
    """仅响应上传目录内经过严格校验的课件文件。"""
    if not is_safe_basename(filename):
        raise HTTPException(status_code=404, detail="文件不存在")
    try:
        file_path = resolve_upload_path(
            filename,
            uploads_dir=UPLOADS_DIR,
            require_exists=True,
        )
    except (UnsafeStoredPath, FileNotFoundError):
        raise HTTPException(status_code=404, detail="文件不存在") from None

    extension = Path(filename).suffix.lower()
    disposition = "inline" if extension == ".pdf" else "attachment"
    encoded_name = quote(filename, safe="")
    return FileResponse(
        file_path,
        media_type=DOWNLOAD_MIME_TYPES[extension],
        headers={
            "Content-Disposition": (
                f"{disposition}; filename*=UTF-8''{encoded_name}"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )
