"""Coverage after successful caches become unavailable; isolated fixtures, no network."""
import tempfile
import unittest
from pathlib import Path

from server.modules import research, sources
from server.modules.sources import adapters
from server.platform.store import Store


class CoverageFailureTests(unittest.TestCase):
    def test_all_current_failures_keep_history_but_are_unavailable(self):
        with tempfile.TemporaryDirectory(prefix='coverage-fixture-') as directory:
            store = Store(Path(directory) / 'test.sqlite')
            try:
                store.now = lambda: '2026-09-21T02:00:00.000000Z'
                sources.seed_sources(store)
                topic = research.handle(store, 'POST', ['topics'], {'question': '[夹具] 缓存覆盖',
                    'keywords': ['fixture'], 'source_ids': ['source-fed'], 'is_fixture': True}, {})
                sources.enqueue(store, 'source-fed', topic['id'])
                scheduler = sources.Scheduler(store, fetcher=lambda *_: adapters.Response(200,
                    b'<rss><channel><item><title>fixture</title><link>https://www.federalreserve.gov/fixture</link></item></channel></rss>'))
                scheduler.tick(False)
                self.assertEqual(sources.coverage(store, topic['id'])['coverage_status'], 'complete')
                cached = store.all('evidence')
                success = store.get('source', 'source-fed')['last_success']
                sources.enqueue(store, 'source-fed', topic['id'])
                def timeout(*_):
                    raise adapters.FetchError('timeout', '[夹具] 超时')
                sources.Scheduler(store, fetcher=timeout).tick(False)
                result = sources.coverage(store, topic['id'])
                self.assertEqual(result['coverage_status'], 'unavailable')
                self.assertEqual(result['sources'][0]['data_status'], 'stale')
                self.assertEqual(result['sources'][0]['last_success'], success)
                self.assertIsNone(result['empty_reason'])
                self.assertIn('历史缓存', result['explanation'])
                self.assertEqual(store.all('evidence'), cached)
            finally:
                store.close()
