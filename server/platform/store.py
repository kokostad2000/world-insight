"""Transactional, versioned storage. Domain validation belongs to module owners."""
import contextlib
import copy
import datetime as dt
import json
import sqlite3
import threading
import uuid
from pathlib import Path

from .errors import ApiError
from .migrations import migrate


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.data_dir = self.path.parent
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._local = threading.local()
        self._policy_index = None
        self.db = sqlite3.connect(str(self.path), isolation_level=None, check_same_thread=False, timeout=15)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('PRAGMA secure_delete=ON')
        self.db.execute('PRAGMA busy_timeout=15000')
        migrate(self.db, self.path)

    @staticmethod
    def now():
        return dt.datetime.now(dt.timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')

    @contextlib.contextmanager
    def transaction(self):
        with self._lock:
            depth = getattr(self._local, 'depth', 0)
            self._local.depth = depth + 1
            if depth == 0:
                self.db.execute('BEGIN IMMEDIATE')
            try:
                yield self
                if depth == 0:
                    self.db.execute('COMMIT')
            except BaseException:
                self._policy_index = None
                if depth == 0 and self.db.in_transaction:
                    self.db.execute('ROLLBACK')
                raise
            finally:
                self._local.depth = depth

    def create(self, kind, data, record_id=None):
        with self.transaction():
            record_id = record_id or str(uuid.uuid4())
            now = self.now()
            record = {**data, 'id': record_id, 'version': 1, 'created_at': now, 'updated_at': now}
            raw = json.dumps(record, ensure_ascii=False, allow_nan=False)
            try:
                self.db.execute('INSERT INTO records(kind,id,topic_id,version,data,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                                (kind, record_id, record.get('topic_id'), 1, raw, now, now))
                self.db.execute('INSERT INTO versions(kind,id,version,data) VALUES(?,?,?,?)', (kind,record_id,1,raw))
            except sqlite3.IntegrityError as exc:
                raise ApiError(409, 'already_exists', '此记录已存在', {'id': record_id}) from exc
            self._policy_index = None
            return record

    def get(self, kind, record_id):
        with self._lock:
            row = self.db.execute('SELECT data FROM records WHERE kind=? AND id=?', (kind, record_id)).fetchone()
            if not row:
                raise ApiError(404, 'not_found', '记录不存在', {'kind':kind,'id':record_id})
            return json.loads(row['data'])

    def list(self, kind, topic_id=None, limit=100, offset=0, search=None, include_deleted=False):
        try:
            limit, offset = min(200, max(1,int(limit))), max(0,int(offset))
        except (TypeError, ValueError) as exc:
            raise ApiError(400, 'invalid_pagination', '分页参数必须是整数') from exc
        where, args = ['kind=?'], [kind]
        if not include_deleted:
            where.append("COALESCE(json_extract(data,'$.deleted'),0)=0")
        if topic_id is not None:
            where.append('(topic_id=? OR EXISTS (SELECT 1 FROM json_each(records.data,\'$.topic_ids\') WHERE value=?))'); args.extend([topic_id,topic_id])
        if search:
            where.append('data LIKE ?'); args.append('%'+search+'%')
        sql = ' AND '.join(where)
        with self._lock:
            total = self.db.execute('SELECT count(*) FROM records WHERE '+sql, args).fetchone()[0]
            items = self.db.execute('SELECT data FROM records WHERE '+sql+' ORDER BY updated_at DESC,id LIMIT ? OFFSET ?', args+[limit,offset]).fetchall()
        return {'items':[json.loads(r[0]) for r in items], 'total':total,'offset':offset,'limit':limit,
                'data_status':'fresh', 'empty_reason':'no_matches' if not total else None}

    def all(self, kind, topic_id=None, include_deleted=False):
        with self._lock:
            if topic_id is None:
                rows = self.db.execute('SELECT data FROM records WHERE kind=? ORDER BY updated_at DESC,id',(kind,)).fetchall()
            else:
                rows = self.db.execute('SELECT data FROM records WHERE kind=? AND (topic_id=? OR EXISTS (SELECT 1 FROM json_each(records.data,\'$.topic_ids\') WHERE value=?)) ORDER BY updated_at DESC,id',(kind,topic_id,topic_id)).fetchall()
        records = [json.loads(r[0]) for r in rows]
        return records if include_deleted else [r for r in records if not r.get('deleted')]

    def find(self, kind, field, value, include_deleted=False):
        if not field.replace('_','').isalnum():
            raise ValueError('Invalid field name')
        with self._lock:
            rows = self.db.execute(f"SELECT data FROM records WHERE kind=? AND json_extract(data,'$.{field}') IS ?",(kind,value)).fetchall()
        records = [json.loads(r[0]) for r in rows]
        return records if include_deleted else [r for r in records if not r.get('deleted')]

    def snapshots(self):
        """Complete read-only version scan, including tombstones and historical references."""
        with self._lock:
            rows = self.db.execute('SELECT kind,data FROM versions ORDER BY kind,id,version').fetchall()
        return [{'kind': row[0], 'record': json.loads(row[1])} for row in rows]

    def policy_snapshots(self, evidence_ids):
        """Select complete requested histories, origins and historical referrers.

        The reusable index contains immutable facts, never permission decisions or
        clock-dependent expiry. Local writes, rollbacks, same-version redaction
        and external SQLite commits invalidate it. Call inside the read transaction.
        Returned copies cannot alter the index or another request's policy context.
        """
        with self._lock:
            revision = (self.db.total_changes, self.db.execute('PRAGMA data_version').fetchone()[0])
            if self._policy_index is None or self._policy_index['revision'] != revision:
                histories, incoming, policies = {}, {}, []
                def refs(value):
                    found = set()
                    if isinstance(value, dict):
                        for key, child in value.items():
                            if key.endswith('evidence_version_ids') and isinstance(child, list):
                                found.update(ref.rsplit('@', 1)[0] for ref in child if isinstance(ref, str) and '@' in ref)
                            elif key in ('evidence_id', 'origin_evidence_id') and isinstance(child, str):
                                found.add(child)
                            else:
                                found.update(refs(child))
                    elif isinstance(value, list):
                        for child in value:
                            found.update(refs(child))
                    return found
                for row in self.db.execute('SELECT kind,id,version,data FROM versions ORDER BY kind,id,version'):
                    entry = {'kind': row['kind'], 'record': json.loads(row['data'])}
                    key = (row['kind'], row['id'])
                    histories.setdefault(key, []).append(entry)
                    if row['kind'] in ('source', 'recovery_source_policy', 'retention_settings'):
                        policies.append(entry)
                    for evidence_id in refs(entry['record']):
                        incoming.setdefault(evidence_id, []).append(entry)
                self._policy_index = {'revision': revision, 'histories': histories,
                                      'incoming': incoming, 'policies': policies}
            index, seen, pending = self._policy_index, set(), list(evidence_ids)
            selected = list(index['policies'])
            while pending:
                record_id = pending.pop()
                if record_id in seen:
                    continue
                seen.add(record_id)
                history = index['histories'].get(('evidence', record_id), [])
                selected.extend(history)
                pending.extend(entry['record']['origin_evidence_id'] for entry in history
                               if entry['record'].get('origin_evidence_id'))
            # Real historical snapshots provide candidate-retention protection.
            # A removed citation or an old original link continues to protect its target.
            for record_id in seen:
                selected.extend(index['incoming'].get(record_id, []))
            unique = {(entry['kind'], entry['record']['id'], entry['record']['version']): entry for entry in selected}
            return copy.deepcopy(list(unique.values()))

    def redact_content(self, kind, record_id, expected_version, reason, operation_id):
        """Explicit licensed-content expiry exception to immutable payload snapshots.

        IDs, version numbers, provenance and user notes survive. No original text
        is copied into the audit. Domain owners decide eligibility and propagation.
        """
        if kind != 'evidence' or not reason or not operation_id:
            raise ApiError(400, 'invalid_redaction', '内容到期清理须指定材料、原因和操作编号')
        with self.transaction():
            old = self.get(kind, record_id)
            if operation_id in old.get('redaction_operation_ids', []):
                return old
            if old['version'] != expected_version:
                raise ApiError(409, 'version_conflict', '材料在清理前已变化，请重新预览')
            self._policy_index = None
            timestamp = self.now()
            for snapshot in self.history(kind, record_id):
                snapshot.update({'excerpt': '', 'translation': '', 'content_fingerprint': None,
                                 'content_expired': True, 'content_redacted_at': timestamp,
                                 'content_redaction_reason': reason})
                raw = json.dumps(snapshot, ensure_ascii=False, allow_nan=False)
                self.db.execute('UPDATE versions SET data=? WHERE kind=? AND id=? AND version=?',
                                (raw, kind, record_id, snapshot['version']))
                if snapshot['version'] == old['version']:
                    self.db.execute('UPDATE records SET data=? WHERE kind=? AND id=?', (raw, kind, record_id))
            return self.update(kind, record_id, {'excerpt': '', 'translation': '', 'content_fingerprint': None,
                'content_expired': True, 'content_redacted_at': timestamp, 'content_redaction_reason': reason,
                'redaction_operation_ids': old.get('redaction_operation_ids', []) + [operation_id]}, expected_version)

    def compact(self):
        """Reclaim redacted database/free-page and WAL bytes after a committed batch."""
        with self._lock:
            if self.db.in_transaction:
                raise RuntimeError('Compaction requires a committed transaction')
            checkpoint = self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
            if checkpoint[0]:
                raise ApiError(503, 'redaction_checkpoint_busy', '清理已提交，数据库仍被读取；稍后重试收缩')
            self.db.execute('VACUUM')
            checkpoint = self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
            if checkpoint[0]:
                raise ApiError(503, 'redaction_checkpoint_busy', '清理已提交，稍后重试日志收缩')

    def update(self, kind, record_id, data, expected_version):
        with self.transaction():
            old = self.get(kind, record_id)
            if isinstance(expected_version, bool) or not isinstance(expected_version,int):
                raise ApiError(400, 'expected_version_required', '修改时必须提交当前版本号')
            if old['version'] != expected_version:
                raise ApiError(409, 'version_conflict', '记录已被其他窗口修改，请查看最新版本后重新保存', {'current_version':old['version'],'current':old})
            clean = {k:v for k,v in data.items() if k not in ('id','version','created_at','updated_at','expected_version')}
            record = {**old, **clean, 'version':old['version']+1,'updated_at':self.now()}
            raw = json.dumps(record,ensure_ascii=False,allow_nan=False)
            self.db.execute('UPDATE records SET topic_id=?,version=?,data=?,updated_at=? WHERE kind=? AND id=?',
                            (record.get('topic_id'),record['version'],raw,record['updated_at'],kind,record_id))
            self.db.execute('INSERT INTO versions(kind,id,version,data) VALUES(?,?,?,?)', (kind,record_id,record['version'],raw))
            self._policy_index = None
            return record

    def history(self, kind, record_id):
        self.get(kind,record_id)
        with self._lock:
            return [json.loads(r[0]) for r in self.db.execute('SELECT data FROM versions WHERE kind=? AND id=? ORDER BY version',(kind,record_id))]

    def version(self, version_id):
        try:
            record_id, version = version_id.rsplit('@',1)
            version = int(version)
        except (ValueError,AttributeError) as exc:
            raise ApiError(400,'invalid_reference','证据引用必须包含明确版本 ID') from exc
        with self._lock:
            row = self.db.execute('SELECT data FROM versions WHERE kind=? AND id=? AND version=?',('evidence',record_id,version)).fetchone()
        if not row:
            raise ApiError(422,'missing_evidence_version','引用的证据版本不存在',{'version_id':version_id})
        return json.loads(row[0])

    def publish(self, event_type, aggregate_id, payload, event_id=None):
        with self.transaction():
            event_id = event_id or str(uuid.uuid4())
            self.db.execute('INSERT OR IGNORE INTO outbox(id,type,aggregate_id,payload,created_at) VALUES(?,?,?,?,?)',
                            (event_id,event_type,aggregate_id,json.dumps(payload,ensure_ascii=False),self.now()))
            return event_id

    def drain(self, consumers, limit=100):
        delivered = 0
        # Process each event and all consumers in one transaction. New events are handled on next tick.
        with self._lock:
            ids = [r[0] for r in self.db.execute('SELECT id FROM outbox WHERE delivered_at IS NULL ORDER BY created_at LIMIT ?',(limit,))]
        for event_id in ids:
            try:
                with self.transaction():
                    row = self.db.execute('SELECT * FROM outbox WHERE id=? AND delivered_at IS NULL',(event_id,)).fetchone()
                    if row is None:
                        continue
                    event = dict(row); event['payload'] = json.loads(event['payload'])
                    for consumer in consumers:
                        consumer(self,event)
                    self.db.execute('UPDATE outbox SET delivered_at=?,last_error=NULL WHERE id=?',(self.now(),event_id))
                    delivered += 1
            except Exception as exc:
                with self.transaction():
                    self.db.execute('UPDATE outbox SET attempts=attempts+1,last_error=? WHERE id=?',(type(exc).__name__,event_id))
        return delivered

    def integrity(self):
        with self._lock:
            check = self.db.execute('PRAGMA integrity_check').fetchone()[0]
            foreign = self.db.execute('PRAGMA foreign_key_check').fetchall()
            broken = self.db.execute('SELECT r.kind,r.id FROM records r LEFT JOIN versions v ON r.kind=v.kind AND r.id=v.id AND r.version=v.version WHERE v.id IS NULL OR v.data!=r.data').fetchall()
            counts = {r[0]:r[1] for r in self.db.execute('SELECT kind,count(*) FROM records GROUP BY kind')}
        invalid_refs = []
        def walk(obj, owner):
            if isinstance(obj,dict):
                for k,v in obj.items():
                    if k.endswith('evidence_version_ids') and isinstance(v,list):
                        for ref in v:
                            try: self.version(ref)
                            except ApiError: invalid_refs.append({'owner':owner,'reference':ref})
                    else: walk(v,owner)
            elif isinstance(obj,list):
                for v in obj: walk(v,owner)
        with self._lock:
            rows = self.db.execute('SELECT kind,id,data FROM versions').fetchall()
            ids = {}
            for kind,record_id in self.db.execute('SELECT kind,id FROM records'):
                ids.setdefault(kind,set()).add(record_id)
            versions = {(r[0],r[1],r[2]) for r in self.db.execute('SELECT kind,id,version FROM versions')}
        for row in rows:
            record=json.loads(row[2]);owner=row[0]+':'+row[1]
            walk(record,owner)
            references={'topic_id':'topic','source_id':'source','origin_evidence_id':'evidence','evidence_id':'evidence',
                        'judgment_id':'judgment','change_id':'change'}
            for field,target_kind in references.items():
                ref=record.get(field)
                if not ref or (field=='source_id' and ref=='manual'):continue
                if ref not in ids.get(target_kind,set()):invalid_refs.append({'owner':owner,'field':field,'reference':ref})
            for field,target_kind in {'topic_ids':'topic','source_ids':'source','claim_ids':'claim','judgment_ids':'judgment'}.items():
                for ref in record.get(field,[]):
                    if ref and ref not in ids.get(target_kind,set()):invalid_refs.append({'owner':owner,'field':field,'reference':ref})
            for field,id_field,target_kind in [('judgment_version','judgment_id','judgment'),('change_version','change_id','change')]:
                if record.get(field) is not None and (target_kind,record.get(id_field),record[field]) not in versions:
                    invalid_refs.append({'owner':owner,'field':field,'reference':str(record.get(id_field))+'@'+str(record[field])})
            for ref in record.get('judgment_versions',[]):
                if ('judgment',ref.get('id'),ref.get('version')) not in versions:invalid_refs.append({'owner':owner,'field':'judgment_versions','reference':ref})
        return {'ok':check=='ok' and not foreign and not broken and not invalid_refs,
                'sqlite':check,'foreign_key_errors':len(foreign),'version_errors':len(broken),'reference_errors':invalid_refs,'counts':counts}

    def close(self):
        with self._lock:
            self.db.close()
