import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from build_language import build, flatten, normalize, parse_json


class LanguageBuildTests(unittest.TestCase):
    def test_case_sensitive_namespaces(self):
        for label in ("Token", "Light", "Sound", "Error", "Template", "Vision", "Warning"):
            namespace = label.upper()
            with self.subTest(label=label):
                result = normalize({label: "独立标签", f"{namespace}.Title": "标题"})
                self.assertEqual(result[label], "独立标签")
                self.assertEqual(result[namespace]["Title"], "标题")

    def test_mixed_nested_and_dotted_keys_in_all_orders(self):
        entries = [
            ("TOKEN.FIELDS", {"name.label": "名称"}),
            ("TOKEN", {"FIELDS": {"actorLink": {"label": "关联角色"}}}),
            ("TOKEN.TitlePrototype", "指示物模板"),
        ]
        expected = {"TOKEN": {"FIELDS": {"name": {"label": "名称"},
                                         "actorLink": {"label": "关联角色"}},
                              "TitlePrototype": "指示物模板"}}
        for permutation in itertools.permutations(entries):
            self.assertEqual(normalize(dict(permutation)), expected)

    def test_scalar_object_conflict_fails_in_both_orders(self):
        entries = [("EDITOR.Font", "字体"), ("EDITOR.Font.Title", "字体")]
        for permutation in itertools.permutations(entries):
            with self.assertRaisesRegex(ValueError, r"EDITOR.Font"):
                normalize(dict(permutation))

    def test_duplicate_raw_keys_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            parse_json('{"TOKEN":{"Title":"a","Title":"b"}}')

    def test_duplicate_expanded_paths_are_rejected_even_if_values_match(self):
        with self.assertRaisesRegex(ValueError, "Duplicate translation path"):
            normalize({"A.B": "same", "A": {"B": "same"}})

    def test_arrays_placeholders_markup_and_unicode_survive(self):
        source = {"X.Messages": ["你好 {name}", "<b>{count}</b>", {"A.B": "保留数组内部内容"}],
                  "X.Empty": {}, "X.False": False, "X.Null": None, "X.Zero": 0}
        self.assertEqual(flatten(normalize(source)), flatten(source))

    def test_leaf_collections_cannot_become_branches(self):
        for value in ([], {}):
            with self.assertRaisesRegex(ValueError, "Leaf/object conflict"):
                normalize({"X": value, "X.Child": "label"})

    def test_empty_segments_and_nonstandard_json_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Empty path segment"):
            normalize({"A..B": "bad"})
        with self.assertRaisesRegex(ValueError, "Invalid JSON constant"):
            parse_json('{"A": NaN}')

    def test_in_place_build_round_trip_and_idempotence(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "cn.json"
            target.write_text(json.dumps({"Token": "指示物", "TOKEN.FIELDS.name.label": "名称"}), encoding="utf-8")
            self.assertEqual(build(target, target), 2)
            first = target.read_bytes()
            self.assertEqual(build(target, target), 2)
            self.assertEqual(first, target.read_bytes())

    def test_validation_only_does_not_rewrite_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "cn.json"
            original = b'{"A.B":"label"}'
            source.write_bytes(original)
            self.assertEqual(build(source), 1)
            self.assertEqual(source.read_bytes(), original)

    def test_failed_cli_does_not_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "cn.json"
            original = b'{"EDITOR.Font":"old", "EDITOR.Font.Title":"new"}'
            source.write_bytes(original)
            result = subprocess.run([sys.executable, str(Path(__file__).with_name("build_language.py")),
                                     str(source), str(source)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("EDITOR.Font", result.stderr)
            self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
