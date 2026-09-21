#!/usr/bin/env python3
"""Official-material metadata review: read-only by default, two explicit phases.

--check-official performs exactly one bounded GET per selected official URL, at
most ten, with TLS verification, no redirects/retries/assets/body persistence.
--register uses reviewed decisions and real loopback HTTP in a NEW SQLite DB;
it performs no upstream requests and never starts a Scheduler.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CACHE = Path('/private/tmp/world-insight-real-acceptance/world-insight.sqlite')
RIGHTS = {'fetch': False, 'store': 'metadata', 'display': 'metadata', 'export': 'metadata', 'ai': False}
SELECTION = [
    ('monetary20260916a.htm', '货币政策声明', 'monetary', 'official_statement'),
    ('monetary20260916b.htm', '经济预测发布公告', 'monetary', 'economic_projections_release'),
    ('monetary20260825a.htm', '贴现率会议纪要发布', 'monetary', 'meeting_minutes_release'),
    ('monetary20260819a.htm', 'FOMC会议纪要发布', 'monetary', 'meeting_minutes_release'),
    ('bcreg20260911a.htm', '监管指导征求意见公告', 'regulation', 'consultation_release'),
    ('bcreg20260910a.htm', '检查周期规则公告', 'regulation', 'regulatory_rule_release'),
    ('orders20260820a.htm', '银行机构申请批准公告', 'regulation', 'approval_release'),
    ('enforcement20260918b.htm', '执法措施终止公告', 'regulation', 'enforcement_release'),
    ('NY.GDP.MKTP.CD:CHN:2025', 'GDP年度统计数据', 'data', 'dataset'),
    ('SP.POP.TOTL:CHN:2025', '人口年度统计数据', 'data', 'dataset'),
]


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def cached_candidates(path):
    connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        sources = {row['id']: row for row in (json.loads(raw) for raw, in connection.execute("SELECT data FROM records WHERE kind='source'"))}
        materials = [json.loads(raw) for raw, in connection.execute("SELECT data FROM records WHERE kind='evidence'")]
        selected = []
        for key, label, topic, material_type in SELECTION:
            matches = [row for row in materials if not row.get('deleted') and not row.get('is_fixture') and
                       (row.get('url', '').endswith('/' + key) or row.get('source_record_id') == key)]
            if len(matches) != 1:
                raise ValueError(f'真实缓存候选须唯一且非fixture：{key}，实际{len(matches)}条')
            row = matches[0]
            source = sources[row['source_id']]
            url = urlsplit(row['url'])
            if url.scheme != 'https' or url.hostname not in {'www.federalreserve.gov', 'data.worldbank.org'} or url.username or url.password:
                raise ValueError('拒绝非官方HTTPS候选')
            selected.append({'key': key, 'type_label': label, 'topic_key': topic, 'material_type': material_type,
                'cached_id': row['id'], 'cached_version': row['version'],
                **{field: row.get(field) for field in ('url', 'title', 'publisher', 'published_at', 'source_updated_at', 'collected_at', 'source_id', 'source_record_id')},
                'cached_license_url': source['license_url'], 'cached_license_checked_at': source.get('checked_at'),
                'publication_precision': 'unknown' if row.get('published_at') is None else 'instant_from_official_rss',
                'observation_period': '2025' if topic == 'data' else None,
                'registered_rights': RIGHTS})
        return selected
    finally:
        connection.close()


class Metadata(HTMLParser):
    """Extract headings/time and licence-link metadata only, never article prose."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.result = {'title': '', 'headings': [], 'dates': [], 'meta': {}, 'license_links': []}
        self.active = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta':
            name = attrs.get('name', attrs.get('property', '')).lower()
            if name in {'date', 'dc.date', 'dc.date.created', 'dc.title', 'og:title', 'article:published_time', 'citation_title', 'author', 'publisher'}:
                self.result['meta'][name] = attrs.get('content', '')[:2000]
        if tag == 'a' and any(word in attrs.get('href', '').lower() for word in ('disclaimer', 'creativecommons.org/licenses', 'terms-of-use')):
            self.result['license_links'].append(attrs['href'][:1000])
        if tag == 'title' or tag in {'h1', 'h2', 'h3', 'time'} or (tag == 'p' and 'article__time' in attrs.get('class', '')):
            self.active.append([tag, 'date' if tag == 'time' or tag == 'p' else tag, attrs.get('datetime', ''), []])

    def handle_data(self, data):
        for item in self.active:
            if sum(map(len, item[3])) < 2500:
                item[3].append(data)

    def handle_endtag(self, tag):
        for item in list(self.active):
            if item[0] != tag:
                continue
            self.active.remove(item)
            value = ' '.join(''.join(item[3]).split())[:2000]
            if item[1] == 'title':
                if not self.result['title']:
                    self.result['title'] = value
            elif item[1] == 'date':
                self.result['dates'].append({'text': value, 'datetime': item[2] or None})
            elif value:
                self.result['headings'].append(value)


def check_official(directory, candidates, cache):
    if directory.exists() and any(directory.iterdir()):
        raise ValueError('联网核对必须指定新的空目录；禁止重跑追加请求。')
    directory.mkdir(parents=True, exist_ok=True)
    report = {'mode': 'official_metadata_review', 'started_at': stamp(), 'cache_db_read_only': str(cache.resolve()),
        'git_commit': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
        'max_upstream_gets': 10, 'retry': False, 'follow_redirects': False, 'tls_verified': True,
        'page_bodies_saved': False, 'candidates': candidates, 'requests': []}
    write_json(directory / 'official-checks.json', report)
    for candidate in candidates:
        if len(report['requests']) >= 10:
            raise ValueError('已达到10次GET上限')
        request = {'key': candidate['key'], 'url': candidate['url'], 'started_at': stamp(), 'method': 'GET'}
        report['requests'].append(request)
        write_json(directory / 'official-checks.json', report)
        started = time.monotonic()
        marker = b'\n--OFFICIAL-TRANSPORT--\n'
        command = ['/usr/bin/curl', '--silent', '--show-error', '--proto', '=https', '--tlsv1.2',
            '--connect-timeout', '8', '--max-time', '20', '--max-filesize', '1048576', '--retry', '0',
            '--max-redirs', '0', '--header', 'Accept: text/html', '--user-agent', 'WorldInsight-OfficialMetadataReview/1.0',
            '--write-out', marker.decode() + '%{json}', '--url', candidate['url']]
        try:
            result = subprocess.run(command, capture_output=True, timeout=23, check=False)
            body, separator, raw = result.stdout.rpartition(marker)
            transport = json.loads(raw) if separator else {}
            request.update({'curl_exit': result.returncode, 'http_status': transport.get('http_code'),
                'response_bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
                'effective_url': transport.get('url_effective'), 'redirect_url': transport.get('redirect_url'),
                'ssl_verify_result': transport.get('ssl_verify_result'),
                'error': result.stderr.decode(errors='replace')[:800] or None})
            if result.returncode == 0 and transport.get('http_code') == 200:
                parser = Metadata()
                parser.feed(body.decode('utf-8', errors='replace'))
                request['metadata'] = parser.result
            else:
                request['metadata'] = None
        except (subprocess.TimeoutExpired, ValueError) as error:
            request.update({'error': type(error).__name__, 'metadata': None})
        request.update({'finished_at': stamp(), 'elapsed_seconds': round(time.monotonic() - started, 6)})
        write_json(directory / 'official-checks.json', report)
        print(json.dumps({'key': request['key'], 'status': request.get('http_status'), 'curl_exit': request.get('curl_exit')}, ensure_ascii=False), flush=True)
    report['finished_at'] = stamp()
    write_json(directory / 'official-checks.json', report)


def register(directory, decisions_path):
    from server.app import Application, handler_class
    from server.platform.config import ensure_data, load_config
    from server.platform.store import Store

    review = json.loads((directory / 'official-checks.json').read_text())
    decisions = json.loads(decisions_path.read_text())
    checked = {row['key']: row for row in decisions['items']}
    candidates = review['candidates']
    if len(candidates) != 10 or len(checked) != 10 or set(checked) != {row['key'] for row in candidates}:
        raise ValueError('必须逐条提交且只提交这10份候选的复核决定')
    for decision in checked.values():
        if decision.get('accept') is not True or not all(decision.get(key) for key in ('reviewed_at', 'method', 'finding')):
            raise ValueError('每条须明确复核时间、方法、结论和接受决定')
    if not decisions.get('reviewer') or (directory / 'world-insight.sqlite').exists():
        raise ValueError('须有明确复核者且数据库尚不存在；不重复登记或覆盖现有库')
    config = load_config(ROOT, data_dir=directory, port=8882)
    identity = ensure_data(config, initialize=True)
    store = Store(config['db_path'])
    write_json(directory / 'instance.json', identity)
    app = Application(config, store, identity)
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_class(app))
    config['port'] = server.server_port
    if server.server_port in {8766, 8874, 8876, 8877, 8878, 8880, 8891}:
        server.server_close()
        store.close()
        raise ValueError('拒绝占用其它验收端口')
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
    thread.start()
    report = {'started_at': stamp(), 'data_dir': str(directory), 'database': str(config['db_path']),
              'port': server.server_port, 'origin': 'manual via POST /api/evidence',
              'scheduler_started': False, 'upstream_gets_during_registration': 0, 'api_calls': [], 'materials': []}

    def api(method, path, body=None):
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
        try:
            connection.request(method, '/api/' + path, body=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
            response = connection.getresponse()
            result = json.loads(response.read())
            report['api_calls'].append({'method': method, 'path': '/api/' + path, 'status': response.status, 'at': stamp()})
            if response.status != 200:
                raise RuntimeError(json.dumps(result, ensure_ascii=False))
            return result
        finally:
            connection.close()

    try:
        for source in api('GET', 'sources')['items']:
            if source['enabled']:
                api('PATCH', 'sources/' + source['id'], {'expected_version': source['version'], 'enabled': False})
        topics = {}
        for key, title in [('monetary', '货币政策与会议发布'), ('regulation', '银行监管发布'), ('data', 'WDI国家背景数据')]:
            topics[key] = api('POST', 'topics', {'question': '开发验收复核：' + title + '的官方元数据是否可追溯？',
                'rationale': '真实官方材料字段与登记流程验收；由开发Agent复核，不代表用户研究判断，也不确认政策执行或事实真伪。',
                'status': 'paused', 'followed': False, 'source_ids': ['source-world-bank' if key == 'data' else 'source-fed'],
                'country_codes': ['CHN'] if key == 'data' else ['USA'], 'is_fixture': False})
        for row in candidates:
            decision = checked[row['key']]
            notes = '\n'.join([
                '开发验收复核；真实来源，非虚构fixture；不是用户研究判断。',
                '复核者：' + decisions['reviewer'], '复核时间：' + decision['reviewed_at'],
                '复核方法：' + decision['method'], '复核结果：' + decision['finding'],
                '材料类型：' + row['type_label'], '原缓存身份：' + row['cached_id'] + '@' + str(row['cached_version']),
                '原缓存采集时刻：' + str(row['collected_at']),
                '许可参考：' + row['cached_license_url'] + '；前次核对：' + str(row['cached_license_checked_at']),
                '本次仅保存/展示/导出标题、链接、发布者、时间和复核笔记；正文和译文均不保存，AI禁用。',
                '发布时间精度：' + row['publication_precision'],
                '观测年：' + str(row['observation_period']) + '；数据集更新日：' + str(row['source_updated_at'])])
            material = api('POST', 'evidence', {'source_id': row['source_id'], 'source_record_id': row['source_record_id'],
                'url': row['url'], 'title': row['title'], 'publisher': row['publisher'], 'published_at': row['published_at'],
                'source_updated_at': row['source_updated_at'], 'material_type': row['material_type'], 'language': 'en',
                'rights': RIGHTS, 'excerpt': '', 'translation': '', 'topic_id': topics[row['topic_key']]['id'],
                'status': 'reviewed', 'notes': notes, 'is_fixture': False})
            readback = api('GET', 'evidence/' + material['id'])
            history = api('GET', 'evidence/' + material['id'] + '/history')
            report['materials'].append({'key': row['key'], 'type_label': row['type_label'], 'topic_key': row['topic_key'],
                                       'registered': material, 'readback': readback, 'history_versions': len(history['items'])})
            write_json(directory / 'registration-report.json', report)
        report['topics'] = topics
        report['checks'] = {'material_count': api('GET', 'evidence')['total'],
            'all_manual': all(item['readback']['ingest_origin'] == 'manual' for item in report['materials']),
            'all_real': all(not item['readback']['is_fixture'] for item in report['materials']),
            'all_metadata_only': all(item['readback']['rights'] == RIGHTS and not item['readback']['excerpt'] and not item['readback']['translation'] for item in report['materials']),
            'all_single_version': all(item['history_versions'] == 1 for item in report['materials']),
            'claim_count': api('GET', 'claims')['total'], 'event_count': api('GET', 'events')['total'],
            'judgment_count': api('GET', 'judgments')['total'],
            'acquisition_receipt_count': len(store.all('evidence_acquisition')),
            'collection_job_count': len(store.all('collection_job')), 'integrity': store.integrity()}
        report['state'] = 'complete'
    except Exception as error:
        report.update({'state': 'failed', 'error': str(error)})
        raise
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        store.close()
        report['stopped_at'] = stamp()
        write_json(directory / 'registration-report.json', report)
    print(json.dumps({'state': report['state'], 'checks': report['checks'], 'data_dir': str(directory), 'port_closed': report['port']}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check-official', action='store_true')
    mode.add_argument('--register', action='store_true')
    parser.add_argument('--cache-db', type=Path, default=CACHE)
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--review-decisions', type=Path)
    args = parser.parse_args()
    if not (args.check_official or args.register):
        print(json.dumps({'mode': 'read_only', 'network_gets': 0, 'registration_writes': 0,
                          'candidates': cached_candidates(args.cache_db)}, ensure_ascii=False, indent=2))
        return
    if args.data_dir is None:
        parser.error('显式执行须指定新的隔离 --data-dir')
    directory = args.data_dir.expanduser().resolve()
    if args.check_official:
        check_official(directory, cached_candidates(args.cache_db), args.cache_db)
    else:
        if args.review_decisions is None:
            parser.error('登记须提供逐条复核决定 --review-decisions')
        register(directory, args.review_decisions)


if __name__ == '__main__':
    main()
