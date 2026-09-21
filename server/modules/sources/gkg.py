"""Bounded GDELT GKG metadata discovery. Never fetch publisher pages."""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import html
import io
import json
import os
import re
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .adapters import FetchError, _check, _external_link

INDEX_URL = 'https://data.gdeltproject.org/gdeltv2/lastupdate.txt'
INDEX_LIMIT = 64 * 1024
ZIP_LIMIT = 4 * 1024 * 1024
EXPANDED_LIMIT = 16 * 1024 * 1024
NOTE = 'GDELT GKG 15 分钟批次时间不是原文发布时间；仅最新批次，未补齐历史；按 PAGE_TITLE 与主题标签匹配关键词及排除词；仅元数据，不抓新闻正文。'


def _error(message):
    return FetchError('invalid_gkg', message)


def manifest(value):
    """Validate persisted as well as remote manifests; paths never come from callers."""
    if not isinstance(value, dict):
        raise _error('GKG 批次清单无效。')
    batch, checksum, size = value.get('batch', ''), value.get('md5', ''), value.get('size')
    if (not isinstance(batch, str) or not re.fullmatch(r'\d{14}', batch)
            or not isinstance(checksum, str) or not re.fullmatch(r'[0-9a-f]{32}', checksum)
            or type(size) is not int or not 0 < size <= ZIP_LIMIT):
        raise _error('GKG 清单含无效批次、校验值或超出 4 MiB 的压缩文件。')
    try:
        timestamp = datetime.strptime(batch, '%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise _error('GKG 批次时间无效。') from exc
    return {'batch': batch, 'md5': checksum, 'size': size,
            'batch_at': timestamp.isoformat().replace('+00:00', 'Z'),
            'url': f'https://data.gdeltproject.org/gdeltv2/{batch}.gkg.csv.zip'}


def parse_index(response):
    _check(response)
    if response.status != 200 or len(response.body) > INDEX_LIMIT:
        raise _error('GKG 最新批次索引为空或超出 64 KiB。')
    try:
        lines = response.body.decode('ascii').splitlines()
    except UnicodeError as exc:
        raise _error('GKG 索引不是有效 ASCII。') from exc
    matches = []
    for line in lines:
        fields = line.split()
        if len(fields) != 3:
            raise _error('GKG 索引行格式无效。')
        size, checksum, url = fields
        match = re.fullmatch(r'https?://data\.gdeltproject\.org/gdeltv2/(\d{14})\.gkg\.csv\.zip', url)
        if match:
            if not size.isdecimal():
                raise _error('GKG 索引大小无效。')
            matches.append(manifest({'batch': match[1], 'md5': checksum, 'size': int(size)}))
    if len(matches) != 1:
        raise _error('GKG 索引必须包含且仅包含一个固定官方域名的 GKG 批次。')
    return matches[0]


def parse_zip(response, item):
    _check(response)
    item = manifest(item)
    body = response.body
    if response.status != 200 or len(body) > ZIP_LIMIT or len(body) != item['size']:
        raise _error('GKG 压缩包大小与索引不符或超出 4 MiB。')
    # The HTTPS transport authenticates the endpoint; MD5 only checks index/file consistency.
    if hashlib.md5(body).hexdigest() != item['md5']:
        raise _error('GKG 压缩包与官方索引 MD5 不符，已拒绝解析。')
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            members = archive.infolist()
            if len(members) != 1:
                raise _error('GKG ZIP 必须仅包含单个 CSV 文件。')
            entry = members[0]
            mode = stat.S_IFMT(entry.external_attr >> 16)
            if (entry.filename != item['batch'] + '.gkg.csv' or entry.is_dir()
                    or mode not in (0, stat.S_IFREG) or entry.flag_bits & 1
                    or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                    or entry.file_size > EXPANDED_LIMIT):
                raise _error('GKG ZIP 文件路径、类型或解压大小不安全，已拒绝解析。')
            with archive.open(entry) as handle:
                raw = handle.read(EXPANDED_LIMIT + 1)
            if len(raw) > EXPANDED_LIMIT or len(raw) != entry.file_size:
                raise _error('GKG 解压响应超出 16 MiB 或文件长度不符。')
        text = raw.decode('utf-8')
    except (zipfile.BadZipFile, UnicodeError, RuntimeError, OSError, EOFError) as exc:
        raise _error('GKG ZIP 或 UTF-8 内容无效，未将错误当作空结果。') from exc
    rows, seen = [], set()
    for line in text.splitlines():
        fields = line.split('\t')
        if len(fields) != 27 or fields[1] != item['batch']:
            raise _error('GKG CSV 列数或批次时间与清单不符。')
        if fields[2] != '1' or not _external_link(fields[4]):
            continue
        title = re.search(r'<PAGE_TITLE>(.*?)</PAGE_TITLE>', fields[26], re.DOTALL)
        if not title or fields[4] in seen:
            continue
        title = ' '.join(html.unescape(title[1]).split())[:2000]
        if not title or len(fields[4]) > 8000:
            continue
        seen.add(fields[4])
        rows.append({'url': fields[4], 'title': title, 'publisher': urlsplit(fields[4]).hostname,
                     'themes': fields[7][:4000], 'gkg_record_id': fields[0][:200]})
    return rows


def result(source, job, item, rows, now):
    from server.modules.knowledge import canonical_url
    from server.platform.errors import ApiError
    words = [word.strip().casefold() for word in job.get('keywords', []) if word.strip()]
    excluded = [word.strip().casefold() for word in job.get('exclude_keywords', []) if word.strip()]
    if not words:
        raise FetchError('query_required', 'GKG 需要活动议题的明确关键词；不推断或抓取全量新闻。')
    evidence = []
    rights = {key: ('metadata' if source['rights'][key] else False) for key in ('store', 'display', 'export')}
    rights.update({'fetch': bool(source['rights']['fetch']), 'ai': False})
    for row in rows:
        searchable = (row['title'] + ' ' + row['themes']).casefold()
        if not any(word in searchable for word in words) or any(word in searchable for word in excluded):
            continue
        try:
            identity = canonical_url(row['url'])
        except ApiError:
            continue
        evidence.append({'source_id': source['id'], 'topic_id': job['topic_id'],
            'url': row['url'], 'source_record_id': identity, 'title': row['title'], 'excerpt': '',
            'channels': [{'source_id': source['id'], 'source_record_id': identity, 'url': row['url'],
                          'publisher': row['publisher'], 'title': row['title'], 'discovered_at': now}],
            'rights': dict(rights), 'material_type': 'news', 'publisher': row['publisher'],
            'language': 'unknown', 'author': None, 'status': 'unverified', 'published_at': None,
            'source_updated_at': None, 'provider_seen_at': item['batch_at'],
            'collected_at': now, 'discovered_at': now, 'notes': NOTE})
    return {'evidence': evidence, 'observations': [], 'data_as_of': item['batch_at'],
            'next_page': None, 'saturated': False, 'not_modified': False,
            'coverage_gap': {'start': job.get('covered_until'), 'end': now, 'reason': NOTE}}


class Cache:
    """Rebuildable, provider-global metadata cache; no news bodies or ZIP extraction."""
    def __init__(self, data_dir):
        self.path = Path(data_dir) / 'sources' / 'gdelt-gkg'
        self.path.mkdir(parents=True, exist_ok=True, mode=0o700)

    @contextlib.contextmanager
    def lock(self):
        with (self.path / 'cache.lock').open('a') as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def read(self, name):
        try:
            path = self.path / name
            if path.stat().st_size > EXPANDED_LIMIT:
                raise _error('GKG 本地缓存超出大小限制。')
            return json.loads(path.read_text())
        except FileNotFoundError:
            return None
        except (ValueError, UnicodeError) as exc:
            raise _error('GKG 本地缓存损坏；未将其当作空结果。') from exc

    def write(self, name, value):
        payload = json.dumps(value, ensure_ascii=False).encode()
        if len(payload) > EXPANDED_LIMIT:
            raise _error('GKG 元数据缓存超出 16 MiB。')
        fd, temporary = tempfile.mkstemp(prefix='.pending-', dir=self.path)
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path / name)
            directory = os.open(self.path, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def key(item):
        item = manifest(item)
        return item['batch'] + '-' + item['md5'] + '.json'

    def rows(self, item):
        return self.read(self.key(item))

    def save_rows(self, item, rows):
        self.write(self.key(item), rows)
