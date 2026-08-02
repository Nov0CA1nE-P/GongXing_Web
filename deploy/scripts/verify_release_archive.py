#!/usr/bin/env python3
"""Validate and transactionally extract one transported Gongxing release."""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
import shutil
import tarfile
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath

from release_integrity import assert_allowed_path, create_manifest, file_sha256


MIB = 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * MIB
MAX_MEMBER_COUNT = 4096
MAX_MEMBER_DECLARED_BYTES = 32 * MIB
MAX_TOTAL_DECLARED_BYTES = 256 * MIB
MAX_COMPRESSION_RATIO = 40
MAX_ACTUAL_WRITTEN_BYTES = 256 * MIB
COPY_CHUNK_BYTES = MIB

MANIFEST_FIELDS = {
    "git_sha",
    "node_version",
    "npm_version",
    "python_version",
    "requirements_lock_sha256",
    "package_lock_sha256",
    "wheelhouse_sha256s_sha256",
    "built_at_utc",
}
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
REQUIREMENT_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)")
WHEEL_PATTERN = re.compile(
    r"^(?P<distribution>[A-Za-z0-9_.]+)-(?P<version>[^-]+)-[^-]+-[^-]+-[^-]+\.whl$"
)


def canonical_distribution(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def parse_manifest(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            raise RuntimeError("release build manifest is malformed")
        key, value = line.split("=", 1)
        if not key or not value or key in result:
            raise RuntimeError("release build manifest contains invalid fields")
        result[key] = value
    if set(result) != MANIFEST_FIELDS:
        raise RuntimeError("release build manifest fields are incomplete or unexpected")
    return result


def normalized_member_name(name: str) -> tuple[str | None, str | None]:
    if "\\" in name or name.startswith("/"):
        raise RuntimeError("archive contains an unsafe path")
    while name.startswith("./"):
        name = name[2:]
    if name in {"", "."}:
        return None, None
    normalized = unicodedata.normalize("NFC", name)
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise RuntimeError("archive contains path traversal")
    display = pure.as_posix()
    return display, display.casefold()


def read_checksum(path: Path, archive: Path) -> str:
    metadata = path.lstat()
    if path.is_symlink() or not path.is_file() or metadata.st_size > 256:
        raise RuntimeError("checksum file must be a small regular file")
    content = path.read_text(encoding="ascii")
    match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._-]+)\n?", content)
    if match is None or match.group(2) != archive.name:
        raise RuntimeError("checksum file is malformed or names another archive")
    return match.group(1)


def parse_locked_requirements(path: Path) -> dict[str, tuple[str, set[str]]]:
    requirements: dict[str, tuple[str, set[str]]] = {}
    current: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        match = REQUIREMENT_PATTERN.match(line)
        if match:
            name = canonical_distribution(match.group(1))
            if name in requirements:
                raise RuntimeError("requirements lock contains a duplicate distribution")
            requirements[name] = (match.group(2), set())
            current = name
            continue
        hash_match = re.search(r"--hash=sha256:([0-9a-f]{64})", line)
        if hash_match and current:
            requirements[current][1].add(hash_match.group(1))
    if not requirements or any(not hashes for _, hashes in requirements.values()):
        raise RuntimeError("requirements lock is incomplete")
    return requirements


def validate_wheelhouse(root: Path) -> None:
    wheelhouse = root / "wheelhouse"
    checksum_file = root / "WHEELHOUSE_SHA256SUMS"
    if not wheelhouse.is_dir() or not checksum_file.is_file():
        raise RuntimeError("offline wheelhouse is incomplete")
    wheel_files = sorted(path for path in wheelhouse.iterdir() if path.is_file())
    if not wheel_files or any(path.suffix != ".whl" for path in wheel_files):
        raise RuntimeError("wheelhouse must contain wheels only")
    expected_checksums: dict[str, str] = {}
    for line in checksum_file.read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._-]+\.whl)", line)
        if match is None or match.group(2) in expected_checksums:
            raise RuntimeError("wheel checksum list is malformed")
        expected_checksums[match.group(2)] = match.group(1)
    if set(expected_checksums) != {path.name for path in wheel_files}:
        raise RuntimeError("wheel checksum list does not match wheelhouse")

    locked = parse_locked_requirements(root / "backend/requirements.lock")
    wheels: dict[str, tuple[str, str]] = {}
    for wheel in wheel_files:
        match = WHEEL_PATTERN.fullmatch(wheel.name)
        if match is None:
            raise RuntimeError("wheel filename is invalid")
        distribution = canonical_distribution(match.group("distribution"))
        if distribution in wheels:
            raise RuntimeError("wheelhouse contains a duplicate distribution")
        digest = file_sha256(wheel)
        if digest != expected_checksums[wheel.name]:
            raise RuntimeError("wheel digest mismatch")
        wheels[distribution] = (match.group("version"), digest)
    if set(wheels) != set(locked):
        raise RuntimeError("wheelhouse does not exactly match the locked dependency plan")
    for distribution, (version, digest) in wheels.items():
        locked_version, allowed_hashes = locked[distribution]
        if version != locked_version or digest not in allowed_hashes:
            raise RuntimeError("wheel does not match its locked version or hash")


def validate_manifest(root: Path, release: str) -> None:
    manifest = parse_manifest(root / "RELEASE_BUILD_MANIFEST.txt")
    if manifest["git_sha"] != release:
        raise RuntimeError("release build manifest Git SHA mismatch")
    digest_checks = {
        "requirements_lock_sha256": root / "backend/requirements.lock",
        "package_lock_sha256": root / "frontend/package-lock.json",
        "wheelhouse_sha256s_sha256": root / "WHEELHOUSE_SHA256SUMS",
    }
    for field, path in digest_checks.items():
        if not SHA256_PATTERN.fullmatch(manifest[field]) or file_sha256(path) != manifest[field]:
            raise RuntimeError("release build manifest digest mismatch")
    if not re.fullmatch(r"v24\.18\.0", manifest["node_version"]):
        raise RuntimeError("release build manifest Node version mismatch")
    if manifest["npm_version"] != "11.16.0":
        raise RuntimeError("release build manifest npm version mismatch")
    if not re.fullmatch(r"Python 3\.12\.\d+", manifest["python_version"]):
        raise RuntimeError("release build manifest Python version mismatch")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", manifest["built_at_utc"]):
        raise RuntimeError("release build manifest timestamp is invalid")


def validate_path_semantics(
    normalized: str,
    collision_key: str,
    is_directory: bool,
    seen: dict[str, bool],
) -> None:
    if collision_key in seen:
        raise RuntimeError("archive contains duplicate or normalized-colliding paths")
    parts = normalized.split("/")
    folded_parts = collision_key.split("/")
    if "wheelhouse" in folded_parts:
        if folded_parts[0] != "wheelhouse" or parts[0] != "wheelhouse":
            raise RuntimeError("wheelhouse is only allowed at the prescribed root path")
    for index in range(1, len(folded_parts)):
        prefix = "/".join(folded_parts[:index])
        if seen.get(prefix) is False:
            raise RuntimeError("archive contains a file/directory prefix conflict")
    if not is_directory:
        descendant_prefix = collision_key + "/"
        if any(key.startswith(descendant_prefix) for key in seen):
            raise RuntimeError("archive contains a file/directory prefix conflict")
    seen[collision_key] = is_directory


def preflight_archive(archive: Path) -> list[tuple[tarfile.TarInfo, str]]:
    archive_metadata = archive.lstat()
    if archive.is_symlink() or not archive.is_file():
        raise RuntimeError("release archive must be a regular file")
    if archive_metadata.st_size <= 0 or archive_metadata.st_size > MAX_ARCHIVE_BYTES:
        raise RuntimeError("release archive exceeds the compressed size budget")
    members: list[tuple[tarfile.TarInfo, str]] = []
    seen: dict[str, bool] = {}
    total_declared = 0
    with tarfile.open(archive, mode="r:gz") as bundle:
        for member in bundle:
            normalized, collision_key = normalized_member_name(member.name)
            if normalized is None or collision_key is None:
                continue
            if len(members) >= MAX_MEMBER_COUNT:
                raise RuntimeError("release archive exceeds the member budget")
            if not (member.isfile() or member.isdir()):
                raise RuntimeError("archive contains a link or special file")
            if member.size < 0 or member.size > MAX_MEMBER_DECLARED_BYTES:
                raise RuntimeError("archive member exceeds the declared size budget")
            if member.isdir() and member.size != 0:
                raise RuntimeError("archive directory has an invalid declared size")
            total_declared += member.size
            if total_declared > MAX_TOTAL_DECLARED_BYTES:
                raise RuntimeError("archive exceeds the total declared size budget")
            assert_allowed_path(normalized)
            validate_path_semantics(
                normalized, collision_key, member.isdir(), seen
            )
            members.append((member, normalized))
    if total_declared > archive_metadata.st_size * MAX_COMPRESSION_RATIO:
        raise RuntimeError("release archive exceeds the compression ratio budget")
    required = {
        "RELEASE_BUILD_MANIFEST.txt",
        "WHEELHOUSE_SHA256SUMS",
        "backend",
        "backend/requirements.lock",
        "frontend",
        "frontend/dist",
        "frontend/package-lock.json",
        "wheelhouse",
    }
    if not required.issubset({name for _, name in members}):
        raise RuntimeError("archive is missing required release content")
    return members


def bounded_stream_copy(
    source: io.BufferedReader,
    destination: io.BufferedWriter,
    declared_size: int,
    total_written: int,
) -> int:
    member_written = 0
    while True:
        chunk = source.read(COPY_CHUNK_BYTES)
        if not chunk:
            break
        member_written += len(chunk)
        total_written += len(chunk)
        if member_written > declared_size:
            raise RuntimeError("archive member wrote more bytes than declared")
        if total_written > MAX_ACTUAL_WRITTEN_BYTES:
            raise RuntimeError("archive exceeds the actual extraction byte budget")
        destination.write(chunk)
    if member_written != declared_size:
        raise RuntimeError("archive member actual size differs from its header")
    return total_written


def extract_members(
    archive: Path,
    members: list[tuple[tarfile.TarInfo, str]],
    destination_root: Path,
) -> None:
    total_written = 0
    member_map = {member.offset: normalized for member, normalized in members}
    with tarfile.open(archive, mode="r:gz") as bundle:
        for member in bundle:
            normalized = member_map.get(member.offset)
            if normalized is None:
                continue
            destination = destination_root / normalized
            if member.isdir():
                destination.mkdir(mode=0o750, parents=True, exist_ok=True)
                os.chmod(destination, 0o750)
                continue
            destination.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
            source = bundle.extractfile(member)
            if source is None:
                raise RuntimeError("archive member could not be read")
            with source, destination.open("xb") as output:
                total_written = bounded_stream_copy(
                    source, output, member.size, total_written
                )
            os.chmod(destination, 0o640)


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
    archive = args.archive.absolute()
    checksum = args.checksum.absolute()
    output_dir = args.output_dir.absolute()
    integrity_manifest = args.integrity_manifest.absolute()
    if output_dir.exists() or output_dir.is_symlink():
        raise RuntimeError("output directory already exists")
    if integrity_manifest.exists() or integrity_manifest.is_symlink():
        raise RuntimeError("integrity manifest already exists")
    if not output_dir.parent.is_dir() or not integrity_manifest.parent.is_dir():
        raise RuntimeError("output parents must already exist")

    archive_metadata = archive.lstat()
    if archive.is_symlink() or not archive.is_file() or archive_metadata.st_size > MAX_ARCHIVE_BYTES:
        raise RuntimeError("release archive exceeds the compressed size budget")
    expected_archive_digest = read_checksum(checksum, archive)
    if file_sha256(archive) != expected_archive_digest:
        raise RuntimeError("archive digest mismatch")
    members = preflight_archive(archive)

    temporary_output = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.extracting-", dir=output_dir.parent)
    )
    temporary_manifest = integrity_manifest.with_name(
        f".{integrity_manifest.name}.tmp-{os.getpid()}"
    )
    try:
        os.chmod(temporary_output, 0o750)
        extract_members(archive, members, temporary_output)
        validate_manifest(temporary_output, args.release)
        validate_wheelhouse(temporary_output)
        create_args = argparse.Namespace(
            directory=temporary_output,
            release=args.release,
            archive_sha256=expected_archive_digest,
            output=temporary_manifest,
            require_root_owner=not args.allow_test_owner,
        )
        create_manifest(create_args)
        temporary_output.rename(output_dir)
        temporary_manifest.rename(integrity_manifest)
    except Exception:
        shutil.rmtree(temporary_output, ignore_errors=True)
        shutil.rmtree(output_dir, ignore_errors=True)
        temporary_manifest.unlink(missing_ok=True)
        integrity_manifest.unlink(missing_ok=True)
        raise
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"release package verification failed: {exc}", file=os.sys.stderr)
        raise SystemExit(1) from None
