"""M2 owns source configuration, durable collection jobs and shared quotas."""
from __future__ import annotations

import fcntl
import hashlib
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from server.platform.errors import ApiError
from . import adapters

UTC = timezone.utc
FREE_ADAPTERS = {'gdelt', 'rss', 'world_bank'}
CONFIG_KEYS = {'feed_url', 'query', 'countries', 'indicators', 'topic_ids'}
SOURCE_FIELDS = {'name', 'adapter', 'domain', 'languages', 'regions', 'license_url', 'checked_at',
                 'rights', 'enabled', 'budget_daily', 'interval_seconds', 'config'}
RUNNING = {'queued', 'running', 'retry'}


def _date(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(UTC)


def _stamp(value):
    return value.astimezone(UTC).isoformat().replace('+00:00', 'Z')


def _later(now, seconds):
    return _stamp(_date(now) + timedelta(seconds=seconds))


def _get(store, kind, record_id):
    try:
        return store.get(kind, record_id)
    except ApiError as exc:
        if exc.status == 404:
            return None
        raise


def _patch(store, kind, record, values):
    return store.update(kind, record['id'], values, record['version'])


def seed_sources(store):
    """Local-only initialization. Does not fetch and never resets user settings."""
    rights = {'fetch': True, 'store': True, 'display': True, 'export': True, 'ai': False}
    definitions = [
        ('source-gdelt', 'GDELT 新闻发现', 'gdelt', 'api.gdeltproject.org',
         'https://gdeltproject.org/about.html', 1800, 500, {'query': '', 'topic_ids': []}),
        ('source-fed', '美国联邦储备委员会 RSS', 'rss', 'www.federalreserve.gov',
         'https://www.federalreserve.gov/disclaimer.htm', 1800, 72,
         {'feed_url': 'https://www.federalreserve.gov/feeds/press_all.xml', 'topic_ids': []}),
        ('source-world-bank', 'World Bank WDI 国家背景', 'world_bank', 'api.worldbank.org',
         'https://data.worldbank.org/summary-terms-of-use', 604800, 20,
         {'countries': ['CHN', 'USA'], 'indicators': list(adapters.INDICATORS), 'topic_ids': []}),
        ('source-manual', '人工登记原始材料', 'manual', '', '', 86400, 0, {}),
        ('source-paid', '付费数据（预留）', 'paid', '', '', 86400, 0, {}),
        ('source-ai', 'AI 能力（预留）', 'ai', '', '', 86400, 0, {}),
    ]
    with store.transaction():
        for sid, name, adapter, domain, license_url, interval, budget, config in definitions:
            if _get(store, 'source', sid):
                continue
            enabled = adapter in FREE_ADAPTERS or adapter == 'manual'
            status = ('not_configured' if adapter == 'gdelt' else 'ready') if adapter in FREE_ADAPTERS else ('manual' if adapter == 'manual' else 'not_configured')
            store.create('source', {'name': name, 'adapter': adapter, 'domain': domain,
                'languages': ['en'] if adapter != 'gdelt' else ['multilingual'], 'regions': ['global'],
                'license_url': license_url, 'checked_at': '2026-09-20',
                'rights': dict(rights) if adapter in FREE_ADAPTERS else {**rights, 'fetch': False},
                'enabled': enabled, 'budget_daily': budget, 'interval_seconds': interval,
                'config': config, 'status': status, 'last_attempt': None, 'last_success': None,
                'data_as_of': None, 'next_check': None, 'requests_today': 0,
                'budget_date': None, 'last_error': None, 'coverage_gaps': [],
                'license_note': '仅采集许可范围内的元数据；不抓新闻正文和图片。AI 默认禁止。',
                'cost_type': 'free' if adapter in FREE_ADAPTERS else ('manual' if adapter == 'manual' else 'disabled'),
            }, record_id=sid)


def _validate(data, existing=None):
    unknown = set(data) - SOURCE_FIELDS - {'expected_version'}
    if unknown:
        raise ApiError(400, 'unknown_fields', '来源配置含不支持的字段。', {'fields': sorted(unknown)})
    source = {**(existing or {}), **{k: v for k, v in data.items() if k in SOURCE_FIELDS}}
    if source.get('adapter') not in FREE_ADAPTERS | {'manual', 'paid', 'ai'}:
        raise ApiError(400, 'invalid_adapter', '请选择支持的来源适配器。')
    if existing and source['adapter'] != existing['adapter']:
        raise ApiError(400, 'immutable_adapter', '适配器类型不能修改，请另建来源。')
    if not isinstance(source.get('name'), str) or not source['name'].strip() or len(source['name']) > 200:
        raise ApiError(400, 'invalid_name', '来源名称须为 1—200 字符。')
    license_url = source.get('license_url', '')
    if license_url:
        try:
            licensed = urlsplit(license_url)
            valid_license = licensed.scheme == 'https' and bool(licensed.hostname) and not licensed.username and not licensed.password
        except ValueError:
            valid_license = False
        if not valid_license:
            raise ApiError(400, 'invalid_license_url', '许可链接须为不含认证信息的 HTTPS 地址。')
    source.setdefault('enabled', False)
    if not isinstance(source['enabled'], bool):
        raise ApiError(400, 'invalid_enabled', 'enabled 须为布尔值。')
    if source['adapter'] in {'paid', 'ai'} and source['enabled']:
        raise ApiError(400, 'paid_disabled', 'P0 不支持启用付费或 AI 适配器。')
    source.setdefault('budget_daily', 50)
    source.setdefault('interval_seconds', 1800)
    for key, low, high in [('budget_daily', 0, 10000), ('interval_seconds', 300, 2592000)]:
        value = source[key]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ApiError(400, 'invalid_configuration', f'{key} 须为 {low}—{high} 的整数。')
    config = source.setdefault('config', {})
    if not isinstance(config, dict) or set(config) - CONFIG_KEYS:
        raise ApiError(400, 'invalid_configuration', '来源 config 含未知配置项。')
    rights = source.setdefault('rights', {key: False for key in ['fetch', 'store', 'display', 'export', 'ai']})
    if not isinstance(rights, dict) or set(rights) != {'fetch', 'store', 'display', 'export', 'ai'} or any(not isinstance(value, bool) for value in rights.values()):
        raise ApiError(400, 'invalid_rights', 'rights 须包含五项布尔许可。')
    if rights['ai']:
        raise ApiError(400, 'ai_disabled', 'P0 默认不允许资料发送给 AI。')
    if source['adapter'] in FREE_ADAPTERS and source['enabled'] and (not rights['fetch'] or not rights['store'] or not source.get('license_url') or not source.get('checked_at')):
        raise ApiError(400, 'license_required', '启用采集前需填写许可链接、核对日期，并允许获取及存储。')
    if source['adapter'] == 'manual':
        rights['fetch'] = False
    if source['adapter'] == 'rss':
        try:
            url = urlsplit(config.get('feed_url', ''))
            valid = url.scheme == 'https' and url.hostname == 'www.federalreserve.gov' and url.path.startswith('/feeds/') and not url.username and not url.password and not url.query and not url.fragment and url.port in (None, 443)
        except ValueError:
            valid = False
        if not valid:
            raise ApiError(400, 'unreviewed_rss', 'P0 RSS 仅支持已核对许可的 Federal Reserve /feeds/ 地址；其他来源先用人工链接登记。')
    if source['adapter'] == 'gdelt':
        query = config.get('query', '')
        if not isinstance(query, str) or len(query) > 500 or any(ord(x) < 32 for x in query):
            raise ApiError(400, 'invalid_query', 'GDELT 查询须为最多 500 字符的文本。')
    if source['adapter'] == 'world_bank':
        countries = config.get('countries', ['CHN', 'USA'])
        indicators = config.get('indicators', list(adapters.INDICATORS))
        if not isinstance(countries, list) or not 1 <= len(countries) <= 20 or any(not isinstance(x, str) or not re.fullmatch('[A-Z]{3}', x) for x in countries):
            raise ApiError(400, 'invalid_countries', '请选择 1—20 个 ISO 三字母国家代码。')
        if not isinstance(indicators, list) or not indicators or any(x not in adapters.INDICATORS for x in indicators):
            raise ApiError(400, 'invalid_indicators', '仅启用已核对许可的 GDP 和人口指标。')
    if not isinstance(config.get('topic_ids', []), list) or any(not isinstance(x, str) for x in config.get('topic_ids', [])):
        raise ApiError(400, 'invalid_topics', 'topic_ids 须为议题 ID 数组。')
    for key in ('languages', 'regions'):
        source.setdefault(key, [])
        if not isinstance(source[key], list) or any(not isinstance(x, str) for x in source[key]):
            raise ApiError(400, 'invalid_configuration', f'{key} 须为文本数组。')
    # Provider endpoints are fixed by code, never user controlled domains.
    source['domain'] = {'gdelt': 'api.gdeltproject.org', 'rss': 'www.federalreserve.gov', 'world_bank': 'api.worldbank.org'}.get(source['adapter'], source.get('domain', ''))
    return {key: source[key] for key in SOURCE_FIELDS if key in source}


def _configured(source):
    return source.get('enabled') and source['adapter'] in FREE_ADAPTERS and source.get('rights', {}).get('fetch') and source.get('rights', {}).get('store')


def _topic_query(store, source, topic_id):
    query = source.get('config', {}).get('query', '').strip()
    if topic_id:
        topic = store.get('topic', topic_id)
        if topic.get('status') != 'active':
            raise ApiError(400, 'topic_inactive', '已暂停或归档议题不创建新采集任务。')
        words = [str(item).strip().replace('"', '') for item in topic.get('keywords', []) if str(item).strip()]
        excludes = [str(item).strip().replace('"', '') for item in topic.get('exclude_keywords', []) if str(item).strip()]
        if not query and words:
            query = '(' + ' OR '.join('"' + word + '"' for word in words[:12]) + ')'
        if excludes:
            query += ' ' + ' '.join('-"' + word + '"' for word in excludes[:12])
    return query.strip()[:500]


def in_maintenance(store):
    return (Path(store.data_dir) / 'maintenance.json').exists()


def enqueue(store, source_id, topic_id=None):
    """Durable nonblocking schedule; all manual/scheduled calls share one job."""
    if in_maintenance(store):
        raise ApiError(503, 'maintenance', '维护期间暂停采集，检查点保持不变。')
    with store.transaction():
        source = store.get('source', source_id)
        if not _configured(source):
            raise ApiError(400, 'source_not_configured', '来源已停用、未配置或仅允许人工登记。')
        query = _topic_query(store, source, topic_id)
        topic = store.get('topic', topic_id) if topic_id else {}
        if source['adapter'] == 'gdelt' and not query:
            raise ApiError(400, 'query_required', 'GDELT 需要配置查询或选择含关键词的真实议题。')
        job_id = 'job-' + hashlib.sha256(f'{source_id}:{topic_id or "global"}'.encode()).hexdigest()[:24]
        job = _get(store, 'collection_job', job_id)
        if job and job['state'] in RUNNING:
            return {'status': 'already_queued', 'job': job}
        now = store.now()
        prior_end = (job or {}).get('covered_until')
        gaps = list((job or {}).get('coverage_gaps', []))
        checkpoint = {'page': 1}
        if source['adapter'] == 'gdelt':
            end = _date(now)
            start = _date(prior_end) - timedelta(minutes=30) if prior_end else end - timedelta(days=1)
            # Our automatic recovery policy is bounded independently of upstream history claims.
            earliest = end - timedelta(days=90)
            if start < earliest:
                gaps.append({'start': _stamp(start), 'end': _stamp(earliest), 'reason': '超出本版 90 天自动补采上限，历史能力未作完整验证。'})
                start = earliest
            checkpoint = {'window_start': _stamp(start), 'window_end': _stamp(min(start + timedelta(hours=6), end)), 'target_end': now, 'page': 1}
        values = {'source_id': source_id, 'topic_id': topic_id, 'query': query,
                  'checkpoint': checkpoint, 'attempts': 0, 'state': 'queued',
                  'keywords': topic.get('keywords', []), 'exclude_keywords': topic.get('exclude_keywords', []),
                  'request_count': (job or {}).get('request_count', 0), 'next_attempt': now,
                  'coverage_gaps': gaps, 'gap_start': gaps[0]['start'] if gaps else None,
                  'gap_end': gaps[-1]['end'] if gaps else None, 'last_error': None,
                  'covered_until': prior_end, 'last_result_count': 0}
        if job:
            job = _patch(store, 'collection_job', job, values)
        else:
            job = store.create('collection_job', values, record_id=job_id)
        return {'status': 'queued', 'job': job}


def coverage(store, topic_id=None):
    sources = []
    for source in store.all('source'):
        if topic_id and source.get('config', {}).get('topic_ids') and topic_id not in source['config']['topic_ids']:
            continue
        if not source.get('enabled') or source['adapter'] not in FREE_ADAPTERS:
            continue
        status = source['status']
        now = store.now()
        if source.get('last_success') and status == 'ready' and _date(now) - _date(source['last_success']) > timedelta(seconds=source['interval_seconds'] * 2):
            status = 'stale'
        jobs = [job for job in store.all('collection_job') if job['source_id'] == source['id'] and (not topic_id or job.get('topic_id') in (None, topic_id))]
        gaps = [gap for job in jobs for gap in job.get('coverage_gaps', [])]
        fresh = status == 'ready' and bool(source.get('last_success'))
        if topic_id and source['adapter'] == 'gdelt':
            fresh = fresh and any(job.get('covered_until') for job in jobs)
        checks_pending = any(job['state'] in RUNNING for job in jobs)
        sources.append({'id': source['id'], 'name': source['name'], 'adapter': source['adapter'],
            'status': status, 'data_status': 'fresh' if fresh else ('stale' if source.get('last_success') else 'unavailable'),
            'last_attempt': source.get('last_attempt'), 'last_success': source.get('last_success'),
            'data_as_of': source.get('data_as_of'), 'next_check': source.get('next_check'),
            'reason': source.get('last_error'), 'coverage_gaps': gaps,
            'last_result_count': source.get('last_result_count'), 'check_complete': fresh and not gaps and not checks_pending})
    complete = sum(item['check_complete'] for item in sources)
    status = 'not_configured' if not sources else ('complete' if complete == len(sources) else ('partial' if any(item['last_success'] for item in sources) else 'unavailable'))
    empty = 'no_matches' if status == 'complete' and all(item['last_result_count'] == 0 for item in sources) else None
    return {'coverage_status': status, 'sources': sources, 'empty_reason': empty,
        'explanation': {'complete': '当前配置来源检查完成，不表示世界信息完整。',
                        'partial': '部分来源检查失败、陈旧或存在采集缺口，无法确认全范围没有变化。',
                        'unavailable': '来源尚未成功检查，无法判断是否有新变化。',
                        'not_configured': '没有启用可采集来源；可继续人工研究。'}[status]}


def handle(store, method, segments, body, query):
    if not segments or segments[0] != 'sources':
        return None
    seed_sources(store)
    if len(segments) == 2 and segments[1] == 'coverage' and method == 'GET':
        return coverage(store, query.get('topic_id'))
    if len(segments) == 2 and segments[1] == 'jobs' and method == 'GET':
        return store.list('collection_job', topic_id=query.get('topic_id'), limit=query.get('limit', 50), offset=query.get('offset', 0))
    if len(segments) == 3 and segments[2] == 'refresh' and method == 'POST':
        return enqueue(store, segments[1], body.get('topic_id'))
    if len(segments) == 1 and method == 'GET':
        result = store.list('source', limit=query.get('limit', 100), offset=query.get('offset', 0))
        for source in result['items']:
            if source.get('budget_date') != store.now()[:10]:
                source['requests_today'] = 0
        return result
    if len(segments) == 1 and method == 'POST':
        data = _validate(body)
        data.update({'status': 'ready' if data['enabled'] and data['adapter'] in FREE_ADAPTERS else ('manual' if data['adapter'] == 'manual' else 'not_configured'), 'last_attempt': None, 'last_success': None, 'data_as_of': None, 'next_check': None, 'requests_today': 0, 'budget_date': None, 'last_error': None})
        return store.create('source', data)
    if len(segments) == 2 and method == 'GET':
        return store.get('source', segments[1])
    if len(segments) == 3 and segments[2] == 'history' and method == 'GET':
        return {'items': store.history('source', segments[1])}
    if len(segments) == 2 and method == 'PATCH':
        with store.transaction():
            source = store.get('source', segments[1])
            data = _validate(body, source)
            data['next_check'] = None
            data['status'] = 'ready' if data['enabled'] and data['adapter'] in FREE_ADAPTERS else ('manual' if data['adapter'] == 'manual' else ('not_configured' if data['adapter'] in {'ai', 'paid'} else 'disabled'))
            return store.update('source', source['id'], data, body.get('expected_version'))
    raise ApiError(404, 'not_found', '来源接口不存在。')


class Scheduler:
    def __init__(self, store, evidence_sink=None, observation_sink=None, fetcher=None):
        self.store = store
        self.evidence_sink = evidence_sink
        self.observation_sink = observation_sink
        self.fetcher = fetcher or adapters.fetch
        self._stop = threading.Event()
        self._thread = None
        self._lock_file = None
        self.last_error = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return self
        lock_path = Path(self.store.data_dir) / 'collector.lock'
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_file = lock_path.open('a+')
        try:
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._lock_file.close()
            self._lock_file = None
            raise ApiError(409, 'collector_running', '此数据目录已有采集实例。')
        seed_sources(self.store)
        with self.store.transaction():
            for job in self.store.all('collection_job'):
                if job['state'] == 'running':
                    _patch(self.store, 'collection_job', job, {'state': 'retry', 'next_attempt': self.store.now(), 'last_error': '上次采集被中断；从持久检查点恢复。'})
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name='world-insight-collector', daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=30)
            if self._thread.is_alive():
                raise ApiError(503, 'collector_stopping', '正在等待当前有界网络请求结束，请稍后重试停止。')
        if self._lock_file:
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
            self._lock_file.close()
            self._lock_file = None

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:
                self.last_error = type(exc).__name__
            self._stop.wait(1)

    def _schedule_due(self):
        now = self.store.now()
        topics = [topic for topic in self.store.all('topic') if topic.get('status') == 'active']
        for source in self.store.all('source'):
            if not _configured(source) or (source.get('next_check') and source['next_check'] > now):
                continue
            config = source.get('config', {})
            topic_ids = config.get('topic_ids', [])
            if source['adapter'] == 'gdelt' and not config.get('query') and not topic_ids:
                topic_ids = [topic['id'] for topic in topics if topic.get('keywords')]
                if not topic_ids:
                    continue
            for topic_id in topic_ids or [None]:
                try:
                    enqueue(self.store, source['id'], topic_id)
                except ApiError as exc:
                    if exc.status not in (400, 404):
                        raise
            with self.store.transaction():
                current = self.store.get('source', source['id'])
                _patch(self.store, 'source', current, {'next_check': _later(now, current['interval_seconds'])})

    def tick(self, schedule=True):
        """One bounded request. Tests can call with fake fetcher and schedule=False."""
        if in_maintenance(self.store):
            return None
        if schedule:
            self._schedule_due()
        now = self.store.now()
        jobs = [job for job in self.store.all('collection_job') if job['state'] in RUNNING and (not job.get('next_attempt') or job['next_attempt'] <= now)]
        if not jobs:
            return None
        job = sorted(jobs, key=lambda item: (item.get('next_attempt') or '', item['id']))[0]
        with self.store.transaction():
            job = self.store.get('collection_job', job['id'])
            source = self.store.get('source', job['source_id'])
            if not _configured(source):
                return _patch(self.store, 'collection_job', job, {'state': 'cancelled', 'last_error': '来源已停用。'})
            # Source-wide spacing and request budget include all topics, manual calls and retries.
            if source['adapter'] == 'gdelt' and source.get('last_attempt') and _date(now) - _date(source['last_attempt']) < timedelta(seconds=6):
                return _patch(self.store, 'collection_job', job, {'state': 'retry', 'next_attempt': _later(source['last_attempt'], 6)})
            count = source.get('requests_today', 0) if source.get('budget_date') == now[:10] else 0
            if count >= source['budget_daily']:
                tomorrow = _stamp((_date(now) + timedelta(days=1)).replace(hour=0, minute=0, second=1, microsecond=0))
                _patch(self.store, 'source', source, {'status': 'quota_exhausted', 'last_error': '本地每日免费请求预算已用尽。', 'next_check': tomorrow})
                return _patch(self.store, 'collection_job', job, {'state': 'retry', 'next_attempt': tomorrow, 'last_error': '请求预算已用尽，检查点保留。'})
            source = _patch(self.store, 'source', source, {'requests_today': count + 1, 'budget_date': now[:10], 'last_attempt': now})
            job = _patch(self.store, 'collection_job', job, {'state': 'running', 'attempts': job['attempts'] + 1, 'request_count': job['request_count'] + 1})
        # No database transaction or Store lock while waiting for upstream.
        if in_maintenance(self.store):
            return job
        try:
            url, headers = adapters.request_for(source, job)
            response = self.fetcher(url, headers)
            parsed = adapters.parse(source, job, response, now)
            return self._succeed(source, job, parsed, now)
        except Exception as exc:
            return self._fail(source, job, exc, now)

    def _succeed(self, source, job, parsed, now):
        if in_maintenance(self.store):
            return job
        if self.evidence_sink is None or self.observation_sink is None:
            from server.modules import knowledge
            evidence_sink = self.evidence_sink or knowledge.ingest
            observation_sink = self.observation_sink or knowledge.upsert_observation
        else:
            evidence_sink, observation_sink = self.evidence_sink, self.observation_sink
        with self.store.transaction():
            current = self.store.get('source', source['id'])
            current_job = self.store.get('collection_job', job['id'])
            if not _configured(current) or current.get('config') != source.get('config') or current.get('rights') != source.get('rights'):
                return _patch(self.store, 'collection_job', current_job, {'state': 'cancelled', 'last_error': '请求期间来源配置或许可发生变化，本批次未入库。'})
            versions = {}
            for item in parsed['evidence']:
                record = evidence_sink(self.store, item)
                versions[item['source_record_id']] = f"{record['id']}@{record['version']}"
            for item in parsed['observations']:
                item['evidence_version_ids'] = [versions[item['source_record_id']]]
                payload = {key: value for key, value in item.items() if key not in ('source_record_id', 'source_updated_at', 'collected_at')}
                payload['notes'] = f"WDI 数据集更新日：{item.get('source_updated_at') or '未知'}；本地采集时间：{item.get('collected_at')}。逐项发布日期未知。"
                observation_sink(self.store, payload)
            checkpoint = dict(job.get('checkpoint', {}))
            gaps = list(job.get('coverage_gaps', []))
            complete = True
            if parsed['next_page']:
                checkpoint['page'] = parsed['next_page']
                complete = False
            if source['adapter'] == 'gdelt':
                start, end, target = (_date(checkpoint[key]) for key in ['window_start', 'window_end', 'target_end'])
                if parsed['saturated']:
                    gaps.append({'start': _stamp(start), 'end': _stamp(end), 'reason': 'GDELT 返回 250 条上限，不能确认此时段覆盖完整。'})
                if end < target:
                    checkpoint['window_start'] = _stamp(end - timedelta(minutes=1))
                    checkpoint['window_end'] = _stamp(min(end + timedelta(hours=6), target))
                    complete = False
            if source['adapter'] == 'rss' and job.get('covered_until') and _date(now) - _date(job['covered_until']) > timedelta(seconds=source['interval_seconds'] * 2):
                gaps.append({'start': job['covered_until'], 'end': now, 'reason': 'RSS 仅提供当前 feed，停机区间已补读可见条目，历史完整性无法保证。'})
            patch = {'state': 'complete' if complete else 'queued', 'checkpoint': checkpoint,
                'last_error': None, 'attempts': 0, 'last_result_count': len(parsed['evidence']), 'last_success': now,
                'next_attempt': _later(now, 6 if source['adapter'] == 'gdelt' else 1),
                'coverage_gaps': gaps, 'gap_start': gaps[0]['start'] if gaps else None,
                'gap_end': gaps[-1]['end'] if gaps else None}
            if complete:
                patch['covered_until'] = now
            job = _patch(self.store, 'collection_job', current_job, patch)
            values = {'status': 'ready', 'last_success': now, 'last_error': None,
                      'data_as_of': parsed['data_as_of'], 'last_result_count': current.get('last_result_count', 0) if parsed['not_modified'] else len(parsed['evidence'])}
            for key in ('etag', 'last_modified'):
                if parsed.get(key):
                    values[key] = parsed[key]
            _patch(self.store, 'source', current, values)
            if current.get('status') in ('failed', 'stale'):
                self.store.publish('source.recovered', source['id'], {'title': source['name'] + ' 已恢复', 'topic_id': job.get('topic_id'), 'source_id': source['id']})
            return job

    def _fail(self, source, job, exc, now):
        if in_maintenance(self.store):
            return job
        code = exc.code if isinstance(exc, adapters.FetchError) else 'processing_failed'
        message = exc.message if isinstance(exc, adapters.FetchError) else '采集入库失败，已回滚当前批次并保留检查点。'
        delay = exc.retry_after if isinstance(exc, adapters.FetchError) and exc.retry_after else min(3600, 30 * (2 ** min(job['attempts'] - 1, 6)))
        with self.store.transaction():
            current = self.store.get('source', source['id'])
            current_job = self.store.get('collection_job', job['id'])
            _patch(self.store, 'source', current, {'status': 'failed', 'last_error': message, 'last_error_code': code, 'next_check': _later(now, delay)})
            job = _patch(self.store, 'collection_job', current_job, {'state': 'retry', 'last_error': message, 'error_code': code, 'next_attempt': _later(now, delay)})
            if current.get('status') != 'failed':
                self.store.publish('source.failed', source['id'], {'title': source['name'] + ' 检查失败', 'topic_id': job.get('topic_id'), 'source_id': source['id'], 'reason': message})
            return job


def start_scheduler(store, evidence_sink=None, observation_sink=None, fetcher=None):
    return Scheduler(store, evidence_sink, observation_sink, fetcher).start()


def stop_scheduler(scheduler):
    if scheduler:
        scheduler.stop()
