import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.new_low_raw_archive import archive, endpoints, verify


class RawArchiveTest(unittest.TestCase):
    def test_import_keeps_empty_action_response_unconfirmed_and_detects_tampering(self):
        day = "2026-11-23"
        raw = b'{"stat":"no data"}'
        source = {"ex_right": {"url": endpoints(day)["ex_right"],
                              "sha256": hashlib.sha256(raw).hexdigest()}}
        with tempfile.TemporaryDirectory() as root:
            args = (day, Path(root), lambda _name, _url: raw)
            capture = archive(*args, source_date=day, mode="archived_import", provenance=source)
            retry = archive(*args, source_date=day, mode="archived_import", provenance=source)
            self.assertNotEqual(capture, retry)
            manifest = verify(capture)
            self.assertEqual(manifest["observations"]["ex_right"]["status"], "unconfirmed_scope")
            self.assertEqual(manifest["sources"]["calendar"]["status"], "unavailable")
            self.assertFalse(manifest["action_coverage_reviewed"])
            self.assertFalse(manifest["score_eligible"])
            self.assertEqual(sorted(p.name for p in capture.iterdir()), ["ex_right.raw", "manifest.json"])
            (capture / "ex_right.raw").write_bytes(b'{"stat":"changed"}')
            with self.assertRaisesRegex(ValueError, "hash or size"):
                verify(capture)
            self.assertEqual(verify(retry)["session"], day)

    def test_import_never_saves_a_hash_mismatch_or_marks_missing_calendar_as_closed(self):
        day = "2026-11-23"
        archived_calendar = json.dumps(dict(stat="OK", date="20261101",
                                            data=[["115/11/20"]])).encode()
        source = {
            name: dict(url=endpoints(day)[name], sha256=sha)
            for name, sha in (("quotes", "0" * 64),
                              ("calendar", hashlib.sha256(archived_calendar).hexdigest()))
        }
        with tempfile.TemporaryDirectory() as root:
            capture = archive(day, Path(root), lambda _name, _url: archived_calendar,
                              source_date=day, mode="archived_import", provenance=source)
            manifest = verify(capture)
            self.assertEqual(manifest["observations"]["calendar"]["status"], "not_yet_observed")
            self.assertEqual(manifest["sources"]["quotes"]["status"], "unavailable")
            self.assertFalse((capture / "quotes.raw").exists())
