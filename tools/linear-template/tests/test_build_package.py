import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build_package


class BuildPackageTests(unittest.TestCase):
    def test_bundle_is_standalone_and_all_checksums_match(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp)
            archive_path = build_package.build(destination / "resource.zip")
            with zipfile.ZipFile(archive_path) as archive:
                self.assertIsNone(archive.testzip())
                archive.extractall(destination / "extracted")
            package = destination / "extracted/linear-fedramp-class-a"
            for line in (package / "SHA256SUMS").read_text().splitlines():
                expected, filename = line.split("  ", 1)
                self.assertEqual(hashlib.sha256((package / filename).read_bytes()).hexdigest(), expected)
            readme = (package / "README.md").read_text()
            self.assertIn("python3 import_template.py preview", readme)
            self.assertNotIn("tools/linear-template/", readme)
            self.assertNotIn("resources/fedramp/", readme)
            result = subprocess.check_output(
                [sys.executable, str(package / "import_template.py"), "preview", "--json"],
                cwd=destination, text=True,
            )
            self.assertEqual((json.loads(result)["issues"], json.loads(result)["sub_issues"]), (51, 43))

    def test_unchanged_inputs_produce_identical_archives(self):
        with tempfile.TemporaryDirectory() as temp:
            first = build_package.build(Path(temp) / "first.zip").read_bytes()
            second = build_package.build(Path(temp) / "second.zip").read_bytes()
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
