from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from evofox_blaze.evidence import read_evidence_file, read_shortcut_journal


class EvidenceTests(unittest.TestCase):
    def test_larger_shortcut_journal_limit_does_not_expand_general_evidence_reads(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "shortcut.jsonl"
            path.write_bytes(b'{"event":"shortcut_config_session"}\n' + b" " * (1024 * 1024))
            with self.assertRaises(ValueError):
                read_evidence_file(path)
            self.assertGreater(len(read_shortcut_journal(path)), 1024 * 1024)
            path.write_bytes(b'{"event":"state_session"}\n' + b" " * (1024 * 1024))
            with self.assertRaises(ValueError):
                read_shortcut_journal(path)
            link = path.with_name("link")
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                read_shortcut_journal(link)

    def test_regular_file_is_read_with_a_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "evidence.json"
            path.write_bytes(b"1234")
            self.assertEqual(read_evidence_file(path, limit=4), b"1234")
            with self.assertRaises(ValueError):
                read_evidence_file(path, limit=3)
            link = path.with_name("link")
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                read_evidence_file(link)
            for limit in (-2, 0, True, 1048577):
                with self.subTest(limit=limit), self.assertRaises(ValueError):
                    read_evidence_file(path, limit=limit)

    def test_device_or_fifo_path_is_refused_without_open(self):
        for mode in (stat.S_IFCHR, stat.S_IFIFO, stat.S_IFDIR):
            with self.subTest(mode=mode), \
                    patch.object(Path, "lstat", return_value=SimpleNamespace(st_mode=mode)), \
                    patch("os.open") as opened:
                with self.assertRaises(ValueError):
                    read_evidence_file(Path("not-a-file"))
                opened.assert_not_called()

    def test_changed_handle_is_closed_without_reading(self):
        with patch.object(Path, "lstat", return_value=SimpleNamespace(st_mode=stat.S_IFREG)), \
                patch("os.open", return_value=42), \
                patch("os.fstat", return_value=SimpleNamespace(st_mode=stat.S_IFCHR)), \
                patch("os.fdopen") as stream, patch("os.close") as closed:
            with self.assertRaises(ValueError):
                read_evidence_file(Path("changed-file"))
            stream.assert_not_called()
            closed.assert_called_once_with(42)


if __name__ == "__main__":
    unittest.main()
