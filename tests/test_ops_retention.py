"""Backup-only fixtures: licensed third-party body expiry must not be reversible."""
import json
import shutil
import sqlite3
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest import mock
from ops import backup, runtime
from server.modules import knowledge, research
from server.platform.store import Store

ROOT = Path(__file__).resolve().parents[1]


class BackupRetentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="world-insight-ops-retention-fixture-")
        self.base = Path(self.tmp.name)
        self.config = runtime.prepare_config(ROOT, self.base / "data", 8874)
        self.config["backup_dir"] = self.base / "backups"
        self.store = Store(self.config["db_path"])
        runtime.atomic_json(self.config["data_dir"] / "instance.json", {"instance_id": str(uuid.uuid4()), "format": 1})
        (self.config["data_dir"] / "attachments").mkdir(exist_ok=True)
        self.store.create("source", {"name": "[fixture] limited content provider", "retention_days": 30}, record_id="fixture-limited")
        self.store.create("source", {"name": "[fixture] no registered term", "retention_days": None}, record_id="fixture-unlimited")
        self.topic = research.handle(self.store, "POST", ["topics"], {"question": "[fixture] content rights retention"}, {})

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def material(self, source="fixture-limited", suffix="limited"):
        row = knowledge.ingest(self.store, {"source_id": source, "title": "[fixture] retained metadata", "url": "https://fixture.example/" + suffix, "topic_id": self.topic["id"], "excerpt": "ORIGINAL_BODY_SECRET_" + suffix, "translation": "ORIGINAL_TRANSLATION_" + suffix, "notes": "USER_NOTE_KEEP_" + suffix, "rights": {"store": True, "display": True, "export": True}, "is_fixture": True})
        old_ref = row["version_id"]
        revised = knowledge.handle(self.store, "PATCH", ["evidence", row["id"]], {"expected_version": row["version"], "excerpt": "REVISED_BODY_SECRET_" + suffix, "translation": "REVISED_TRANSLATION_" + suffix, "notes": "USER_NOTE_KEEP_" + suffix, "change_reason": "explicit fixture revision"}, {})
        judgment = research.handle(self.store, "POST", ["judgments"], {"topic_id": self.topic["id"], "conclusion": "[fixture] user analysis remains", "evidence_version_ids": [old_ref], "is_fixture": True}, {})
        return revised, old_ref, judgment

    def legacy_package(self, target):
        """Construct an authentic old format-1 package without retention sanitization."""
        with tempfile.TemporaryDirectory(dir=self.base) as tmp:
            stage = Path(tmp)
            dest = sqlite3.connect(stage / backup.DB_NAME)
            self.store.db.backup(dest)
            dest.execute("PRAGMA journal_mode=DELETE")
            dest.close()
            shutil.copyfile(self.config["data_dir"] / "instance.json", stage / "instance.json")
            runtime.atomic_json(stage / "non-sensitive-config.json", {"port": 8874})
            entries = [{"path": path.name, "size": path.stat().st_size, "sha256": backup.sha256(path)} for path in sorted(stage.iterdir())]
            manifest = {"format": 1, "state": "complete", "database": backup.inspect_database(stage / backup.DB_NAME), "instance_id": runtime.read_json(stage / "instance.json")["instance_id"], "files": entries}
            with zipfile.ZipFile(target, "w") as archive:
                for entry in entries:
                    archive.write(stage / entry["path"], entry["path"])
                archive.writestr("manifest.json", json.dumps(manifest))
        return target

    def assert_redacted(self, path, row, old_ref, judgment, suffix="limited"):
        with sqlite3.connect(path) as db:
            records = [json.loads(raw) for (raw,) in db.execute("SELECT data FROM versions WHERE kind='evidence' AND id=? ORDER BY version", (row["id"],))]
            self.assertEqual(len(records), 2)
            self.assertTrue(all(record.get("excerpt") == "" and record.get("translation") == "" and record.get("content_fingerprint") is None for record in records))
            self.assertTrue(all(record["notes"] == "USER_NOTE_KEEP_" + suffix for record in records))
            saved = json.loads(db.execute("SELECT data FROM records WHERE kind='judgment' AND id=?", (judgment["id"],)).fetchone()[0])
            self.assertEqual(saved["evidence_version_ids"], [old_ref])
        raw = Path(path).read_bytes()
        self.assertNotIn(("ORIGINAL_BODY_SECRET_" + suffix).encode(), raw)
        self.assertNotIn(("REVISED_BODY_SECRET_" + suffix).encode(), raw)
        self.assertNotIn(("ORIGINAL_TRANSLATION_" + suffix).encode(), raw)
        self.assertNotIn(("REVISED_TRANSLATION_" + suffix).encode(), raw)
        self.assertEqual(backup.inspect_database(path)["integrity"], "ok")

    def test_bounded_source_all_versions_omitted_in_archive_not_live_database(self):
        row, old_ref, judgment = self.material()
        result = backup.create_backup(self.config)
        self.assertEqual(result["manifest"]["content_policy"]["omitted_evidence_ids"], [row["id"]])
        self.assertEqual(result["manifest"]["content_policy"]["versions_with_content_removed"], 2)
        self.assertEqual(self.store.version(old_ref)["excerpt"], "ORIGINAL_BODY_SECRET_limited")
        with zipfile.ZipFile(result["package"]) as archive:
            raw_db = self.base / "unpacked-raw.sqlite"
            raw_db.write_bytes(archive.read(backup.DB_NAME))
            manifest = json.loads(archive.read("manifest.json"))
            entry = next(item for item in manifest["files"] if item["path"] == backup.DB_NAME)
            self.assertEqual(backup.sha256(raw_db), entry["sha256"])
            self.assert_redacted(raw_db, row, old_ref, judgment)

    def test_default_unbounded_source_preserves_all_legal_content(self):
        row, old_ref, judgment = self.material("fixture-unlimited", "unlimited")
        result = backup.create_backup(self.config)
        self.assertEqual(result["manifest"]["content_policy"]["omitted_evidence_count"], 0)
        stage = self.base / "validated"
        backup.unpack_verified(result["package"], stage)
        with sqlite3.connect(stage / backup.DB_NAME) as db:
            records = [json.loads(raw) for (raw,) in db.execute("SELECT data FROM versions WHERE kind='evidence'")]
            self.assertEqual(records[0]["excerpt"], "ORIGINAL_BODY_SECRET_unlimited")
            self.assertEqual(records[1]["translation"], "REVISED_TRANSLATION_unlimited")
            self.assertEqual(records[1]["notes"], "USER_NOTE_KEEP_unlimited")

    def test_legacy_bounded_package_is_sanitized_before_restore(self):
        row, old_ref, judgment = self.material()
        package = self.legacy_package(self.base / "legacy.wibackup")
        destination = runtime.prepare_config(ROOT, self.base / "restored", 8875)
        preview = backup.restore_backup(destination, package)
        self.assertEqual(preview["content_policy"]["omitted_evidence_count"], 1)
        self.assertFalse(destination["db_path"].exists())
        result = backup.restore_backup(destination, package, apply=True)
        self.assertEqual(result["status"], "restored")
        self.assert_redacted(destination["db_path"], row, old_ref, judgment)

    def test_current_stricter_policy_prevents_old_unbounded_package_body_revival(self):
        row, old_ref, judgment = self.material("fixture-unlimited", "policy-change")
        package = self.legacy_package(self.base / "before-policy.wibackup")
        source = self.store.get("source", "fixture-unlimited")
        self.store.update("source", source["id"], {"retention_days": 7}, source["version"])
        self.store.close()
        result = backup.restore_backup(self.config, package, apply=True, replace=True)
        self.assertEqual(result["content_policy"]["omitted_evidence_count"], 1)
        self.assert_redacted(Path(result["restore_point"]) / backup.DB_NAME, row, old_ref, judgment, "policy-change")
        self.assert_redacted(self.config["db_path"], row, old_ref, judgment, "policy-change")

    def test_standalone_migration_snapshot_api_removes_expired_body_bytes(self):
        row, old_ref, judgment = self.material()
        target = self.base / "migration-before.sqlite"
        destination = sqlite3.connect(target)
        self.store.db.backup(destination)
        destination.close()
        report = backup.sanitize_snapshot(target, policy_source=self.config["db_path"])
        self.assertEqual(report["omitted_evidence_count"], 1)
        self.assert_redacted(target, row, old_ref, judgment)
        with self.assertRaises(runtime.OpsError):
            backup.sanitize_snapshot(self.config["db_path"], policy_source=self.config["db_path"])

    def test_invalid_source_term_blocks_backup_without_replacing_valid_package(self):
        self.material()
        valid = backup.create_backup(self.config)["package"]
        source = self.store.get("source", "fixture-limited")
        self.store.update("source", source["id"], {"retention_days": "unknown"}, source["version"])
        with self.assertRaises(runtime.OpsError):
            backup.create_backup(self.config)
        self.assertEqual(backup.validate_backup(valid)["state"], "complete")


if __name__ == "__main__":
    unittest.main()
