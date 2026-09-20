"""Actual macOS processes + SQLite; test repositories/data are isolated and marked fixtures."""
import json
import os
import signal
import sys
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
import unittest
import urllib.request
import zipfile
from pathlib import Path
from unittest import mock
from ops import backup, runtime, update
from server.platform.store import Store

ROOT = Path(__file__).resolve().parents[1]


class OperationsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suite = tempfile.TemporaryDirectory(prefix="world-insight-ops-fixture-")
        cls.base = Path(cls.suite.name)
        cls.repo = cls.base / "中文 项目 code"
        shutil.copytree(ROOT, cls.repo, ignore=shutil.ignore_patterns(".git", ".worktrees", "__pycache__", ".env", ".test-data", "*.pyc"))
        def git(*args):
            return subprocess.run(["git", *args], cwd=cls.repo, check=True, capture_output=True, text=True).stdout.strip()
        cls.git = staticmethod(git)
        git("init", "-b", "main")
        git("config", "user.name", "World Insight Fixture")
        git("config", "user.email", "fixture@localhost")
        git("add", ".")
        git("commit", "-m", "Explicit isolated operations fixture baseline")
        cls.old_commit = git("rev-parse", "HEAD")
        (cls.repo / "VERSION").write_text("0.1.1-fixture\n")
        git("add", "VERSION")
        git("commit", "-m", "Fixture valid version")
        cls.good_commit = git("rev-parse", "HEAD")
        git("switch", "--detach", cls.old_commit)
        migrations = cls.repo / "server/platform/migrations.py"
        migrations.write_text(migrations.read_text().replace("SCHEMA_VERSION = 1", "SCHEMA_VERSION = 2") + '\nMIGRATIONS.append((2, ["CREATE TABLE fixture_migration(value TEXT)", "THIS IS INVALID SQL"]))\n')
        (cls.repo / "VERSION").write_text("0.2.0-failed-migration-fixture\n")
        git("add", "server/platform/migrations.py", "VERSION")
        git("commit", "-m", "Fixture intentionally failing migration")
        cls.bad_migration_commit = git("rev-parse", "HEAD")
        git("switch", "--detach", cls.old_commit)
        app = cls.repo / "server/app.py"
        app.write_text(app.read_text().replace("{'status':'ok','app':'world-insight'", "{'status':'fixture_unhealthy','app':'world-insight'", 1))
        (cls.repo / "VERSION").write_text("0.1.2-failed-health-fixture\n")
        git("add", "server/app.py", "VERSION")
        git("commit", "-m", "Fixture intentionally failing target health")
        cls.bad_health_commit = git("rev-parse", "HEAD")
        git("switch", "--detach", cls.old_commit)
        migrations = cls.repo / "server/platform/migrations.py"
        migrations.write_text(migrations.read_text().replace("SCHEMA_VERSION = 1", "SCHEMA_VERSION = 2") + '\nMIGRATIONS.append((2, ["CREATE TABLE fixture_success(value TEXT)"]))\n')
        (cls.repo / "VERSION").write_text("0.2.0-good-migration-fixture\n")
        git("add", "server/platform/migrations.py", "VERSION")
        git("commit", "-m", "Fixture valid schema migration")
        cls.good_migration_commit = git("rev-parse", "HEAD")
        git("switch", "--detach", cls.old_commit)
        migrations = cls.repo / "server/platform/migrations.py"
        migrations.write_text(migrations.read_text().replace("def migrate(db, path=None):", 'def migrate(db, path=None):\n    if path:\n        Path(path).parent.joinpath("fixture-migration-entered").write_text("Explicit fixture pause before migration")\n        import time\n        time.sleep(30)'))
        (cls.repo / "VERSION").write_text("0.2.0-interrupted-fixture\n")
        git("add", "server/platform/migrations.py", "VERSION")
        git("commit", "-m", "Fixture controlled migration interruption point")
        cls.interrupt_commit = git("rev-parse", "HEAD")
        git("switch", "--detach", cls.old_commit)


    @classmethod
    def tearDownClass(cls):
        cls.suite.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="数据 夹具-", dir=self.base)
        self.data = Path(self.directory.name) / "研究 数据"
        self.config = runtime.prepare_config(self.repo, self.data, 8874)
        self.config["backup_dir"] = Path(self.directory.name) / "备份 包"
        self.config["no_scheduler"] = True
        self.extra_configs = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for config in [self.config] + self.extra_configs:
            try:
                runtime.stop(config)
            except runtime.OpsError:
                pass
        self.directory.cleanup()

    def api(self, method, path, value=None, config=None):
        config = config or self.config
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        request = urllib.request.Request(f'http://127.0.0.1:{config["port"]}/api/{path}', data=json.dumps(value).encode() if value is not None else None, method=method, headers={"Content-Type": "application/json"})
        with opener.open(request, timeout=3) as response:
            return json.load(response)

    def start_fixture(self):
        started = runtime.start(self.config, initialize=True, open_browser=False)
        topic = self.api("POST", "topics", {"question": "[明确测试夹具] Mac持久化验收", "is_fixture": True})
        evidence = self.api("POST", "evidence", {"title": "[测试夹具] 原始通告", "url": "https://fixture.example/ops", "topic_id": topic["id"], "is_fixture": True})
        judgment = self.api("POST", "judgments", {"topic_id": topic["id"], "conclusion": "[夹具] 尚无执行证据", "evidence_version_ids": [evidence["version_id"]], "is_fixture": True})
        (self.data / "attachments" / "允许保存的夹具.txt").write_text("附件夹具：用于恢复校验，不是真实国际局势材料。")
        return started, topic, evidence, judgment

    def test_real_start_reuse_stop_and_restart_edit(self):
        first, topic, _, _ = self.start_fixture()
        second = runtime.start(self.config, open_browser=False)
        self.assertEqual(first["pid"], second["pid"])
        self.assertEqual(second["status"], "reused")
        self.assertEqual(runtime.stop(self.config)["status"], "stopped")
        self.assertTrue(self.config["db_path"].exists())
        runtime.start(self.config, open_browser=False)
        edited = self.api("PATCH", "topics/" + topic["id"], {"expected_version": 1, "rationale": "重启后继续保存"})
        self.assertEqual(edited["version"], 2)

    def test_local_preflight_port_occupied_and_missing_data_identity(self):
        report = runtime.check(self.config)
        self.assertFalse(report["ok"])
        with socket.socket() as occupied:
            occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            occupied.bind(("127.0.0.1", 8874))
            occupied.listen()
            report = runtime.check(self.config, initialize=True)
            self.assertFalse(report["ok"])
            self.assertTrue(any(row["name"] == "port" and row["level"] == "block" for row in report["checks"]))
            with self.assertRaises(runtime.OpsError):
                runtime.start(self.config, initialize=True, open_browser=False)
            self.assertIsNotNone(occupied.getsockname())
        self.assertFalse(self.config["db_path"].exists())

    def test_running_backup_and_empty_restore_continue_edit(self):
        _, topic, evidence, judgment = self.start_fixture()
        dashboard = self.api("GET", "dashboard?window=24h")
        self.api("POST", "changes/read", {"snapshot_at": dashboard["snapshot_at"], "items": [{"id": row["id"], "version": row["version"]} for row in dashboard["items"]]})
        package = backup.create_backup(self.config)["package"]
        manifest = backup.validate_backup(package, 1)
        self.assertEqual(manifest["database"]["counts"]["topic"], 1)
        self.assertGreater(manifest["database"]["counts"].get("read_state", 0), 0)
        self.assertFalse(any(".env" in row["path"] for row in manifest["files"]))
        restored = runtime.prepare_config(self.repo, Path(self.directory.name) / "恢复 空实例", 8875)
        restored["no_scheduler"] = True
        self.extra_configs.append(restored)
        self.assertEqual(backup.restore_backup(restored, package)["status"], "preview")
        self.assertFalse(restored["db_path"].exists())
        result = backup.restore_backup(restored, package, apply=True)
        self.assertEqual(result["status"], "restored")
        runtime.start(restored, open_browser=False)
        saved = self.api("PATCH", "judgments/" + judgment["id"], {"expected_version": 1, "conclusion": "[夹具] 从备份恢复后编辑", "change_reason": "实际恢复验收"}, config=restored)
        self.assertEqual(saved["version"], 2)
        self.assertEqual(self.api("GET", f'evidence/{evidence["id"]}/history', config=restored)["items"][0]["version"], 1)
        self.assertTrue((restored["data_dir"] / "attachments" / "允许保存的夹具.txt").exists())

    def test_corrupt_and_incompatible_backup_never_replace_existing(self):
        self.start_fixture()
        valid = backup.create_backup(self.config)["package"]
        runtime.stop(self.config)
        fingerprint = update.database_fingerprint(self.config["db_path"])
        corrupt = Path(self.directory.name) / "broken.wibackup"
        corrupt.write_bytes(b"not a backup")
        with self.assertRaises(runtime.OpsError):
            backup.restore_backup(self.config, corrupt, apply=True, replace=True)
        with self.assertRaises(runtime.OpsError):
            backup.validate_backup(valid, maximum_schema=0)
        with self.assertRaises(runtime.OpsError):
            backup.restore_backup(self.config, valid, apply=True)
        self.assertEqual(update.database_fingerprint(self.config["db_path"]), fingerprint)
        restored = backup.restore_backup(self.config, valid, apply=True, replace=True)
        self.assertTrue(Path(restored["recovery_package"]).exists())
        self.assertTrue((Path(restored["restore_point"]) / backup.DB_NAME).exists())

    def test_backup_disk_failure_keeps_previous_valid_package(self):
        self.start_fixture()
        valid = backup.create_backup(self.config)["package"]
        target = Path(self.directory.name) / "disk-full.wibackup"
        with mock.patch.object(backup, "_snapshot", side_effect=OSError("fixture disk full")):
            with self.assertRaises(OSError):
                backup.create_backup(self.config, target)
        self.assertTrue(Path(valid).exists())
        self.assertFalse(target.exists())
        self.assertTrue(target.with_name(target.name + ".partial").exists())
        self.assertEqual(backup.validate_backup(valid)["state"], "complete")

    def test_dirty_and_untracked_update_protection(self):
        self.start_fixture()
        version = self.repo / "VERSION"
        original = version.read_text()
        untracked = self.repo / "未提交研究笔记.txt"
        try:
            version.write_text("fixture unsaved change\n")
            untracked.write_text("保留夹具未跟踪文件")
            before = update.database_fingerprint(self.config["db_path"])
            with self.assertRaises(runtime.OpsError):
                update.update(self.config, self.good_commit)
            self.assertEqual(version.read_text(), "fixture unsaved change\n")
            self.assertTrue(untracked.exists())
            self.assertEqual(update.database_fingerprint(self.config["db_path"]), before)
        finally:
            version.write_text(original)
            untracked.unlink()

    def test_successful_update_selection_and_new_write_rollback_guard(self):
        _, topic, _, _ = self.start_fixture()
        changed = update.update(self.config, self.good_commit)
        self.assertEqual(changed["status"], "updated")
        self.assertEqual(runtime.health(8874)["version"], "0.1.1-fixture")
        runtime.stop(self.config)
        resumed = runtime.start(self.config, open_browser=False)
        self.assertIn(self.good_commit, resumed["root"])
        self.api("PATCH", "topics/" + topic["id"], {"expected_version": 1, "rationale": "升级后新增，不能丢失"})
        with self.assertRaises(runtime.OpsError) as caught:
            update.rollback(self.config, changed["update_id"])
        self.assertIn("新写入", str(caught.exception))
        self.assertEqual(self.api("GET", "topics/" + topic["id"])["rationale"], "升级后新增，不能丢失")
        self.assertEqual(runtime.health(8874)["version"], "0.1.1-fixture")

    def test_failing_migration_restores_program_data_and_attachments(self):
        _, topic, evidence, _ = self.start_fixture()
        before = update.database_fingerprint(self.config["db_path"])
        with self.assertRaises(runtime.OpsError) as caught:
            update.update(self.config, self.bad_migration_commit)
        self.assertIn("已恢复兼容", str(caught.exception))
        self.assertEqual(runtime.health(8874)["version"], "0.1.0")
        self.assertEqual(update.database_fingerprint(self.config["db_path"]), before)
        self.assertEqual(self.api("GET", "topics/" + topic["id"])["question"], topic["question"])
        self.assertEqual(self.api("GET", f'evidence/{evidence["id"]}/history')["items"][0]["version"], 1)
        self.assertTrue((self.data / "attachments" / "允许保存的夹具.txt").exists())
        with sqlite3.connect(self.config["db_path"]) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 1)
            self.assertFalse(db.execute("SELECT name FROM sqlite_master WHERE name='fixture_migration'").fetchall())
        self.assertFalse((self.data / "maintenance.json").exists())

    def test_target_health_failure_rolls_back_and_download_failure_is_safe(self):
        _, topic, _, _ = self.start_fixture()
        with self.assertRaises(runtime.OpsError):
            update.update(self.config, self.bad_health_commit)
        self.assertEqual(runtime.health(8874)["version"], "0.1.0")
        before = update.database_fingerprint(self.config["db_path"])
        with self.assertRaises(runtime.OpsError):
            update.update(self.config, "fixture-nonexistent-target")
        self.assertEqual(update.database_fingerprint(self.config["db_path"]), before)
        self.assertEqual(self.api("GET", "topics/" + topic["id"])["id"], topic["id"])

    def test_script_and_command_entrypoints_in_chinese_space_path(self):
        command = [str(self.repo / "start.command"), "--data-dir", str(self.data), "--port", "8874", "--init", "--no-browser", "--no-scheduler"]
        started = subprocess.run(command, capture_output=True, text=True, timeout=25)
        self.assertEqual(started.returncode, 0, started.stderr)
        pid = json.loads(started.stdout)["pid"]
        repeat = subprocess.run(command, capture_output=True, text=True, timeout=10)
        self.assertEqual(json.loads(repeat.stdout)["pid"], pid)
        checked = subprocess.run([str(self.repo / "scripts/check-config.sh"), "--data-dir", str(self.data), "--port", "8874"], capture_output=True, text=True, timeout=10)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        stopped = subprocess.run([str(self.repo / "stop.command"), "--data-dir", str(self.data), "--port", "8874"], capture_output=True, text=True, timeout=25)
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        self.assertTrue(self.config["db_path"].exists())

    def test_successful_schema_migration_can_explicitly_roll_back_without_new_writes(self):
        _, topic, _, _ = self.start_fixture()
        changed = update.update(self.config, self.good_migration_commit)
        self.assertEqual(backup.inspect_database(self.config["db_path"])["schema_version"], 2)
        reverted = update.rollback(self.config, changed["update_id"])
        self.assertEqual(reverted["status"], "rolled_back")
        self.assertEqual(backup.inspect_database(self.config["db_path"])["schema_version"], 1)
        self.assertEqual(runtime.health(8874)["version"], "0.1.0")
        self.assertEqual(self.api("GET", "topics/" + topic["id"])["id"], topic["id"])

    def test_upgrade_backup_failure_aborts_before_migration(self):
        self.start_fixture()
        before = update.database_fingerprint(self.config["db_path"])
        with mock.patch.object(backup, "_snapshot", side_effect=OSError("fixture disk full")):
            with self.assertRaises(runtime.OpsError):
                update.update(self.config, self.good_migration_commit)
        self.assertEqual(runtime.health(8874)["version"], "0.1.0")
        self.assertEqual(update.database_fingerprint(self.config["db_path"]), before)
        self.assertFalse((self.data / "maintenance.json").exists())

    def test_interrupted_update_recovers_and_does_not_duplicate_migrations(self):
        _, topic, _, _ = self.start_fixture()
        process = subprocess.Popen([sys.executable, "-m", "ops.cli", "update", "--root", str(self.repo), "--data-dir", str(self.data), "--port", "8874", "--no-scheduler", "--target", self.interrupt_commit], cwd=self.repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        entered = self.data / "fixture-migration-entered"
        deadline = time.monotonic() + 15
        while not entered.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(.1)
        self.assertTrue(entered.exists(), "fixture migration did not enter controlled pause")
        process.kill()  # Only the explicit fixture update CLI; the pending app is recovered via recorded ownership.
        process.communicate(timeout=5)
        marker = runtime.read_json(self.data / "maintenance.json")
        self.assertIsNotNone(marker)
        self.assertIsNotNone(runtime.pending_runtime(self.config))
        result = update.recover(self.config, marker["update_id"])
        self.assertEqual(result["status"], "recovered_to_old")
        self.assertEqual(runtime.health(8874)["version"], "0.1.0")
        self.assertEqual(self.api("GET", "topics/" + topic["id"])["id"], topic["id"])
        with self.assertRaises(runtime.OpsError):
            update.recover(self.config, marker["update_id"])
        self.assertEqual(backup.inspect_database(self.config["db_path"])["schema_version"], 1)

    def test_directory_permission_and_tampered_manifest_are_blocked(self):
        self.data.mkdir()
        self.data.chmod(0o500)
        try:
            report = runtime.check(self.config, initialize=True)
            self.assertTrue(any(row["name"] == "data_dir" and row["level"] == "block" for row in report["checks"]))
        finally:
            self.data.chmod(0o700)
        self.start_fixture()
        package = Path(backup.create_backup(self.config)["package"])
        tampered = Path(self.directory.name) / "tampered.wibackup"
        with zipfile.ZipFile(package) as original, zipfile.ZipFile(tampered, "w") as changed:
            for name in original.namelist():
                content = original.read(name)
                if name == "manifest.json":
                    manifest = json.loads(content)
                    manifest["files"][0]["sha256"] = "0" * 64
                    content = json.dumps(manifest).encode()
                changed.writestr(name, content)
        before = update.database_fingerprint(self.config["db_path"])
        with self.assertRaises(runtime.OpsError):
            backup.restore_backup(self.config, tampered, apply=True, replace=True)
        self.assertEqual(update.database_fingerprint(self.config["db_path"]), before)

    def test_new_code_directory_reopens_existing_data_and_normal_stop_is_safe(self):
        _, topic, _, _ = self.start_fixture()
        runtime.stop(self.config)
        new_root = Path(self.directory.name) / "另一 程序目录"
        shutil.copytree(self.repo, new_root, ignore=shutil.ignore_patterns(".git", "__pycache__", ".env"))
        other = runtime.prepare_config(new_root, self.data, 8874)
        other["no_scheduler"] = True
        resumed = runtime.start(other, open_browser=False)
        self.assertEqual(Path(resumed["root"]), new_root.resolve())
        self.assertEqual(self.api("GET", "topics/" + topic["id"])["id"], topic["id"])
        runtime.stop(other)
        self.assertTrue(self.config["db_path"].exists())

    def test_restore_does_not_treat_unbound_personal_files_as_empty(self):
        self.start_fixture()
        package = backup.create_backup(self.config)["package"]
        unknown = runtime.prepare_config(self.repo, Path(self.directory.name) / "已有资料目录", 8875)
        unknown["data_dir"].mkdir()
        personal = unknown["data_dir"] / "个人笔记.txt"
        personal.write_text("fixture keep me")
        preview = backup.restore_backup(unknown, package)
        self.assertTrue(preview["requires_replace"])
        with self.assertRaises(runtime.OpsError):
            backup.restore_backup(unknown, package, apply=True, replace=True)
        self.assertEqual(personal.read_text(), "fixture keep me")
        self.assertFalse(unknown["db_path"].exists())

    def test_backup_rejects_non_evidence_orphan_references(self):
        self.start_fixture()
        good = backup.create_backup(self.config)["package"]
        runtime.stop(self.config)
        store = Store(self.config["db_path"])
        store.create("evidence_alias", {"key": "fixture:broken", "evidence_id": "fixture-missing-evidence"})
        self.assertFalse(store.integrity()["ok"])
        store.close()
        with self.assertRaises(runtime.OpsError) as caught:
            backup.create_backup(self.config)
        self.assertIn("领域引用", str(caught.exception))
        self.assertEqual(backup.validate_backup(good)["state"], "complete")

    def test_restore_rejects_missing_read_state_version_before_touching_target(self):
        self.start_fixture()
        good = Path(backup.create_backup(self.config)["package"])
        runtime.stop(self.config)
        before = update.database_fingerprint(self.config["db_path"])
        with tempfile.TemporaryDirectory(prefix="ops-orphan-backup-", dir=self.directory.name) as tmp:
            stage = Path(tmp)
            manifest = backup.unpack_verified(good, stage)
            store = Store(stage / backup.DB_NAME)
            change = store.all("change")[0]
            store.create("read_state", {"change_id": change["id"], "change_version": 999, "topic_id": change.get("topic_id")})
            counts = {row[0]: row[1] for row in store.db.execute("SELECT kind,count(*) FROM records GROUP BY kind")}
            version_count = store.db.execute("SELECT count(*) FROM versions").fetchone()[0]
            store.close()
            manifest["database"]["counts"], manifest["database"]["version_count"] = counts, version_count
            for entry in manifest["files"]:
                entry["sha256"] = backup.sha256(stage / entry["path"])
                entry["size"] = (stage / entry["path"]).stat().st_size
            package = Path(self.directory.name) / "orphan-read-state.wibackup"
            with zipfile.ZipFile(package, "w") as archive:
                for entry in manifest["files"]:
                    archive.write(stage / entry["path"], entry["path"])
                archive.writestr("manifest.json", json.dumps(manifest))
            with self.assertRaises(runtime.OpsError) as caught:
                backup.restore_backup(self.config, package, apply=True, replace=True)
            self.assertIn("版本引用", str(caught.exception))
        self.assertEqual(update.database_fingerprint(self.config["db_path"]), before)

    def test_secret_config_not_echoed_and_missing_dependency_blocks(self):
        env = self.repo / ".env"
        old = env.read_text() if env.exists() else None
        try:
            env.write_text("WORLD_INSIGHT_PORT=DO_NOT_ECHO_SECRET\n")
            with self.assertRaises(runtime.OpsError) as caught:
                runtime.prepare_config(self.repo, self.data)
            self.assertNotIn("DO_NOT_ECHO_SECRET", str(caught.exception))
            env.write_text("WORLD_INSIGHT_PORT=8874\n")
            with mock.patch.object(runtime.sys, "version_info", (3, 10, 0)):
                report = runtime.check(self.config, initialize=True)
            self.assertTrue(any(row["name"] == "python" and row["level"] == "block" for row in report["checks"]))
        finally:
            if old is None:
                env.unlink(missing_ok=True)
            else:
                env.write_text(old)


if __name__ == "__main__":
    unittest.main()
