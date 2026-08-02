#!/usr/bin/env python3
"""Validate production settings without printing secret values."""

from __future__ import annotations

import argparse
import grp
import os
import stat
import sys
from pathlib import Path


def validate_metadata(path: Path, expected_uid: int, expected_gid: int) -> None:
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError("environment file must be a regular file")
    if metadata.st_uid != expected_uid or metadata.st_gid != expected_gid:
        raise RuntimeError("environment file owner or group is invalid")
    if stat.S_IMODE(metadata.st_mode) not in {0o600, 0o640}:
        raise RuntimeError("environment file permissions are invalid")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--release-dir", required=True, type=Path)
    parser.add_argument("--test-mode", action="store_true")
    args = parser.parse_args()
    env_file = args.env_file.resolve(strict=True)
    release_dir = args.release_dir.resolve(strict=True)
    if args.test_mode:
        if os.getenv("GONGXING_DEPLOY_TEST_MODE") != "1":
            raise RuntimeError("test mode is not available")
        expected_uid = os.getuid()
        expected_gid = os.getgid()
    else:
        expected_uid = 0
        expected_gid = grp.getgrnam("gongxing").gr_gid
    validate_metadata(env_file, expected_uid, expected_gid)

    sys.path.insert(0, str(release_dir / "backend"))
    from dotenv import dotenv_values

    values = dotenv_values(env_file)
    for key, value in values.items():
        if value is not None:
            os.environ[key] = value
    import config

    if config.APP_ENV != "production":
        raise RuntimeError("APP_ENV is not production")
    if config.TRUSTED_ORIGINS != ["https://test.novocaine.me"]:
        raise RuntimeError("trusted origins do not match the restricted site")
    if config.CORS_ALLOWED_ORIGINS:
        raise RuntimeError("same-origin production must not enable CORS")
    if config.TRUSTED_PROXY_IPS != ["127.0.0.1"]:
        raise RuntimeError("trusted proxy must be the local Nginx address")
    if not config.ADMIN_COOKIE_SECURE or not config.UVICORN_PROXY_HEADERS:
        raise RuntimeError("production cookie or proxy mode is disabled")

    expected_data = Path("/var/lib/gongxing/data")
    if Path(config.DATABASE_PATH) != expected_data / "site.db":
        raise RuntimeError("database path is outside the persistent data directory")
    data_link = release_dir / "data"
    if not data_link.is_symlink() or data_link.resolve(strict=False) != expected_data:
        raise RuntimeError("release data link is invalid")
    if Path(config.UPLOADS_DIR).resolve(strict=False) != expected_data / "uploads":
        raise RuntimeError("uploads path is outside the persistent data directory")
    if Path(config.COURSEWARE_TEMP_DIR).resolve(strict=False) != expected_data / "tmp" / "courseware":
        raise RuntimeError("courseware temporary path is outside persistent data")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("production configuration validation failed", file=sys.stderr)
        raise SystemExit(1) from None
