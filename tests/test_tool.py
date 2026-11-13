import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ios_backup  # noqa: E402
import subway_tool as st  # noqa: E402


class EnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.data = {"lastSaved": "now", "currencies": {"2": {"value": 7}}}
        st.KEY_OVERRIDE = None
        st.IV_OVERRIDE = None

    def tearDown(self):
        st.KEY_OVERRIDE = None
        st.IV_OVERRIDE = None

    def test_round_trip_formats(self):
        for fmt in ("aes", "plain", "inline"):
            with self.subTest(fmt=fmt):
                env = st.encode_env(self.data, 3, fmt)
                self.assertEqual(env["_subway_format"], fmt)
                self.assertEqual(st.decrypt_env(env), self.data)

    def test_plain_data_is_inner_json(self):
        env = st.encode_env(self.data, 1, "plain")
        self.assertEqual(json.loads(env["data"]), self.data)
        self.assertNotEqual(env["data"], st.encode_env(self.data, 1, "aes")["data"])

    def test_key_override_hex(self):
        st.KEY_OVERRIDE = "hex:" + (b"0" * 32).hex()
        env = st.encode_env(self.data, 3, "aes")
        st.KEY_OVERRIDE = None
        with self.assertRaises(st.ToolError):
            st.decrypt_env(env)
        st.KEY_OVERRIDE = "hex:" + (b"0" * 32).hex()
        self.assertEqual(st.decrypt_env(env), self.data)


class LocalBackendTests(unittest.TestCase):
    def test_read_write_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = st.LocalDirBackend(tmp)
            backend.write("wallet.json", b"hello")
            self.assertEqual(backend.read("wallet.json"), b"hello")
            self.assertEqual(backend.list_files(), ["wallet.json"])
            self.assertTrue((Path(tmp) / "wallet.json").is_file())


class IosBackupTests(unittest.TestCase):
    def make_backup(self, root):
        backup = Path(root) / "backup"
        backup.mkdir()
        db = backup / "Manifest.db"
        conn = sqlite3.connect(db)
        conn.execute(
            "CREATE TABLE Files (fileID TEXT PRIMARY KEY, domain TEXT, "
            "relativePath TEXT, flags INTEGER, file BLOB)"
        )
        for rel in ("Documents", "Documents/profile"):
            conn.execute(
                "INSERT INTO Files VALUES (?, ?, ?, 2, NULL)",
                (ios_backup.file_id(rel), ios_backup.APP_DOMAIN, rel),
            )
        rel = "Documents/profile/wallet.json"
        fid = ios_backup.file_id(rel)
        conn.execute(
            "INSERT INTO Files VALUES (?, ?, ?, 1, NULL)",
            (fid, ios_backup.APP_DOMAIN, rel),
        )
        (backup / fid[:2]).mkdir()
        self.original = b'{"version":1,"data":"{\\"currencies\\":{\\"2\\":{\\"value\\":1}}}"}'
        (backup / fid[:2] / fid).write_bytes(self.original)
        conn.commit()
        conn.close()
        return backup, fid

    def test_pull_edit_push(self):
        with tempfile.TemporaryDirectory() as tmp:
            backup, fid = self.make_backup(tmp)
            dest, count = ios_backup.pull(backup, Path(tmp) / "work")
            self.assertEqual(count, 1)
            self.assertEqual((dest / "wallet.json").read_bytes(), self.original)

            (dest / "wallet.json").write_text(
                '{"version":1,"data":"{\\"currencies\\":{\\"2\\":{\\"value\\":42}}}"}',
                encoding="utf-8",
            )
            (dest / "top_run.json").write_text('{"version":1,"data":"{}"}', encoding="utf-8")
            undo = Path(tmp) / "undo"
            pushed = ios_backup.push(backup, dest, undo_dir=undo)
            self.assertEqual(pushed, 2)

            new_fid = ios_backup.file_id("Documents/profile/top_run.json")
            self.assertTrue((backup / new_fid[:2] / new_fid).is_file())
            self.assertTrue((undo / "Manifest.db").is_file())
            self.assertTrue((undo / fid[:2] / fid).is_file())

            conn = sqlite3.connect(backup / "Manifest.db")
            rows = conn.execute(
                "SELECT relativePath, flags FROM Files WHERE domain = ? ORDER BY relativePath",
                (ios_backup.APP_DOMAIN,),
            ).fetchall()
            conn.close()
            self.assertIn(("Documents/profile/top_run.json", 1), rows)
            self.assertIn(("Documents/profile/wallet.json", 1), rows)

    def test_resolve_and_describe(self):
        with tempfile.TemporaryDirectory() as tmp:
            backup, _ = self.make_backup(tmp)
            self.assertEqual(ios_backup.resolve_backup(backup), backup)
            self.assertIn("1 profile files", ios_backup.describe(backup))


class BackendSelectionTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("SUBWAY_PROFILE_DIR", None)
        st.select_backend(None)

    def test_env_selects_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["SUBWAY_PROFILE_DIR"] = tmp
            backend = st.select_backend()
            self.assertIsInstance(backend, st.LocalDirBackend)


if __name__ == "__main__":
    unittest.main()
