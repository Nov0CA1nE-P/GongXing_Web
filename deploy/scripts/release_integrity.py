#!/usr/bin/env python3
"""Create and verify deterministic manifests for extracted release directories."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import unicodedata
from pathlib import Path, PurePosixPath


RELEASE_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")
FORBIDDEN_EXACT = {
    ".env",
    "id_ed25519",
    "id_rsa",
    "restic-password",
}
FORBIDDEN_SUFFIXES = (
    ".db",
    ".db-shm",
    ".db-wal",
    ".htpasswd",
    ".key",
    ".pdf",
    ".pem",
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative_path(relative: Path) -> str:
    value = unicodedata.normalize("NFC", relative.as_posix())
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise RuntimeError("release contains an unsafe path")
    if "\\" in value:
        raise RuntimeError("release contains a non-POSIX path")
    return value


def assert_allowed_path(relative: str) -> None:
    parts = PurePosixPath(relative).parts
    lowered = [unicodedata.normalize("NFC", part).casefold() for part in parts]
    if lowered[0] == "data":
        raise RuntimeError("release contains a persistent data directory")
    for part in lowered:
        if part == ".env" or part.startswith(".env."):
            raise RuntimeError("release contains an environment file")
        if part in FORBIDDEN_EXACT or part.endswith(FORBIDDEN_SUFFIXES):
            raise RuntimeError("release contains a forbidden file")
    if "wheelhouse" in lowered and (
        lowered[0] != "wheelhouse" or parts[0] != "wheelhouse"
    ):
        raise RuntimeError("wheelhouse is only allowed at the prescribed root path")


def scan_directory(root: Path, require_root_owner: bool) -> list[dict[str, object]]:
    resolved = root.resolve(strict=True)
    root_stat = resolved.lstat()
    if not stat.S_ISDIR(root_stat.st_mode):
        raise RuntimeError("release root is not a directory")
    if require_root_owner and root_stat.st_uid != 0:
        raise RuntimeError("release root must be owned by root")
    if require_root_owner and root_stat.st_mode & 0o022:
        raise RuntimeError("release root must not be writable by group or others")

    entries: list[dict[str, object]] = []
    collision_keys: set[str] = set()
    for path in sorted(resolved.rglob("*"), key=lambda item: item.relative_to(resolved).as_posix()):
        relative = safe_relative_path(path.relative_to(resolved))
        collision_key = relative.casefold()
        if collision_key in collision_keys:
            raise RuntimeError("release contains normalized-colliding paths")
        collision_keys.add(collision_key)
        assert_allowed_path(relative)
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise RuntimeError("release contains a symbolic link")
        if require_root_owner and metadata.st_uid != 0:
            raise RuntimeError("release entries must be owned by root")
        if require_root_owner and metadata.st_mode & 0o022:
            raise RuntimeError("release entries must not be writable by group or others")
        if stat.S_ISDIR(metadata.st_mode):
            kind = "directory"
            digest = None
            size = 0
        elif stat.S_ISREG(metadata.st_mode):
            kind = "file"
            digest = file_sha256(path)
            size = metadata.st_size
        else:
            raise RuntimeError("release contains a special file")
        entries.append(
            {
                "path": relative,
                "kind": kind,
                "mode": stat.S_IMODE(metadata.st_mode),
                "size": size,
                "sha256": digest,
            }
        )
    return entries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--directory", required=True, type=Path)
    create.add_argument("--release", required=True)
    create.add_argument("--archive-sha256", required=True)
    create.add_argument("--output", required=True, type=Path)
    create.add_argument("--require-root-owner", action="store_true")
    verify = subparsers.add_parser("verify")
    verify.add_argument("--directory", required=True, type=Path)
    verify.add_argument("--release", required=True)
    verify.add_argument("--manifest", required=True, type=Path)
    verify.add_argument("--require-root-owner", action="store_true")
    return parser.parse_args()


def validate_release(value: str) -> None:
    if not RELEASE_PATTERN.fullmatch(value):
        raise RuntimeError("invalid release ID")


def create_manifest(args: argparse.Namespace) -> int:
    validate_release(args.release)
    if not re.fullmatch(r"[0-9a-f]{64}", args.archive_sha256):
        raise RuntimeError("invalid archive digest")
    if args.output.exists() or args.output.is_symlink():
        raise RuntimeError("integrity manifest output already exists")
    payload = {
        "format": 1,
        "release": args.release,
        "archive_sha256": args.archive_sha256,
        "entries": scan_directory(args.directory, args.require_root_owner),
    }
    args.output.write_text(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    os.chmod(args.output, 0o600)
    return 0


def verify_manifest(args: argparse.Namespace) -> int:
    validate_release(args.release)
    manifest_stat = args.manifest.lstat()
    if not stat.S_ISREG(manifest_stat.st_mode) or args.manifest.is_symlink():
        raise RuntimeError("integrity manifest must be a regular file")
    if args.require_root_owner and manifest_stat.st_uid != 0:
        raise RuntimeError("integrity manifest must be owned by root")
    if args.require_root_owner and manifest_stat.st_mode & 0o077:
        raise RuntimeError("integrity manifest must not be accessible by group or others")
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    if payload.get("format") != 1 or payload.get("release") != args.release:
        raise RuntimeError("integrity manifest release mismatch")
    actual = scan_directory(args.directory, args.require_root_owner)
    if actual != payload.get("entries"):
        raise RuntimeError("release directory changed after verification")
    return 0


def main() -> int:
    args = parse_args()
    if args.command == "create":
        return create_manifest(args)
    return verify_manifest(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"release integrity verification failed: {exc}", file=os.sys.stderr)
        raise SystemExit(1) from None
