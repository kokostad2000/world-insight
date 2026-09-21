"""Isolated fixtures; these are domain/SQLite tests, not real-source or browser acceptance."""
import json
import tempfile
import unittest
from pathlib import Path
from server.platform.errors import ApiError
from server.platform.store import Store
from server.modules import knowledge, research


class CoreDomainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="world-insight-core-fixture-")
        self.path = Path(self.tmp.name) / "core.sqlite3"
        self.store = Store(self.path)
        self.topic = self.call("POST", "topics", {"question": "[测试夹具] 航道政策变化", "is_fixture": True})

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def call(self, method, path, data=None, query=None):
        for module in (knowledge, research):
            result = module.handle(self.store, method, path.split("/"), data or {}, query or {})
            if result is not None:
                return result
        self.fail("Unmatched route")

    def evidence(self, **patch):
        # This tiny synthetic document is complete; partial excerpts have separate non-merge regression cases.
        return self.call("POST", "evidence", {"title": "[测试夹具] 官方通告", "url": "https://fixture.example/policy", "topic_id": self.topic["id"], "rights": {"store": True, "display": True, "export": True}, "excerpt": "夹具：这是用于验证版本留存的通告", "content_scope":"full", "is_fixture": True, **patch})

    def judgment(self, evidence=None, **patch):
        return self.call("POST", "judgments", {"topic_id": self.topic["id"], "conclusion": "[测试夹具] 尚须验证政策是否执行", "evidence_version_ids": [evidence["version_id"]] if evidence else [], "assumptions": ["执行主体遵循已公布政策"], "confidence_reason": "仅有一份文件，未验证执行", "review_date": "2026-10-01", "reviewer": "夹具审阅者", "status": "reviewed", "is_fixture": True, **patch})

    def test_closed_loop_persist_revision_conflict_and_export(self):
        evidence = self.evidence(published_at="2026-09-10")
        claim = self.call("POST", "claims", {"subject": "测试主体", "statement": "宣布政策，尚未证实实施", "evidence_version_ids": [evidence["version_id"]], "topic_id": self.topic["id"]})
        event = self.call("POST", "events", {"title": "政策宣布", "topic_id": self.topic["id"], "claim_ids": [claim["id"]], "occurred_at": "2026-09-10", "time_precision": "day", "location": {"country_code": "CHN", "name": "中国", "precision": "country"}})
        self.assertEqual(event["verification_status"], "unverified")
        judgment = self.judgment(evidence)
        self.store.close()
        self.store = Store(self.path)
        updated = self.call("PATCH", f'judgments/{judgment["id"]}', {"expected_version": 1, "conclusion": "政策生效仍未确认", "change_reason": "复查原文后明确未知项"})
        self.assertEqual(updated["version"], 2)
        with self.assertRaises(ApiError) as caught:
            self.call("PATCH", f'judgments/{judgment["id"]}', {"expected_version": 1, "conclusion": "第二窗口旧内容", "change_reason": "模拟过期窗口"})
        self.assertEqual(caught.exception.status, 409)
        exported = self.call("GET", "exports", query={"topic_id": self.topic["id"]})
        self.assertEqual(exported["histories"]["judgments"][judgment["id"]][0]["conclusion"], judgment["conclusion"])
        self.assertEqual(exported["citations"][0]["published_at"], "2026-09-10")
        self.assertTrue(self.store.integrity()["ok"])

    def test_precise_dedup_keeps_channels_and_multi_topic_unlink(self):
        first = self.evidence()
        other = self.call("POST", "topics", {"question": "[夹具] 第二议题"})
        duplicate = self.evidence(url="https://fixture.example/policy?utm_source=rss", source_id="rss", topic_id=other["id"])
        self.assertEqual(first["id"], duplicate["id"])
        self.assertEqual(len(duplicate["channels"]), 2)
        self.assertEqual(set(duplicate["topic_ids"]), {self.topic["id"], other["id"]})
        self.assertEqual(self.call("GET", "evidence", query={"topic_id": other["id"]})["total"], 1)
        moved = self.call("PATCH", f'evidence/{first["id"]}', {"topic_ids": [other["id"]], "expected_version": duplicate["version"]})
        self.assertEqual(moved["topic_id"], other["id"])
        self.assertEqual(self.call("GET", "evidence", query={"topic_id": self.topic["id"]})["total"], 0)
        self.assertEqual(len(self.store.history("evidence", first["id"])), 3)

    def test_repeated_ingest_is_idempotent(self):
        first = self.evidence()
        again = self.evidence()
        self.assertEqual(again["version"], 1)
        self.assertEqual(first["id"], again["id"])

    def test_older_database_channel_identities_are_backfilled(self):
        # Simulate a persisted database from before aliases existed, not a mocked Store.
        old = self.store.create('evidence', {
            'title':'[旧版夹具] 已合并材料','source_id':'manual','source_record_id':None,
            'url':'https://fixture.example/original','excerpt':'','topic_id':self.topic['id'],
            'topic_ids':[self.topic['id']], 'rights':{'store':'metadata','display':'metadata','export':'metadata'},
            'channels':[{'source_id':'manual','url':'https://fixture.example/original'},
                        {'source_id':'rss','source_record_id':'alternate','url':'https://fixture.example/alternate'}]})
        fetched = self.evidence(title='[旧版夹具] 已合并材料',source_id='rss',source_record_id='alternate',
                                url='https://fixture.example/alternate',excerpt='')
        self.assertEqual(fetched['id'],old['id'])
        self.assertEqual(self.store.list('evidence')['total'],1)
        self.assertEqual(self.store.get('knowledge_index','evidence-alias-v1')['revision'],1)

    def test_similar_titles_do_not_merge_and_cannot_infer_event_time(self):
        a = self.evidence(excerpt="", title="某地区宣布停火", url="https://fixture.example/a")
        b = self.evidence(excerpt="", title="某地区宣布停火", url="https://fixture.example/b")
        self.assertNotEqual(a["id"], b["id"])
        result = self.call("GET", "evidence", query={"similar_to": a["id"]})
        self.assertEqual(result["items"][0]["association_status"], "candidate_only")
        event = self.call("POST", "events", {"title": "未知实施状态的宣布", "topic_id": self.topic["id"], "evidence_version_ids": [a["version_id"]]})
        self.assertIsNone(event["occurred_at"])
        self.assertEqual(event["time_precision"], "unknown")
        self.assertEqual(self.call("GET", "events", query={"since": "2026-09-20"})["total"], 0)

    def test_conflicting_claims_stay_separate(self):
        evidence = self.evidence()
        claims = [self.call("POST", "claims", {"subject": subject, "statement": statement, "evidence_version_ids": [evidence["version_id"]], "dispute_status": "disputed"}) for subject, statement in (("来源甲", "5人"), ("来源乙", "12人"))]
        event = self.call("POST", "events", {"title": "伤亡说法存在分歧", "claim_ids": [c["id"] for c in claims], "verification_status": "disputed"})
        self.assertEqual(len(event["claim_ids"]), 2)
        self.assertNotIn("casualties", event)

    def test_format_change_preserves_research_review_state(self):
        evidence = self.evidence()
        judgment = self.judgment(evidence)
        updated = self.evidence(excerpt="夹具：这是用于验证版本留存的通告 ")
        self.store.drain([research.on_event], limit=100)
        self.assertEqual(self.store.get("judgment", judgment["id"])["status"], "reviewed")
        changed = self.evidence(title="[测试夹具] 官方通告（格式修订）")
        self.assertTrue(changed["change_candidate"])
        self.store.drain([research.on_event], limit=100)
        self.assertEqual(self.store.get("judgment", judgment["id"])["status"], "reviewed")
        self.assertEqual(changed["status"], "unverified")

    def test_correction_propagates_idempotently_and_preserves_history(self):
        evidence = self.evidence()
        judgment = self.judgment(evidence)
        scenario = self.call("POST", "scenarios", {"topic_id": self.topic["id"], "title": "夹具情景", "description": "可能进一步限制通行", "evidence_version_ids": [evidence["version_id"]]})
        path = self.call("POST", "impact-paths", {"topic_id": self.topic["id"], "title": "路径夹具", "nodes": [{"id": "a", "label": "通道限制"}, {"id": "b", "label": "运输延迟"}, {"id": "c", "label": "供应压力"}], "edges": [{"from": "a", "to": "b", "status": "assumption", "evidence_version_ids": [evidence["version_id"]]}, {"from": "b", "to": "c", "status": "unverified"}]})
        self.call("POST", f'evidence/{evidence["id"]}/corrections', {"expected_version": evidence["version"], "reason": "发布者正式撤回", "status": "withdrawn", "substantive": True})
        row = self.store.db.execute("SELECT * FROM outbox WHERE type='evidence.corrected'").fetchone()
        event = dict(row)
        event["payload"] = json.loads(event["payload"])
        research.on_event(self.store, event)
        once = self.store.get("judgment", judgment["id"])
        research.on_event(self.store, event)
        self.assertEqual(once["version"], self.store.get("judgment", judgment["id"])["version"])
        self.assertEqual(once["status"], "needs_review")
        self.assertEqual(self.store.history("judgment", judgment["id"])[0]["status"], "reviewed")
        self.assertEqual(self.store.get("scenario", scenario["id"])["status"], "needs_review")
        revised_path = self.store.get("impact_path", path["id"])
        self.assertTrue(revised_path["edges"][0]["needs_review"])
        self.assertFalse(revised_path["edges"][1]["needs_review"])
        self.assertEqual(self.store.version(evidence["version_id"])["excerpt"], evidence["excerpt"])

    def test_no_substantive_confirmation_no_retraction(self):
        evidence = self.evidence()
        with self.assertRaises(ApiError):
            self.call("POST", f'evidence/{evidence["id"]}/corrections', {"expected_version": 1, "reason": "只有换行变化", "status": "withdrawn", "substantive": False})
        self.assertEqual(self.store.get("evidence", evidence["id"])["version"], 1)

    def test_country_position_cannot_claim_exact_coordinates(self):
        with self.assertRaises(ApiError):
            self.call("POST", "events", {"title": "国家范围事件", "location": {"precision": "country", "country_code": "CHN", "lat": 35, "lon": 105}})

    def test_annual_metrics_preserve_period_and_unknown(self):
        data = {"indicator": "GDP", "country_code": "CHN", "period": "2024", "value": None, "unit": "USD", "frequency": "annual", "source_id": "wdi", "topic_id": self.topic["id"]}
        first = knowledge.upsert_observation(self.store, data)
        second = knowledge.upsert_observation(self.store, data)
        self.assertEqual(first["version"], second["version"])
        revised = knowledge.upsert_observation(self.store, {**data, "value": 100})
        self.assertEqual(revised["version"], 2)
        self.assertEqual(revised["period"], "2024")
        self.assertIsNone(self.store.history("observation", first["id"])[0]["value"])

    def test_same_indicator_url_distinct_observation_identity(self):
        a = self.evidence(source_id="wdi", source_record_id="GDP:2024", excerpt="")
        b = self.evidence(source_id="wdi", source_record_id="GDP:2025", excerpt="")
        self.assertNotEqual(a["id"], b["id"])

    def test_assumption_judgment_mark_survives_review_and_export(self):
        judgment = self.judgment()
        self.assertEqual(judgment["evidence_support"], "assumption_only")
        exported = self.call("GET", "exports", query={"topic_id": self.topic["id"], "format": "markdown"})
        self.assertIn("假设型暂定判断／缺乏证据支持", exported["content"])
        with self.assertRaises(ApiError):
            self.judgment(assumptions=[])

    def test_reviewed_scenario_can_truthfully_lack_opposition(self):
        evidence = self.evidence()
        scenario = self.call("POST", "scenarios", {"topic_id": self.topic["id"], "title": "夹具竞争情景", "description": "通道恢复", "evidence_version_ids": [evidence["version_id"]], "assumptions": ["协商继续"], "signals": ["发布正式安排"], "counterevidence_search": "尚未找到；已查官方材料", "invalidation_conditions": "谈判中止", "valid_until": "2026-12-31", "review_date": "2026-10-01", "reviewer": "本地用户", "status": "reviewed"})
        self.assertEqual(scenario["opposing_evidence_version_ids"], [])

    def test_indeterminate_review_is_separate_and_references_old_judgment(self):
        judgment = self.judgment()
        review = self.call("POST", "reviews", {"judgment_id": judgment["id"], "judgment_version": 1, "outcome": "indeterminate", "rationale": "未取得执行结果材料"})
        self.assertEqual(review["topic_id"], self.topic["id"])
        result = self.call("GET", "reviews")
        self.assertEqual(result["summary"]["indeterminate_count"], 1)
        self.assertEqual(result["summary"]["decidable_count"], 0)

    def test_split_preserves_history_and_marks_dependents(self):
        evidence = self.evidence()
        merged = self.evidence(source_id="rss", url="https://fixture.example/repost")
        judgment = self.judgment(evidence)
        result = self.call("POST", f'evidence/{evidence["id"]}/split', {"expected_version": merged["version"], "reason": "两个渠道误合并", "channels": [merged["channels"][1]]})
        self.assertNotEqual(result["original"]["id"], result["split"]["id"])
        self.store.drain([research.on_event], limit=100)
        self.assertEqual(self.store.get("judgment", judgment["id"])["status"], "needs_review")
        repeated = self.evidence(source_id="rss", url="https://fixture.example/repost")
        self.assertEqual(repeated["id"], result["split"]["id"])

    def test_review_clears_due_date_only_for_current_version(self):
        judgment = self.judgment(review_date="2026-09-01")
        self.call("POST", "reviews", {"judgment_id": judgment["id"], "judgment_version": 1, "outcome": "indeterminate", "rationale": "夹具：本轮已核查，无法判定"})
        current = self.store.get("judgment", judgment["id"])
        self.assertIsNone(current["review_date"])
        self.assertEqual(current["last_reviewed_version"], 1)
        self.call("PATCH", f'judgments/{judgment["id"]}', {"expected_version": current["version"], "review_date": "2026-10-01", "change_reason": "新增后续观察期限"})
        self.call("POST", "reviews", {"judgment_id": judgment["id"], "judgment_version": 1, "outcome": "indeterminate", "rationale": "只补录历史复盘"})
        self.assertEqual(self.store.get("judgment", judgment["id"])["review_date"], "2026-10-01")

    def test_ten_reports_share_one_identified_source_chain(self):
        original = self.evidence(excerpt="", material_type="official_document")
        for n in range(9):
            self.evidence(excerpt="", url=f"https://fixture.example/report-{n}", title=f"夹具报道 {n}", origin_evidence_id=original["id"])
        result = self.call("GET", "evidence")
        self.assertEqual(result["source_counts"]["report_count"], 10)
        self.assertEqual(result["source_counts"]["identified_source_chain_count"], 1)
        self.assertIn("不等于", result["source_counts"]["note"])

    def test_history_endpoint_obeys_current_display_restriction(self):
        evidence = self.evidence()
        self.call("POST", f'evidence/{evidence["id"]}/corrections', {"expected_version": 1, "reason": "来源收紧展示范围", "status": "restricted", "substantive": False})
        history = self.call("GET", f'evidence/{evidence["id"]}/history')
        self.assertTrue(all(not row["excerpt"] for row in history["items"]))

    def test_repeated_channel_without_excerpt_uses_persistent_alias(self):
        first = self.evidence()
        second = self.evidence(source_id="rss", url="https://fixture.example/repost", source_record_id="rss-article")
        self.assertEqual(first["id"], second["id"])
        self.store.close()
        self.store = Store(self.path)
        third = self.evidence(source_id="rss", url="https://fixture.example/repost", source_record_id="rss-article", excerpt="")
        self.assertEqual(first["id"], third["id"])
        self.assertEqual(self.call("GET", "evidence")["total"], 1)

    def test_transitive_reposts_share_one_origin_chain(self):
        first = self.evidence(excerpt="")
        second = self.evidence(excerpt="", url="https://fixture.example/repost-a", origin_evidence_id=first["id"])
        self.evidence(excerpt="", url="https://fixture.example/repost-b", origin_evidence_id=second["id"])
        counts = self.call("GET", "evidence")["source_counts"]
        self.assertEqual(counts["identified_source_chain_count"], 1)
        self.assertEqual(counts["independence_unconfirmed_count"], 0)

    def test_export_filters_rights_and_secrets(self):
        marker = "STORED_BUT_NOT_DISPLAYABLE_FIXTURE_7741"
        self.store.create("source", {"name": "夹具来源", "api_key": "DO_NOT_EXPORT", "rights": {"store": True, "display": False, "export": False}}, record_id="secret-source")
        evidence = self.evidence(source_id="secret-source", excerpt=marker, rights={"store": True, "display": True, "export": False})
        self.assertEqual(evidence["excerpt"], "")
        self.assertEqual(self.store.get("evidence", evidence["id"])["excerpt"], marker)
        self.judgment(evidence)
        exported = self.call("GET", "exports", query={"topic_id": self.topic["id"]})
        serialized = json.dumps(exported, ensure_ascii=False)
        self.assertNotIn("DO_NOT_EXPORT", serialized)
        self.assertNotIn(marker, serialized)
        self.assertIn("content_restricted", serialized)

    def test_restriction_propagates_without_erasing_metadata(self):
        evidence = self.evidence()
        judgment = self.judgment(evidence)
        self.call("POST", f'evidence/{evidence["id"]}/corrections', {"expected_version": 1, "reason": "来源展示权限改变", "status": "restricted", "substantive": False, "rights": {"store": True, "display": False, "export": False}})
        self.store.drain([research.on_event])
        self.assertEqual(self.store.get("judgment", judgment["id"])["status"], "needs_review")
        exported = self.call("GET", "exports", query={"topic_id": self.topic["id"]})
        self.assertEqual(exported["citations"][0]["excerpt"], "")
        self.assertEqual(exported["citations"][0]["title"], evidence["title"])


if __name__ == "__main__":
    unittest.main()
