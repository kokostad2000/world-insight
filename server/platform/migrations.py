"""Root-owned migration registry. Each version is atomic; no executescript commits."""
import hashlib
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1
MIGRATIONS = [(1, [
    'CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)',
    'CREATE TABLE records(kind TEXT NOT NULL,id TEXT NOT NULL,topic_id TEXT,version INTEGER NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(kind,id))',
    'CREATE INDEX records_topic ON records(kind,topic_id,updated_at DESC)',
    'CREATE INDEX records_updated ON records(kind,updated_at DESC)',
    "CREATE INDEX records_url ON records(kind,json_extract(data,'$.canonical_url'))",
    "CREATE INDEX records_normalized_url ON records(kind,json_extract(data,'$.url'))",
    "CREATE INDEX records_fingerprint ON records(kind,json_extract(data,'$.content_fingerprint'))",
    "CREATE INDEX records_source_record ON records(kind,json_extract(data,'$.source_record_id'))",
    'CREATE TABLE versions(kind TEXT NOT NULL,id TEXT NOT NULL,version INTEGER NOT NULL,data TEXT NOT NULL,PRIMARY KEY(kind,id,version),FOREIGN KEY(kind,id) REFERENCES records(kind,id))',
    'CREATE TABLE outbox(id TEXT PRIMARY KEY,type TEXT NOT NULL,aggregate_id TEXT NOT NULL,payload TEXT NOT NULL,created_at TEXT NOT NULL,delivered_at TEXT,attempts INTEGER NOT NULL DEFAULT 0,last_error TEXT)',
    'CREATE INDEX outbox_pending ON outbox(delivered_at,created_at)',
])]


def current_version(db):
    return db.execute('PRAGMA user_version').fetchone()[0]


def migrate(db, path=None):
    current = current_version(db)
    if current > SCHEMA_VERSION:
        raise RuntimeError(f'数据库版本 {current} 高于程序支持 {SCHEMA_VERSION}，请使用兼容程序；未修改数据')
    for version, statements in MIGRATIONS:
        checksum = hashlib.sha256('\n'.join(statements).encode()).hexdigest()
        if version <= current:
            row = db.execute('SELECT checksum FROM schema_migrations WHERE version=?',(version,)).fetchone()
            if row is None or row[0] != checksum:
                raise RuntimeError('迁移历史校验不一致，停止打开数据库')
            continue
        checkpoint = None
        if current and path:
            checkpoint = Path(path).with_name(f'migration-before-{current}-to-{version}.sqlite')
            if not checkpoint.exists():
                dest = sqlite3.connect(str(checkpoint)); db.backup(dest); dest.close()
            # Pre-migration recovery artifacts obey the same source-content policy
            # as user backups. A failed sanitation blocks the migration.
            from ops.backup import sanitize_snapshot
            sanitize_snapshot(checkpoint, policy_source=path)
        try:
            db.execute('BEGIN IMMEDIATE')
            for statement in statements: db.execute(statement)
            db.execute('INSERT INTO schema_migrations VALUES(?,?,strftime(\'%Y-%m-%dT%H:%M:%fZ\',\'now\'))',(version,checksum))
            db.execute(f'PRAGMA user_version={version}')
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction: db.execute('ROLLBACK')
            raise
        current = version
