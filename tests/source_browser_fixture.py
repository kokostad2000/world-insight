"""Reproducible source browser fixture using the real app/static/Scheduler.

Run only on a new, explicitly isolated data directory. No HTTP provider request
is made: the fetch boundary injects labelled RSS/GDELT responses and counts every
adapter invocation. A local control file switches fixture modes; no fixture UI
or extra HTTP routes are added. The clock advances only when explicitly asked,
so retry/quota observations are deterministic, not claims about elapsed time.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import threading
from server.app import serve
from server.modules import research, sources
from server.modules.sources import adapters
from server.platform.config import load_config
from server.platform.errors import ApiError
from server.platform.store import Store
from ops.runtime import atomic_json


class BrowserFixture(sources.Scheduler):
    def __init__(self, store):
        self.clock = datetime.now(timezone.utc)
        self.mode = 'success'
        self.requests = []
        self.control_id = None
        self.observation_lock = threading.Lock()
        super().__init__(store, fetcher=self.fixture_fetch)
        store.now = lambda: self.clock.isoformat(timespec='microseconds').replace('+00:00', 'Z')
        for source in store.all('source'):
            if source['adapter'] in sources.FREE_ADAPTERS:
                sources.handle(store, 'PATCH', ['sources', source['id']], {
                    'expected_version': source['version'],
                    'enabled': source['id'] in ('source-fed', 'source-gdelt'),
                    'budget_daily': 30,
                    **({'config': {'query': 'explicit acceptance fixture', 'topic_ids': []}}
                       if source['id'] == 'source-gdelt' else {})}, {})
        self.topic = research.handle(store, 'POST', ['topics'], {
            'question': '[隔离验收] 来源失败和配额不影响人工研究', 'followed': True,
            'source_ids': ['source-fed', 'source-gdelt'], 'keywords': [],
            'rationale': '仅工程样本，无真实采集、无现实结论', 'is_fixture': True}, {})
        self.judgment = research.handle(store, 'POST', ['judgments'], {
            'topic_id': self.topic['id'], 'conclusion': '[隔离验收] 来源状态尚需核查',
            'assumptions': ['这是明确隔离的工程样本'], 'is_fixture': True}, {})
        for source_id in ('source-fed', 'source-gdelt'):
            job = sources.enqueue(store, source_id, self.topic['id'])['job']
            for _ in range(12):
                super().tick(False)
                if store.get('collection_job', job['id'])['state'] == 'complete':
                    break
                self.clock += timedelta(seconds=7)
            else:
                raise RuntimeError('Fixture warmup failed to complete')
        self.snapshot('warm')

    def fixture_fetch(self, url, headers):
        adapter = 'gdelt' if 'gdeltproject.org' in url else 'rss'
        self.requests.append({'adapter': adapter, 'mode': self.mode, 'at': self.store.now()})
        if self.mode == 'timeout_all' or (self.mode == 'empty_rss_timeout_gdelt' and adapter == 'gdelt'):
            raise adapters.FetchError('timeout', '[隔离故障注入] 新闻源请求超时；保留历史缓存')
        if adapter == 'rss':
            item = '' if self.mode == 'empty_rss_timeout_gdelt' else '''<item>
<title>[隔离验收] RSS 历史缓存通告</title><link>https://www.federalreserve.gov/fixture/browser-source</link>
<guid>source-browser-fixture-rss</guid><pubDate>Fri, 18 Sep 2026 15:00:00 GMT</pubDate></item>'''
            return adapters.Response(200, ('<rss><channel>'+item+'</channel></rss>').encode())
        return adapters.Response(200, json.dumps({'articles': [{
            'title': '[隔离验收] GDELT 历史缓存报道',
            'url': 'https://example.org/source-browser-fixture', 'domain': 'example.org',
            'seendate': '20260918T150000Z'}]}).encode())

    def snapshot(self, label=None):
        with self.observation_lock, self.store.transaction():
            evidence = self.store.all('evidence')
            encoded = json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode()
            result = {'is_fixture': True, 'network_calls': 0, 'mode': self.mode,
                      'observed_at': self.store.now(), 'topic_id': self.topic['id'],
                      'judgment_id': self.judgment['id'],
                      'adapter_invocations': {key: sum(row['adapter'] == key for row in self.requests)
                                              for key in ('rss', 'gdelt')},
                      'requests': list(self.requests), 'coverage': sources.coverage(self.store),
                      'sources': self.store.all('source'),
                      'evidence_count': len(evidence),
                      'evidence_sha256': hashlib.sha256(encoded).hexdigest(),
                      'evidence_versions': [f"{row['id']}@{row['version']}" for row in evidence],
                      'jobs': self.store.all('collection_job')}
        atomic_json(self.store.data_dir / 'fixture-observation.json', result)
        if label:
            if not re.fullmatch('[a-z0-9_-]+', label):
                raise ValueError('Invalid fixture observation label')
            atomic_json(self.store.data_dir / f'fixture-{label}.json', result)
        return result

    def _loop(self):
        while not self._stop.wait(.1):
            path = self.store.data_dir / 'fixture-control.json'
            if path.exists():
                command = json.loads(path.read_text())
                if command.get('id') != self.control_id:
                    self.control_id = command['id']
                    self.mode = command.get('mode') or self.mode
                    if self.mode not in ('success', 'timeout_all', 'empty_rss_timeout_gdelt'):
                        raise ValueError('Invalid fixture response mode')
                    self.clock += timedelta(seconds=command.get('advance_seconds', 0))
                    self.snapshot(command.get('label'))
            result = super().tick(False)
            if result:
                self.snapshot()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8891)
    parser.add_argument('--control', action='store_true')
    parser.add_argument('--mode', choices=('success', 'timeout_all', 'empty_rss_timeout_gdelt'))
    parser.add_argument('--advance-seconds', type=int, default=0)
    parser.add_argument('--label')
    parser.add_argument('--verify-acceptance', action='store_true',
                        help='Verify the retained raw observations after the documented browser sequence')
    parser.add_argument('--replay-scheduler', action='store_true',
                        help='Replay backend conditions on a new database, without browser or HTTP service')
    args = parser.parse_args()
    data = args.data_dir.expanduser().resolve()
    if args.verify_acceptance:
        verify_acceptance(data)
        return
    if args.control:
        if args.advance_seconds < 0 or (args.label and not re.fullmatch('[a-z0-9_-]+', args.label)):
            raise SystemExit('Use a nonnegative fixture clock advance and a safe observation label')
        if not (data / 'runtime.json').is_file():
            raise SystemExit('Explicit fixture service is not running')
        atomic_json(data / 'fixture-control.json', {
            'id': datetime.now(timezone.utc).isoformat(), 'mode': args.mode,
            'advance_seconds': args.advance_seconds, 'label': args.label})
        return
    if (data / 'world-insight.sqlite').exists():
        raise SystemExit('Use a new isolated fixture directory; existing data is never reset')
    if args.replay_scheduler:
        replay_scheduler(data)
        return
    # Injection is local to this process; production source/app files are unchanged.
    sources.start_scheduler = lambda store: BrowserFixture(store).start()
    serve(load_config(data_dir=data, port=args.port), initialize=True)


def replay_scheduler(data):
    """Latest-code regression only; real browser acceptance remains a separate run."""
    store = Store(data / 'world-insight.sqlite')
    try:
        sources.seed_sources(store)
        fixture = BrowserFixture(store)
        fixture.mode = 'timeout_all'
        fixture.clock += timedelta(seconds=60)
        for sid in ('source-gdelt', 'source-fed'):
            sources.enqueue(store, sid, fixture.topic['id'])
            fixture.tick(False)
        fixture.snapshot('ac09')
        fixture.mode = 'empty_rss_timeout_gdelt'
        fixture.clock += timedelta(seconds=60)
        for _ in range(2):
            fixture.tick(False)
        fixture.snapshot('ac23')
        fixture.mode = 'success'
        current = store.get('source', 'source-fed')
        sources.handle(store, 'PATCH', ['sources', current['id']],
                       {'expected_version': current['version'], 'budget_daily': 4}, {})
        for _ in range(4):
            sources.enqueue(store, 'source-fed', fixture.topic['id'])
            fixture.tick(False)
        fixture.snapshot('ac10')
        current = store.get('source', 'source-fed')
        try:
            sources.handle(store, 'PATCH', ['sources', current['id']], {
                'expected_version': current['version'],
                'config': {'feed_url': 'https://example.org/unapproved.xml'}}, {})
        except ApiError as error:
            assert error.status == 400
        else:
            raise AssertionError('Invalid source configuration was accepted')
        fixture.snapshot('after_invalid')
        research.handle(store, 'PATCH', ['judgments', fixture.judgment['id']], {
            'expected_version': 1, 'conclusion': '[隔离验收] 无效来源配置被拒后，人工研究仍可保存',
            'change_reason': 'Explicit scheduler replay, not a browser action'}, {})
        fixture.mode = 'timeout_all'
        fixture.clock += timedelta(days=1)
        for _ in range(2):
            fixture.tick(False)
        fixture.snapshot('ac09_recheck')
    finally:
        store.close()
    verify_acceptance(data)


def verify_acceptance(data):
    """Assert captured backend facts; this does not automate or replace the UI checks."""
    phases = {name: json.loads((data / f'fixture-{name}.json').read_text())
              for name in ('warm', 'ac09', 'ac23', 'ac10', 'after_invalid', 'ac09_recheck')}
    by_id = lambda phase: {row['id']: row for row in phases[phase]['coverage']['sources']}
    successes = lambda phase: {key: row['last_success'] for key, row in by_id(phase).items()}
    assert phases['ac09']['coverage']['coverage_status'] == 'unavailable'
    assert all(row['status'] == 'failed' for row in by_id('ac09').values())
    assert successes('ac09') == successes('warm')
    assert phases['ac23']['coverage']['coverage_status'] == 'partial'
    assert phases['ac23']['coverage']['empty_reason'] is None
    assert by_id('ac23')['source-fed']['last_result_count'] == 0
    assert by_id('ac23')['source-fed']['data_status'] == 'fresh'
    assert by_id('ac23')['source-gdelt']['status'] == 'failed'
    assert phases['ac10']['adapter_invocations'] == {'rss': 4, 'gdelt': 6}
    assert by_id('ac10')['source-fed']['status'] == 'quota_exhausted'
    assert phases['ac10']['sources'] == phases['after_invalid']['sources']
    assert phases['ac10']['adapter_invocations'] == phases['after_invalid']['adapter_invocations']
    assert phases['ac09_recheck']['coverage']['coverage_status'] == 'unavailable'
    assert all(row['status'] == 'failed' for row in by_id('ac09_recheck').values())
    assert successes('ac09_recheck') == successes('ac10')
    assert phases['ac09_recheck']['adapter_invocations'] == {'rss': 5, 'gdelt': 7}
    assert {row['evidence_count'] for row in phases.values()} == {2}
    assert len({row['evidence_sha256'] for row in phases.values()}) == 1
    assert all(row['network_calls'] == 0 for row in phases.values())
    for phase in phases.values():
        assert all(not row['enabled'] for row in phase['sources'] if row['adapter'] in ('ai', 'paid'))
    connection = sqlite3.connect(f'file:{data}/world-insight.sqlite?mode=ro', uri=True)
    try:
        judgment = json.loads(connection.execute('SELECT data FROM records WHERE kind=? AND id=?',
            ('judgment', phases['warm']['judgment_id'])).fetchone()[0])
        assert judgment['version'] == 2 and '无效来源配置被拒后' in judgment['conclusion']
        original = json.loads(connection.execute('SELECT data FROM versions WHERE kind=? AND id=? AND version=1',
            ('judgment', judgment['id'])).fetchone()[0])
        assert original['conclusion'] == '[隔离验收] 来源状态尚需核查'
    finally:
        connection.close()
    for name, phase in phases.items():
        print(name, phase['coverage']['coverage_status'], phase['adapter_invocations'],
              'cache', phase['evidence_count'], phase['evidence_sha256'])
    print('PASS: captured AC09/10/23/27 backend assertions; browser observations are recorded separately')


if __name__ == '__main__':
    main()
