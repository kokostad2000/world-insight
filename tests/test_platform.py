import sqlite3
import tempfile
import unittest
from pathlib import Path
from server.platform.errors import ApiError
from server.platform.store import Store
from server.platform import migrations


class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'research.sqlite';self.store=Store(self.path)
    def tearDown(self): self.store.close();self.tmp.cleanup()

    def test_version_conflict_and_restart(self):
        old=self.store.create('evidence',{'title':'原文'})
        self.store.update('evidence',old['id'],{'title':'修订'},1)
        with self.assertRaises(ApiError) as error:self.store.update('evidence',old['id'],{'title':'丢失更新'},1)
        self.assertEqual(error.exception.status,409)
        self.store.close();self.store=Store(self.path)
        self.assertEqual(self.store.version(old['id']+'@1')['title'],'原文')
        self.assertEqual(self.store.get('evidence',old['id'])['title'],'修订')

    def test_domain_write_and_outbox_atomic(self):
        with self.assertRaises(RuntimeError):
            with self.store.transaction():
                item=self.store.create('evidence',{'title':'不应存在'})
                self.store.publish('evidence.created',item['id'],{})
                raise RuntimeError('fixture crash')
        self.assertEqual(self.store.list('evidence')['total'],0)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM outbox').fetchone()[0],0)

    def test_failed_propagation_retries_without_duplicate(self):
        self.store.publish('fixture.changed','x',{},event_id='evt-1')
        calls=[]
        def consumer(store,event):
            calls.append(event['id']); store.create('change',{'type':'fixture'},'change-'+event['id'])
            if len(calls)==1:raise RuntimeError('fixture delivery failure')
        self.assertEqual(self.store.drain([consumer]),0)
        self.assertEqual(self.store.list('change')['total'],0)
        self.assertEqual(self.store.drain([consumer]),1)
        self.assertEqual(self.store.drain([consumer]),0)
        self.assertEqual(self.store.list('change')['total'],1)

    def test_migration_failure_rolls_back_schema_and_data(self):
        topic=self.store.create('topic',{'question':'保留的议题'})
        original=migrations.MIGRATIONS;version=migrations.SCHEMA_VERSION
        try:
            migrations.SCHEMA_VERSION=2
            migrations.MIGRATIONS=original+[(2,['CREATE TABLE partial_migration(id TEXT)','INVALID SQL fixture'])]
            with self.assertRaises(sqlite3.Error):migrations.migrate(self.store.db,self.path)
            self.assertEqual(migrations.current_version(self.store.db),1)
            self.assertIsNone(self.store.db.execute("SELECT name FROM sqlite_master WHERE name='partial_migration'").fetchone())
            self.assertEqual(self.store.get('topic',topic['id'])['question'],'保留的议题')
            self.assertTrue(self.path.with_name('migration-before-1-to-2.sqlite').exists())
        finally:migrations.MIGRATIONS=original;migrations.SCHEMA_VERSION=version

    def test_integrity_rejects_missing_reference(self):
        self.store.create('judgment',{'evidence_version_ids':['missing@1']})
        self.assertFalse(self.store.integrity()['ok'])


if __name__=='__main__':unittest.main()
