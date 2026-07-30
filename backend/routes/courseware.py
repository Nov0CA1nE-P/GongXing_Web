import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)

from auth import AdminSession, require_admin, require_admin_write
from config import (
    COURSEWARE_MAX_UPLOAD_BYTES,
    COURSEWARE_TEMP_DIR,
    UPLOADS_DIR,
)
from database import get_db
from file_storage import (
    MULTIPART_OVERHEAD_BYTES,
    UnsafeStoredPath,
    resolve_upload_path,
    serialize_courseware_row,
    serialize_public_courseware_row,
    store_validated_upload,
)

router = APIRouter(prefix="/api/courseware", tags=["courseware"])
LOGGER = logging.getLogger(__name__)


@router.get("/list")
def list_courseware(tag: str = ""):
    """获取可公开PDF列表。可选按 tag 筛选。"""
    conn = get_db()
    try:
        if tag:
            rows = conn.execute(
                "SELECT * FROM courseware WHERE tags LIKE ? "
                "ORDER BY created_at DESC, id DESC",
                (f"%{tag}%",),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM courseware ORDER BY created_at DESC, id DESC"
            ).fetchall()
        result = [
            serialize_public_courseware_row(row, uploads_dir=UPLOADS_DIR)
            for row in rows
        ]
        return [item for item in result if item is not None]
    finally:
        conn.close()


@router.get("/admin/list")
def admin_list_courseware(
    _admin: AdminSession = Depends(require_admin),
):
    """管理员查看全部历史课件，包括PPT/PPTX兼容记录。"""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM courseware ORDER BY created_at DESC, id DESC"
        ).fetchall()
        return [serialize_courseware_row(row) for row in rows]
    finally:
        conn.close()


@router.get("/{courseware_id}")
def get_courseware(courseware_id: int):
    """获取单个可公开PDF详情。"""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM courseware WHERE id = ?",
            (courseware_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="课件不存在")
    result = serialize_public_courseware_row(row, uploads_dir=UPLOADS_DIR)
    if result is None:
        raise HTTPException(status_code=404, detail="课件不存在")
    return result


@router.post("/upload")
async def upload_courseware(
    request: Request,
    title: str = Form(...),
    date: str = Form(""),
    description: str = Form(""),
    tags: str = Form(""),
    file: UploadFile = File(...),
    _admin: AdminSession = Depends(require_admin_write),
):
    """上传并验证新课件（管理员功能）。"""
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = 0
        if (
            declared_size > 0
            and declared_size
            > COURSEWARE_MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD_BYTES
        ):
            await file.close()
            raise HTTPException(
                status_code=413,
                detail="上传请求超过允许的大小",
            )

    final_path: Path | None = None
    conn = None
    committed = False
    try:
        final_name, final_path = await store_validated_upload(
            file,
            uploads_dir=UPLOADS_DIR,
            temp_dir=COURSEWARE_TEMP_DIR,
            max_bytes=COURSEWARE_MAX_UPLOAD_BYTES,
        )
        pdf_path = final_name if final_name.endswith(".pdf") else ""
        pptx_path = final_name if not pdf_path else ""

        internal_date = date.strip() or datetime.now(timezone.utc).strftime(
            "%Y-%m-%d"
        )
        conn = get_db()
        cursor = conn.execute(
            "INSERT INTO courseware "
            "(title, date, description, tags, pdf_path, pptx_path) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                title,
                internal_date,
                description,
                tags,
                pdf_path,
                pptx_path,
            ),
        )
        conn.commit()
        committed = True
        return {"id": cursor.lastrowid, "message": "上传成功"}
    except HTTPException:
        if conn is not None:
            conn.rollback()
        raise
    except Exception as exc:
        if conn is not None:
            conn.rollback()
        raise HTTPException(
            status_code=500,
            detail="课件保存失败",
        ) from exc
    finally:
        await file.close()
        if conn is not None:
            conn.close()
        if final_path is not None and not committed:
            try:
                if final_path.exists() and not final_path.is_symlink():
                    final_path.unlink()
            except OSError:
                LOGGER.warning("未能清理一个数据库未提交的课件文件")


@router.delete("/{courseware_id}")
def delete_courseware(
    courseware_id: int,
    _admin: AdminSession = Depends(require_admin_write),
):
    """只删除允许上传目录内的课件文件和对应数据库记录。"""
    conn = get_db()
    quarantined: list[tuple[Path, Path, Path]] = []
    committed = False
    try:
        row = conn.execute(
            "SELECT * FROM courseware WHERE id = ?",
            (courseware_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="课件不存在")

        paths: list[Path] = []
        for stored_value in {row["pdf_path"], row["pptx_path"]}:
            if not stored_value:
                continue
            try:
                candidate = resolve_upload_path(
                    stored_value,
                    uploads_dir=UPLOADS_DIR,
                    require_exists=False,
                )
            except UnsafeStoredPath:
                raise HTTPException(
                    status_code=409,
                    detail="课件文件路径异常，未执行删除",
                ) from None
            if candidate.exists():
                if candidate.is_symlink() or not candidate.is_file():
                    raise HTTPException(
                        status_code=409,
                        detail="课件文件路径异常，未执行删除",
                    )
                paths.append(candidate)

        temp_root = Path(COURSEWARE_TEMP_DIR)
        temp_root.mkdir(parents=True, exist_ok=True)
        if temp_root.is_symlink():
            raise HTTPException(status_code=500, detail="文件存储暂时不可用")

        for original in paths:
            quarantine_id = uuid.uuid4().hex
            recovery_hold = temp_root / (
                f".recover-{quarantine_id}-{courseware_id}.hold"
            )
            cleanable_delete = temp_root / (
                f".delete-{quarantine_id}-{courseware_id}.delete"
            )
            os.replace(original, recovery_hold)
            quarantined.append(
                (original, recovery_hold, cleanable_delete)
            )

        conn.execute(
            "DELETE FROM courseware WHERE id = ?",
            (courseware_id,),
        )
        conn.commit()
        committed = True
    except HTTPException:
        conn.rollback()
        raise
    except Exception as exc:
        conn.rollback()
        raise HTTPException(status_code=500, detail="课件删除失败") from exc
    finally:
        if not committed:
            for original, recovery_hold, _ in reversed(quarantined):
                try:
                    if recovery_hold.exists() and not original.exists():
                        os.replace(recovery_hold, original)
                except OSError:
                    LOGGER.error(
                        "课件删除失败且文件自动恢复失败，"
                        "已保留一个人工恢复副本"
                    )
        conn.close()

    for _, recovery_hold, cleanable_delete in quarantined:
        try:
            os.replace(recovery_hold, cleanable_delete)
        except OSError:
            LOGGER.error(
                "课件数据库记录已删除，但隔离文件状态转换失败，"
                "已保留人工处理副本"
            )
            continue
        try:
            cleanable_delete.unlink()
        except OSError:
            LOGGER.warning("未能立即清理一个已确认删除的课件文件")
    return {"message": "删除成功"}
