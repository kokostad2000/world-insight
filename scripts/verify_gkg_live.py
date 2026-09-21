#!/usr/bin/env python3
"""Explicit, isolated GKG acceptance: dry-run by default; at most two live GET attempts."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def run_live(directory):
    from server.app import Application
    from server.modules import sources
    from server.modules.sources import adapters, gkg
    from server.platform.config import ensure_data, load_config
    from server.platform.store import Store

    # An existing data directory is never an implicit target for this acceptance script.
    directory = directory.expanduser().resolve()
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('验收必须使用新的空目录；不会修改现有研究库或复用上次请求。')
    config = load_config(ROOT, data_dir=directory, port=8880)
    identity = ensure_data(config, initialize=True)
    store = Store(config['db_path'])
    write_json(directory / 'instance.json', identity)
    app = Application(config, store, identity)
    report = {'mode': 'live_scheduler_transport', 'started_at': stamp(), 'data_dir': str(directory),
              'database': str(config['db_path']), 'reserved_browser_port': 8880, 'http_listener_started': False,
              'max_get_attempts': 2, 'new_get_attempts': 0, 'retry_policy': 'stop on first failure; no retry',
              'paid_calls': 0, 'ai_calls': 0, 'tls_verification': True, 'requests': [], 'ticks': []}
    report['git_commit'] = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    locks = []
    original_fetch = adapters.fetch
    expected_zip = None
    last_get_started = None

    def journal(event):
        with (directory / 'transport.jsonl').open('a') as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + '\n')
            handle.flush()
            os.fsync(handle.fileno())

    def observed_transport(url, headers=None, *, max_bytes=2097152):
        """Audit wrapper delegates unchanged to the production TLS/curl transport."""
        nonlocal expected_zip, last_get_started
        number = len(report['requests'])
        allowed = gkg.INDEX_URL if number == 0 else expected_zip
        limit = gkg.INDEX_LIMIT if number == 0 else gkg.ZIP_LIMIT
        if number >= 2 or url != allowed or max_bytes != limit:
            raise adapters.FetchError('acceptance_bound', '验收限制阻止额外、越界或非标准大小的请求。')
        started = time.monotonic()
        request = {'number': number + 1, 'method': 'GET', 'url': url, 'started_at': stamp(),
                   'max_bytes': max_bytes, 'tls_verification': True,
                   'since_previous_get_seconds': None if last_get_started is None else round(started - last_get_started, 6)}
        last_get_started = started
        report['requests'].append(request)
        journal({'event': 'request_started', **request})
        try:
            response = original_fetch(url, headers, max_bytes=max_bytes)
            request.update({'http_status': response.status, 'response_bytes': len(response.body),
                            'sha256': hashlib.sha256(response.body).hexdigest(), 'headers': response.headers})
            if number == 0 and response.status == 200:
                item = gkg.parse_index(response)
                expected_zip = item['url']
                request['manifest'] = item
                # The index contains only official file metadata. Raw ZIP is not persisted here.
                (directory / 'live-index.txt').write_bytes(response.body)
            elif number == 1:
                request['md5'] = hashlib.md5(response.body).hexdigest()
            return response
        except Exception as error:
            request.update({'error_type': type(error).__name__,
                            'error_code': getattr(error, 'code', 'transport_failed'),
                            'error_message': getattr(error, 'message', '正式传输失败，未重试。')})
            raise
        finally:
            request.update({'finished_at': stamp(), 'elapsed_seconds': round(time.monotonic() - started, 6)})
            journal({'event': 'request_finished', **request})

    try:
        for name in ('service.lock', 'collector.lock'):
            handle = (directory / name).open('a+')
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locks.append(handle)
        sources.seed_sources(store)
        for source in store.all('source'):
            if source['adapter'] in sources.FREE_ADAPTERS:
                patch = {'expected_version': source['version'], 'enabled': source['adapter'] == 'gdelt_gkg'}
                if source['adapter'] == 'gdelt_gkg':
                    patch.update({'budget_daily': 2, 'name': 'GDELT GKG（真实接入验收）'})
                app.dispatch('PATCH', '/api/sources/' + source['id'], patch, {})
        topics = [app.dispatch('POST', '/api/topics', {
            'question': '真实接入验收 · ' + word + ' · 当前批次发现了哪些材料？',
            'keywords': [word], 'source_ids': ['source-gdelt-gkg'], 'is_fixture': False,
            'rationale': '有界真实免费源技术接入验收；只登记待核查材料元数据，不生成现实说法或研究结论。',
        }, {}) for word in ('Iran', 'Russia', 'sanctions')]
        app.dispatch('POST', '/api/sources/source-gdelt-gkg/refresh', {}, {})
        # This wraps observability only; Scheduler recognizes and invokes the production transport path.
        adapters.fetch = observed_transport
        scheduler = sources.Scheduler(store)
        deadline = time.monotonic() + 90
        report['state'] = 'running'
        while time.monotonic() < deadline:
            if last_get_started is not None and time.monotonic() < last_get_started + 6.1:
                time.sleep(min(6.1, last_get_started + 6.1 - time.monotonic()))
            scheduler.tick(schedule=False)
            jobs = store.all('collection_job')
            source = store.get('source', 'source-gdelt-gkg')
            report['ticks'].append({'at': stamp(), 'source': source, 'jobs': jobs})
            report['new_get_attempts'] = len(report['requests'])
            write_json(directory / 'live-report.json', report)
            # Includes parser/ingestion/budget errors: never advance to another real attempt after failure.
            if any(job.get('last_error') or job['state'] == 'cancelled' for job in jobs):
                report['state'] = 'failed_stopped_without_retry'
                break
            if all(job['state'] == 'complete' for job in jobs):
                report['state'] = 'complete'
                break
            time.sleep(0.05)
        else:
            report['state'] = 'bounded_deadline_reached'
        while app.drain():
            pass
        evidence = store.all('evidence')
        cache = gkg.Cache(directory)
        index = cache.read('index.json')
        metadata = cache.rows(index['manifest']) if index else None
        report.update({'finished_at': stamp(), 'new_get_attempts': len(report['requests']),
            'source': app.dispatch('GET', '/api/sources/source-gdelt-gkg', {}, {}),
            'sources': store.all('source'), 'jobs': store.all('collection_job'),
            'cached_metadata_count': len(metadata) if metadata is not None else None,
            'cached_publisher_domains': len({row['publisher'] for row in metadata}) if metadata is not None else None,
            'evidence_count': len(evidence),
            'checks': {'no_excerpt': all(not row['excerpt'] for row in evidence),
                       'unknown_published_at': all(row['published_at'] is None for row in evidence),
                       'metadata_only': all(row['rights']['store'] == 'metadata' for row in evidence),
                       'collector_origin': all(row.get('ingest_origin') == 'collector' for row in evidence),
                       'real_records_not_fixtures': all(not row.get('is_fixture') for row in evidence),
                       'claim_count': len(store.all('claim')), 'event_count': len(store.all('event')),
                       'judgment_count': len(store.all('judgment'))},
            'topics': [{'id': topic['id'], 'question': topic['question'],
                        'evidence_count': len(store.all('evidence', topic_id=topic['id'])),
                        'coverage': sources.coverage(store, topic['id'])} for topic in topics],
            'materials': [{key: row.get(key) for key in ('id', 'version', 'url', 'source_record_id', 'title',
                'publisher', 'published_at', 'provider_seen_at', 'rights', 'status', 'topic_ids', 'channels')}
                for row in evidence]})
        return report
    finally:
        adapters.fetch = original_fetch
        report['process_stopped_at'] = stamp()
        write_json(directory / 'live-report.json', report)
        store.close()
        for handle in reversed(locks):
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()


def main():
    parser = argparse.ArgumentParser(description='GKG 正式 Scheduler 有界验收；默认 dry-run，不联网、不建库。')
    parser.add_argument('--live', action='store_true', help='显式允许最多两个真实 GET，任一失败停止')
    parser.add_argument('--data-dir', type=Path, help='新的空隔离目录；绝不默认使用正式研究库')
    args = parser.parse_args()
    if not args.live:
        print(json.dumps({'mode': 'dry_run', 'network_requests': 0, 'database_created': False,
            'planned_topics': ['真实接入验收 · Iran', '真实接入验收 · Russia', '真实接入验收 · sanctions'],
            'planned_get_limit': 2, 'port': '8880 reserved; no listener', 'required_flags': '--live --data-dir NEW_EMPTY_DIRECTORY'}, ensure_ascii=False, indent=2))
        return 0
    if args.data_dir is None:
        parser.error('--live 必须明确提供新的 --data-dir')
    try:
        report = run_live(args.data_dir)
    except (ValueError, OSError) as error:
        print('验收停止：' + str(error), file=sys.stderr)
        return 1
    print(json.dumps({key: report.get(key) for key in ('state', 'data_dir', 'new_get_attempts',
                     'cached_metadata_count', 'evidence_count', 'checks', 'process_stopped_at')}, ensure_ascii=False, indent=2))
    return 0 if report['state'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
