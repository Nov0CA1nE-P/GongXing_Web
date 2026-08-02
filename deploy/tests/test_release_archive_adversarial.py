from __future__ import annotations

import importlib.util
import io
import tarfile
import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy/scripts/verify_release_archive.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("verify_release_archive", SCRIPT)
archive_verifier = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(archive_verifier)


class ReleaseArchiveBudgetTests(unittest.TestCase):
    def make_archive(self, root: Path, members: list[tuple[str, bytes]]) -> Path:
        archive = root / "fixture.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            for name, payload in members:
                info = tarfile.TarInfo(name)
                info.size = len(payload)
                bundle.addfile(info, io.BytesIO(payload))
        return archive

    def assert_preflight_rejected(self, archive: Path, **limits: int) -> None:
        with patch.multiple(archive_verifier, **limits):
            with self.assertRaises(RuntimeError):
                archive_verifier.preflight_archive(archive)

    def test_rejects_high_compression_ratio(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = self.make_archive(Path(temp), [("large.txt", b"0" * 8192)])
            self.assert_preflight_rejected(archive, MAX_COMPRESSION_RATIO=2)

    def test_rejects_oversized_compressed_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = self.make_archive(Path(temp), [("small.txt", b"x")])
            self.assert_preflight_rejected(archive, MAX_ARCHIVE_BYTES=archive.stat().st_size - 1)

    def test_rejects_oversized_single_member(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = self.make_archive(Path(temp), [("large.txt", b"x" * 33)])
            self.assert_preflight_rejected(archive, MAX_MEMBER_DECLARED_BYTES=32)

    def test_rejects_oversized_total(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = self.make_archive(
                Path(temp), [("one.txt", b"x" * 20), ("two.txt", b"y" * 20)]
            )
            self.assert_preflight_rejected(archive, MAX_TOTAL_DECLARED_BYTES=32)

    def test_rejects_too_many_members(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = self.make_archive(
                Path(temp), [(f"{index}.txt", b"x") for index in range(4)]
            )
            self.assert_preflight_rejected(archive, MAX_MEMBER_COUNT=3)

    def test_stream_copy_rejects_header_actual_size_mismatch(self):
        with self.assertRaises(RuntimeError):
            archive_verifier.bounded_stream_copy(io.BytesIO(b"12345"), io.BytesIO(), 4, 0)

    def test_stream_copy_rejects_actual_total_budget(self):
        with patch.object(archive_verifier, "MAX_ACTUAL_WRITTEN_BYTES", 4):
            with self.assertRaises(RuntimeError):
                archive_verifier.bounded_stream_copy(io.BytesIO(b"12345"), io.BytesIO(), 5, 0)


if __name__ == "__main__":
    unittest.main()
