import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import toolchain


class ImmutableToolCacheTests(unittest.TestCase):
    def test_download_is_verified_before_cache_write_and_reused_without_network(self):
        payload = b"pinned executable fixture"
        checksum = hashlib.sha256(payload).hexdigest()
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(toolchain, "CACHE", Path(temporary)),
            patch.object(
                toolchain.urllib.request, "urlopen", return_value=io.BytesIO(payload)
            ) as fetch,
        ):
            target = toolchain.download(
                "fixture.bin", "https://example.invalid/pinned", checksum
            )
            self.assertEqual(payload, target.read_bytes())
            fetch.assert_called_once_with("https://example.invalid/pinned", timeout=60)
            self.assertEqual(
                target,
                toolchain.download(
                    "fixture.bin", "https://example.invalid/pinned", checksum
                ),
            )
            self.assertEqual(1, fetch.call_count)

    def test_wrong_download_is_not_cached(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(toolchain, "CACHE", Path(temporary)),
            patch.object(
                toolchain.urllib.request, "urlopen", return_value=io.BytesIO(b"changed")
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                toolchain.download(
                    "fixture.bin", "https://example.invalid/pinned", "0" * 64
                )
            self.assertFalse((Path(temporary) / "fixture.bin").exists())

    def test_changed_cached_tool_fails_without_substitution(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(toolchain, "CACHE", Path(temporary)),
            patch.object(toolchain.urllib.request, "urlopen") as fetch,
        ):
            target = Path(temporary) / "fixture.bin"
            target.write_bytes(b"changed")
            with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                toolchain.download(
                    "fixture.bin", "https://example.invalid/pinned", "0" * 64
                )
            fetch.assert_not_called()
            self.assertEqual(b"changed", target.read_bytes())


if __name__ == "__main__":
    unittest.main()
