import io
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import patch as recipe


class LootPatchTests(unittest.TestCase):
    def setUp(self):
        if "registry_class" not in recipe.JARS[0]:
            self.skipTest("рецепт без registry_class: патч не применяется")

    def upstream_loot(self):
        spec = recipe.JARS[0]
        local = recipe.ROOT / "files" / "mods" / spec["upstream_name"]
        if local.is_file():
            upstream = local.read_bytes()
        else:
            upstream = recipe.github_release_asset(
                spec["github_repo"], spec["github_tag"], spec["upstream_name"]
            )
        actual = recipe.sha512(upstream)
        self.assertEqual(spec["sha512"], actual)
        with zipfile.ZipFile(io.BytesIO(upstream)) as jar:
            return upstream, jar.read(spec["registry_class"])

    def test_selftest_passes(self):
        classpath = recipe.compile_transformer()
        result = recipe.java_tool(
            [
                "java",
                "-Xmx128m",
                "-cp",
                classpath,
                "PatchPortingLib",
                "--self-test",
            ]
        )
        self.assertIn("loot serializers detached", result.stdout.decode())

    def test_real_upstream_detached(self):
        upstream, original = self.upstream_loot()
        self.assertNotIn(b"class_2370", original)
        classpath = recipe.compile_transformer()
        patched = recipe.patch_loot_serializers(original, classpath)
        self.assertNotEqual(patched, original)
        self.assertIn(b"class_2370", patched)
        with self.assertRaises(subprocess.CalledProcessError):
            recipe.patch_loot_serializers(patched, classpath)
        recipe.assert_no_content_id_change(
            "fixture.jar",
            upstream,
            self.repack(upstream, patched),
            set(),
            {recipe.JARS[0]["registry_class"]},
        )

    def repack(self, upstream, patched_class):
        import os

        spec = recipe.JARS[0]
        data = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(upstream)) as source:
            with zipfile.ZipFile(data, "w") as target:
                for info in source.infolist():
                    payload = source.read(info.filename)
                    if info.filename == spec["registry_class"]:
                        payload = patched_class
                    target.writestr(info, payload)
        fd, tmppath = tempfile.mkstemp(suffix=".jar")
        os.close(fd)
        out = Path(tmppath)
        out.write_bytes(data.getvalue())
        return out

    def content_jar(self, entries):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            for name, payload in entries.items():
                archive.writestr(name, payload)
        return data.getvalue()

    def test_changed_unlisted_content_fails(self):
        upstream = self.content_jar({"a": b"1"})
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "out.jar"
            out.write_bytes(self.content_jar({"a": b"2"}))
            with self.assertRaisesRegex(SystemExit, "изменилась запись"):
                recipe.assert_no_content_id_change(
                    "fixture.jar", upstream, out, set(), set()
                )

    def test_missing_content_fails(self):
        upstream = self.content_jar({"a": b"1", "gone": b"x"})
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "out.jar"
            out.write_bytes(self.content_jar({"a": b"1"}))
            with self.assertRaisesRegex(SystemExit, "пропала запись"):
                recipe.assert_no_content_id_change(
                    "fixture.jar", upstream, out, set(), set()
                )


if __name__ == "__main__":
    unittest.main()
