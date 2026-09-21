"""Remaining Mac acceptance: real script/process/restore behavior, isolated fixtures.

No upstream calls, Finder automation, OS sleep, or container claim. Port 8877 is
used serially and only identity-owned services are stopped. Optional explicit
WORLD_INSIGHT_MAC_ACCEPTANCE_RETAIN writes a new stopped browser fixture; normal
test runs remove their own temporary directories.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

from ops import backup, runtime, update

ROOT = Path(__file__).resolve().parents[1]
PORT = 8877


def inventory(config):
    """Read a coherent full-record/version inventory plus attachment bytes."""
    with sqlite3.connect(f'file:{config["db_path"]}?mode=ro', uri=True) as db:
        db.execute("BEGIN")
        tables = {}
        for table, order in (("records", "kind,id"), ("versions", "kind,id,version")):
            tables[table] = [list(row) for row in db.execute(
                f"SELECT kind,id,version,data FROM {table} ORDER BY {order}")]
        schema = db.execute("PRAGMA user_version").fetchone()[0]
    attachments = {path.relative_to(config["data_dir"]).as_posix(): {
        "size": path.stat().st_size, "sha256": backup.sha256(path)}
        for path in sorted((config["data_dir"] / "attachments").rglob("*")) if path.is_file()}
    return {**tables, "schema": schema, "attachments": attachments}


def inventory_summary(value):
    counts = {}
    for kind, _, _, _ in value["records"]:
        counts[kind] = counts.get(kind, 0) + 1
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"record_counts": counts, "version_count": len(value["versions"]),
            "attachment_count": len(value["attachments"]), "sha256": hashlib.sha256(canonical.encode()).hexdigest()}


@unittest.skipUnless(sys.platform == "darwin", "This acceptance batch targets actual macOS")
class MacAcceptanceRemainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.suite = tempfile.TemporaryDirectory(prefix="world-insight-mac-remaining-fixture-")
        cls.base = Path(cls.suite.name)
        cls.repo = cls.base / "中文 代码 fixture"
        shutil.copytree(ROOT, cls.repo, ignore=shutil.ignore_patterns(
            ".git", ".worktrees", ".env", "__pycache__", "*.pyc", ".test-data"))
        def git(*args):
            return subprocess.run(["git", *args], cwd=cls.repo, check=True,
                                  capture_output=True, text=True).stdout.strip()
        git("init", "-b", "main")
        git("config", "user.name", "World Insight Isolated Acceptance")
        git("config", "user.email", "fixture@localhost")
        git("add", ".")
        git("commit", "-m", "Explicit isolated Mac acceptance baseline")
        cls.old_commit = git("rev-parse", "HEAD")
        (cls.repo / "VERSION").write_text("0.1.1-mac-acceptance-fixture\n")
        git("add", "VERSION")
        git("commit", "-m", "Explicit same-schema fixture update")
        cls.new_commit = git("rev-parse", "HEAD")
        git("switch", "--detach", cls.old_commit)

    @classmethod
    def tearDownClass(cls):
        cls.suite.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="隔离 资料-", dir=self.base)
        self.directory_path = Path(self.directory.name)
        self.config = runtime.prepare_config(self.repo, self.directory_path / "原始 数据", PORT)
        self.config["backup_dir"] = self.directory_path / "有效 备份"
        self.config["no_scheduler"] = True
        self.configs = [self.config]
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for config in self.configs:
            runtime.stop(config)
        self.directory.cleanup()

    def api(self, method, path, body=None, config=None):
        target = config or self.config
        request = urllib.request.Request(f'http://127.0.0.1:{target["port"]}/api/{path}',
                    data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
                    method=method, headers={"Content-Type": "application/json"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=5) as response:
            return json.load(response)

    def trace(self, case, **values):
        print("MAC_ACCEPTANCE_EVIDENCE " + json.dumps({"case": case, "fixture": True, **values},
                                                       ensure_ascii=False, sort_keys=True), flush=True)

    def start_full_fixture(self):
        started = runtime.start(self.config, initialize=True, open_browser=False)
        for source in self.api("GET", "sources")["items"]:
            if source["adapter"] in {"rss", "gdelt", "world_bank"}:
                self.api("PATCH", "sources/" + source["id"], {
                    "expected_version": source["version"], "enabled": False,
                    "budget_daily": 3 if source["adapter"] == "rss" else 4})
        settings = self.api("GET", "retention")
        self.api("PATCH", "retention", {"expected_version": settings["version"],
                 "candidate_retention_enabled": False, "batch_limit": 7})
        topic = self.api("POST", "topics", {
            "question": "[隔离验收] Mac 全对象与阅读状态", "is_fixture": True,
            "followed": True, "country_codes": ["USA"], "rationale": "仅工程样本，不是国际事件"})
        evidence = self.api("POST", "evidence", {
            "topic_id": topic["id"], "title": "[隔离验收] 合法人工材料", "source_id": "manual",
            "url": "https://example.org/mac-acceptance", "published_at": "2026-09-10",
            "excerpt": "隔离自编材料：仅验证数据保留。", "notes": "第一版人工笔记",
            "rights": {"store": True, "display": True, "export": True}, "is_fixture": True})
        self.api("PATCH", "evidence/" + evidence["id"], {
            "expected_version": evidence["version"], "notes": "第二版人工笔记，旧引用仍固定 v1",
            "change_reason": "隔离验收笔记修订"})
        claim = self.api("POST", "claims", {
            "topic_id": topic["id"], "subject": "隔离主体", "statement": "工程样本的单方说法",
            "evidence_version_ids": [evidence["version_id"]], "is_fixture": True})
        event = self.api("POST", "events", {
            "topic_id": topic["id"], "title": "[隔离验收] 旧日期事件", "claim_ids": [claim["id"]],
            "occurred_at": "2026-09-10", "time_precision": "day", "is_fixture": True,
            "location": {"country_code": "USA", "name": "美国", "precision": "country"}})
        judgment = self.api("POST", "judgments", {
            "topic_id": topic["id"], "conclusion": "[隔离验收] 尚无独立确认",
            "evidence_version_ids": [evidence["version_id"]], "is_fixture": True})
        judgment = self.api("PATCH", "judgments/" + judgment["id"], {
            "expected_version": judgment["version"], "conclusion": "[隔离验收] 已保留旧材料版本",
            "change_reason": "为异常退出和恢复建立判断历史"})
        scenario = self.api("POST", "scenarios", {
            "topic_id": topic["id"], "title": "[隔离验收] 待验证情景", "description": "无法确定是否发生",
            "evidence_version_ids": [evidence["version_id"]], "is_fixture": True})
        path = self.api("POST", "impact-paths", {
            "topic_id": topic["id"], "title": "[隔离验收] 结构化路径", "is_fixture": True,
            "nodes": [{"id": "a", "label": "说法"}, {"id": "b", "label": "尚未验证的影响"}],
            "edges": [{"from": "a", "to": "b", "status": "assumption",
                       "evidence_version_ids": [evidence["version_id"]], "note": "仅假设"}]})
        review = self.api("POST", "reviews", {
            "topic_id": topic["id"], "judgment_id": judgment["id"], "judgment_version": 1,
            "outcome": "indeterminate", "rationale": "隔离样本没有真实结果", "is_fixture": True})
        metric = self.api("POST", "metrics", {
            "topic_id": topic["id"], "indicator": "[隔离验收] 年度未知值", "country_code": "USA",
            "period": "2025", "value": None, "unit": "USD", "frequency": "annual",
            "evidence_version_ids": [evidence["version_id"]], "is_fixture": True})
        brief = self.api("POST", "briefs", {"topic_id": topic["id"]})
        dashboard = self.api("GET", "dashboard?window=24h&limit=200")
        self.assertGreater(len(dashboard["items"]), 2)
        marked = self.api("POST", "changes/read", {
            "snapshot_at": dashboard["snapshot_at"],
            "items": [{"id": row["id"], "version": row["version"]} for row in dashboard["items"][:2]]})
        self.assertEqual(len(marked["marked"]), 2)
        attachments = self.config["data_dir"] / "attachments"
        (attachments / "合法自编 说明.txt").write_text("隔离自编附件：正常/异常退出和恢复后必须完整。")
        (attachments / "nested").mkdir()
        (attachments / "nested/版本样本.bin").write_bytes(b"EXPLICIT-MAC-FIXTURE\x00\x01\x02")
        return {"started": started, "topic": topic, "evidence": evidence,
                "judgment": judgment, "read_items": marked["marked"],
                "objects": {"topics": topic["id"], "evidence": evidence["id"], "claims": claim["id"],
                    "events": event["id"], "judgments": judgment["id"], "scenarios": scenario["id"],
                    "impact-paths": path["id"], "reviews": review["id"], "metrics": metric["id"], "briefs": brief["id"]}}

    def stable_inventory(self, config=None):
        target = config or self.config
        previous = inventory(target)
        for _ in range(40):
            time.sleep(.025)
            current = inventory(target)
            if current == previous:
                return current
            previous = current
        self.fail("Fixture data did not settle before the controlled interruption")

    def assert_fixture_http(self, fixture, config=None):
        for collection, record_id in fixture["objects"].items():
            self.assertEqual(self.api("GET", collection + "/" + record_id, config=config)["id"], record_id)
        versions = self.api("GET", "evidence/" + fixture["evidence"]["id"] + "/history", config=config)["items"]
        self.assertEqual({record["version"] for record in versions}, {1, 2})
        judgment = self.api("GET", "judgments/" + fixture["judgment"]["id"], config=config)
        self.assertEqual(judgment["evidence_version_ids"], [fixture["evidence"]["version_id"]])
        dashboard = self.api("GET", "dashboard?window=24h&limit=200", config=config)
        read_ids = {(row["id"], row["version"]) for row in dashboard["items"] if row["read"]}
        self.assertTrue({(row["id"], row["version"]) for row in fixture["read_items"]}.issubset(read_ids))
        self.assertFalse(self.api("GET", "sources/source-fed", config=config)["enabled"])
        self.assertEqual(self.api("GET", "sources/source-fed", config=config)["budget_daily"], 3)
        settings = self.api("GET", "retention", config=config)
        self.assertFalse(settings["candidate_retention_enabled"])
        self.assertEqual(settings["batch_limit"], 7)

    def test_actual_scripts_with_python_absent_from_isolated_path_block_with_guidance(self):
        only_bin = self.directory_path / "仅必需 Shell 工具"
        only_bin.mkdir()
        (only_bin / "dirname").symlink_to("/usr/bin/dirname")
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith("WORLD_INSIGHT_")}
        environment["PATH"] = str(only_bin)
        self.assertIsNone(shutil.which("python3", path=str(only_bin)))
        self.assertIsNone(shutil.which("python3.11", path=str(only_bin)))
        results = []
        for entry in ("start.sh", "check-config.sh"):
            run = subprocess.run([str(self.repo / "scripts" / entry), "--data-dir",
                     str(self.config["data_dir"]), "--port", str(PORT), "--init"],
                     cwd=self.repo, env=environment, capture_output=True, text=True, timeout=5)
            self.assertEqual(run.returncode, 1)
            self.assertEqual(run.stdout, "")
            self.assertIn("未找到 Python 3.11", run.stderr)
            self.assertIn("README", run.stderr)
            self.assertIn("WORLD_INSIGHT_PYTHON", run.stderr)
            results.append({"entry": entry, "exit_code": run.returncode, "stderr": run.stderr.strip()})
        self.assertFalse(self.config["data_dir"].exists())
        self.trace("AC-25-real-entrypoint", isolated_path_has_python=False, scripts=results,
                   data_created=False, system_dependencies_modified=False)

    def test_sigkill_restart_preserves_all_records_versions_read_state_settings_and_attachments(self):
        fixture = self.start_full_fixture()
        before = self.stable_inventory()
        summary = inventory_summary(before)
        for kind in ("topic", "evidence", "claim", "event", "judgment", "scenario", "impact_path",
                     "review", "observation", "brief", "read_state", "source", "retention_settings"):
            self.assertGreater(summary["record_counts"].get(kind, 0), 0, kind)
        self.assertGreater(summary["version_count"], len(before["records"]))
        old_pid = fixture["started"]["pid"]
        owner = runtime.own_runtime(self.config)
        self.assertEqual(owner["pid"], old_pid)
        self.assertEqual(owner["data_dir"], str(self.config["data_dir"]))
        os.kill(old_pid, signal.SIGKILL)
        deadline = time.monotonic() + 5
        while runtime.is_alive(old_pid) and time.monotonic() < deadline:
            time.sleep(.025)
        self.assertFalse(runtime.is_alive(old_pid))
        self.assertEqual(inventory(self.config), before)
        restarted = runtime.start(self.config, open_browser=False)
        self.assertNotEqual(restarted["pid"], old_pid)
        after = self.stable_inventory()
        self.assertEqual(after, before, "Every stored current/history record and attachment must survive SIGKILL")
        self.assert_fixture_http(fixture)
        saved = self.api("PATCH", "judgments/" + fixture["judgment"]["id"], {
            "expected_version": fixture["judgment"]["version"], "conclusion": "[隔离验收] SIGKILL 重启后继续编辑",
            "change_reason": "实际 Mac 进程异常终止后 HTTP 保存"})
        self.assertEqual(saved["version"], fixture["judgment"]["version"] + 1)
        self.assertEqual(saved["evidence_version_ids"], [fixture["evidence"]["version_id"]])
        self.trace("AC-28", original_pid=old_pid, killed_signal="SIGKILL", restarted_pid=restarted["pid"],
                   before=summary, after=inventory_summary(after), all_rows_and_attachments_identical=True,
                   resumed_judgment_version=saved["version"], http_objects_read=len(fixture["objects"]),
                   container="not_applicable_native_stdlib")

    def test_rejected_rollback_current_backup_restores_new_records_attachments_and_read_state(self):
        fixture = self.start_full_fixture()
        changed = update.update(self.config, self.new_commit)
        self.assertEqual(changed["status"], "updated")
        selected = runtime.selected_program(self.config)
        self.assertEqual(runtime.health(PORT)["version"], "0.1.1-mac-acceptance-fixture")
        new_topic = self.api("POST", "topics", {
            "question": "[隔离验收] 升级后新增且不能丢失", "is_fixture": True, "followed": True})
        new_evidence = self.api("POST", "evidence", {
            "topic_id": new_topic["id"], "source_id": "manual", "title": "[隔离验收] 升级后新增材料",
            "url": "https://example.org/after-update", "notes": "回退拒绝前的新恢复包必须包含此笔记",
            "is_fixture": True})
        added = self.config["data_dir"] / "attachments/升级后新增 附件.txt"
        added.write_text("明确隔离样本：只有升级后才新增的附件。")
        added_hash = backup.sha256(added)
        before_reject = self.stable_inventory()
        with self.assertRaises(runtime.OpsError) as rejected:
            update.rollback(self.config, changed["update_id"])
        self.assertIn("新写入", str(rejected.exception))
        self.assertEqual(runtime.selected_program(self.config), selected)
        self.assertEqual(self.stable_inventory(), before_reject)
        events = [json.loads(line) for line in (self.config["data_dir"] / "logs/operations.jsonl").read_text().splitlines()]
        refusal = [row for row in events if row["event"] == "rollback_refused_new_writes"]
        self.assertEqual(len(refusal), 1)
        recovery_package = Path(refusal[0]["current_backup"])
        self.assertTrue(recovery_package.is_file())
        manifest = backup.validate_backup(recovery_package)
        self.assertEqual(manifest["label"], "before-requested-rollback")
        self.assertGreaterEqual(manifest["database"]["counts"]["read_state"], 2)
        self.assertEqual(manifest["database"]["counts"]["topic"], 2)
        runtime.stop(self.config)
        restored = runtime.prepare_config(selected, self.directory_path / "空目录 恢复副本", PORT)
        restored["no_scheduler"] = True
        self.configs.append(restored)
        self.assertFalse(restored["db_path"].exists())
        self.assertEqual(backup.restore_backup(restored, recovery_package)["status"], "preview")
        self.assertEqual(backup.restore_backup(restored, recovery_package, apply=True)["status"], "restored")
        restored_before_start = inventory(restored)
        self.assertEqual(restored_before_start["records"], before_reject["records"])
        self.assertEqual(restored_before_start["versions"], before_reject["versions"])
        self.assertEqual(restored_before_start["attachments"], before_reject["attachments"])
        runtime.start(restored, open_browser=False)
        self.assert_fixture_http(fixture, restored)
        self.assertEqual(self.api("GET", "topics/" + new_topic["id"], config=restored)["question"], new_topic["question"])
        self.assertEqual(self.api("GET", "evidence/" + new_evidence["id"], config=restored)["notes"], new_evidence["notes"])
        self.assertEqual(backup.sha256(restored["data_dir"] / added.relative_to(self.config["data_dir"])), added_hash)
        edited = self.api("PATCH", "topics/" + new_topic["id"], {
            "expected_version": new_topic["version"], "rationale": "从拒绝回退时保留的新恢复包恢复后继续编辑"}, restored)
        self.assertEqual(edited["version"], 2)
        runtime.stop(restored)
        self.trace("AC-34-and-AC-30-HTTP", refusal="new_writes", backup_label=manifest["label"],
                   restored_exact_current_and_history_rows=True,
                   restored_new_topic_id=new_topic["id"], restored_new_evidence_id=new_evidence["id"],
                   restored_new_attachment_sha256=added_hash,
                   restored_read_states=manifest["database"]["counts"]["read_state"],
                   resumed_topic_version=edited["version"], original_active_program_unchanged=True)
        retained = os.environ.get("WORLD_INSIGHT_MAC_ACCEPTANCE_RETAIN")
        if retained:
            self.retain_browser_fixture(Path(retained), selected, recovery_package, fixture, new_topic, new_evidence)

    def retain_browser_fixture(self, destination, selected, package, fixture, new_topic, new_evidence):
        """Explicit opt-in artifact for root; leave it stopped, never overwrite."""
        destination = destination.expanduser().resolve()
        if destination.exists():
            self.fail("Explicit browser fixture destination already exists; refusing to overwrite")
        destination.mkdir(parents=True)
        code = destination / "浏览器验收 代码"
        shutil.copytree(selected, code, ignore=shutil.ignore_patterns(".git", ".env", "__pycache__", "*.pyc"))
        kept_package = destination / "拒绝回退前当前状态.wibackup"
        shutil.copy2(package, kept_package)
        kept = runtime.prepare_config(code, destination / "恢复实例 数据", PORT)
        result = backup.restore_backup(kept, kept_package, apply=True)
        self.assertEqual(result["status"], "restored")
        details = {
            "is_fixture": True, "status": "restored_and_stopped", "port": PORT,
            "code_dir": str(code), "data_dir": str(kept["data_dir"]), "backup": str(kept_package),
            "original_topic_id": fixture["topic"]["id"], "evidence_id": fixture["evidence"]["id"],
            "fixed_evidence_version": fixture["evidence"]["version_id"], "judgment_id": fixture["judgment"]["id"],
            "judgment_version": fixture["judgment"]["version"], "read_items": fixture["read_items"],
            "new_topic_id": new_topic["id"], "new_evidence_id": new_evidence["id"],
            "source_check": {"id": "source-fed", "enabled": False, "budget_daily": 3},
            "retention_check": {"candidate_retention_enabled": False, "batch_limit": 7},
            "attachments": inventory(kept)["attachments"], "no_browser_validation_claimed": True,
            "start_command": [str(code / "scripts/start.sh"), "--data-dir", str(kept["data_dir"]),
                              "--port", str(PORT), "--no-browser", "--no-scheduler"]}
        (destination / "browser-fixture.json").write_text(json.dumps(details, ensure_ascii=False, indent=2))
        self.trace("AC-30-browser-fixture-ready", manifest=str(destination / "browser-fixture.json"),
                   fixture_status=details["status"], actual_browser_steps=False)


if __name__ == "__main__":
    unittest.main()
