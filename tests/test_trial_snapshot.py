"""Focused regression coverage for the read-only PRD M4 snapshot helper."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from server.platform.store import Store


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "capture_trial_snapshot.py"


class TrialSnapshotTests(unittest.TestCase):
    def test_observation_change_history_and_runtime_commit_are_captured(self):
        with tempfile.TemporaryDirectory(prefix="world-insight-trial-snapshot-fixture-") as temporary:
            base = Path(temporary)
            data_dir = base / "data"
            data_dir.mkdir()
            program_root = base / "running-program"
            program_root.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=program_root, check=True)
            subprocess.run([
                "git", "-c", "user.name=Trial Fixture", "-c", "user.email=trial@example.invalid",
                "commit", "--allow-empty", "-q", "-m", "fixture runtime",
            ], cwd=program_root, check=True)
            runtime_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=program_root, check=True,
                text=True, capture_output=True,
            ).stdout.strip()

            instance_id = "explicit-trial-snapshot-fixture"
            trial_start = datetime.now(timezone.utc) - timedelta(seconds=5)
            trial_start_text = trial_start.isoformat(timespec="microseconds").replace("+00:00", "Z")
            runtime_start_text = (trial_start - timedelta(seconds=5)).isoformat(
                timespec="microseconds"
            ).replace("+00:00", "Z")
            class HealthHandler(BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path != "/api/health":
                        self.send_error(404)
                        return
                    payload = json.dumps({
                        "status": "ok", "instance_id": instance_id, "data_dir": str(data_dir),
                        "pid": os.getpid(),
                    }).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)

                def log_message(self, *_):
                    pass

            health_server = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
            health_thread = threading.Thread(target=health_server.serve_forever, daemon=True)
            health_thread.start()
            self.addCleanup(health_server.server_close)
            self.addCleanup(health_server.shutdown)

            (data_dir / "instance.json").write_text(json.dumps({"instance_id": instance_id, "format": 1}))
            (data_dir / "runtime.json").write_text(json.dumps({
                "pid": os.getpid(),
                "port": health_server.server_address[1],
                "data_dir": str(data_dir),
                "root": str(program_root),
                "instance_id": instance_id,
                "version": "fixture",
                "started_at": runtime_start_text,
            }))
            store = Store(data_dir / "world-insight.sqlite")
            try:
                real_now = store.now
                store.now = lambda: (trial_start - timedelta(hours=1)).isoformat(
                    timespec="microseconds"
                ).replace("+00:00", "Z")
                source = store.create("source", {
                    "name": "[fixture] source", "adapter": "world_bank", "enabled": True,
                    "status": "ready", "budget_daily": 20, "requests_today": 0,
                    "interval_seconds": 604800,
                    "rights": {"fetch": True, "store": True, "display": True,
                               "export": True, "ai": False},
                }, "source-fixture")
                cited_source = store.create("source", {
                    "name": "[fixture] cited manual source", "adapter": "manual", "enabled": True,
                    "status": "manual", "budget_daily": 0, "requests_today": 0,
                    "interval_seconds": 86400,
                }, "source-cited-fixture")
                store.now = real_now
                topics = []
                for number in range(5):
                    topics.append(store.create("topic", {
                        "question": f"[fixture] topic {number}", "status": "active", "followed": True,
                        "is_fixture": False, "country_codes": ["USA"],
                        "source_ids": [source["id"]],
                    }, f"topic-{number}"))
                store.create("observation", {
                    "topic_id": None, "topic_ids": [], "indicator": "SP.POP.TOTL",
                    "country_code": "USA", "period": "2025", "published_at": None,
                    "source_id": source["id"], "evidence_version_ids": [],
                }, "observation-global")
                store.create("change", {
                    "topic_id": topics[0]["id"], "topic_ids": [topics[0]["id"]],
                    "type": "evidence.created", "aggregate_id": "evidence-fixture",
                    "discovered_at": "2026-09-22T01:00:00Z", "occurred_at": None,
                    "status": "unverified", "needs_review": False,
                    "evidence_version_ids": [],
                }, "change-fixture")
                cited_evidence = store.create("evidence", {
                    "title": "[fixture] cited version one", "topic_id": "outside-selected-topics",
                    "topic_ids": ["outside-selected-topics"], "source_id": cited_source["id"],
                    "source_record_id": "cited-1", "published_at": None,
                    "source_updated_at": None, "collected_at": trial_start_text,
                    "discovered_at": trial_start_text, "status": "unverified",
                    "is_fixture": False,
                }, "evidence-cited")
                store.update("evidence", cited_evidence["id"], {
                    "title": "[fixture] cited version two",
                }, cited_evidence["version"])
                store.create("evidence_acquisition", {
                    "evidence_id": cited_evidence["id"],
                    "evidence_version_id": f"{cited_evidence['id']}@1",
                    "source_id": cited_source["id"], "source_version": cited_source["version"],
                    "job_id": None, "job_version": None,
                    "collected_at": trial_start_text, "received_at": trial_start_text,
                }, "acquisition-cited")
                store.create("judgment", {
                    "topic_id": topics[0]["id"], "conclusion": "[fixture] judgment",
                    "judgment_type": "assessment",
                    "evidence_version_ids": [f"{cited_evidence['id']}@1"],
                    "opposing_evidence_version_ids": [], "missing_evidence": [],
                    "review_date": None, "status": "draft", "reviewer": None,
                }, "judgment-fixture")
                job = store.create("collection_job", {
                    "source_id": source["id"], "topic_id": topics[0]["id"],
                    "state": "retry", "attempts": 1, "request_count": 1,
                    "last_error": "[fixture] temporary failure", "coverage_gaps": [],
                }, "job-fixture")
                source = store.update("source", source["id"], {
                    "status": "failed", "last_error": "[fixture] temporary failure",
                }, source["version"])
                source = store.update("source", source["id"], {
                    "status": "ready", "last_error": None,
                }, source["version"])
                store.update("collection_job", job["id"], {
                    "state": "complete", "last_error": None,
                }, job["version"])
            finally:
                store.close()

            output = base / "snapshot.json"
            command = [
                sys.executable, str(SCRIPT), str(data_dir), str(output),
                "--phase", "start", "--reviewer", "fixture checker",
                "--expected-instance-id", instance_id,
                "--trial-start-at", trial_start_text,
            ]
            for topic in topics:
                command.extend(["--topic-id", topic["id"]])
            result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(output.read_text())

            self.assertEqual(payload["schema"], "world_insight_trial_snapshot/v2")
            self.assertEqual(payload["counts"]["observation"], 1)
            self.assertEqual(payload["per_topic_counts"][topics[0]["id"]]["observation"], 1)
            self.assertEqual(payload["records"]["change"][0]["type"], "evidence.created")
            self.assertEqual(payload["records"]["change"][0]["discovered_at"], "2026-09-22T01:00:00Z")
            self.assertEqual(payload["citation_versions"][0]["version_id"], "evidence-cited@1")
            self.assertEqual(payload["citation_versions"][0]["title"], "[fixture] cited version one")
            self.assertIn("source-cited-fixture", {row["id"] for row in payload["sources"]})
            self.assertIn("acquisition-cited", {row["id"] for row in payload["acquisition_receipts"]})
            self.assertEqual(payload["program_root"], str(program_root.resolve()))
            self.assertEqual(payload["program_git_commit"], runtime_commit)
            self.assertEqual(payload["git_commit"], runtime_commit)
            self.assertFalse(payload["minimum_168h_elapsed"])
            self.assertGreaterEqual(payload["trial_elapsed_seconds"], 5)
            self.assertNotEqual(payload["snapshot_tool_git_commit"], runtime_commit)
            self.assertEqual(
                [row["status"] for row in payload["source_version_history"]
                 if row["id"] == source["id"]],
                ["ready", "failed", "ready"],
            )
            self.assertEqual(
                [row["state"] for row in payload["collection_job_version_history"]],
                ["retry", "complete"],
            )

            duplicate = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
            self.assertNotEqual(duplicate.returncode, 0)
            self.assertIn("refusing to overwrite", duplicate.stderr)

            daily_output = base / "daily.json"
            daily_command = list(command)
            daily_command[daily_command.index(str(output))] = str(daily_output)
            daily_command[daily_command.index("start")] = "daily"
            start_sha256 = hashlib.sha256(output.read_bytes()).hexdigest()
            daily_command.extend([
                "--start-snapshot", str(output), "--expected-start-sha256", start_sha256,
            ])
            daily = subprocess.run(daily_command, cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(daily.returncode, 0, daily.stderr)
            daily_payload = json.loads(daily_output.read_text())
            self.assertEqual(
                daily_payload["start_snapshot_sha256"],
                start_sha256,
            )

            stale_output = base / "stale-start.json"
            stale_command = list(command)
            stale_command[stale_command.index(str(output))] = str(stale_output)
            stale_command[stale_command.index("--trial-start-at") + 1] = (
                trial_start - timedelta(hours=1)
            ).isoformat(timespec="microseconds").replace("+00:00", "Z")
            stale = subprocess.run(stale_command, cwd=ROOT, text=True, capture_output=True)
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("within 15 minutes", stale.stderr)

            early_end_output = base / "early-end.json"
            early_end_command = list(command)
            early_end_command[early_end_command.index(str(output))] = str(early_end_output)
            early_end_command[early_end_command.index("start")] = "end"
            early_end_command.extend([
                "--start-snapshot", str(output), "--expected-start-sha256", start_sha256,
            ])
            early_end = subprocess.run(early_end_command, cwd=ROOT, text=True, capture_output=True)
            self.assertNotEqual(early_end.returncode, 0)
            self.assertIn("at least 168 real hours", early_end.stderr)

            (program_root / "untracked.txt").write_text("fixture dirty worktree")
            dirty_output = base / "dirty-start.json"
            dirty_command = list(command)
            dirty_command[dirty_command.index(str(output))] = str(dirty_output)
            dirty = subprocess.run(dirty_command, cwd=ROOT, text=True, capture_output=True)
            self.assertNotEqual(dirty.returncode, 0)
            self.assertIn("clean Git program root", dirty.stderr)


if __name__ == "__main__":
    unittest.main()
