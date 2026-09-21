"""AC04/08/18: isolated fixtures through real loopback HTTP, not browser acceptance."""
import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

from server.app import Application, handler_class
from server.modules import sources
from server.modules.sources import adapters
from server.platform.config import load_config
from server.platform.store import Store

RIGHTS = {'fetch': False, 'store': True, 'display': True, 'export': True, 'ai': False}
RSS_OLD = b'''<rss><channel><item><title>[fixture] Last-week policy report</title>
<link>https://www.federalreserve.gov/fixture/last-week.htm</link><guid>temporal-fixture-last-week</guid>
<pubDate>Mon, 14 Sep 2026 08:00:00 GMT</pubDate><description>Fixture only: policy was announced last week.</description>
</item></channel></rss>'''


class TemporalReadHttpAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='world-insight-temporal-read-fixture-')
        self.config = load_config(data_dir=Path(self.temp.name), port=8881)
        self.store = Store(self.config['db_path'])
        self.now = '2026-09-21T09:00:00.000000Z'
        self.store.now = lambda: self.now
        self.app = Application(self.config, self.store, {'instance_id': 'temporal-read-fixture'})
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_class(self.app))
        self.config['port'] = self.server.server_port
        self.assertNotIn(self.server.server_port, {8874, 8877, 8878, 8880, 8891})
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01})
        self.thread.start()
        # Actual browser/API transport remains real HTTP. No provider transport is permitted.
        self.block_network = patch.object(adapters, 'fetch', side_effect=AssertionError('External GET forbidden in temporal/read fixtures'))
        self.block_network.start()
        for row in self.api('sources')['items']:
            if row['adapter'] in sources.FREE_ADAPTERS:
                self.api('sources/' + row['id'], {'expected_version': row['version'], 'enabled': False}, 'PATCH')

    def tearDown(self):
        self.block_network.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.store.close()
        self.temp.cleanup()

    def request(self, path, body=None, method=None, query=None):
        if query:
            path += '?' + urlencode(query)
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        connection.request(method or ('POST' if body is not None else 'GET'), '/api/' + path,
            body=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
        response = connection.getresponse()
        status, result = response.status, json.loads(response.read())
        connection.close()
        return status, result

    def api(self, path, body=None, method=None, query=None):
        status, result = self.request(path, body, method, query)
        self.assertEqual(status, 200, (path, result))
        return result

    def topic(self, title='[夹具] 时间与阅读验收', **values):
        return self.api('topics', {'question': title, 'source_ids': ['source-manual'], 'is_fixture': True, **values})

    def evidence(self, key, topic=None, **values):
        return self.api('evidence', {'title': '[夹具] ' + key, 'url': 'https://fixture.example/' + key,
            'source_id': 'source-manual', 'topic_id': topic['id'] if topic else None,
            'rights': RIGHTS, 'is_fixture': True, **values})

    def judgment(self, topic, evidence):
        return self.api('judgments', {'topic_id': topic['id'], 'conclusion': '[夹具] 尚未核对执行结果',
            'evidence_version_ids': [evidence['version_id']], 'status': 'reviewed', 'reviewer': '隔离夹具审阅者',
            'confidence_reason': '[夹具] 只验证路由与版本，不证明现实事实',
            'review_date': '2026-10-01', 'is_fixture': True})

    def collect_old_rss(self, topic):
        source = self.api('sources/source-fed')
        if not source['enabled']:
            self.api('sources/source-fed', {'expected_version': source['version'], 'enabled': True}, 'PATCH')
        self.api('sources/source-fed/refresh', {'topic_id': topic['id']})
        scheduler = sources.Scheduler(self.store, fetcher=lambda *_: adapters.Response(200, RSS_OLD))
        result = scheduler.tick(schedule=False)
        self.assertEqual(result['state'], 'complete')
        # This is the same registered outbox dispatcher as the normal service worker.
        while self.app.drain():
            pass
        return self.api('evidence', query={'topic_id': topic['id']})['items'][0]

    def test_ac04_old_publication_collected_today_stays_outside_today_events(self):
        topic = self.topic(source_ids=['source-fed'], keywords=['fixture'])
        evidence = self.collect_old_rss(topic)
        self.assertEqual(evidence['published_at'], '2026-09-14T08:00:00Z')
        self.assertEqual(evidence['collected_at'], self.now)
        self.assertEqual(evidence['discovered_at'], self.now)
        old_event = self.api('events', {'topic_id': topic['id'], 'title': '[夹具] 上周发生的宣布',
            'occurred_at': '2026-09-14T16:00:00+08:00', 'time_precision': 'instant',
            'evidence_version_ids': [evidence['version_id']], 'is_fixture': True})
        unknown_event = self.api('events', {'topic_id': topic['id'], 'title': '[夹具] 发生时间未知',
            'evidence_version_ids': [evidence['version_id']], 'is_fixture': True})
        today = {'topic_id': topic['id'], 'since': '2026-09-21T00:00:00+08:00',
                 'until': '2026-09-21T23:59:59+08:00'}
        self.assertEqual(self.api('events', query=today)['total'], 0)
        self.assertEqual(self.api('evidence', query={**today, 'time_field': 'collected_at'})['total'], 1)
        self.assertEqual(self.api('evidence', query={**today, 'time_field': 'published_at'})['total'], 0)
        discovered = self.api('dashboard', query={'window': '24h', 'topic_id': topic['id']})
        self.assertEqual({row['aggregate_id'] for row in discovered['items']},
                         {evidence['id'], old_event['id'], unknown_event['id']})
        self.assertTrue(all(row['discovered_at'] == self.now for row in discovered['items']))
        self.assertEqual(next(row for row in discovered['items'] if row['aggregate_id'] == old_event['id'])['occurred_at'], '2026-09-14T16:00:00+08:00')
        self.assertIsNone(next(row for row in discovered['items'] if row['aggregate_id'] == unknown_event['id'])['occurred_at'])
        # A same-day repeated request keeps one identity and never creates a new event.
        again = self.collect_old_rss(topic)
        self.assertEqual(again['id'], evidence['id'])
        self.assertEqual(self.api('events', query=today)['total'], 0)
        self.assertEqual(self.api('events', query={'topic_id': topic['id']})['total'], 2)

    def test_ac08_format_candidate_does_not_create_retraction_or_review_alerts(self):
        topic = self.topic()
        first = self.evidence('format-only', topic, excerpt='[夹具] 第一行\n第二行')
        judgment = self.judgment(topic, first)
        brief = self.api('briefs', {'topic_id': topic['id']})
        self.now = '2026-09-21T09:01:00.000000Z'
        changed = self.evidence('format-only', topic, excerpt='[夹具] 第一行\n\n第二行')
        self.assertTrue(changed['change_candidate'])
        self.assertEqual(changed['version'], 2)
        self.assertEqual(changed['status'], 'unverified')
        self.assertEqual(self.api('judgments/' + judgment['id'])['status'], 'reviewed')
        self.assertEqual(self.api('briefs/' + brief['id'])['status'], 'generated')
        rows = self.api('dashboard', query={'window': '24h', 'topic_id': topic['id']})['items']
        candidate = next(row for row in rows if row['aggregate_id'] == first['id'] and row['type'] == 'evidence.updated')
        self.assertFalse(candidate['needs_review'])
        self.assertIn('尚未确认实质更正', candidate['title'])
        self.assertFalse(any(row['type'] in {'evidence.corrected', 'research.needs_review'} for row in rows))
        self.assertEqual(self.api('notifications', query={'status': 'unread'})['total'], 0)
        status, _ = self.request('evidence/' + first['id'] + '/corrections',
            {'expected_version': 2, 'status': 'withdrawn', 'substantive': False, 'reason': '[夹具] 只是空行变化'})
        self.assertEqual(status, 400)
        self.assertEqual(self.api('evidence/' + first['id'])['version'], 2)
        self.assertEqual(self.api('judgments/' + judgment['id'])['evidence_version_ids'], [first['version_id']])
        history = self.api('evidence/' + first['id'] + '/history')['items']
        self.assertEqual([row['excerpt'] for row in history], ['[夹具] 第一行\n第二行', '[夹具] 第一行\n\n第二行'])

    def test_ac18_filtered_page_snapshot_then_real_correction_leaves_hidden_and_new_unread(self):
        topic = self.topic('[夹具] 本页议题')
        other = self.topic('[夹具] 被筛选排除议题')
        self.now = '2026-09-21T09:01:00.000000Z'
        unloaded_one = self.evidence('unloaded-one', topic)
        self.now = '2026-09-21T09:02:00.000000Z'
        unloaded_two = self.evidence('unloaded-two', topic)
        self.now = '2026-09-21T09:03:00.000000Z'
        visible = self.evidence('visible-before-correction', topic)
        self.now = '2026-09-21T09:03:10.000000Z'
        judgment = self.judgment(topic, visible)
        self.now = '2026-09-21T09:04:00.000000Z'
        filtered = self.evidence('filtered-other-topic', other)
        self.now = '2026-09-21T09:05:00.000000Z'
        page = self.api('dashboard', query={'window': 'unread', 'topic_id': topic['id'], 'limit': 2, 'offset': 0})
        self.assertEqual(page['total'], 4)
        self.assertEqual({row['aggregate_id'] for row in page['items']}, {visible['id'], judgment['id']})
        payload = {'snapshot_at': page['snapshot_at'], 'items': [{'id': row['id'], 'version': row['version']} for row in page['items']]}
        self.now = '2026-09-21T09:06:00.000000Z'
        arrived = self.evidence('arrived-after-snapshot', topic)
        self.now = '2026-09-21T09:07:00.000000Z'
        corrected = self.api('evidence/' + visible['id'] + '/corrections',
            {'expected_version': visible['version'], 'status': 'withdrawn', 'substantive': True,
             'reason': '[夹具] 另一窗口在页面加载后确认撤回'})
        self.assertEqual(corrected['status'], 'withdrawn')
        self.now = '2026-09-21T09:08:00.000000Z'
        marked = self.api('changes/read', payload)
        self.assertEqual(marked['marked'], payload['items'])
        self.assertEqual(marked['skipped'], [])
        remaining = self.api('dashboard', query={'window': 'unread', 'limit': 200})
        aggregates = {row['aggregate_id'] for row in remaining['items']}
        self.assertTrue({unloaded_one['id'], unloaded_two['id'], filtered['id'], arrived['id']} <= aggregates)
        self.assertTrue(any(row['aggregate_id'] == visible['id'] and row['type'] == 'evidence.corrected'
                            for row in remaining['items']))
        self.assertFalse({row['id'] for row in page['items']} & {row['id'] for row in remaining['items']})
        self.assertEqual({(row['change_id'], row['change_version']) for row in self.store.all('read_state')},
                         {(row['id'], row['version']) for row in page['items']})
        due = next(row for row in remaining['review_due'] if row['id'] == judgment['id'])
        self.assertEqual(due['status'], 'needs_review')
        self.assertEqual(due['evidence_version_ids'], [visible['version_id']])
        self.assertGreater(self.api('notifications', query={'status': 'unread'})['total'], 0)

    def test_ac18_first_run_baseline_history_and_later_correction_use_real_routes(self):
        empty = self.api('dashboard')
        self.assertTrue(empty['first_run'])
        self.assertEqual(empty['window'], '24h')
        self.assertEqual(self.store.all('read_state'), [])
        self.now = '2026-09-14T09:00:00.000000Z'
        historical = self.evidence('historical-unscoped')
        self.now = '2026-09-21T09:00:00.000000Z'
        topic = self.topic()
        self.assertEqual(topic['reading_baseline'], self.now)
        dashboard = self.api('dashboard')
        self.assertFalse(dashboard['first_run'])
        self.assertEqual(dashboard['window'], '24h')
        self.assertEqual(dashboard['total'], 0)
        self.assertEqual(self.api('dashboard', query={'window': 'unread'})['total'], 0)
        history = self.api('dashboard', query={'window': 'custom', 'since': '2026-09-01T00:00:00Z'})
        self.assertEqual(history['total'], 1)
        self.assertTrue(history['items'][0]['before_reading_baseline'])
        self.assertFalse(history['items'][0]['read'])
        self.assertEqual(self.store.all('read_state'), [])
        status, _ = self.request('topics/' + topic['id'], {'expected_version': topic['version'],
                                'reading_baseline': '2026-09-22T00:00:00Z'}, 'PATCH')
        self.assertEqual(status, 400)
        self.now = '2026-09-21T09:01:00.000000Z'
        self.api('evidence/' + historical['id'] + '/corrections', {'expected_version': historical['version'],
                 'substantive': True, 'status': 'corrected', 'reason': '[夹具] 首次基线之后新确认更正'})
        unread = self.api('dashboard', query={'window': 'unread'})
        self.assertEqual([row['type'] for row in unread['items']], ['evidence.corrected'])
        self.assertFalse(unread['items'][0]['read'])
        self.assertFalse(unread['items'][0]['before_reading_baseline'])
        self.assertEqual(self.store.all('read_state'), [])


if __name__ == '__main__':
    unittest.main()
