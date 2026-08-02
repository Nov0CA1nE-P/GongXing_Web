#!/usr/bin/env python3
"""Validate and safely extract one transported Gongxing release archive."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import stat
import tarfile
from pathlib import Path, PurePosixPath

from release_integrity import assert_allowed_path, create_manifest, file_sha256


def parse_manifest(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            raise RuntimeError("release build manifest is malformed")
        key, value = line.split("=", 1)
        if not key or key in result:
            raise RuntimeError("release build manifest contains duplicate keys")
        result[key] = value
    return result


def normalized_member_name(name: str) -> str | None:
    if "\\" in name or name.startswith("/"):
        raise RuntimeError("archive contains an unsafe path")
    while name.startswith("./"):
        name = name[2:]
    if name in {"", "."}:
        return None
    pure = PurePosixPath(name)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise RuntimeError("archive contains path traversal")
    return pure.as_posix()


def read_checksum(path: Path, archive: Path) -> str:
    content = path.read_text(encoding="ascii")
    match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._-]+)\n?", content)
    if match is None or match.group(2) != archive.name:
        raise RuntimeError("checksum file is malformed or names another archive")
    return match.group(1)


def validate_wheelhouse(root: Path) -> None:
    wheelhouse = root / "wheelhouse"
    checksum_file = root / "WHEELHOUSE_SHA256SUMS"
    wheel_files = sorted(path for path in wheelhouse.iterdir() if path.is_file())
    if not wheel_files or any(path.suffix != ".whl" for path in wheel_files):
        raise RuntimeError("wheelhouse must contain wheels only")
    expected: dict[str, str] = {}
    for line in checksum_file.read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._-]+\.whl)", line)
        if match is None or match.group(2) in expected:
            raise RuntimeError("wheel checksum list is malformed")
        expected[match.group(2)] = match.group(1)
    if set(expected) != {path.name for path in wheel_files}:
        raise RuntimeError("wheel checksum list does not match wheelhouse")
    for wheel in wheel_files:
        if file_sha256(wheel) != expected[wheel.name]:
            raise RuntimeError("wheel digest mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--checksum", required=True, type=Path)
    parser.add_argument("--release", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--integrity-manifest", required=True, type=Path)
    parser.add_argument("--allow-test-owner", action="store_true")
    args = parser.parse_args()

    if not re.fullmatch(r"[0-9a-f]{7,40}", args.release):
        raise RuntimeError("invalid release ID")
    archive = args.archive.resolve(strict=True)
    checksum = args.checksum.resolve(strict=True)
    expected_archive_digest = read_checksum(checksum, archive)
    if file_sha256(archive) != expected_archive_digest:
        raise RuntimeError("archive digest mismatch")
    if args.output_dir.exists() or args.output_dir.is_symlink():
        raise RuntimeError("output directory already exists")
    if args.integrity_manifest.exists() or args.integrity_manifest.is_symlink():
        raise RuntimeError("integrity manifest already exists")

    members: list[tuple[tarfile.TarInfo, str]] = []
    seen: set[str] = set()
    with tarfile.open(archive, mode="r:gz") as bundle:
        for member in bundle.getmembers():
            normalized = normalized_member_name(member.name)
            if normalized is None:
                continue
            if normalized in seen:
                raise RuntimeError("archive contains duplicate paths")
            seen.add(normalized)
            assert_allowed_path(normalized)
            if not (member.isfile() or member.isdir()):
                raise RuntimeError("archive contains a link or special file")
            members.append((member, normalized))

        required = {
            "RELEASE_BUILD_MANIFEST.txt",
            "WHEELHOUSE_SHA256SUMS",
            "backend",
            "backend/requirements.lock",
            "frontend",
            "frontend/dist",
            "wheelhouse",
        }
        if not required.issubset(seen):
            raise RuntimeError("archive is missing required release content")

        args.output_dir.mkdir(mode=0o750, parents=False)
        try:
            for member, normalized in sorted(members, key=lambda item: item[1]):
                destination = args.output_dir / normalized
                if member.isdir():
                    destination.mkdir(mode=0o750, parents=True, exist_ok=True)
                    os.chmod(destination, 0o750)
                    continue
                destination.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
                source = bundle.extractfile(member)
                if source is None:
                    raise RuntimeError("archive member could not be read")
                with source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output)
                os.chmod(destination, 0o640)
        except Exception:
            shutil.rmtree(args.output_dir, ignore_errors=True)
            raise

    manifest = parse_manifest(args.output_dir / "RELEASE_BUILD_MANIFEST.txt")
    if manifest.get("git_sha") != args.release:
        shutil.rmtree(args.output_dir, ignore_errors=True)
        raise RuntimeError("release build manifest Git SHA mismatch")
    validate_wheelhouse(args.output_dir)

    create_args = argparse.Namespace(
        directory=args.output_dir,
        release=args.release,
        archive_sha256=expected_archive_digest,
        output=args.integrity_manifest,
        require_root_owner=not args.allow_test_owner,
    )
    create_manifest(create_args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"release package verification failed: {exc}", file=os.sys.stderr)
        raise SystemExit(1) from None
