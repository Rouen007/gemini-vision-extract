from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "gemini_vision.py"
SPEC = importlib.util.spec_from_file_location("gemini_vision", SCRIPT)
gemini_vision = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(gemini_vision)


class GeminiVisionTests(unittest.TestCase):
    def test_safe_error_redacts_key_values(self):
        message = gemini_vision.safe_error(RuntimeError("request secret-key failed"), "secret-key")
        self.assertEqual(message, "request [REDACTED] failed")

    def test_conflicting_environment_keys_fail_closed(self):
        with self.assertRaises(RuntimeError):
            gemini_vision.resolve_api_key({"GEMINI_API_KEY": "a", "GOOGLE_API_KEY": "b"})

    def test_environment_key_source_never_contains_key(self):
        key, source = gemini_vision.resolve_api_key({"GEMINI_API_KEY": "secret"})
        self.assertEqual(key, "secret")
        self.assertEqual(source, "GEMINI_API_KEY")
        self.assertNotIn(key, source)

    def test_prepare_requires_absolute_unique_image_paths(self):
        with self.assertRaises(ValueError):
            gemini_vision.prepare_items([{"id": "a", "path": "relative.png"}])

    def test_batching_caps_items_and_bytes(self):
        items = [{"id": str(i), "path": Path(f"/{i}.png"), "_bytes": n}
                 for i, n in enumerate([7, 4, 4, 1])]
        batches = gemini_vision.make_batches(items, max_raw_bytes=8, max_items=2)
        self.assertEqual([[x["id"] for x in b] for b in batches], [["0"], ["1", "2"], ["3"]])

    def test_extract_envelope_keeps_batch_item_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for name in ("a.png", "b.png", "c.png"):
                path = Path(tmp) / name
                path.write_bytes(b"png")
                paths.append(path)
            items = [{"id": p.stem, "path": str(p)} for p in paths]
            with mock.patch.object(gemini_vision, "_mime_type", return_value="image/png"), \
                 mock.patch.object(gemini_vision, "_call_with_retry", side_effect=[{"x": 1}, {"x": 2}]):
                envelope = gemini_vision.extract_items(
                    items, "prompt", {"type": "object"}, api_key="secret",
                    max_items_per_batch=2, concurrency=1,
                )
        self.assertEqual(envelope["input_count"], 3)
        self.assertEqual([b["item_ids"] for b in envelope["batches"]], [["a", "b"], ["c"]])

    def test_cli_check_key_needs_no_request(self):
        with mock.patch.object(gemini_vision, "resolve_api_key", return_value=("secret", "test")), \
             mock.patch.object(gemini_vision, "check_api_key", return_value="models/test"), \
             mock.patch.object(gemini_vision.sys, "argv", ["gemini_vision.py", "--check-key"]):
            self.assertEqual(gemini_vision.main(), 0)


if __name__ == "__main__":
    unittest.main()
