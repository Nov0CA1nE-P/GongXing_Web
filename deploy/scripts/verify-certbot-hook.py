#!/usr/bin/env python3
"""Verify the installed Certbot deploy hook and its containing directory."""

from __future__ import annotations

import argparse
import os
import stat
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hook", required=True, type=Path)
    parser.add_argument("--test-uid", type=int)
    parser.add_argument("--test-gid", type=int)
    args = parser.parse_args()
    expected_uid = expected_gid = 0
    if args.test_uid is not None or args.test_gid is not None:
        if os.getenv("GONGXING_DEPLOY_TEST_MODE") != "1":
            raise RuntimeError("test ownership overrides are disabled")
        if args.test_uid is None or args.test_gid is None:
            raise RuntimeError("both test ownership overrides are required")
        expected_uid, expected_gid = args.test_uid, args.test_gid

    hook = Path(os.path.abspath(os.fspath(args.hook)))
    parent_metadata = hook.parent.lstat()
    if stat.S_ISLNK(parent_metadata.st_mode) or not stat.S_ISDIR(parent_metadata.st_mode):
        raise RuntimeError("hook parent is not a real directory")
    if (parent_metadata.st_uid, parent_metadata.st_gid) != (expected_uid, expected_gid):
        raise RuntimeError("hook parent ownership is invalid")
    if stat.S_IMODE(parent_metadata.st_mode) & 0o022:
        raise RuntimeError("hook parent is writable by an untrusted user")

    metadata = hook.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError("hook is not a regular file")
    if (metadata.st_uid, metadata.st_gid) != (expected_uid, expected_gid):
        raise RuntimeError("hook ownership is invalid")
    mode = stat.S_IMODE(metadata.st_mode)
    if not mode & stat.S_IXUSR or mode & 0o022:
        raise RuntimeError("hook permissions are invalid")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print("certbot hook installation validation failed", file=os.sys.stderr)
        raise SystemExit(1) from None
