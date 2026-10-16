import copy
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import import_template as importer


class PortableTemplateTests(unittest.TestCase):
    def setUp(self):
        self.data = importer.load_package(importer.DEFAULT_PACKAGE)

    def test_export_has_complete_milestone_and_parent_mapping(self):
        self.assertEqual(len(self.data["milestones"]), 7)
        self.assertEqual(len(self.data["issues"]), 51)
        groups = {}
        for issue in self.data["issues"]:
            if issue["parent"]:
                groups[issue["parent"]] = groups.get(issue["parent"], 0) + 1
        self.assertEqual(sorted(groups.values()), [9, 11, 23])
        counts = importer.Counter(i["milestone"] for i in self.data["issues"])
        self.assertEqual([counts[m["key"]] for m in self.data["milestones"]], [4, 8, 8, 9, 6, 6, 10])

    def test_export_retains_checkboxes_table_and_public_links(self):
        html = "".join(i["description_html"] for i in self.data["issues"])
        self.assertEqual(html.count('data-type="todo_item"'), 209)
        self.assertEqual(html.count("<table>"), 1)
        self.assertIn("https://www.fedramp.gov/", html)
        for fragment in ("linear.app", "STE-", "assigneeId", "teamId", "Cycle 1"):
            self.assertNotIn(fragment, json.dumps(self.data))

    def test_plan_imports_each_issue_once_with_parent_before_children(self):
        seen = set()
        for issue in importer.ordered_issues(self.data):
            if issue["parent"]:
                self.assertIn(issue["parent"], seen)
            self.assertNotIn(issue["key"], seen)
            seen.add(issue["key"])
        self.assertEqual(len(seen), 51)

    def test_invalid_graphs_rejected_before_browser_start(self):
        for mutation in ("orphan_parent", "self_parent", "cycle", "orphan_milestone", "duplicate_key", "duplicate_title"):
            with self.subTest(mutation=mutation):
                data = copy.deepcopy(self.data)
                first, second = data["issues"][:2]
                if mutation == "orphan_parent":
                    first["parent"] = "missing"
                elif mutation == "self_parent":
                    first["parent"] = first["key"]
                elif mutation == "cycle":
                    first["parent"], second["parent"] = second["key"], first["key"]
                elif mutation == "orphan_milestone":
                    first["milestone"] = "missing"
                elif mutation == "duplicate_key":
                    second["key"] = first["key"]
                else:
                    second["title"] = first["title"]
                with self.assertRaises(importer.PackageError):
                    importer.validate_package(data)

    def test_unsupported_fields_and_version_are_rejected(self):
        for mutate in (
            lambda d: d.update(version=2),
            lambda d: d.update(version=True),
            lambda d: d["project"].update(teamId="source-id"),
            lambda d: d["issues"][0].update(assignee="source-user"),
            lambda d: d["issues"][0].update(priority=1),
        ):
            data = copy.deepcopy(self.data)
            mutate(data)
            with self.assertRaises(importer.PackageError):
                importer.validate_package(data)

    def test_unsafe_or_private_html_is_rejected(self):
        for html in (
            '<script>alert(1)</script>', '<img src="https://uploads.linear.app/private">',
            '<p onclick="alert(1)">Text</p>', '<a href="javascript:alert(1)">link</a>',
            '<a href="https://linear.app/private/issue/SEC-1">private</a>',
            '<a href="https://user:password@example.com">credentials</a>',
            '<a href="//example.com">scheme relative</a>',
        ):
            data = copy.deepcopy(self.data)
            data["issues"][0]["description_html"] = html
            with self.subTest(html=html), self.assertRaises(importer.PackageError):
                importer.validate_package(data)

    def test_preview_never_calls_browser_import(self):
        with patch.object(importer, "apply_import", side_effect=AssertionError("Browser must not start")), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(importer.main(["preview", "--json"]), 0)
            self.assertEqual(importer.main(["import", "--workspace", "acme", "--team", "SEC", "--json"]), 0)

    def test_apply_requires_destination(self):
        with patch.object(importer, "apply_import", side_effect=AssertionError("Browser must not start")), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(importer.main(["import", "--apply"]), 1)
            self.assertEqual(importer.main(["import", "--apply", "--workspace", "https://linear.app/acme", "--team", "SEC"]), 1)

    def test_existing_receipt_stops_apply_before_dependency_import(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            (out / "receipt.json").write_text('{}')
            args = importer.parser().parse_args(["import", "--workspace", "acme", "--team", "SEC", "--apply", "--output-dir", temp])
            with self.assertRaisesRegex(importer.PackageError, "already exists"):
                importer.apply_import(self.data, args)

    def test_plan_maps_destination_without_source_ids(self):
        args = importer.parser().parse_args(["import", "--workspace", "other-org", "--team", "ENG", "--name", "My template"])
        result = importer.plan(self.data, args)
        self.assertEqual((result["name"], result["workspace"], result["team"]), ("My template", "other-org", "ENG"))
        self.assertEqual(result["sub_issues"], 43)
        self.assertEqual(result["scope"], "workspace")

    def test_fingerprint_detects_content_edits(self):
        modified = copy.deepcopy(self.data)
        modified["issues"][0]["title"] += " changed"
        self.assertNotEqual(importer.fingerprint(modified), importer.fingerprint(self.data))

    def test_text_roundtrip_preserves_inline_and_block_content(self):
        self.assertEqual(importer.html_text('<h2>Checks</h2><p>Use <strong>secure</strong> accounts.</p><ul><li><p>A &amp; B</p></li></ul>'),
                         "Checks Use secure accounts. A & B")

    def test_oversized_and_malformed_packages(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "template.json"
            for content in ("x" * 2_000_001, "{broken"):
                path.write_text(content)
                with self.assertRaises((ValueError, importer.PackageError)):
                    importer.load_package(path)

    def test_help_and_offline_preview_work_as_standalone_script(self):
        script = Path(importer.__file__)
        for args in ([], ["--help"], ["import", "--help"], ["preview", "--json"]):
            run = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
        preview = json.loads(subprocess.check_output([sys.executable, str(script), "preview", "--json"], text=True))
        self.assertEqual((preview["issues"], len(preview["milestones"])), (51, 7))

    def test_default_resource_is_independent_of_working_directory(self):
        with tempfile.TemporaryDirectory() as unrelated:
            output = subprocess.check_output(
                [sys.executable, str(Path(importer.__file__).resolve()), "preview", "--json"],
                cwd=unrelated, text=True,
            )
        self.assertEqual(json.loads(output)["issues"], 51)


if __name__ == "__main__":
    unittest.main()
