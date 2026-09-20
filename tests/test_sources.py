"""Behavior tests use actual SQLite, bounded fake upstreams and isolated data dirs."""
import concurrent.futures
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from server.modules import research, sources
from server.modules.sources import adapters
from server.platform.errors import ApiError
from server.platform.store import Store

RSS = b'''<?xml version="1.0"?><rss version="2.0"><channel><title>Fixture feed</title><item><title>Fixture policy statement</title><link>https://www.federalreserve.gov/fixture/statement.htm</link><guid>fixture-1</guid><pubDate>Fri, 18 Sep 2026 15:00:00 GMT</pubDate><description>Fixture only</description></item></channel></rss>'''


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='world-insight-sources-test-')
        self.path = Path(self.temp.name) / 'test.sqlite'
        self.store = Store(self.path)
        self.clock = '2026-09-20T15:00:00.000000Z'
        self.store.now = lambda: self.clock
        sources.seed_sources(self.store)
        self.calls = []

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def update_source(self, sid, **values):
        old = self.store.get('source', sid)
        return self.store.update('source', sid, values, old['version'])

    def sink(self, store, data):
        # Callback seam doubles, not the knowledge domain acceptance test.
        found = store.find('evidence', 'source_record_id', data['source_record_id'])
        return found[0] if found else store.create('evidence', data)

    def metric_sink(self, store, data):
        return store.create('observation', data)

    def scheduler(self, response=None, fetcher=None):
        def fake(url, headers):
            self.calls.append((url, headers))
            return response or adapters.Response(200, RSS)
        return sources.Scheduler(self.store, self.sink, self.metric_sink, fetcher or fake)

    def only_source(self, sid):
        for item in self.store.all('source'):
            if item['adapter'] in sources.FREE_ADAPTERS and item['id'] != sid:
                self.update_source(item['id'], enabled=False)

    def topic(self, source_ids=None, **patch):
        return research.handle(self.store, 'POST', ['topics'], {
            'question': '[来源范围夹具] 哪些材料发生变化？', 'is_fixture': True,
            'source_ids': source_ids or [], 'keywords': ['Fixture'], **patch}, {})

    def update_topic(self, topic, **patch):
        old = self.store.get('topic', topic['id'])
        return research.handle(self.store, 'PATCH', ['topics', topic['id']],
                               {'expected_version': old['version'], **patch}, {})

    def test_selected_sources_constrain_schedule_and_topic_coverage(self):
        topic = self.topic(['source-fed'])
        self.scheduler()._schedule_due()
        jobs = self.store.all('collection_job')
        self.assertEqual([(j['source_id'], j['topic_id']) for j in jobs], [('source-fed', topic['id'])])
        self.assertEqual([x['id'] for x in sources.coverage(self.store, topic['id'])['sources']], ['source-fed'])
        self.assertEqual(self.calls, [])
        for sid in ('source-gdelt', 'source-world-bank'):
            with self.assertRaises(ApiError) as rejected:
                sources.handle(self.store, 'POST', ['sources', sid, 'refresh'], {'topic_id': topic['id']}, {})
            self.assertEqual(rejected.exception.code, 'source_outside_topic_scope')

    def test_empty_selection_defaults_to_enabled_free_sources_only(self):
        topic = self.topic()
        self.update_source('source-world-bank', enabled=False)
        self.scheduler()._schedule_due()
        self.assertEqual({(j['source_id'], j['topic_id']) for j in self.store.all('collection_job')},
                         {('source-fed', topic['id']), ('source-gdelt', topic['id'])})
        self.assertEqual({x['id'] for x in sources.coverage(self.store, topic['id'])['sources']},
                         {'source-fed', 'source-gdelt'})

    def test_source_topic_allowlist_intersection_and_unscoped_refresh(self):
        selected = self.topic(['source-fed'])
        excluded = self.topic(['source-fed'])
        other_source = self.topic(['source-world-bank'])
        source = self.store.get('source', 'source-fed')
        self.update_source(source['id'], config={**source['config'], 'topic_ids': [selected['id'], other_source['id']]})
        result = sources.handle(self.store, 'POST', ['sources', source['id'], 'refresh'], {}, {})
        self.assertEqual([j['topic_id'] for j in result['jobs']], [selected['id']])
        self.assertEqual(sources.coverage(self.store, excluded['id'])['sources'], [])
        for topic in (excluded, other_source):
            with self.assertRaises(ApiError) as rejected:
                sources.enqueue(self.store, source['id'], topic['id'])
            self.assertEqual(rejected.exception.code, 'source_outside_topic_scope')
        self.update_topic(selected, status='paused')
        with self.assertRaises(ApiError) as rejected:
            sources.enqueue(self.store, source['id'])
        self.assertEqual(rejected.exception.code, 'source_outside_topic_scope')
        self.assertEqual(len(self.store.all('collection_job')), 1)

    def test_source_page_refresh_fans_out_only_to_selected_active_topics(self):
        first, second = self.topic(['source-fed']), self.topic(['source-fed'])
        self.topic(['source-world-bank'])
        self.topic(['source-fed'], status='archived')
        reply = sources.enqueue(self.store, 'source-fed')
        self.assertEqual({j['topic_id'] for j in reply['jobs']}, {first['id'], second['id']})
        self.assertEqual(sources.enqueue(self.store, 'source-fed')['status'], 'already_queued')
        self.assertEqual(len(self.store.all('collection_job')), 2)
        with self.assertRaises(ApiError):
            sources.enqueue(self.store, 'source-gdelt')

    def test_scope_edit_cancels_queued_work_before_budget_or_network(self):
        topic = self.topic(['source-fed'])
        old = sources.enqueue(self.store, 'source-fed', topic['id'])['job']
        self.update_topic(topic, source_ids=['source-world-bank'])
        job = self.scheduler().tick(False)
        self.assertEqual(job['state'], 'cancelled')
        self.assertEqual(job['checkpoint'], old['checkpoint'])
        self.assertEqual(self.calls, [])
        self.assertEqual(self.store.get('source', 'source-fed')['requests_today'], 0)
        self.assertNotIn('source-fed', [x['id'] for x in sources.coverage(self.store, topic['id'])['sources']])

    def test_scope_edit_during_request_discards_response_without_ingestion(self):
        topic = self.topic(['source-fed'])
        sources.enqueue(self.store, 'source-fed', topic['id'])
        def upstream(url, headers):
            self.update_topic(topic, source_ids=['source-world-bank'])
            return adapters.Response(200, RSS)
        job = self.scheduler(fetcher=upstream).tick(False)
        self.assertEqual(job['state'], 'cancelled')
        self.assertEqual(self.store.all('evidence'), [])
        self.assertIsNone(job.get('covered_until'))
        self.assertEqual(self.store.get('source', 'source-fed')['requests_today'], 1)

    def test_topic_coverage_does_not_reuse_other_topic_success_or_etag(self):
        first, second = self.topic(['source-fed']), self.topic(['source-fed'])
        sources.enqueue(self.store, 'source-fed', first['id'])
        self.scheduler(adapters.Response(200, RSS, {'etag': '"fixture-first"'})).tick(False)
        self.assertEqual(sources.coverage(self.store, first['id'])['coverage_status'], 'complete')
        self.assertEqual(sources.coverage(self.store, second['id'])['coverage_status'], 'unavailable')
        self.assertEqual(sources.coverage(self.store)['coverage_status'], 'partial')
        sources.enqueue(self.store, 'source-fed', second['id'])
        self.scheduler().tick(False)
        self.assertNotIn('If-None-Match', self.calls[-1][1])
        self.assertEqual(sources.coverage(self.store, second['id'])['coverage_status'], 'complete')

    def test_changed_query_requires_new_snapshot_before_complete(self):
        topic = self.topic(['source-fed'])
        sources.enqueue(self.store, 'source-fed', topic['id'])
        self.scheduler(adapters.Response(200, RSS, {'etag': '"old-scope"'})).tick(False)
        self.update_source('source-fed', next_check='2026-09-21T00:00:00Z')
        self.update_topic(topic, keywords=['different fixture'])
        self.assertEqual(sources.coverage(self.store, topic['id'])['coverage_status'], 'unavailable')
        scheduler = self.scheduler()
        scheduler._schedule_due()
        job = self.store.all('collection_job')[0]
        self.assertEqual(job['state'], 'queued')
        self.assertIsNone(job['covered_until'])
        self.assertIsNone(job['etag'])
        scheduler.tick(False)
        result = sources.coverage(self.store, topic['id'])
        self.assertEqual(result['coverage_status'], 'complete')
        self.assertEqual(result['empty_reason'], 'no_matches')
        self.assertNotIn('If-None-Match', self.calls[-1][1])

    def test_new_topic_does_not_inherit_global_coverage_or_queued_work(self):
        global_job = sources.enqueue(self.store, 'source-fed')['job']
        topic = self.topic(['source-fed'])
        self.assertEqual(self.scheduler().tick(False)['state'], 'cancelled')
        self.assertEqual(self.calls, [])
        self.scheduler()._schedule_due()
        jobs = self.store.all('collection_job')
        self.assertTrue(any(j['id'] != global_job['id'] and j['topic_id'] == topic['id'] for j in jobs))
        self.assertEqual(sources.coverage(self.store, topic['id'])['coverage_status'], 'unavailable')

    def test_last_empty_page_does_not_erase_snapshot_matches(self):
        self.only_source('source-world-bank')
        sources.enqueue(self.store, 'source-world-bank')
        first = [{'page': 1, 'pages': 2, 'lastupdated': '2026-07-13'}, [
            {'indicator': {'id': 'SP.POP.TOTL'}, 'countryiso3code': 'CHN', 'date': '2025', 'value': 100}]]
        self.scheduler(adapters.Response(200, json.dumps(first).encode())).tick(False)
        self.clock = '2026-09-20T15:01:00Z'
        last = [{'page': 2, 'pages': 2, 'lastupdated': '2026-07-13'}, []]
        self.scheduler(adapters.Response(200, json.dumps(last).encode())).tick(False)
        result = sources.coverage(self.store)
        self.assertEqual(result['coverage_status'], 'complete')
        self.assertEqual(result['sources'][0]['last_result_count'], 1)
        self.assertIsNone(result['empty_reason'])

    def test_seed_is_local_idempotent_preserves_config_and_disables_paid(self):
        self.update_source('source-fed', budget_daily=2)
        sources.seed_sources(self.store)
        self.assertEqual(len(self.store.all('source')), 6)
        self.assertEqual(self.store.get('source', 'source-fed')['budget_daily'], 2)
        self.assertFalse(self.store.get('source', 'source-paid')['enabled'])
        self.assertFalse(self.store.get('source', 'source-ai')['enabled'])

    def test_unreviewed_rss_and_paid_ai_activation_rejected(self):
        for url in ['http://www.federalreserve.gov/feeds/x.xml', 'https://127.0.0.1/a', 'https://www.federalreserve.gov.evil.test/feeds/a', 'https://u:p@www.federalreserve.gov/feeds/a', 'https://www.federalreserve.gov/feeds/x?token=secret']:
            source = self.store.get('source', 'source-fed')
            with self.assertRaises(ApiError):
                sources.handle(self.store, 'PATCH', ['sources', source['id']], {'expected_version': source['version'], 'config': {'feed_url': url}}, {})
        for sid in ['source-ai', 'source-paid']:
            source = self.store.get('source', sid)
            with self.assertRaises(ApiError):
                sources.handle(self.store, 'PATCH', ['sources', sid], {'expected_version': source['version'], 'enabled': True}, {})

    def test_gdelt_without_query_does_not_schedule_request(self):
        self.only_source('source-gdelt')
        self.assertIsNone(self.scheduler().tick())
        self.assertEqual(self.calls, [])
        with self.assertRaises(ApiError):
            sources.enqueue(self.store, 'source-gdelt')

    def test_concurrent_manual_refresh_deduplicates_durable_job(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            replies = list(pool.map(lambda _: sources.enqueue(self.store, 'source-fed'), range(20)))
        self.assertEqual(sum(x['status'] == 'queued' for x in replies), 1)
        self.assertEqual(len(self.store.all('collection_job')), 1)
        self.assertEqual(self.calls, [])

    def test_shared_budget_includes_failures_and_restart(self):
        self.update_source('source-fed', budget_daily=1)
        sources.enqueue(self.store, 'source-fed')
        scheduler = self.scheduler(adapters.Response(500, b'error'))
        first = scheduler.tick(schedule=False)
        self.assertEqual(first['state'], 'retry')
        self.store.close()
        self.store = Store(self.path)
        self.clock = '2026-09-20T15:10:00.000000Z'
        self.store.now = lambda: self.clock
        scheduler = self.scheduler()
        scheduler.tick(schedule=False)
        self.assertEqual(self.store.get('source', 'source-fed')['status'], 'quota_exhausted')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.store.all('collection_job')[0]['checkpoint']['page'], 1)
        self.clock = '2026-09-21T00:01:00.000000Z'
        scheduler.tick(schedule=False)
        self.assertEqual(self.store.get('source', 'source-fed')['requests_today'], 1)
        self.assertEqual(len(self.calls), 2)

    def test_network_does_not_hold_store_transaction_or_block_reads(self):
        sources.enqueue(self.store, 'source-fed')
        entered, release = threading.Event(), threading.Event()
        def fetcher(url, headers):
            entered.set()
            self.assertTrue(release.wait(2))
            return adapters.Response(200, RSS)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            job = pool.submit(self.scheduler(fetcher=fetcher).tick, False)
            self.assertTrue(entered.wait(1))
            read = pool.submit(self.store.get, 'source', 'source-fed')
            self.assertEqual(read.result(timeout=.5)['id'], 'source-fed')
            release.set()
            self.assertEqual(job.result(timeout=2)['state'], 'complete')

    def test_rss_dates_conditional_requests_and_304_keep_cache_count(self):
        self.only_source('source-fed')
        sources.enqueue(self.store, 'source-fed')
        self.scheduler(adapters.Response(200, RSS, {'etag': '"fixture"'})).tick(False)
        record = self.store.all('evidence')[0]
        self.assertEqual(record['published_at'], '2026-09-18T15:00:00Z')
        self.assertEqual(record['collected_at'], self.clock)
        sources.enqueue(self.store, 'source-fed')
        self.scheduler(adapters.Response(304, b'')).tick(False)
        self.assertEqual(self.calls[-1][1]['If-None-Match'], '"fixture"')
        self.assertEqual(self.store.get('source', 'source-fed')['last_result_count'], 1)
        self.assertIsNone(sources.coverage(self.store)['empty_reason'])
        self.assertEqual(len(self.store.all('evidence')), 1)

    def test_gdelt_seen_time_not_publication_and_200_html_is_failure(self):
        source = self.store.get('source', 'source-gdelt')
        result = adapters.parse(source, {'topic_id': None}, adapters.Response(200, json.dumps({'articles': [{'url': 'https://example.com/fixture', 'title': 'Fixture', 'seendate': '20260919T000000Z'}]}).encode()), self.clock)
        item = result['evidence'][0]
        self.assertIsNone(item['published_at'])
        self.assertEqual(item['provider_seen_at'], '2026-09-19T00:00:00Z')
        with self.assertRaises(adapters.FetchError):
            adapters.parse(source, {}, adapters.Response(200, b'Timespan is too short.'), self.clock)

    def test_world_bank_year_null_value_units_and_durable_pagination(self):
        def upstream(url, headers):
            self.calls.append((url, headers))
            page = int(parse_qs(urlsplit(url).query)['page'][0])
            data = [{'page': page, 'pages': 2, 'lastupdated': '2026-07-13'}, [{'indicator': {'id': 'NY.GDP.MKTP.CD'}, 'countryiso3code': 'CHN', 'date': str(2026-page), 'value': None if page == 1 else 10}]]
            return adapters.Response(200, json.dumps(data).encode())
        sources.enqueue(self.store, 'source-world-bank')
        first = self.scheduler(fetcher=upstream).tick(False)
        self.assertEqual(first['checkpoint']['page'], 2)
        self.assertEqual(first['state'], 'queued')
        self.store.close()
        self.store = Store(self.path)
        self.clock = '2026-09-20T15:01:00.000000Z'
        self.store.now = lambda: self.clock
        self.assertEqual(self.scheduler(fetcher=upstream).tick(False)['state'], 'complete')
        observations = sorted(self.store.all('observation'), key=lambda x: x['period'], reverse=True)
        self.assertEqual(observations[0]['period'], '2025')
        self.assertIsNone(observations[0]['value'])
        self.assertIsNone(observations[0]['published_at'])
        self.assertEqual(observations[0]['unit'], 'USD')
        self.assertEqual(len(observations[0]['evidence_version_ids']), 1)
        self.assertIn('page=2', self.calls[-1][0])
        self.assertTrue(self.store.integrity()['ok'])

    def test_one_empty_one_failed_is_partial_not_no_matches(self):
        self.update_source('source-gdelt', enabled=False)
        sources.enqueue(self.store, 'source-fed')
        self.scheduler(adapters.Response(200, b'<rss><channel/></rss>')).tick(False)
        sources.enqueue(self.store, 'source-world-bank')
        self.scheduler(adapters.Response(504, b'')).tick(False)
        result = sources.coverage(self.store)
        self.assertEqual(result['coverage_status'], 'partial')
        self.assertIsNone(result['empty_reason'])

    def test_all_failed_unavailable_with_stale_cache_preserved(self):
        self.only_source('source-fed')
        sources.enqueue(self.store, 'source-fed')
        self.scheduler().tick(False)
        sources.enqueue(self.store, 'source-fed')
        self.scheduler(adapters.Response(504, b'')).tick(False)
        result = sources.coverage(self.store)
        self.assertNotEqual(result['coverage_status'], 'complete')
        self.assertEqual(result['sources'][0]['data_status'], 'stale')
        self.assertEqual(len(self.store.all('evidence')), 1)

    def test_failure_notifications_only_transition_recovery_once(self):
        sources.enqueue(self.store, 'source-fed')
        scheduler = self.scheduler(adapters.Response(500, b''))
        scheduler.tick(False)
        self.clock = '2026-09-20T15:10:00.000000Z'
        scheduler.tick(False)
        self.clock = '2026-09-20T15:20:00.000000Z'
        self.scheduler().tick(False)
        events = self.store.db.execute('SELECT type FROM outbox').fetchall()
        self.assertEqual([row[0] for row in events].count('source.failed'), 1)
        self.assertEqual([row[0] for row in events].count('source.recovered'), 1)

    def test_atomic_ingest_failure_retries_without_partial_writes(self):
        sources.enqueue(self.store, 'source-fed')
        def bad_sink(store, data):
            store.create('evidence', data)
            raise RuntimeError('fixture failure')
        scheduler = sources.Scheduler(self.store, bad_sink, self.metric_sink, lambda *_: adapters.Response(200, RSS))
        self.assertEqual(scheduler.tick(False)['state'], 'retry')
        self.assertEqual(self.store.all('evidence'), [])
        self.assertEqual(self.store.get('source', 'source-fed')['requests_today'], 1)

    def test_rss_sleep_gap_preserved_without_fabricated_history(self):
        sources.enqueue(self.store, 'source-fed')
        self.scheduler().tick(False)
        self.clock = '2026-09-24T15:00:00.000000Z'
        sources.enqueue(self.store, 'source-fed')
        job = self.scheduler().tick(False)
        self.assertEqual(len(job['coverage_gaps']), 1)
        self.assertEqual(job['gap_start'], '2026-09-20T15:00:00.000000Z')

    def test_gdelt_recovery_policy_and_saturated_windows_report_gaps(self):
        self.update_source('source-gdelt', config={'query': 'fixture', 'topic_ids': []})
        job = sources.enqueue(self.store, 'source-gdelt')['job']
        self.store.update('collection_job', job['id'], {'state': 'complete', 'covered_until': '2026-01-01T00:00:00Z'}, job['version'])
        job = sources.enqueue(self.store, 'source-gdelt')['job']
        self.assertEqual(len(job['coverage_gaps']), 1)
        payload = {'articles': [{'url': f'https://example.com/fixture/{i}', 'title': f'Fixture {i}'} for i in range(250)]}
        job = self.scheduler(adapters.Response(200, json.dumps(payload).encode())).tick(False)
        self.assertEqual(job['state'], 'queued')
        self.assertEqual(len(job['coverage_gaps']), 2)
        self.assertNotEqual(sources.coverage(self.store)['coverage_status'], 'complete')

    def test_gdelt_source_wide_spacing_and_upstream_retry_after(self):
        self.update_source('source-gdelt', config={'query': 'fixture', 'topic_ids': []})
        sources.enqueue(self.store, 'source-gdelt')
        job = self.scheduler(adapters.Response(429, b'', {'retry-after': '120'})).tick(False)
        self.assertEqual(job['next_attempt'], '2026-09-20T15:02:00Z')
        self.assertEqual(self.store.get('source', 'source-gdelt')['status'], 'failed')

    def test_scheduler_lock_prevents_duplicate_process_instances(self):
        with patch.object(sources.Scheduler, '_loop', lambda scheduler: scheduler._stop.wait(5)):
            first = self.scheduler().start()
            try:
                self.assertIs(first.start(), first)
                with self.assertRaises(ApiError):
                    self.scheduler().start()
            finally:
                first.stop()
            second = self.scheduler().start()
            second.stop()

    def test_xml_entity_and_non_public_resolution_rejected(self):
        with self.assertRaises(adapters.FetchError):
            adapters.parse(self.store.get('source', 'source-fed'), {}, adapters.Response(200, b'<!DOCTYPE rss><rss><channel/></rss>'), self.clock)
        with patch.object(adapters.socket, 'getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 443))]):
            with self.assertRaises(adapters.FetchError):
                adapters.public_host('www.federalreserve.gov')
        with self.assertRaises(adapters.FetchError):
            adapters.public_host('evil.test')

    def test_maintenance_prevents_queue_requests_and_inflight_ingestion(self):
        marker = self.store.data_dir / 'maintenance.json'
        job = sources.enqueue(self.store, 'source-fed')['job']
        marker.write_text('{}')
        self.assertIsNone(self.scheduler().tick(False))
        with self.assertRaises(ApiError) as blocked:
            sources.enqueue(self.store, 'source-fed')
        self.assertEqual(blocked.exception.status, 503)
        self.assertEqual(self.calls, [])
        marker.unlink()
        def fetcher(url, headers):
            marker.write_text('{}')
            return adapters.Response(200, RSS)
        self.scheduler(fetcher=fetcher).tick(False)
        self.assertEqual(self.store.all('evidence'), [])
        self.assertEqual(self.store.get('collection_job', job['id'])['checkpoint'], job['checkpoint'])
        marker.unlink()
        self.scheduler().tick(False)
        self.assertEqual(len(self.store.all('evidence')), 1)

    def test_actual_knowledge_callbacks_preserve_versions_and_indicator_years(self):
        # The real knowledge owner now participates; upstream remains a labelled fixture.
        sources.enqueue(self.store, 'source-fed')
        scheduler = sources.Scheduler(self.store, fetcher=lambda *_: adapters.Response(200, RSS))
        self.assertEqual(scheduler.tick(False)['state'], 'complete')
        first = self.store.all('evidence')[0]
        self.assertEqual(first['version'], 1)
        sources.enqueue(self.store, 'source-fed')
        scheduler.tick(False)
        self.assertEqual(self.store.all('evidence')[0]['version'], 1)
        payload = [{'page': 1, 'pages': 1, 'lastupdated': '2026-07-13'}, [
            {'indicator': {'id': 'SP.POP.TOTL'}, 'countryiso3code': 'CHN', 'date': '2025', 'value': 100},
            {'indicator': {'id': 'SP.POP.TOTL'}, 'countryiso3code': 'CHN', 'date': '2024', 'value': None}]]
        sources.enqueue(self.store, 'source-world-bank')
        actual = sources.Scheduler(self.store, fetcher=lambda *_: adapters.Response(200, json.dumps(payload).encode()))
        result = actual.tick(False)
        self.assertEqual(result['state'], 'complete', result)
        self.assertEqual(len(self.store.all('observation')), 2)
        self.assertEqual(len(self.store.all('evidence')), 3)
        payload[1][0]['value'] = 105
        sources.enqueue(self.store, 'source-world-bank')
        actual.tick(False)
        record = [x for x in self.store.all('observation') if x['period'] == '2025'][0]
        self.assertEqual(record['version'], 2)
        self.assertEqual(self.store.history('observation', record['id'])[0]['value'], 100)
        self.assertTrue(self.store.integrity()['ok'])

    def test_source_edits_require_version_and_pagination_validation(self):
        old = self.store.get('source', 'source-fed')
        self.update_source('source-fed', name='Fixture changed')
        with self.assertRaises(ApiError) as conflict:
            sources.handle(self.store, 'PATCH', ['sources', old['id']], {'expected_version': old['version'], 'name': 'stale edit'}, {})
        self.assertEqual(conflict.exception.status, 409)
        with self.assertRaises(ApiError):
            sources.handle(self.store, 'GET', ['sources'], {}, {'limit': 'oops'})

    def test_retention_limit_is_explicit_nullable_integer_and_versioned(self):
        source = self.store.get('source', 'source-fed')
        self.assertIsNone(source['retention_days'])
        for invalid in (0, -1, 36501, True, 1.5, '30'):
            with self.assertRaises(ApiError) as rejected:
                sources.handle(self.store, 'PATCH', ['sources', source['id']],
                               {'expected_version': source['version'], 'retention_days': invalid}, {})
            self.assertEqual(rejected.exception.code, 'invalid_retention')
        for value in (1, 30, 36500, None):
            source = sources.handle(self.store, 'PATCH', ['sources', source['id']],
                                    {'expected_version': source['version'], 'retention_days': value}, {})
            self.assertEqual(source['retention_days'], value)
        self.assertEqual([x['retention_days'] for x in self.store.history('source', source['id'])],
                         [None, 1, 30, 36500, None])

    def test_default_evidence_sink_explicitly_marks_collector_origin(self):
        sources.enqueue(self.store, 'source-fed')
        from server.modules import knowledge
        calls = []
        original = knowledge.ingest
        def ingest(store, data, *, origin):
            calls.append(origin)
            return original(store, data)
        with patch.object(knowledge, 'ingest', ingest):
            job = sources.Scheduler(self.store, fetcher=lambda *_: adapters.Response(200, RSS)).tick(False)
        self.assertEqual(job['state'], 'complete')
        self.assertEqual(calls, ['collector'])


if __name__ == '__main__':
    unittest.main()
