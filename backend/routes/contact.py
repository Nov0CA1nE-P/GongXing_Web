from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from abuse_protection import (
    consume_rules,
    public_identity,
    visitor_and_ip_rules,
)
from auth import AdminSession, require_admin, require_admin_write
from contact_retention import classify_contact_timestamp, utc_now
from database import get_db

router = APIRouter(prefix="/api/contact", tags=["contact"])


class ContactSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    contact_info: str = Field(default="", max_length=200)
    message: str = Field(min_length=1, max_length=2000)


@router.post("/submit")
def submit_contact(data: ContactSubmit, request: Request):
    """学生提交联系表单"""
    if not data.name.strip() or not data.message.strip():
        raise HTTPException(status_code=400, detail="称呼和留言内容不能为空")

    identity = public_identity(request)
    consume_rules(
        visitor_and_ip_rules(
            identity,
            "contact",
            visitor_limits=((3, 3600), (10, 86400)),
            ip_limits=((60, 3600), (200, 86400)),
        )
    )

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO contact_submissions "
            "(name, contact_info, message) VALUES (?, ?, ?)",
            (data.name.strip(), data.contact_info.strip(), data.message.strip()),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    worker = getattr(request.app.state, "contact_retention_worker", None)
    if worker is not None:
        worker.notify_changed()
    return {"message": "提交成功"}


@router.get("/submissions")
def list_submissions(
    _admin: AdminSession = Depends(require_admin),
):
    """管理员查看联系表单提交记录"""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM contact_submissions ORDER BY created_at DESC, id DESC"
        ).fetchall()
    finally:
        conn.close()

    now = utc_now()
    visible = []
    for row in rows:
        retention = classify_contact_timestamp(row["created_at"], now=now)
        if not retention.is_visible:
            continue
        item = dict(row)
        item["retention_status"] = retention.retention_status
        item["expires_at"] = retention.expires_at
        visible.append(item)
    return visible


@router.delete("/submissions/{submission_id}", status_code=204)
def delete_submission(
    submission_id: int,
    request: Request,
    _admin: AdminSession = Depends(require_admin_write),
):
    """管理员手动删除联系记录或已经处理完的删除申请。"""
    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT id FROM contact_submissions WHERE id = ?",
            (submission_id,),
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="联系记录不存在")
        conn.execute(
            "DELETE FROM contact_submissions WHERE id = ?",
            (submission_id,),
        )
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    worker = getattr(request.app.state, "contact_retention_worker", None)
    if worker is not None:
        worker.notify_changed()
    return Response(status_code=204)
