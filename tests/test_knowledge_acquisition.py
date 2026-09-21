"""Isolated SQLite fixtures for the receipt helper, not wired HTTP/browser acceptance."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.modules import knowledge
from server.modules.knowledge import acquisition
from server.modules.knowledge.rights import build_policy_context
from server.platform.errors import ApiError
from server.platform.store import Store


WEEK = "2026-09-14T09:00:00.000000Z"
TODAY = "2026-09-21T09:00:00.000000Z"


class AcquisitionReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="world-insight-acquisition-fixture-")
        self.path = Path(self.tmp.name) / "fixture.sqlite3"
        self.store = Store(self.path)
        self.now = WEEK
        self.store.now = lambda: self.now
        self.source = self.store.create("source", {
            "name": "[夹具] 收取凭据来源", "retention_days": 10,
            "rights": {"fetch": True, "store": "metadata", "display": "metadata", "export": "metadata", "ai": False},
        }, record_id="fixture-source")
        self.job = self.store.create("collection_job", {
            "source_id": self.source["id"], "state": "running", "is_fixture": True,
        }, record_id="fixture-job")
        self.evidence = self.material()

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def material(self, **overrides):
        # Represents the persisted result handed to the helper by the ingest owner.
        return self.store.create("evidence", {
            "title": "[夹具] 上周发布的材料", "source_id": self.source["id"],
            "published_at": "2026-09-14T08:00:00Z", "collected_at": WEEK,
            "discovered_at": WEEK, "first_collected_at": WEEK, "ingest_origin": "collector",
            "manually_touched": False, "channels": [], "excerpt": "", "translation": "",
            "rights": self.source["rights"], "status": "unverified", "is_fixture": True,
            **overrides,
        })

    def receipt(self, material=None, **overrides):
        return acquisition.record_acquisition(self.store, material or self.evidence, **{
            "origin": "collector", "source_id": self.source["id"], "job_id": self.job["id"],
            **overrides,
        })

    def test_recollection_changes_only_receipt_not_first_time_versions_expiry_or_outbox(self):
        first = self.receipt()
        initial_history = self.store.history("evidence", self.evidence["id"])
        self.now = TODAY
        policy_before = build_policy_context(self.store.snapshots(), now=TODAY)
        again = self.receipt()
        self.assertEqual(again["collected_at"], TODAY)
        self.assertEqual(again["received_at"], TODAY)
        self.assertEqual(again["version"], first["version"] + 1)
        self.assertEqual(again["evidence_version_id"], f'{self.evidence["id"]}@1')
        self.assertEqual(self.store.get("evidence", self.evidence["id"]), self.evidence)
        self.assertEqual(self.store.history("evidence", self.evidence["id"]), initial_history)
        self.assertEqual(build_policy_context(self.store.snapshots(), now=TODAY), policy_before)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM outbox").fetchone()[0], 0)
        self.assertEqual([row["collected_at"] for row in self.store.history(acquisition.KIND, self.evidence["id"])], [WEEK, TODAY])
        self.store.close()
        self.store = Store(self.path)
        self.assertEqual(acquisition.latest_acquisition(self.store, self.evidence["id"]), again)
        self.assertTrue(self.store.integrity()["ok"])

    def test_retry_is_idempotent_across_offsets_and_late_completion_cannot_regress(self):
        self.now = TODAY
        current = self.receipt(collected_at="2026-09-21T17:00:00+08:00")
        self.now = "2026-09-21T10:00:00.000000Z"
        self.assertEqual(self.receipt(collected_at=TODAY), current)
        self.assertEqual(self.receipt(collected_at=WEEK), current)
        self.assertEqual(len(self.store.history(acquisition.KIND, self.evidence["id"])), 1)
        for value in ("2026-09-21", "2026-09-21T09:00:00", "unknown", 0):
            with self.subTest(value=value), self.assertRaises(ApiError) as caught:
                self.receipt(collected_at=value)
            self.assertEqual(caught.exception.code, "invalid_acquisition_time")
        self.assertEqual(acquisition.latest_acquisition(self.store, self.evidence["id"]), current)

    def test_actual_ingest_composed_in_one_transaction_records_duplicate_but_not_failure(self):
        data = {"title": "[夹具] 正式 ingest 旧文", "url": "https://fixture.example/old-news",
                "source_id": self.source["id"], "published_at": "2026-09-14T08:00:00Z", "is_fixture": True}
        # Explicit composition is the integration contract, not a claim that the
        # production ingest or Scheduler call sites have already been changed.
        with self.store.transaction():
            first = knowledge.ingest(self.store, data, origin="collector")
            self.receipt(first)
        saved = self.store.get("evidence", first["id"])
        self.now = TODAY
        with self.store.transaction():
            duplicate = knowledge.ingest(self.store, data, origin="collector")
            latest = self.receipt(duplicate)
        self.assertTrue(duplicate["deduplicated"])
        self.assertEqual(latest["collected_at"], TODAY)
        self.assertEqual(self.store.get("evidence", first["id"]), saved)
        receipts_before = acquisition.acquisition_index(self.store)
        with self.assertRaises(ApiError):
            with self.store.transaction():
                result = knowledge.ingest(self.store, {**data, "title": ""}, origin="collector")
                self.receipt(result)
        self.assertEqual(acquisition.acquisition_index(self.store), receipts_before)

    def test_manual_edit_and_suppressed_deletion_do_not_refresh_or_reappear(self):
        first = self.receipt()
        self.now = TODAY
        edited = self.store.update("evidence", self.evidence["id"], {"notes": "[夹具] 人工笔记"}, 1)
        self.assertIsNone(self.receipt(edited, origin="manual"))
        self.assertEqual(acquisition.latest_acquisition(self.store, edited["id"]), first)
        self.assertIsNone(self.receipt({**edited, "suppressed": "deleted"}))
        deleted = self.store.update("evidence", edited["id"], {"deleted": True}, edited["version"])
        self.assertIsNone(self.receipt(deleted))
        # Defensive check also consults the current tombstone, not just the result.
        self.assertIsNone(self.receipt({**deleted, "deleted": False}))
        self.assertEqual(acquisition.latest_acquisition(self.store, edited["id"]), first)
        fresh = self.material()
        self.assertIsNone(self.receipt(fresh, origin="manual"))
        self.assertIsNone(acquisition.latest_acquisition(self.store, fresh["id"]))

    def test_same_transaction_failure_rolls_back_material_and_receipt_together(self):
        first = self.receipt()
        self.now = TODAY
        with self.assertRaisesRegex(RuntimeError, "batch failure"):
            with self.store.transaction():
                edited = self.store.update("evidence", self.evidence["id"], {"title": "[夹具] 新字段"}, 1)
                self.receipt(edited)
                created = self.material()
                self.receipt(created)
                raise RuntimeError("batch failure after ingestion")
        self.assertEqual(self.store.get("evidence", self.evidence["id"]), self.evidence)
        self.assertEqual(acquisition.latest_acquisition(self.store, self.evidence["id"]), first)
        self.assertIsNone(acquisition.latest_acquisition(self.store, created["id"]))
        self.assertEqual(self.store.list("evidence")["total"], 1)
        with self.assertRaises(ApiError):
            with self.store.transaction():
                created = self.material()
                self.receipt(created, job_id="nonexistent-job")
        self.assertIsNone(acquisition.latest_acquisition(self.store, created["id"]))
        self.assertEqual(self.store.list("evidence")["total"], 1)

    def test_source_and_job_versions_are_traceable_without_writing_their_entities(self):
        first = self.receipt()
        self.assertEqual((first["source_version"], first["job_version"]), (1, 1))
        source_b = self.store.create("source", {"name": "[夹具] 第二来源"}, record_id="fixture-other")
        job_b = self.store.create("collection_job", {"source_id": source_b["id"]}, record_id="fixture-other-job")
        linked = self.store.update("evidence", self.evidence["id"], {"channels": [{"source_id": source_b["id"]}]}, 1)
        second = self.receipt(linked, source_id=source_b["id"], job_id=job_b["id"])
        self.assertEqual(second["collected_at"], first["collected_at"])
        self.assertEqual(second["source_id"], source_b["id"])
        self.assertEqual(second["evidence_version_id"], f'{linked["id"]}@2')
        self.assertEqual(self.store.history(acquisition.KIND, linked["id"])[0]["job_id"], self.job["id"])
        self.assertEqual(self.store.get("collection_job", job_b["id"]), job_b)
        self.assertEqual(self.store.get("source", source_b["id"]), source_b)
        with self.assertRaises(ApiError) as caught:
            self.receipt(linked, source_id=source_b["id"], job_id=self.job["id"])
        self.assertEqual(caught.exception.code, "acquisition_source_mismatch")
        with self.assertRaises(ApiError):
            self.receipt(linked, source_id="unrelated", job_id=None)
        with self.assertRaises(ApiError) as caught:
            self.receipt(self.evidence)
        self.assertEqual(caught.exception.code, "acquisition_version_conflict")

    def test_unknown_legacy_source_and_job_remain_unknown_not_inferred(self):
        legacy = self.material(source_id="fixture-legacy")
        receipt = self.receipt(legacy, source_id="fixture-legacy", job_id=None)
        self.assertIsNone(receipt["source_version"])
        self.assertIsNone(receipt["job_id"])
        self.assertIsNone(receipt["job_version"])

    def test_receipt_is_content_free_even_for_expired_or_restricted_material(self):
        # The helper never receives permission to copy bodies or restore them.
        restricted = self.material(status="restricted", content_expired=True,
            excerpt="[夹具] 不得复制的旧正文", translation="[夹具] 不得复制的译文", content_fingerprint="fixture-secret")
        receipt = self.receipt(restricted)
        self.assertEqual(receipt["evidence_version_id"], f'{restricted["id"]}@1')
        for key in ("excerpt", "translation", "content_fingerprint", "title", "url", "rights", "notes", "first_collected_at"):
            self.assertNotIn(key, receipt)
        self.assertEqual(self.store.get("evidence", restricted["id"]), restricted)

    def test_read_helpers_do_not_invent_history_or_swallow_other_store_errors(self):
        self.assertIsNone(acquisition.latest_acquisition(self.store, self.evidence["id"]))
        self.assertEqual(acquisition.acquisition_index(self.store), {})
        receipt = self.receipt()
        self.assertEqual(acquisition.acquisition_index(self.store), {self.evidence["id"]: receipt})
        for error in (ApiError(503, "not_found", "[夹具] 服务错误"), ApiError(404, "another_error", "[夹具] 其他错误")):
            with self.subTest(code=error.code, status=error.status):
                with patch.object(self.store, "get", side_effect=error), self.assertRaises(ApiError) as caught:
                    acquisition.latest_acquisition(self.store, self.evidence["id"])
                self.assertIs(caught.exception, error)


if __name__ == "__main__":
    unittest.main()
