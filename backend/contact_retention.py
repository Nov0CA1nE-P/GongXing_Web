import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from database import get_db

LOGGER = logging.getLogger(__name__)

RETENTION_DAYS = 90
RETENTION_DELTA = timedelta(days=RETENTION_DAYS)
MAX_SELF_CHECK_SECONDS = 60 * 60
FAILURE_RETRY_SECONDS = 5 * 60
SQLITE_UTC_FORMAT = "%Y-%m-%d %H:%M:%S"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_sqlite_utc(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, SQLITE_UTC_FORMAT).replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def retention_cutoff(now: datetime) -> datetime:
    return now.astimezone(timezone.utc) - RETENTION_DELTA


def format_sqlite_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime(SQLITE_UTC_FORMAT)


@dataclass(frozen=True)
class ContactRetentionView:
    retention_status: str
    expires_at: str | None
    is_visible: bool


def classify_contact_timestamp(
    value: object,
    *,
    now: datetime,
) -> ContactRetentionView:
    created_at = parse_sqlite_utc(value)
    if created_at is None:
        return ContactRetentionView("invalid_timestamp", None, True)
    expires_at = created_at + RETENTION_DELTA
    return ContactRetentionView(
        "active",
        expires_at.isoformat().replace("+00:00", "Z"),
        expires_at > now.astimezone(timezone.utc),
    )


def purge_expired_contacts(
    *,
    now: datetime | None = None,
    connection_factory: Callable = get_db,
) -> int:
    current = (now or utc_now()).astimezone(timezone.utc)
    conn = connection_factory()
    try:
        cursor = conn.execute(
            """
            DELETE FROM contact_submissions
            WHERE datetime(created_at) IS NOT NULL
              AND datetime(created_at) <= datetime(?)
            """,
            (format_sqlite_utc(retention_cutoff(current)),),
        )
        conn.commit()
        return cursor.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def next_contact_expiry(
    *,
    now: datetime | None = None,
    connection_factory: Callable = get_db,
) -> datetime | None:
    current = (now or utc_now()).astimezone(timezone.utc)
    conn = connection_factory()
    try:
        rows = conn.execute(
            "SELECT created_at FROM contact_submissions"
        ).fetchall()
    finally:
        conn.close()
    expiries = []
    for row in rows:
        created_at = parse_sqlite_utc(row["created_at"])
        if created_at is not None:
            expiry = created_at + RETENTION_DELTA
            if expiry > current:
                expiries.append(expiry)
    return min(expiries, default=None)


class ContactRetentionWorker:
    def __init__(
        self,
        *,
        purge: Callable[[], int] = purge_expired_contacts,
        next_expiry: Callable[[], datetime | None] = next_contact_expiry,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._purge = purge
        self._next_expiry = next_expiry
        self._clock = clock
        self._changed = asyncio.Event()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("联系记录清理任务已经启动")
        self._task = asyncio.create_task(
            self._run(),
            name="contact-retention",
        )

    def notify_changed(self) -> None:
        self._changed.set()

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _run(self) -> None:
        while True:
            # 先清除旧通知；执行期间到达的新通知会保留并使等待立即返回。
            self._changed.clear()
            try:
                # SQLite 操作很短，直接在任务内完成，关闭时不会遗留线程。
                self._purge()
                next_expiry = self._next_expiry()
                now = self._clock().astimezone(timezone.utc)
                if next_expiry is None:
                    delay = MAX_SELF_CHECK_SECONDS
                else:
                    delay = min(
                        MAX_SELF_CHECK_SECONDS,
                        max(0.0, (next_expiry - now).total_seconds()),
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("联系记录自动清理失败，将在后台重试")
                delay = FAILURE_RETRY_SECONDS

            try:
                await asyncio.wait_for(self._changed.wait(), timeout=delay)
            except asyncio.TimeoutError:
                continue
