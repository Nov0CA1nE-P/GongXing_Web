import logging
import os
import re
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from xml.etree import ElementTree

import olefile
from olefile.olefile import OleFileError
from fastapi import HTTPException, UploadFile

from config import (
    COURSEWARE_MAX_UPLOAD_BYTES,
    COURSEWARE_TEMP_DIR,
    UPLOADS_DIR,
)

LOGGER = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024
MULTIPART_OVERHEAD_BYTES = 1024 * 1024
TEMP_FILE_MAX_AGE_SECONDS = 24 * 60 * 60
MAX_PPTX_ENTRIES = 2048
MAX_PPTX_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
MAX_CONTENT_TYPES_BYTES = 1024 * 1024
MAX_PRESENTATION_XML_BYTES = 8 * 1024 * 1024
MAX_OOXML_ENTRIES = MAX_PPTX_ENTRIES
MAX_OOXML_UNCOMPRESSED_BYTES = MAX_PPTX_UNCOMPRESSED_BYTES
MAX_DOCUMENT_XML_BYTES = 8 * 1024 * 1024

SUPPORTED_MIME_TYPES = {
    ".pdf": {"application/pdf"},
    ".ppt": {
        "application/vnd.ms-powerpoint",
        "application/mspowerpoint",
        "application/powerpoint",
    },
    ".pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    },
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    },
    ".jpg": {"image/jpeg"},
}
DOWNLOAD_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": (
        "application/vnd.openxmlformats-officedocument."
        "presentationml.presentation"
    ),
    ".docx": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    ),
    ".jpg": "image/jpeg",
}
PPTX_MAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "presentationml.presentation.main+xml"
)
_CLEANABLE_TEMP_NAME_RE = re.compile(
    r"^(?:\.upload-[0-9a-f]{32}\.part|"
    r"\.delete-[0-9a-f]{32}-[0-9]+\.delete)$"
)
_RECOVERY_HOLD_NAME_RE = re.compile(
    r"^\.recover-[0-9a-f]{32}-[0-9]+\.hold$"
)
_UUID_FILE_RE = re.compile(r"^[0-9a-f]{32}\.(?:pdf|ppt|pptx|docx|jpg)$")


class UnsafeStoredPath(ValueError):
    """数据库文件路径不能安全映射到当前上传目录。"""


def _normalized_content_type(value: str | None) -> str:
    return (value or "").split(";", 1)[0].strip().lower()


def is_safe_basename(value: str) -> bool:
    if not value or value in {".", ".."}:
        return False
    if "/" in value or "\\" in value or "\x00" in value:
        return False
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        return False
    if Path(value).name != value:
        return False
    return Path(value).suffix.lower() in SUPPORTED_MIME_TYPES


def classify_stored_path(value: str) -> tuple[str, str]:
    """返回路径类别和安全 basename，不返回或使用原始绝对路径。"""
    if not value:
        raise UnsafeStoredPath("empty")

    if "/" not in value and "\\" not in value:
        if not is_safe_basename(value):
            raise UnsafeStoredPath("invalid")
        kind = "new" if _UUID_FILE_RE.fullmatch(value) else "legacy_basename"
        return kind, value
    if "/" in value and "\\" in value:
        raise UnsafeStoredPath("mixed")

    windows_path = PureWindowsPath(value)
    use_windows = bool(
        "\\" in value
        or windows_path.drive
        or value.startswith("//")
    )
    if use_windows:
        path = windows_path
        parts = path.parts
        parent_parts = [part.lower() for part in path.parent.parts]
        kind = "windows_legacy"
    else:
        path = PurePosixPath(value)
        parts = path.parts
        parent_parts = list(path.parent.parts)
        kind = "posix_legacy"

    if ".." in parts or not is_safe_basename(path.name):
        raise UnsafeStoredPath("invalid")
    if len(parent_parts) < 2 or parent_parts[-2:] != ["data", "uploads"]:
        raise UnsafeStoredPath("outside")
    return kind, path.name


def safe_stored_basename(value: str) -> str:
    return classify_stored_path(value)[1]


def resolve_upload_path(
    stored_value: str,
    *,
    uploads_dir: str | Path = UPLOADS_DIR,
    require_exists: bool,
) -> Path:
    filename = safe_stored_basename(stored_value)
    root = Path(uploads_dir)
    if root.is_symlink():
        raise UnsafeStoredPath("symlink")
    resolved_root = root.resolve()
    candidate = root / filename
    if candidate.is_symlink():
        raise UnsafeStoredPath("symlink")
    resolved_candidate = candidate.resolve(strict=False)
    if resolved_candidate.parent != resolved_root:
        raise UnsafeStoredPath("outside")
    if require_exists and (
        not resolved_candidate.exists() or not resolved_candidate.is_file()
    ):
        raise FileNotFoundError(filename)
    return resolved_candidate


def serialize_courseware_row(row) -> dict:
    result = dict(row)
    for field in ("pdf_path", "pptx_path", "file_path"):
        stored_value = result.get(field, "")
        if not stored_value:
            result[field] = ""
            continue
        try:
            result[field] = safe_stored_basename(stored_value)
        except UnsafeStoredPath:
            result[field] = ""
    reference = courseware_file_reference(row)
    if reference is None:
        result["file_path"] = ""
        result["file_type"] = ""
        result["display_mode"] = ""
    else:
        filename, extension = reference
        result["file_path"] = filename
        result["file_type"] = extension.lstrip(".")
        result["display_mode"] = (
            "inline" if extension in {".pdf", ".jpg"} else "download"
        )
    return result


def courseware_file_reference(row) -> tuple[str, str] | None:
    """统一解析通用字段和旧字段，返回安全文件名与扩展名。"""
    source = dict(row)
    if source.get("file_path"):
        try:
            filename = safe_stored_basename(source["file_path"])
        except UnsafeStoredPath:
            return None
        extension = Path(filename).suffix.lower()
        return (filename, extension) if extension in SUPPORTED_MIME_TYPES else None
    candidates: list[str] = []
    for field in ("pdf_path", "pptx_path"):
        if source.get(field):
            candidates.append(source[field])
    for stored_value in candidates:
        try:
            filename = safe_stored_basename(stored_value)
        except UnsafeStoredPath:
            continue
        extension = Path(filename).suffix.lower()
        if extension in SUPPORTED_MIME_TYPES:
            return filename, extension
    return None


def courseware_file_type(row) -> str | None:
    reference = courseware_file_reference(row)
    return reference[1].lstrip(".") if reference else None


def has_pdf_content_signature(path: Path) -> bool:
    """轻量检查前1024字节中的PDF签名，不等同于完整PDF语法验证。"""
    with path.open("rb") as stream:
        return b"%PDF-" in stream.read(1024)


def public_pdf_filename(
    row,
    *,
    uploads_dir: str | Path = UPLOADS_DIR,
) -> str | None:
    """返回可公开下载的 PDF 文件名；任何路径或文件异常都视为不可公开。"""
    stored_value = dict(row).get("pdf_path", "")
    if not stored_value:
        return None
    try:
        filename = safe_stored_basename(stored_value)
        if Path(filename).suffix.lower() != ".pdf":
            return None
        file_path = resolve_upload_path(
            stored_value,
            uploads_dir=uploads_dir,
            require_exists=True,
        )
    except (UnsafeStoredPath, FileNotFoundError):
        return None
    if file_path.is_symlink() or not file_path.is_file():
        return None
    try:
        if not has_pdf_content_signature(file_path):
            return None
    except OSError:
        return None
    # 内容检查和返回之间再次确认，文件消失或被替换时安全失败。
    if (
        not file_path.exists()
        or file_path.is_symlink()
        or not file_path.is_file()
    ):
        return None
    return filename


def public_courseware_reference(
    row,
    *,
    uploads_dir: str | Path = UPLOADS_DIR,
) -> tuple[str, str] | None:
    """返回公开支持格式的安全文件引用；异常和内容篡改均视为不可用。"""
    source = dict(row)
    reference = courseware_file_reference(row)
    if reference is None:
        return None
    filename, extension = reference
    if extension == ".ppt" or (
        not source.get("file_path") and extension in {".pptx", ".docx", ".jpg"}
    ):
        # 旧字段中的演示文稿只保留后台兼容和删除能力；新记录走通用字段。
        return None
    try:
        file_path = resolve_upload_path(
            filename,
            uploads_dir=uploads_dir,
            require_exists=True,
        )
        _validate_file_content(file_path, extension)
    except (UnsafeStoredPath, FileNotFoundError, OSError, RuntimeError, ValueError):
        return None
    if file_path.is_symlink() or not file_path.is_file():
        return None
    return filename, extension


def serialize_public_courseware_row(
    row,
    *,
    uploads_dir: str | Path = UPLOADS_DIR,
) -> dict | None:
    reference = public_courseware_reference(row, uploads_dir=uploads_dir)
    if reference is None:
        return None
    filename, extension = reference
    source = dict(row)
    return {
        "id": source["id"],
        "title": source["title"],
        "description": source.get("description", ""),
        "tags": source.get("tags", ""),
        # 保留 pdf_path 兼容现有 PDF 客户端；新客户端使用通用字段。
        "pdf_path": filename if extension == ".pdf" else "",
        "file_path": filename,
        "file_type": extension.lstrip("."),
        "display_mode": "inline" if extension in {".pdf", ".jpg"} else "download",
    }


def _read_limited(archive: zipfile.ZipFile, name: str, limit: int) -> bytes:
    with archive.open(name) as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("PPTX XML 超过安全上限")
    return data


def _validate_pptx(path: Path) -> None:
    if not zipfile.is_zipfile(path):
        raise ValueError("PPTX 文件结构无效")
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_PPTX_ENTRIES:
                raise ValueError("PPTX ZIP 条目过多")

            total_size = 0
            names = set()
            for entry in entries:
                pure_name = PurePosixPath(entry.filename)
                if (
                    pure_name.is_absolute()
                    or PureWindowsPath(entry.filename).drive
                    or ".." in pure_name.parts
                    or "\\" in entry.filename
                ):
                    raise ValueError("PPTX ZIP 包含危险路径")
                total_size += entry.file_size
                if total_size > MAX_PPTX_UNCOMPRESSED_BYTES:
                    raise ValueError("PPTX 解压后内容超过安全上限")
                names.add(entry.filename)
            if len(names) != len(entries):
                raise ValueError("PPTX ZIP 包含重复条目")

            required = {"[Content_Types].xml", "ppt/presentation.xml"}
            if not required.issubset(names):
                raise ValueError("PPTX 缺少必要结构")
            content_info = archive.getinfo("[Content_Types].xml")
            presentation_info = archive.getinfo("ppt/presentation.xml")
            if content_info.file_size > MAX_CONTENT_TYPES_BYTES:
                raise ValueError("PPTX 内容类型 XML 超过安全上限")
            if presentation_info.file_size > MAX_PRESENTATION_XML_BYTES:
                raise ValueError("PPTX 主文档 XML 超过安全上限")

            content_types = _read_limited(
                archive,
                "[Content_Types].xml",
                MAX_CONTENT_TYPES_BYTES,
            )
            _read_limited(
                archive,
                "ppt/presentation.xml",
                MAX_PRESENTATION_XML_BYTES,
            )
            root = ElementTree.fromstring(content_types)
            valid_main_type = any(
                element.attrib.get("PartName") == "/ppt/presentation.xml"
                and element.attrib.get("ContentType") == PPTX_MAIN_CONTENT_TYPE
                for element in root
                if element.tag.rsplit("}", 1)[-1] == "Override"
            )
            if not valid_main_type:
                raise ValueError("PPTX 主文档类型声明无效")
    except (
        zipfile.BadZipFile,
        KeyError,
        ElementTree.ParseError,
        RuntimeError,
        NotImplementedError,
        OSError,
    ) as exc:
        raise ValueError("PPTX 文件结构无效") from exc


DOCX_MAIN_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument."
    "wordprocessingml.document.main+xml"
)


def _validate_docx(path: Path) -> None:
    """校验 DOCX 的 ZIP 结构和主文档类型，不将压缩包解压到磁盘。"""
    if not zipfile.is_zipfile(path):
        raise ValueError("DOCX 文件结构无效")
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_OOXML_ENTRIES:
                raise ValueError("DOCX ZIP 条目过多")
            total_size = 0
            names: set[str] = set()
            for entry in entries:
                pure_name = PurePosixPath(entry.filename)
                if (
                    pure_name.is_absolute()
                    or PureWindowsPath(entry.filename).drive
                    or ".." in pure_name.parts
                    or "\\" in entry.filename
                ):
                    raise ValueError("DOCX ZIP 包含危险路径")
                if entry.filename in names:
                    raise ValueError("DOCX ZIP 包含重复条目")
                names.add(entry.filename)
                total_size += entry.file_size
                if total_size > MAX_OOXML_UNCOMPRESSED_BYTES:
                    raise ValueError("DOCX 解压后内容超过安全上限")
                if entry.file_size and entry.compress_size == 0:
                    raise ValueError("DOCX ZIP 压缩信息无效")
                if (
                    entry.compress_size
                    and entry.file_size / entry.compress_size > 200
                ):
                    raise ValueError("DOCX ZIP 压缩比异常")

            required = {"[Content_Types].xml", "word/document.xml"}
            if not required.issubset(names):
                raise ValueError("DOCX 缺少必要结构")
            content_info = archive.getinfo("[Content_Types].xml")
            document_info = archive.getinfo("word/document.xml")
            if content_info.file_size > MAX_CONTENT_TYPES_BYTES:
                raise ValueError("DOCX 内容类型 XML 超过安全上限")
            if document_info.file_size > MAX_DOCUMENT_XML_BYTES:
                raise ValueError("DOCX 主文档 XML 超过安全上限")
            content_types = _read_limited(
                archive, "[Content_Types].xml", MAX_CONTENT_TYPES_BYTES
            )
            _read_limited(archive, "word/document.xml", MAX_DOCUMENT_XML_BYTES)
            root = ElementTree.fromstring(content_types)
            valid_main_type = any(
                element.attrib.get("PartName") == "/word/document.xml"
                and element.attrib.get("ContentType") == DOCX_MAIN_CONTENT_TYPE
                for element in root
                if element.tag.rsplit("}", 1)[-1] == "Override"
            )
            if not valid_main_type:
                raise ValueError("DOCX 主文档类型声明无效")
    except (
        zipfile.BadZipFile,
        KeyError,
        ElementTree.ParseError,
        RuntimeError,
        NotImplementedError,
        OSError,
    ) as exc:
        raise ValueError("DOCX 文件结构无效") from exc


def _validate_jpeg(path: Path) -> None:
    """检查 JPEG 段结构、图像帧和文件结束标记。"""
    data = path.read_bytes()
    if len(data) < 4 or data[:2] != b"\xff\xd8" or data[-2:] != b"\xff\xd9":
        raise ValueError("JPG 文件结构无效")
    position = 2
    saw_frame = False
    saw_scan = False
    length = len(data)
    while position < length - 2:
        if data[position] != 0xFF:
            raise ValueError("JPG 文件段结构无效")
        while position < length and data[position] == 0xFF:
            position += 1
        if position >= length:
            raise ValueError("JPG 文件段结构无效")
        marker = data[position]
        position += 1
        if marker == 0xD9:
            break
        if marker == 0xDA:
            saw_scan = True
            # 扫描数据直到 EOI；其中的 FF00 是转义字节。
            while position < length - 1:
                if data[position] == 0xFF:
                    if data[position + 1] == 0xD9:
                        if not saw_frame or not saw_scan:
                            raise ValueError("JPG 缺少有效图像帧")
                        return
                    if data[position + 1] == 0x00:
                        position += 2
                        continue
                position += 1
            raise ValueError("JPG 缺少结束标记")
        if marker in {0x01} or 0xD0 <= marker <= 0xD7:
            continue
        if position + 2 > length:
            raise ValueError("JPG 文件段长度无效")
        segment_length = int.from_bytes(data[position:position + 2], "big")
        if segment_length < 2 or position + segment_length > length:
            raise ValueError("JPG 文件段长度无效")
        if 0xC0 <= marker <= 0xC3 or 0xC5 <= marker <= 0xC7 or 0xC9 <= marker <= 0xCB or 0xCD <= marker <= 0xCF:
            if segment_length < 8:
                raise ValueError("JPG 图像帧无效")
            height = int.from_bytes(data[position + 3:position + 5], "big")
            width = int.from_bytes(data[position + 5:position + 7], "big")
            if not width or not height:
                raise ValueError("JPG 图像尺寸无效")
            saw_frame = True
        position += segment_length
    if not saw_frame or not saw_scan:
        raise ValueError("JPG 缺少有效图像帧")


def _validate_file_content(path: Path, extension: str) -> None:
    if extension == ".pdf":
        if not has_pdf_content_signature(path):
            raise ValueError("PDF 文件签名无效")
        return
    if extension == ".ppt":
        try:
            if not olefile.isOleFile(str(path)):
                raise ValueError("PPT OLE 容器无效")
            with olefile.OleFileIO(str(path)) as container:
                if not container.exists("PowerPoint Document"):
                    raise ValueError("文件不是有效的旧版 PowerPoint")
        except (OSError, IOError, OleFileError) as exc:
            raise ValueError("PPT OLE 容器损坏") from exc
        return
    if extension == ".pptx":
        _validate_pptx(path)
        return
    if extension == ".docx":
        _validate_docx(path)
        return
    if extension == ".jpg":
        _validate_jpeg(path)
        return
    raise ValueError("文件类型不受支持")


def validate_upload_metadata(upload: UploadFile) -> str:
    filename = upload.filename or ""
    if not is_safe_basename(filename):
        raise HTTPException(
            status_code=400,
            detail="仅支持有效的 PDF、PPT、PPTX、DOCX、JPG 文件名",
        )
    extension = Path(filename).suffix.lower()
    content_type = _normalized_content_type(upload.content_type)
    if content_type not in SUPPORTED_MIME_TYPES[extension]:
        raise HTTPException(
            status_code=400,
            detail="文件扩展名与声明的 MIME 类型不匹配",
        )
    return extension


async def store_validated_upload(
    upload: UploadFile,
    *,
    uploads_dir: str | Path | None = None,
    temp_dir: str | Path | None = None,
    max_bytes: int | None = None,
) -> tuple[str, Path]:
    extension = validate_upload_metadata(upload)
    uploads_root = Path(uploads_dir or UPLOADS_DIR)
    temporary_root = Path(temp_dir or COURSEWARE_TEMP_DIR)
    effective_max_bytes = (
        COURSEWARE_MAX_UPLOAD_BYTES if max_bytes is None else max_bytes
    )
    uploads_root.mkdir(parents=True, exist_ok=True)
    temporary_root.mkdir(parents=True, exist_ok=True)
    if uploads_root.is_symlink() or temporary_root.is_symlink():
        raise HTTPException(status_code=500, detail="文件存储暂时不可用")

    temp_path = temporary_root / f".upload-{uuid.uuid4().hex}.part"
    final_name = f"{uuid.uuid4().hex}{extension}"
    final_path = uploads_root / final_name
    total = 0
    moved = False

    try:
        with temp_path.open("xb") as output:
            while True:
                chunk = await upload.read(CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > effective_max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail="上传文件超过允许的大小",
                    )
                output.write(chunk)
        if total == 0:
            raise HTTPException(status_code=400, detail="上传文件不能为空")
        try:
            _validate_file_content(temp_path, extension)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        os.replace(temp_path, final_path)
        moved = True
        return final_name, final_path
    except HTTPException:
        raise
    except (OSError, IOError) as exc:
        raise HTTPException(status_code=500, detail="文件存储失败") from exc
    finally:
        if temp_path.exists() and not temp_path.is_symlink():
            try:
                temp_path.unlink()
            except OSError:
                LOGGER.warning("未能清理一个课件上传临时文件")
        if not moved and final_path.exists() and not final_path.is_symlink():
            try:
                final_path.unlink()
            except OSError:
                LOGGER.warning("未能清理一个未提交的课件文件")


def cleanup_stale_temporary_files(
    *,
    temp_dir: str | Path | None = None,
    now: float | None = None,
) -> None:
    root = Path(temp_dir or COURSEWARE_TEMP_DIR)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        LOGGER.warning("课件临时目录不可用，已跳过启动清理")
        return
    if root.is_symlink():
        LOGGER.warning("课件临时目录是符号链接，已跳过启动清理")
        return

    cutoff = (time.time() if now is None else now) - TEMP_FILE_MAX_AGE_SECONDS
    try:
        entries = list(root.iterdir())
    except OSError:
        LOGGER.warning("无法检查课件临时目录，已跳过启动清理")
        return
    for entry in entries:
        # 恢复保留态可能是数据库失败后的唯一副本，永不自动清理。
        if _RECOVERY_HOLD_NAME_RE.fullmatch(entry.name):
            continue
        if not _CLEANABLE_TEMP_NAME_RE.fullmatch(entry.name):
            continue
        try:
            if entry.is_symlink() or not entry.is_file():
                continue
            if entry.stat().st_mtime < cutoff:
                entry.unlink()
        except OSError:
            LOGGER.warning("未能清理一个过期的课件临时文件")


def prepare_storage() -> None:
    Path(UPLOADS_DIR).mkdir(parents=True, exist_ok=True)
    cleanup_stale_temporary_files()
