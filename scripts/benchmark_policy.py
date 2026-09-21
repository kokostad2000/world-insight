#!/usr/bin/env python3
"""Isolated PRD-capacity HTTP policy benchmark; no real research or upstream I/O."""
import argparse
import concurrent.futures
import contextlib
import hashlib
import http.client
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.app import Application, handler_class
from server.modules import knowledge, research
from server.platform.config import load_config
from server.platform.store import Store

SESSIONS = 5
EVIDENCE_COUNT = 20_000
RESEARCH_COUNT = 5_000
TOPIC_COUNT = 10
CATEGORIES = ('filter', 'search', 'bundle')


def hardware():
    result = {'platform': platform.platform(), 'python': platform.python_version(),
        'machine': platform.machine(), 'cpu_count': os.cpu_count()}
    if sys.platform == 'darwin':
        try:
            values = subprocess.check_output(['/usr/sbin/sysctl', '-n', 'hw.memsize', 'hw.model',
                'machdep.cpu.brand_string'], text=True, stderr=subprocess.DEVNULL, timeout=3).splitlines()
            result.update(memory_bytes=int(values[0]), model=values[1], cpu=values[2])
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            result['hardware_details'] = 'unavailable in this execution environment'
    return result


def percentile(values, fraction):
    return sorted(values)[math.ceil(len(values) * fraction) - 1]


def seed(store):
    """Exactly 20k metadata-only materials and 5k claims/events, all fixture-labelled."""
    grants = {'fetch': False, 'store': True, 'display': True, 'export': True, 'ai': False}
    with store.transaction():
        store.create('source', {'name': '[隔离性能夹具] 本地合成来源', 'adapter': 'manual',
            'rights': grants, 'retention_days': None, 'is_fixture': True}, 'benchmark-source')
        for index in range(TOPIC_COUNT):
            store.create('topic', {'question': f'[隔离性能夹具] 研究议题 {index}', 'status': 'active',
                'followed': True, 'source_ids': ['benchmark-source'], 'country_codes': [], 'is_fixture': True}, f'fixture-topic-{index}')
        stamp = store.now()
        for index in range(EVIDENCE_COUNT):
            topic = f'fixture-topic-{index % TOPIC_COUNT}'
            tag = 'benchmarkneedle' if (index // TOPIC_COUNT) % 2 == 0 else 'other-material'
            store.create('evidence', {'title': f'[隔离性能夹具] 合成材料 {index} {tag}',
                'source_id': 'benchmark-source', 'source_record_id': str(index),
                'topic_id': topic, 'topic_ids': [topic], 'url': f'https://fixture.invalid/material/{index}',
                'excerpt': '', 'translation': '', 'content_fingerprint': None, 'content_scope': 'excerpt',
                'rights': grants, 'channels': [], 'status': 'unverified', 'notes': '', 'is_fixture': True,
                'ingest_origin': 'collector', 'first_collected_at': stamp, 'collected_at': stamp,
                'published_at': None, 'manually_touched': False}, f'fixture-evidence-{index}')
        for index in range(RESEARCH_COUNT // 2):
            topic = f'fixture-topic-{index % TOPIC_COUNT}'
            ref = f'fixture-evidence-{index}@1'
            store.create('claim', {'subject': '[隔离性能夹具] 主体', 'statement': f'[隔离性能夹具] 说法 {index}',
                'topic_id': topic, 'evidence_version_ids': [ref], 'dispute_status': 'unverified', 'is_fixture': True}, f'fixture-claim-{index}')
            store.create('event', {'title': f'[隔离性能夹具] 事件 {index}', 'topic_id': topic,
                'evidence_version_ids': [ref], 'claim_ids': [f'fixture-claim-{index}'], 'occurred_at': None,
                'time_precision': 'unknown', 'location': {'precision': 'unknown', 'name': '未知'},
                'verification_status': 'unverified', 'is_fixture': True}, f'fixture-event-{index}')
        for index in range(TOPIC_COUNT):
            store.create('judgment', {'topic_id': f'fixture-topic-{index}', 'conclusion': '[隔离性能夹具] 暂定判断',
                'evidence_version_ids': [f'fixture-evidence-{index}@1'], 'status': 'draft', 'is_fixture': True}, f'fixture-judgment-{index}')


class Measurements:
    """Thread-local spans observe real calls without changing their results."""
    def __init__(self, app, store):
        self.app, self.store = app, store
        self.local = threading.local()
        self.records, self.lock = {}, threading.Lock()
        self.original_dispatch = app.dispatch
        self.original_policy = knowledge.policy_context
        self.original_snapshots = store.snapshots
        self.original_transaction = store.transaction

    def dispatch(self, method, path, body, query):
        key = query.get('benchmark_request')
        self.local.record = {'request_id': key, 'policy_calls': 0, 'policy_seconds': 0., 'snapshot_calls': 0,
            'snapshot_seconds': 0., 'snapshot_rows': 0, 'transaction_wait_seconds': 0., 'transaction_hold_seconds': 0.}
        self.local.depth = 0
        started = time.perf_counter()
        try:
            return self.original_dispatch(method, path, body, query)
        finally:
            record = self.local.record
            record['dispatch_seconds'] = time.perf_counter() - started
            with self.lock:
                self.records[key] = record
            self.local.record = None

    def policy(self, store):
        started = time.perf_counter()
        try:
            return self.original_policy(store)
        finally:
            record = getattr(self.local, 'record', None)
            if record is not None:
                record['policy_calls'] += 1
                record['policy_seconds'] += time.perf_counter() - started

    def snapshots(self):
        started = time.perf_counter()
        rows = self.original_snapshots()
        record = getattr(self.local, 'record', None)
        if record is not None:
            record['snapshot_calls'] += 1
            record['snapshot_seconds'] += time.perf_counter() - started
            record['snapshot_rows'] += len(rows)
        return rows

    @contextlib.contextmanager
    def transaction(self):
        record = getattr(self.local, 'record', None)
        outer = record is not None and getattr(self.local, 'depth', 0) == 0
        started = time.perf_counter()
        with self.original_transaction():
            acquired = time.perf_counter()
            self.local.depth = getattr(self.local, 'depth', 0) + 1
            if outer:
                record['transaction_wait_seconds'] += acquired - started
            try:
                yield self.store
            finally:
                self.local.depth -= 1
                if outer:
                    record['transaction_hold_seconds'] += time.perf_counter() - acquired

    @contextlib.contextmanager
    def enabled(self):
        with patch.object(self.app, 'dispatch', self.dispatch), patch.object(self.store, 'snapshots', self.snapshots), \
                patch.object(self.store, 'transaction', self.transaction), \
                patch.object(knowledge, 'policy_context', self.policy), patch.object(research, 'policy_context', self.policy):
            yield


def endpoint(category, session, iteration, request_id):
    topic = f'fixture-topic-{session}'
    if category == 'bundle':
        return f'/api/topics/{topic}/bundle?benchmark_request={request_id}'
    offset = (iteration * 50) % 900
    query = f'topic_id={topic}&limit=50&offset={offset}&benchmark_request={request_id}'
    return '/api/evidence?' + query + ('&search=benchmarkneedle' if category == 'search' else '&status=unverified')


def validate(category, content):
    body = json.loads(content)
    if category == 'bundle':
        if len(body['evidence']) != 2_000 or len(body['events']) != 250 or len(body['claims']) != 250:
            raise RuntimeError('Incorrect topic bundle fixture counts')
    elif body.get('total') != (1_000 if category == 'search' else 2_000) or len(body['items']) != 50:
        raise RuntimeError('Incorrect search/filter fixture counts')


def summarize(samples):
    result = {}
    for category in CATEGORIES:
        rows = [sample for sample in samples if sample['category'] == category]
        values = [sample['http_seconds'] for sample in rows]
        result[category] = {'count': len(rows), 'http_p50_seconds': statistics.median(values),
            'http_p95_seconds': percentile(values, .95), 'http_max_seconds': max(values),
            'http_mean_seconds': statistics.mean(values), 'response_mean_bytes': statistics.mean(row['bytes'] for row in rows),
            'policy_calls': sum(row['policy_calls'] for row in rows), 'snapshot_calls': sum(row['snapshot_calls'] for row in rows),
            'snapshot_rows_total': sum(row['snapshot_rows'] for row in rows)}
        for field in ('policy_seconds', 'snapshot_seconds', 'transaction_wait_seconds', 'transaction_hold_seconds', 'dispatch_seconds'):
            result[category][field + '_sum'] = sum(row[field] for row in rows)
            result[category][field + '_mean'] = statistics.mean(row[field] for row in rows)
        result[category]['context_non_snapshot_seconds_sum'] = sum(row['policy_seconds'] - row['snapshot_seconds'] for row in rows)
    return result


def run(output, rounds=8, port=8874):
    output = Path(output).expanduser().resolve()
    if output.exists():
        raise ValueError('Output already exists; choose a new report path')
    if rounds < 4:
        raise ValueError('Use at least four rounds, yielding 20 measurements per endpoint')
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='world-insight-policy-capacity-fixture-') as directory:
        config = load_config(data_dir=Path(directory) / 'data', port=port)
        store = Store(config['db_path'])
        print(json.dumps({'stage': 'seed', 'fixture_directory': directory, 'evidence': EVIDENCE_COUNT,
            'claims_and_events': RESEARCH_COUNT, 'topics': TOPIC_COUNT}), flush=True)
        seed(store)
        seed_seconds = time.perf_counter() - started
        app = Application(config, store, {'instance_id': 'policy-capacity-fixture'})
        server = ThreadingHTTPServer(('127.0.0.1', port), handler_class(app))
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
        measurements = Measurements(app, store)
        samples = []
        thread.start()
        try:
            with measurements.enabled(), concurrent.futures.ThreadPoolExecutor(max_workers=SESSIONS) as pool:
                for category in CATEGORIES:
                    for iteration in range(-1, rounds):
                        barrier = threading.Barrier(SESSIONS)
                        def read(session):
                            request_id = f'{category}-{iteration}-{session}'
                            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=120)
                            barrier.wait()
                            tick = time.perf_counter()
                            connection.request('GET', endpoint(category, session, max(iteration, 0), request_id))
                            response = connection.getresponse()
                            content = response.read()
                            elapsed = time.perf_counter() - tick
                            connection.close()
                            if response.status != 200:
                                raise RuntimeError(f'Benchmark request failed: {response.status}, {request_id}')
                            return request_id, session, elapsed, content
                        # Decode only after all five responses arrive, excluding
                        # client JSON parsing contention from the measured round.
                        completed = list(pool.map(read, range(SESSIONS)))
                        for request_id, session, elapsed, content in completed:
                            validate(category, content)
                            if iteration >= 0:
                                samples.append({'category': category, 'round': iteration, 'session': session,
                                    'http_seconds': elapsed, 'bytes': len(content), **measurements.records[request_id]})
                        print(json.dumps({'stage': 'warmup' if iteration == -1 else 'measure', 'category': category,
                            'round': iteration, 'round_max_seconds': max(row[2] for row in completed)}), flush=True)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
            store.close()
    tracked = ['server/platform/store.py', 'server/modules/knowledge/__init__.py', 'server/modules/knowledge/rights.py',
        'server/modules/knowledge/policy_period.py', 'server/modules/knowledge/lifecycle.py', 'server/modules/research/__init__.py']
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    report = {'recorded_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'commit': commit,
        'environment': {**hardware(), 'port': port, 'network': 'loopback only; no upstream I/O',
            'cache': 'warm SQLite/OS caches after isolated seed; one five-request warmup round per category excluded'},
        'fixture': {'evidence': EVIDENCE_COUNT, 'claims': RESEARCH_COUNT // 2, 'events': RESEARCH_COUNT // 2,
            'topics': TOPIC_COUNT, 'judgments': TOPIC_COUNT, 'sources': 1, 'activity_changes': 0,
            'versions_per_record': 1, 'body_bytes_per_evidence': 0, 'concurrent_sessions': SESSIONS},
        'method': {'rounds_per_category': rounds, 'samples_per_category': rounds * SESSIONS,
            'p95': 'nearest-rank ceil(0.95*N) over separate repeated endpoint samples',
            'spans': 'policy includes snapshots; sums are cumulative observed service time and are not additive wall time',
            'client': 'five simultaneous threads; response JSON validation occurs after each round'},
        'seed_seconds': seed_seconds, 'total_seconds': time.perf_counter() - started,
        'code_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in tracked},
        'summaries': summarize(samples), 'samples': samples,
        'boundaries': 'Synthetic real HTTP API measurements on fresh isolated data. Not browser first usable content, real-source coverage, large full text, cold storage, or seven-day acceptance.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'report': str(output), 'summaries': report['summaries'], 'boundaries': report['boundaries']}, ensure_ascii=False, indent=2), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--rounds', type=int, default=8)
    parser.add_argument('--port', type=int, default=8874)
    arguments = parser.parse_args()
    run(arguments.output, arguments.rounds, arguments.port)
