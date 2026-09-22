"""GKG fixtures and real SQLite. No upstream calls; recorded live payload is replayed separately."""
import concurrent.futures
import hashlib
import io
import json
import struct
import tempfile
import threading
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from server.modules import research, sources
from server.modules.sources import adapters, gkg
from server.platform.errors import ApiError
from server.platform.store import Store

BATCH = '20260921020000'


def csv_line(title='Fixture climate policy', url='https://publisher.example/fixture', batch=BATCH, record=1):
    fields = [''] * 27
    fields[:5] = [f'{batch}-{record}', batch, '1', 'publisher.example', url]
    fields[7] = 'ENV_CLIMATE;'
    fields[26] = f'<PAGE_TITLE>{title}</PAGE_TITLE><PAGE_PRECISEPUBTIMESTAMP>20000101000000</PAGE_PRECISEPUBTIMESTAMP><QUOTATIONS>DO NOT RETAIN THIS CONTENT</QUOTATIONS>'
    return '\t'.join(fields) + '\n'


def payload(raw=None, filename=None, extra=False):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(filename or BATCH + '.gkg.csv', raw if raw is not None else csv_line())
        if extra:
            archive.writestr('extra.txt', 'fixture')
    body = buffer.getvalue()
    item = gkg.manifest({'batch': BATCH, 'md5': hashlib.md5(body).hexdigest(), 'size': len(body)})
    index = adapters.Response(200, f"{len(body)} {item['md5']} http://data.gdeltproject.org/gdeltv2/{BATCH}.gkg.csv.zip\n".encode())
    return item, index, adapters.Response(200, body)


class GkgParserTests(unittest.TestCase):
    def test_live_observed_batch_size_remains_inside_bounded_envelope(self):
        item = gkg.manifest({
            'batch': '20260922150000',
            'md5': 'ad89d137d38429d21bbc14bae930d182',
            'size': 6578603,
        })
        self.assertLess(item['size'], gkg.ZIP_LIMIT)
        self.assertLess(20389639, gkg.EXPANDED_LIMIT)
        self.assertEqual(gkg.ZIP_LIMIT, 8 * 1024 * 1024)
        self.assertEqual(gkg.EXPANDED_LIMIT, 32 * 1024 * 1024)

    def test_fixed_index_https_upgrade_and_metadata_only(self):
        item, index, response = payload()
        self.assertEqual(gkg.parse_index(index), item)
        self.assertTrue(item['url'].startswith('https://data.gdeltproject.org/'))
        rows = gkg.parse_zip(response, item)
        self.assertEqual(rows[0]['title'], 'Fixture climate policy')
        self.assertNotIn('QUOTATIONS', json.dumps(rows))
        self.assertNotIn('20000101', json.dumps(rows))

    def test_index_rejects_other_domains_paths_credentials_duplicate_and_large(self):
        item, index, _ = payload()
        text = index.body.decode()
        for invalid in [text.replace('data.gdeltproject.org', 'evil.example'),
                        text.replace('/gdeltv2/', '/gdeltv2/../'),
                        text.replace('data.gdeltproject.org', 'user@data.gdeltproject.org'),
                        text + text, 'x' * (gkg.INDEX_LIMIT + 1),
                        text.replace(str(item['size']), str(gkg.ZIP_LIMIT + 1), 1)]:
            with self.subTest(value=invalid[:70]), self.assertRaises(adapters.FetchError):
                gkg.parse_index(adapters.Response(200, invalid.encode()))

    def test_zip_integrity_size_and_single_file_path_limits(self):
        item, _, response = payload()
        wrong = {**item, 'md5': '0' * 32}
        with self.assertRaises(adapters.FetchError):
            gkg.parse_zip(response, wrong)
        with self.assertRaises(adapters.FetchError):
            gkg.parse_zip(adapters.Response(200, response.body[:-1]), item)
        for name, extra in [('../escape.csv', False), ('/tmp/escape.csv', False), (None, True)]:
            malicious, _, response = payload(filename=name, extra=extra)
            with self.subTest(name=name), self.assertRaises(adapters.FetchError):
                gkg.parse_zip(response, malicious)

    def test_zip_bomb_and_false_expanded_size_are_rejected(self):
        item, _, response = payload(raw='x' * (gkg.EXPANDED_LIMIT + 1))
        self.assertLess(len(response.body), gkg.ZIP_LIMIT)
        with self.assertRaises(adapters.FetchError):
            gkg.parse_zip(response, item)
        # Claim a small length in both headers; CRC/format validation still rejects truncated data.
        body = bytearray(response.body)
        struct.pack_into('<I', body, 22, 1)
        central = body.index(b'PK\x01\x02')
        struct.pack_into('<I', body, central + 24, 1)
        item['md5'] = hashlib.md5(body).hexdigest()
        with self.assertRaises(adapters.FetchError):
            gkg.parse_zip(adapters.Response(200, bytes(body)), item)

    def test_malformed_columns_wrong_batch_symlink_and_missing_title(self):
        for raw in ['not\ta\tgkg\n', csv_line(batch='20260921021500')]:
            item, _, response = payload(raw)
            with self.assertRaises(adapters.FetchError):
                gkg.parse_zip(response, item)
        item, _, response = payload(csv_line().replace('<PAGE_TITLE>', '<OTHER>').replace('</PAGE_TITLE>', '</OTHER>'))
        self.assertEqual(gkg.parse_zip(response, item), [])
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            info = zipfile.ZipInfo(BATCH + '.gkg.csv')
            info.create_system = 3
            info.external_attr = 0o120777 << 16
            archive.writestr(info, 'target')
        body = buffer.getvalue()
        item = {'batch': BATCH, 'md5': hashlib.md5(body).hexdigest(), 'size': len(body)}
        with self.assertRaises(adapters.FetchError):
            gkg.parse_zip(adapters.Response(200, body), item)


class GkgSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='gkg-fixture-')
        self.path = Path(self.temp.name) / 'test.sqlite'
        self.store = Store(self.path)
        self.clock = datetime(2026, 9, 21, 2, 0, tzinfo=timezone.utc)
        self.store.now = self.now
        sources.seed_sources(self.store)
        self.calls = []
        self.item, self.index, self.zip = payload(csv_line('Fixture climate Russia', 'https://publisher.example/both', record=1)
            + csv_line('Fixture climate talks', 'https://publisher.example/climate', record=2)
            + csv_line('Fixture Russia warning', 'https://publisher.example/russia', record=3))
        for source in self.store.all('source'):
            if source['adapter'] in sources.FREE_ADAPTERS:
                self.patch_source(source['id'], enabled=source['adapter'] == 'gdelt_gkg')

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def now(self):
        return self.clock.isoformat(timespec='microseconds').replace('+00:00', 'Z')

    def patch_source(self, sid='source-gdelt-gkg', **values):
        old = self.store.get('source', sid)
        return self.store.update('source', sid, values, old['version'])

    def topic(self, words=None, **values):
        return research.handle(self.store, 'POST', ['topics'], {'question': '[GKG 夹具] 有哪些材料？',
            'is_fixture': True, 'keywords': ['climate'] if words is None else words,
            'source_ids': ['source-gdelt-gkg'], **values}, {})

    def fetch(self, url, headers):
        self.calls.append(url)
        self.assertFalse(self.store.db.in_transaction, 'Network must run outside Store transaction')
        self.assertEqual(headers, {})
        self.assertIn(url, (gkg.INDEX_URL, self.item['url']))
        return self.index if url == gkg.INDEX_URL else self.zip

    def tick(self, scheduler=None, seconds=6):
        result = (scheduler or sources.Scheduler(self.store, fetcher=self.fetch)).tick(False)
        self.clock += timedelta(seconds=seconds)
        return result

    def complete(self):
        for _ in range(20):
            if all(job['state'] == 'complete' for job in self.store.all('collection_job')):
                return
            self.tick()
        self.fail(str(self.store.all('collection_job')))

    def test_two_gets_shared_across_topics_then_cache_reuse_and_keyword_change(self):
        climate = self.topic()
        russia = self.topic(['Russia'])
        excluded = self.topic(exclude_keywords=['Russia'])
        sources.enqueue(self.store, 'source-gdelt-gkg')
        self.complete()
        self.assertEqual(self.calls, [gkg.INDEX_URL, self.item['url']])
        self.assertEqual(len(self.store.all('evidence')), 3)
        both = next(row for row in self.store.all('evidence') if row['url'].endswith('/both'))
        self.assertEqual(set(both['topic_ids']), {climate['id'], russia['id']})
        self.assertNotIn(excluded['id'], both['topic_ids'])
        for row in self.store.all('evidence'):
            self.assertIsNone(row['published_at'])
            self.assertEqual(row['provider_seen_at'], '2026-09-21T02:00:00Z')
            self.assertEqual(row['publisher'], 'publisher.example')
            self.assertEqual(row['rights']['store'], 'metadata')
            self.assertEqual(row['excerpt'], '')
            self.assertEqual(row['ingest_origin'], 'collector')
            self.assertEqual(row['source_record_id'], row['url'])
        sources.enqueue(self.store, 'source-gdelt-gkg')
        self.complete()
        self.assertEqual(len(self.calls), 2)
        old = self.store.get('topic', climate['id'])
        research.handle(self.store, 'PATCH', ['topics', old['id']], {'expected_version': old['version'], 'keywords': ['warning']}, {})
        sources.enqueue(self.store, 'source-gdelt-gkg', old['id'])
        self.complete()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.store.get('source', 'source-gdelt-gkg')['requests_today'], 2)
        cache_text = ''.join(path.read_text() for path in gkg.Cache(self.store.data_dir).path.glob('*.json'))
        self.assertNotIn('DO NOT RETAIN', cache_text)

    def test_default_disabled_no_keywords_scope_or_paid_fallback(self):
        source = self.store.get('source', 'source-gdelt-gkg')
        for configuration in ({'query': 'climate'}, {'feed_url': 'https://evil.example'}, {'countries': ['USA']}):
            with self.assertRaises(ApiError):
                sources.handle(self.store, 'PATCH', ['sources', source['id']], {'expected_version': source['version'], 'config': configuration}, {})
        topic = self.topic([])
        with self.assertRaises(ApiError) as invalid:
            sources.enqueue(self.store, source['id'], topic['id'])
        self.assertEqual(invalid.exception.code, 'query_required')
        self.assertIsNone(sources.Scheduler(self.store, fetcher=self.fetch).tick())
        state = sources.coverage(self.store, topic['id'])
        self.assertEqual(state['coverage_status'], 'unavailable')
        self.assertIn('关键词', state['sources'][0]['reason'])
        other = self.topic(source_ids=['source-fed'])
        with self.assertRaises(ApiError):
            sources.enqueue(self.store, source['id'], other['id'])
        self.assertEqual(self.calls, [])
        self.assertFalse(self.store.get('source', 'source-paid')['enabled'])
        self.assertFalse(self.store.get('source', 'source-ai')['enabled'])

    def test_index_checkpoint_survives_restart_and_new_topic_reuses_cache(self):
        self.topic()
        sources.enqueue(self.store, 'source-gdelt-gkg')
        first = self.tick()
        self.assertEqual(first['checkpoint']['manifest']['md5'], self.item['md5'])
        self.assertEqual(first['checkpoint']['phase'], 'zip')
        self.assertIsNone(first.get('last_success'))
        self.store.close()
        self.store = Store(self.path)
        self.store.now = self.now
        second = self.tick()
        self.assertEqual(second['state'], 'complete')
        added = self.topic(['Russia'])
        sources.enqueue(self.store, 'source-gdelt-gkg', added['id'])
        self.complete()
        self.assertEqual(self.calls, [gkg.INDEX_URL, self.item['url']])

    def test_shared_doc_budget_interval_and_disabled_consumption(self):
        self.topic()
        self.patch_source('source-gdelt', enabled=True, budget_daily=2, requests_today=1,
                          budget_date=self.now()[:10], last_attempt=self.now(), status='failed', last_error='[夹具] DOC timeout')
        self.patch_source(budget_daily=2)
        sources.enqueue(self.store, 'source-gdelt-gkg')
        self.assertEqual(self.tick()['state'], 'retry')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.tick()['checkpoint']['phase'], 'zip')
        self.patch_source('source-gdelt', enabled=False)
        self.assertEqual(self.tick()['state'], 'retry')
        self.assertEqual(self.calls, [gkg.INDEX_URL])
        source = sources.handle(self.store, 'GET', ['sources', 'source-gdelt-gkg'], {}, {})
        self.assertEqual(source['provider_requests_today'], 2)
        self.assertEqual(source['provider_budget_daily'], 2)
        self.assertEqual(source['status'], 'quota_exhausted')
        self.clock += timedelta(days=1)
        self.assertEqual(self.tick()['state'], 'complete')
        self.assertEqual(self.store.get('source', 'source-gdelt')['status'], 'failed')
        self.assertEqual(len(self.calls), 2)

    def test_duplicate_configurations_share_global_batch_and_index(self):
        first = self.store.get('source', 'source-gdelt-gkg')
        second = sources.handle(self.store, 'POST', ['sources'], {key: value for key, value in first.items() if key in sources.SOURCE_FIELDS}, {})
        self.topic(source_ids=[first['id'], second['id']])
        sources.enqueue(self.store, first['id'])
        sources.enqueue(self.store, second['id'])
        self.complete()
        self.assertEqual(self.calls, [gkg.INDEX_URL, self.item['url']])
        self.assertEqual(sum(item['request_count'] for item in self.store.all('collection_job')), 2)

    def test_concurrent_collectors_do_not_duplicate_request_or_hold_store_lock(self):
        self.topic()
        sources.enqueue(self.store, 'source-gdelt-gkg')
        entered, release = threading.Event(), threading.Event()
        def slow(url, headers):
            result = self.fetch(url, headers)
            entered.set()
            self.assertTrue(release.wait(3))
            return result
        with concurrent.futures.ThreadPoolExecutor() as pool:
            work = pool.submit(sources.Scheduler(self.store, fetcher=slow).tick, False)
            self.assertTrue(entered.wait(3))
            sources.Scheduler(self.store, fetcher=self.fetch).tick(False)
            self.assertEqual(self.store.get('source', 'source-gdelt-gkg')['requests_today'], 1)
            release.set()
            work.result(3)
        self.assertEqual(self.calls, [gkg.INDEX_URL])
        self.clock += timedelta(seconds=6)
        self.complete()
        self.assertEqual(len(self.calls), 2)

    def test_429_shared_backoff_and_md5_failure_keep_checkpoint_no_false_empty(self):
        self.topic()
        self.topic(['Russia'])
        sources.enqueue(self.store, 'source-gdelt-gkg')
        self.tick()
        def limited(url, headers):
            self.calls.append(url)
            return adapters.Response(429, b'', {'retry-after': '60'})
        failed = self.tick(sources.Scheduler(self.store, fetcher=limited))
        self.assertEqual(failed['state'], 'retry')
        self.tick()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.store.all('evidence'), [])
        self.clock += timedelta(seconds=60)
        self.zip = adapters.Response(200, b'x' * self.item['size'])
        self.tick()
        self.assertEqual(self.store.all('evidence'), [])
        self.assertIsNone(sources.coverage(self.store)['empty_reason'])

    def test_latest_only_coverage_stays_partial_even_for_no_matches_and_long_sleep(self):
        topic = self.topic(['unmatched fixture keyword'])
        sources.enqueue(self.store, 'source-gdelt-gkg')
        self.complete()
        result = sources.coverage(self.store, topic['id'])
        self.assertEqual(result['coverage_status'], 'partial')
        self.assertIsNone(result['empty_reason'])
        self.assertEqual(result['sources'][0]['last_result_count'], 0)
        self.assertIn('未补齐历史', result['sources'][0]['coverage_gaps'][0]['reason'])
        self.clock += timedelta(days=2)
        sources.enqueue(self.store, 'source-gdelt-gkg')
        self.complete()
        self.assertEqual(self.calls, [gkg.INDEX_URL, self.item['url'], gkg.INDEX_URL])
        self.assertEqual(len(sources.coverage(self.store, topic['id'])['sources'][0]['coverage_gaps']), 1)

    def test_maintenance_pauses_cache_and_network_and_scope_edit_drops_response(self):
        topic = self.topic()
        sources.enqueue(self.store, 'source-gdelt-gkg')
        maintenance = Path(self.store.data_dir) / 'maintenance.json'
        maintenance.write_text('{}')
        before = self.store.all('collection_job')
        self.assertIsNone(self.tick())
        self.assertEqual(self.calls, [])
        self.assertEqual(self.store.all('collection_job'), before)
        maintenance.unlink()
        self.tick()
        def changed(url, headers):
            response = self.fetch(url, headers)
            old = self.store.get('topic', topic['id'])
            research.handle(self.store, 'PATCH', ['topics', old['id']], {'expected_version': old['version'], 'keywords': ['changed fixture']}, {})
            return response
        result = self.tick(sources.Scheduler(self.store, fetcher=changed))
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual(self.store.all('evidence'), [])
        self.assertIsNone(gkg.Cache(self.store.data_dir).rows(self.item))

    def test_maintenance_created_during_request_leaves_checkpoint_without_cache_write(self):
        self.topic()
        sources.enqueue(self.store, 'source-gdelt-gkg')
        self.tick()
        checkpoint = self.store.all('collection_job')[0]['checkpoint']
        def paused(url, headers):
            response = self.fetch(url, headers)
            (Path(self.store.data_dir) / 'maintenance.json').write_text('{}')
            return response
        result = self.tick(sources.Scheduler(self.store, fetcher=paused))
        self.assertEqual(result['checkpoint'], checkpoint)
        self.assertEqual(self.store.all('evidence'), [])
        self.assertIsNone(gkg.Cache(self.store.data_dir).rows(self.item))

    def test_source_failure_and_recovery_events_do_not_clear_doc_failure(self):
        topic = self.topic()
        self.patch_source('source-gdelt', status='failed', last_error='[夹具] 独立 DOC 失败')
        sources.enqueue(self.store, 'source-gdelt-gkg')
        def timeout(*_):
            raise adapters.FetchError('timeout', '[夹具] GKG 超时')
        self.tick(sources.Scheduler(self.store, fetcher=timeout))
        self.clock += timedelta(seconds=60)
        self.complete()
        events = [row[0] for row in self.store.db.execute("SELECT type FROM outbox WHERE aggregate_id='source-gdelt-gkg'")]
        self.assertEqual(events.count('source.failed'), 1)
        self.assertEqual(events.count('source.recovered'), 1)
        self.assertIsNone(self.store.get('source', 'source-gdelt-gkg').get('last_error_code'))
        self.assertTrue(all(job.get('error_code') is None for job in self.store.all('collection_job')))
        self.assertEqual(self.store.get('source', 'source-gdelt')['status'], 'failed')
        self.assertEqual(sources.coverage(self.store, topic['id'])['coverage_status'], 'partial')

    def test_ingestion_rollback_reuses_valid_metadata_without_second_zip_request(self):
        self.topic()
        sources.enqueue(self.store, 'source-gdelt-gkg')
        self.tick()
        called = []
        def broken_sink(store, entry):
            called.append(entry['url'])
            store.create('evidence', {'title': '[夹具] 应回滚'})
            raise RuntimeError('[夹具] 磁盘事务失败')
        failed = self.tick(sources.Scheduler(self.store, evidence_sink=broken_sink, fetcher=self.fetch))
        self.assertEqual(failed['state'], 'retry')
        self.assertTrue(called)
        self.assertEqual(self.store.all('evidence'), [])
        self.assertIsNotNone(gkg.Cache(self.store.data_dir).rows(self.item))
        self.clock += timedelta(seconds=60)
        self.complete()
        self.assertEqual(self.calls, [gkg.INDEX_URL, self.item['url']])
        self.assertEqual(len(self.store.all('evidence')), 3)

    def test_source_disabled_during_index_does_not_publish_or_cache_response(self):
        self.topic()
        sources.enqueue(self.store, 'source-gdelt-gkg')
        def revoked(url, headers):
            response = self.fetch(url, headers)
            self.patch_source(enabled=False)
            return response
        result = self.tick(sources.Scheduler(self.store, fetcher=revoked))
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual(self.store.all('evidence'), [])
        self.assertIsNone(gkg.Cache(self.store.data_dir).read('index.json'))

    def test_batch_record_ids_and_url_tracking_do_not_create_duplicate_materials(self):
        from server.modules import knowledge
        topic = self.topic()
        source = self.store.get('source', 'source-gdelt-gkg')
        job = sources.enqueue(self.store, source['id'], topic['id'])['job']
        for index in range(2):
            rows = [{'url': f'https://publisher.example/story?utm_source=batch{index}',
                     'title': 'Fixture climate story', 'themes': '', 'publisher': 'publisher.example',
                     'gkg_record_id': f'20260921020{index}00-{index}'}]
            for item in gkg.result(source, job, self.item, rows, self.now())['evidence']:
                knowledge.ingest(self.store, item, origin='collector')
        self.assertEqual(len(self.store.all('evidence')), 1)
        self.assertEqual(self.store.all('evidence')[0]['source_record_id'], 'https://publisher.example/story')
        self.assertEqual(self.store.all('evidence')[0]['channels'][0]['url'], 'https://publisher.example/story?utm_source=batch0')


if __name__ == '__main__':
    unittest.main()
