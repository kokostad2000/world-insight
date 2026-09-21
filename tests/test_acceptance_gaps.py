"""AC gaps: isolated SQLite and real child processes, never real-source/sleep proof.

Only the backup case binds 127.0.0.1:8877. All child processes are owned by this
suite; a busy port fails preflight without killing its occupant. Provider results
and the backup interruption point are explicit fixture/fault-injection seams.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
import zipfile

from ops import backup, runtime
from server.app import Application
from server.modules import sources
from server.modules.sources import adapters
from server.platform.store import Store

ROOT = Path(__file__).resolve().parents[1]
PORT = 8877
RSS = b'''<rss><channel><item><title>Explicit acceptance fixture RSS</title>
<link>https://www.federalreserve.gov/fixture/ac-gap-report</link>
<guid>ac-gap-rss</guid><pubDate>Fri, 18 Sep 2026 15:00:00 GMT</pubDate>
</item></channel></rss>'''


class AcceptanceGapTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="world-insight-acceptance-gap-fixture-")
        self.base = Path(self.directory.name)
        self.children = []
        self.live_config = None
        self.store = Store(self.base / "fixture.sqlite")
        self.config = runtime.prepare_config(ROOT, self.base, PORT)
        self.app = Application(self.config, self.store, {"instance_id": "explicit-acceptance-fixture"})
        self.addCleanup(self.cleanup)

    def cleanup(self):
        # Never discover/kill a port occupant: only Popen handles created here.
        for child in self.children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)
            for stream in (child.stdin, child.stdout, child.stderr):
                if stream:
                    stream.close()
        if self.live_config is not None:
            runtime.stop(self.live_config)
        self.store.close()
        self.directory.cleanup()

    def call(self, method, path, body=None, query=None):
        result = self.app.dispatch(method, "/api/" + path, body or {}, query or {})
        self.app.drain()
        return result

    def child(self, code, *args, cwd=ROOT):
        process = subprocess.Popen([sys.executable, "-c", code, *map(str, args)],
                                   cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        self.children.append(process)
        return process

    def wait_marker(self, path, child):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if path.exists():
                return json.loads(path.read_text())
            if child.poll() is not None:
                stdout, stderr = child.communicate(timeout=1)
                self.fail(f"Owned fixture child exited {child.returncode}: {stdout} {stderr}")
            time.sleep(.025)
        self.fail("Owned fixture child did not reach its bounded readiness point")

    def trace(self, case, **values):
        print("AC_GAP_EVIDENCE " + json.dumps({"case": case, "fixture": True, **values},
                                             ensure_ascii=False, sort_keys=True), flush=True)

    def test_two_distinct_sources_keep_five_and_twelve_claims_and_citations(self):
        topic = self.call("POST", "topics", {"question": "[隔离验收] 两来源伤亡说法分歧", "is_fixture": True})
        materials, claims = [], []
        for suffix, number in (("a", 5), ("b", 12)):
            source = self.call("POST", "sources", {
                "name": f"[隔离验收] 独立登记来源 {suffix}", "adapter": "manual",
                "domain": f"{suffix}.example.org", "enabled": True,
                "rights": {"fetch": False, "store": True, "display": True, "export": True, "ai": False}})
            evidence = self.call("POST", "evidence", {
                "topic_id": topic["id"], "source_id": source["id"],
                "title": f"[隔离验收] 来源 {suffix} 报告 {number} 人",
                "url": f"https://{suffix}.example.org/ac-06", "publisher": source["name"],
                "published_at": "2026-09-18", "is_fixture": True})
            materials.append(evidence)
            claims.append(self.call("POST", "claims", {
                "topic_id": topic["id"], "subject": source["name"],
                "statement": f"[隔离验收] 报告 {number} 人伤亡，尚未独立确认",
                "evidence_version_ids": [evidence["version_id"]], "dispute_status": "disputed",
                "is_fixture": True}))
        event = self.call("POST", "events", {
            "title": "[隔离验收] 两来源人数存在分歧", "topic_id": topic["id"],
            "claim_ids": [item["id"] for item in claims], "verification_status": "disputed",
            "is_fixture": True})
        self.assertEqual(len({item["source_id"] for item in materials}), 2)
        self.assertEqual(len({item["id"] for item in materials}), 2)
        self.assertEqual(set(event["claim_ids"]), {item["id"] for item in claims})
        self.assertEqual(event["verification_status"], "disputed")
        self.assertNotIn("casualties", event)
        exported = self.call("GET", "exports", query={"topic_id": topic["id"], "format": "json"})
        by_id = {item["id"]: item for item in exported["claims"]}
        for claim, evidence in zip(claims, materials):
            self.assertEqual(by_id[claim["id"]]["statement"], claim["statement"])
            self.assertEqual(by_id[claim["id"]]["evidence_version_ids"], [evidence["version_id"]])
        self.assertEqual({item["version_id"] for item in exported["citations"]},
                         {item["version_id"] for item in materials})
        self.assertEqual({item["source_id"] for item in exported["citations"]},
                         {item["source_id"] for item in materials})
        self.assertNotIn("casualties", exported["events"][0])
        self.trace("AC-06", source_count=2, evidence_count=2, claim_count=2,
                   fixed_citations=[item["version_id"] for item in materials], combined_casualty_value=False)

    def test_two_news_sources_timeout_preserves_cache_and_last_success_but_is_unavailable(self):
        sources.seed_sources(self.store)
        self.clock = "2026-09-20T15:00:00Z"
        self.store.now = lambda: self.clock
        source_ids = ("source-fed", "source-gdelt")
        for sid, patch in (("source-world-bank", {"enabled": False}),
                           ("source-gdelt", {"config": {"query": "explicit fixture", "topic_ids": []}})):
            old = self.store.get("source", sid)
            self.call("PATCH", "sources/" + sid, {"expected_version": old["version"], **patch})
        calls = []
        failing = False
        def fixture_fetch(url, headers):
            calls.append(url)
            if failing:
                raise adapters.FetchError("timeout", "[隔离故障注入] 此新闻源请求超时")
            if "gdeltproject.org" in url:
                return adapters.Response(200, json.dumps({"articles": [{
                    "title": "[隔离验收] GDELT 元数据样本", "url": "https://b.example.org/ac-gap-report",
                    "domain": "b.example.org", "seendate": "20260918T150000Z"}]}).encode())
            return adapters.Response(200, RSS)
        scheduler = sources.Scheduler(self.store, fetcher=fixture_fetch)
        for sid in source_ids:
            job = sources.enqueue(self.store, sid)["job"]
            for step in range(10):
                result = scheduler.tick(False)
                self.assertIsNotNone(result)
                if self.store.get("collection_job", job["id"])["state"] == "complete":
                    break
                self.clock = f"2026-09-20T15:00:{(step + 1) * 7:02d}Z"
            self.assertEqual(self.store.get("collection_job", job["id"])["state"], "complete")
        cached = self.store.all("evidence")
        self.assertEqual(len(cached), 2)
        original_success = {sid: self.store.get("source", sid)["last_success"] for sid in source_ids}
        original_requests = {sid: self.store.get("source", sid)["requests_today"] for sid in source_ids}
        self.assertEqual(sources.coverage(self.store)["coverage_status"], "complete")
        failing = True
        self.clock = "2026-09-20T15:03:00Z"
        calls_before_failure = len(calls)
        for sid in source_ids:
            sources.enqueue(self.store, sid)
        for _ in source_ids:
            result = scheduler.tick(False)
            self.assertEqual(result["state"], "retry")
            self.assertEqual(result["error_code"], "timeout")
        self.assertEqual(len(calls) - calls_before_failure, 2)
        result = sources.coverage(self.store)
        self.assertEqual({row["id"] for row in result["sources"]}, set(source_ids))
        self.assertIsNone(result["empty_reason"])
        for row in result["sources"]:
            self.assertEqual(row["status"], "failed")
            self.assertEqual(row["data_status"], "stale")
            self.assertFalse(row["check_complete"])
            self.assertEqual(row["last_success"], original_success[row["id"]])
            self.assertIn("超时", row["reason"])
            self.assertEqual(self.store.get("source", row["id"])["requests_today"],
                             original_requests[row["id"]] + 1)
        self.assertEqual(self.store.all("evidence"), cached)
        self.trace("AC-09", coverage_status=result["coverage_status"], last_success=original_success,
                   cached_records=len(cached), current_failed_sources=2, network_calls=0,
                   provider_results="injected")
        self.assertEqual(result["coverage_status"], "unavailable",
                         "All currently enabled news checks timed out; stale cache must not imply partial live coverage")

    @unittest.skipUnless(os.name == "posix", "Requires POSIX process signals and flock")
    def test_scheduler_lock_excludes_second_process_and_releases_after_sigkill(self):
        sources.seed_sources(self.store)
        for source in self.store.all("source"):
            if source["adapter"] in sources.FREE_ADAPTERS:
                self.call("PATCH", "sources/" + source["id"], {"expected_version": source["version"], "enabled": False})
        code = '''
import json, os, sys
from pathlib import Path
from server.modules.sources import Scheduler
from server.platform.store import Store
from server.platform.errors import ApiError
store = Store(Path(sys.argv[1]))
scheduler = Scheduler(store, fetcher=lambda *args: (_ for _ in ()).throw(AssertionError("No upstream call allowed")))
try:
    try:
        scheduler.start()
    except ApiError as error:
        Path(sys.argv[2]).write_text(json.dumps({"pid": os.getpid(), "status": error.status, "code": error.code}))
        sys.exit(23)
    Path(sys.argv[2]).write_text(json.dumps({"pid": os.getpid(), "status": "started"}))
    sys.stdin.readline()
finally:
    scheduler.stop()
    store.close()
'''
        first_marker = self.base / "collector-first.json"
        first = self.child(code, self.store.path, first_marker)
        ready = self.wait_marker(first_marker, first)
        self.assertEqual(ready, {"pid": first.pid, "status": "started"})
        second_marker = self.base / "collector-second.json"
        second = self.child(code, self.store.path, second_marker)
        rejected = self.wait_marker(second_marker, second)
        second.communicate(timeout=3)
        self.assertEqual(second.returncode, 23)
        self.assertEqual(rejected, {"pid": second.pid, "status": 409, "code": "collector_running"})
        self.assertNotEqual(first.pid, second.pid)
        self.assertIsNone(first.poll())
        first.kill()
        first.communicate(timeout=3)
        self.assertEqual(first.returncode, -signal.SIGKILL)
        third_marker = self.base / "collector-after-kill.json"
        third = self.child(code, self.store.path, third_marker)
        self.assertEqual(self.wait_marker(third_marker, third)["status"], "started")
        third.communicate("stop\n", timeout=3)
        self.assertEqual(third.returncode, 0)
        self.assertEqual(self.store.all("collection_job"), [])
        self.trace("AC-36-process-lock-only", first_pid=first.pid, rejected_pid=second.pid,
                   rejection_code=rejected["code"], first_exit=first.returncode,
                   restarted_pid=third.pid, restarted_exit=third.returncode, actual_sleep=False)

    @unittest.skipUnless(os.name == "posix", "Requires POSIX SIGKILL")
    def test_online_backup_sigkill_keeps_previous_package_and_rejects_partial(self):
        copy = self.base / "中文 代码 fixture"
        shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(
            ".git", ".worktrees", ".env", "__pycache__", "*.pyc", ".test-data"))
        config = runtime.prepare_config(copy, self.base / "运行中 资料", PORT)
        config["backup_dir"] = self.base / "独立 备份"
        config["no_scheduler"] = True
        self.live_config = config
        started = runtime.start(config, initialize=True, open_browser=False)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        request = urllib.request.Request(f"http://127.0.0.1:{PORT}/api/topics", method="POST",
                  data=json.dumps({"question": "[隔离验收] 在线备份中断", "is_fixture": True}).encode(),
                  headers={"Content-Type": "application/json"})
        with opener.open(request, timeout=3) as response:
            topic = json.load(response)
        previous = Path(backup.create_backup(config, output=config["backup_dir"] / "previous-valid.wibackup")["package"])
        prior_hash = backup.sha256(previous)
        prior_manifest = backup.validate_backup(previous, maximum_schema=1)
        target = config["backup_dir"] / "interrupted.wibackup"
        partial = target.with_name(target.name + ".partial")
        marker = self.base / "backup-writing.json"
        code = '''
import json, os, sys, threading, zipfile
from pathlib import Path
from ops import backup, runtime
config = runtime.prepare_config(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]))
original_write = zipfile.ZipFile.write
paused = False
def controlled_write(archive, *args, **kwargs):
    global paused
    result = original_write(archive, *args, **kwargs)
    if not paused:
        paused = True
        archive.fp.flush()
        os.fsync(archive.fp.fileno())
        Path(sys.argv[5]).write_text(json.dumps({"pid": os.getpid(), "phase": "partial_zip_member_written"}))
        if not threading.Event().wait(30):
            raise RuntimeError("Controlled fixture pause expired before parent interruption")
    return result
zipfile.ZipFile.write = controlled_write
print(json.dumps(backup.create_backup(config, output=Path(sys.argv[4]))), flush=True)
'''
        child = self.child(code, copy, config["data_dir"], PORT, target, marker, cwd=copy)
        self.assertEqual(self.wait_marker(marker, child), {"pid": child.pid, "phase": "partial_zip_member_written"})
        self.assertTrue(partial.is_file())
        self.assertGreater(partial.stat().st_size, 0)
        self.assertFalse(target.exists())
        child.kill()
        stdout, stderr = child.communicate(timeout=3)
        self.assertEqual(child.returncode, -signal.SIGKILL)
        self.assertEqual(stdout, "")
        self.assertFalse(target.exists())
        self.assertFalse(zipfile.is_zipfile(partial))
        self.assertEqual(backup.sha256(previous), prior_hash)
        revalidated = backup.validate_backup(previous, maximum_schema=1)
        # Validation adds a fresh policy evaluation timestamp; archive bytes are
        # independently hash-checked above, so compare the stable archive claims.
        for field in ("state", "files", "database", "instance_id", "created_at"):
            self.assertEqual(revalidated[field], prior_manifest[field])
        with self.assertRaises(runtime.OpsError):
            backup.validate_backup(partial, maximum_schema=1)
        restore_config = runtime.prepare_config(copy, self.base / "拒绝未完成包 恢复目标", PORT)
        with self.assertRaises(runtime.OpsError):
            backup.restore_backup(restore_config, partial, apply=True)
        self.assertFalse(restore_config["db_path"].exists())
        events = [json.loads(line) for line in (config["data_dir"] / "logs/operations.jsonl").read_text().splitlines()]
        self.assertEqual([row["package"] for row in events if row["event"] == "backup_complete"], [str(previous)])
        self.assertEqual(runtime.health(PORT)["pid"], started["pid"])
        with opener.open(f'http://127.0.0.1:{PORT}/api/topics/{topic["id"]}', timeout=3) as response:
            self.assertEqual(json.load(response)["id"], topic["id"])
        self.trace("AC-29", server_pid=started["pid"], interrupted_backup_pid=child.pid,
                   backup_exit=child.returncode, partial_bytes=partial.stat().st_size,
                   previous_package_sha256=prior_hash, previous_still_valid=True,
                   final_package_exists=False, incomplete_restore_rejected=True,
                   live_topic_readable=True, fault="SIGKILL after first ZIP member before finalization")
        stopped = runtime.stop(config)
        self.assertEqual(stopped["status"], "stopped")
        self.live_config = None


if __name__ == "__main__":
    unittest.main()
