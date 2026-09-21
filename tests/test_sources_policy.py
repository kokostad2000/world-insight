"""Country-scoped WDI and source policy events; isolated SQLite, no network."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.modules import knowledge, research, sources
from server.modules.sources import adapters
from server.platform.errors import ApiError
from server.platform.store import Store


class SourcePolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='world-insight-source-policy-fixture-')
        self.store = Store(Path(self.temp.name) / 'test.sqlite')
        self.store.now = lambda: '2026-09-21T02:00:00.000000Z'
        sources.seed_sources(self.store)
        self.calls = []

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def topic(self, countries):
        return research.handle(self.store, 'POST', ['topics'], {'question': '[夹具] 国家背景', 'is_fixture': True,
            'source_ids': ['source-world-bank'], 'country_codes': countries}, {})

    def topic_patch(self, topic, **patch):
        old = self.store.get('topic', topic['id'])
        return research.handle(self.store, 'PATCH', ['topics', topic['id']], {'expected_version': old['version'], **patch}, {})

    def source_patch(self, **patch):
        old = self.store.get('source', 'source-world-bank')
        return sources.handle(self.store, 'PATCH', ['sources', old['id']], {'expected_version': old['version'], **patch}, {})

    def payload(self, page=1, pages=1):
        # Deliberately return a country outside a USA-only request as a defensive parsing check.
        return adapters.Response(200, json.dumps([{'page': page, 'pages': pages, 'lastupdated': '2026-07-13'}, [
            {'indicator': {'id': 'SP.POP.TOTL'}, 'countryiso3code': country, 'date': str(2026-page), 'value': 0 if country == 'USA' else None}
            for country in ('USA', 'CHN')]]).encode())

    def fetch(self, url, headers):
        self.calls.append(url)
        return self.payload()

    def events(self):
        return [json.loads(row[0]) for row in self.store.db.execute("SELECT payload FROM outbox WHERE type='source.policy_changed' ORDER BY rowid")]

    def test_country_intersection_controls_request_response_and_global_storage(self):
        topic = self.topic(['USA', 'GBR'])
        job = sources.enqueue(self.store, 'source-world-bank', topic['id'])['job']
        self.assertEqual(job['country_codes'], ['USA'])
        result = sources.Scheduler(self.store, fetcher=self.fetch).tick(False)
        self.assertEqual(result['state'], 'complete')
        self.assertIn('/country/USA/', self.calls[0]); self.assertNotIn('CHN', self.calls[0])
        observations = self.store.all('observation')
        self.assertEqual([(r['country_code'], r['period'], r['value']) for r in observations], [('USA', '2025', 0)])
        self.assertTrue(all(r['topic_id'] is None and r.get('topic_ids') == [] for r in observations + self.store.all('evidence')))
        self.assertEqual([r['country_code'] for r in research.bundle(self.store, topic['id'])['observations']], ['USA'])

    def test_no_explicit_or_disjoint_country_never_infers_country_or_consumes_budget(self):
        for countries in ([], ['GBR']):
            with self.subTest(countries=countries):
                topic = self.topic(countries)
                with self.assertRaises(ApiError) as rejected:
                    sources.enqueue(self.store, 'source-world-bank', topic['id'])
                self.assertEqual(rejected.exception.code, 'world_bank_country_scope_empty')
                sources.Scheduler(self.store, fetcher=self.fetch)._schedule_due()
                self.assertEqual(self.store.all('collection_job'), [])
                coverage = sources.coverage(self.store, topic['id'])
                self.assertNotEqual(coverage['coverage_status'], 'complete')
                self.assertIsNone(coverage['empty_reason'])
                self.assertIn('国家', coverage['sources'][0]['reason'])
        self.assertEqual(self.calls, [])
        self.assertEqual(self.store.get('source', 'source-world-bank')['requests_today'], 0)

    def test_country_edit_invalidates_success_and_resets_query_checkpoint(self):
        topic = self.topic(['USA'])
        sources.enqueue(self.store, 'source-world-bank', topic['id'])
        scheduler = sources.Scheduler(self.store, fetcher=self.fetch)
        scheduler.tick(False)
        self.assertEqual(sources.coverage(self.store, topic['id'])['coverage_status'], 'complete')
        self.topic_patch(topic, country_codes=['CHN'])
        self.assertEqual(sources.coverage(self.store, topic['id'])['coverage_status'], 'unavailable')
        scheduler._schedule_due()
        job = self.store.all('collection_job')[0]
        self.assertEqual(job['country_codes'], ['CHN'])
        self.assertEqual(job['checkpoint']['page'], 1)
        self.assertIsNone(job['last_success'])
        scheduler.tick(False)
        self.assertIn('/country/CHN/', self.calls[-1])
        self.assertEqual([r['country_code'] for r in research.bundle(self.store, topic['id'])['observations']], ['CHN'])
        self.assertEqual({r['country_code'] for r in self.store.all('observation')}, {'USA', 'CHN'})

    def test_country_edit_during_network_discards_old_scope_response(self):
        topic = self.topic(['USA'])
        sources.enqueue(self.store, 'source-world-bank', topic['id'])
        def upstream(url, headers):
            self.calls.append(url)
            self.topic_patch(topic, country_codes=['CHN'])
            return self.payload()
        result = sources.Scheduler(self.store, fetcher=upstream).tick(False)
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual(self.store.all('observation'), [])
        self.assertEqual(self.store.all('evidence'), [])
        self.assertEqual(self.store.get('source', 'source-world-bank')['requests_today'], 1)

    def test_country_selection_survives_restart_and_pagination(self):
        topic = self.topic(['USA'])
        sources.enqueue(self.store, 'source-world-bank', topic['id'])
        result = sources.Scheduler(self.store, fetcher=lambda *_: self.payload(1, 2)).tick(False)
        self.assertEqual(result['checkpoint']['page'], 2)
        self.store.close()
        self.store = Store(Path(self.temp.name) / 'test.sqlite')
        self.store.now = lambda: '2026-09-21T02:01:00.000000Z'
        def second(url, headers):
            self.calls.append(url)
            return self.payload(2, 2)
        result = sources.Scheduler(self.store, fetcher=second).tick(False)
        self.assertEqual(result['state'], 'complete')
        self.assertIn('/country/USA/', self.calls[0]); self.assertIn('page=2', self.calls[0])
        self.assertEqual({r['country_code'] for r in self.store.all('observation')}, {'USA'})
        self.assertEqual({r['period'] for r in self.store.all('observation')}, {'2024', '2025'})

    def test_global_refresh_preserves_existing_manual_topic_associations(self):
        topic = self.topic(['USA'])
        sources.enqueue(self.store, 'source-world-bank', topic['id'])
        scheduler = sources.Scheduler(self.store, fetcher=self.fetch)
        scheduler.tick(False)
        manual_topic = self.topic(['CHN'])
        evidence = self.store.all('evidence')[0]
        observation = self.store.all('observation')[0]
        knowledge.handle(self.store, 'PATCH', ['evidence', evidence['id']], {'expected_version': evidence['version'], 'topic_id': manual_topic['id'], 'notes': '[夹具] 人工关联的资料'}, {})
        knowledge.handle(self.store, 'PATCH', ['metrics', observation['id']], {'expected_version': observation['version'], 'topic_id': manual_topic['id']}, {})
        sources.enqueue(self.store, 'source-world-bank', topic['id'])
        scheduler.tick(False)
        self.assertEqual(self.store.get('evidence', evidence['id'])['topic_id'], manual_topic['id'])
        self.assertEqual(self.store.get('observation', observation['id'])['topic_id'], manual_topic['id'])
        self.assertNotIn(topic['id'], self.store.get('observation', observation['id'])['topic_ids'])

    def test_policy_events_only_for_rights_narrowing(self):
        self.source_patch(name='[夹具] 仅修改来源名')
        self.assertEqual(self.events(), [])
        original = self.store.get('source', 'source-world-bank')['rights']
        for action in ('display', 'export', 'store'):
            self.source_patch(rights=original, enabled=False)
            before = len(self.events())
            changed = self.source_patch(rights={**original, action: False}, enabled=False)
            event = self.events()[-1]
            self.assertEqual(len(self.events()), before + 1)
            self.assertEqual(event['source_id'], changed['id'])
            self.assertEqual(event['source_version'], changed['version'])
            self.assertEqual(event['previous_version'], changed['version'] - 1)
            self.assertEqual(event['rights_narrowed'], [action])
            self.assertFalse(event['retention_shortened'])
            self.source_patch(name='[夹具] 已收窄后的改名')
            self.assertEqual(len(self.events()), before + 1)
        self.source_patch(rights=original)
        self.assertEqual(len(self.events()), 3)

    def test_retention_policy_events_only_for_new_or_shorter_limits(self):
        for value, expected_count in ((30, 1), (30, 1), (60, 1), (None, 1), (7, 2), (1, 3)):
            self.source_patch(retention_days=value)
            self.assertEqual(len(self.events()), expected_count)
        last = self.events()[-1]
        self.assertEqual((last['old_retention_days'], last['new_retention_days']), (7, 1))
        self.assertTrue(last['retention_shortened'])
        self.assertEqual(last['rights_narrowed'], [])

    def test_policy_event_and_source_version_are_atomic(self):
        old = self.store.get('source', 'source-world-bank')
        with patch.object(self.store, 'publish', side_effect=RuntimeError('[夹具] outbox failed')):
            with self.assertRaises(RuntimeError):
                self.source_patch(retention_days=10)
        self.assertEqual(self.store.get('source', old['id']), old)
        self.assertEqual(self.events(), [])
        changed = self.source_patch(retention_days=10)
        row = self.store.db.execute("SELECT id,delivered_at FROM outbox WHERE type='source.policy_changed'").fetchone()
        self.assertEqual(row[0], f"source-policy:{old['id']}@{changed['version']}")
        self.assertIsNone(row[1])


if __name__ == '__main__':
    unittest.main()
