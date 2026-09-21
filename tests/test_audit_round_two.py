"""Behavioral regressions for independent P0 audit findings."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from server.app import Application
from server.modules import activity, knowledge, research, sources
from server.platform.store import Store
from server.platform import migrations


class AuditRoundTwo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = Store(Path(self.tmp.name)/'world-insight.sqlite')
        sources.seed_sources(self.s)
        self.t = research.handle(self.s,'POST',['topics'],{'question':'隔离第二轮审查'}, {})

    def tearDown(self):
        self.s.close()
        self.tmp.cleanup()

    def test_rights_narrowing_normal_edit_propagates_to_judgment_and_brief(self):
        e = knowledge.ingest(self.s,{'title':'合法摘录','rights':{'store':True,'display':True,'export':True},'excerpt':'隔离文本'})
        j = research.handle(self.s,'POST',['judgments'],{'topic_id':self.t['id'],'conclusion':'隔离判断',
            'evidence_version_ids':[e['id']+'@1'],'status':'reviewed','reviewer':'测试','confidence_reason':'来源明确','review_date':'2099-01-01'}, {})
        brief = activity.make_brief(self.s,{'topic_id':self.t['id']})
        knowledge.handle(self.s,'PATCH',['evidence',e['id']],{'expected_version':e['version'],
            'rights':{'store':True,'display':False,'export':False}}, {})
        self.s.drain([research.on_event,activity.on_event])
        self.assertEqual(self.s.get('judgment',j['id'])['status'],'needs_review')
        self.assertEqual(self.s.get('brief',brief['id'])['status'],'needs_review')
        exported = research.export(self.s,{'topic_id':self.t['id']})
        self.assertTrue(all(not row['excerpt'] for row in exported['citations']))

    def test_change_preserves_hypothesis_label_at_its_saved_version(self):
        j = research.handle(self.s,'POST',['judgments'],{'topic_id':self.t['id'],'conclusion':'仅有假设的审阅判断',
            'assumptions':['明确假设'],'status':'reviewed','reviewer':'测试','confidence_reason':'暂无支持证据','review_date':'2099-01-01'}, {})
        self.s.drain([activity.on_event])
        created = next(c for c in self.s.all('change') if c['type']=='judgment.created')
        self.assertEqual(created['status'],'reviewed')
        self.assertEqual(created['evidence_support'],'assumption_only')
        self.assertTrue(created['missing_evidence'])
        # Reproduce a pre-amendment record without support labels.
        self.s.update('change',created['id'],{'evidence_support':None,'missing_evidence':None,'status':None},created['version'])
        e = knowledge.ingest(self.s,{'title':'后来才登记的材料'})
        research.handle(self.s,'PATCH',['judgments',j['id']],{'expected_version':j['version'],
            'evidence_version_ids':[e['id']+'@1'],'missing_evidence':'','change_reason':'后来取得材料'}, {})
        shown=next(c for c in activity.dashboard(self.s,{'window':'7d'})['items'] if c['id']==created['id'])
        self.assertEqual(shown['evidence_support'],'assumption_only')

    def test_conclusion_changed_filter_ignores_metadata_only_versions(self):
        j = research.handle(self.s,'POST',['judgments'],{'topic_id':self.t['id'],'conclusion':'尚待核实'}, {})
        j = research.handle(self.s,'PATCH',['judgments',j['id']],{'expected_version':j['version'],
            'review_date':'2099-01-01','change_reason':'只调整复查日期'}, {})
        self.assertEqual(research.handle(self.s,'GET',['judgments'],{}, {'changed':'true'})['total'],0)
        research.handle(self.s,'PATCH',['judgments',j['id']],{'expected_version':j['version'],
            'conclusion':'基于新增核查调整解释','change_reason':'结论实质修订'}, {})
        filtered = research.handle(self.s,'GET',['judgments'],{}, {'changed':'true','limit':'1'})
        self.assertEqual(filtered['total'],1)
        self.assertEqual(filtered['items'][0]['id'],j['id'])

    def test_unread_notification_filter_precedes_pagination(self):
        rows=[self.s.create('notification',{'reason':'隔离提醒','status':'unread'}) for _ in range(21)]
        for row in self.s.all('notification')[:20]:
            self.s.update('notification',row['id'],{'status':'read'},row['version'])
        unread=activity.handle(self.s,'GET',['notifications'],{}, {'status':'unread','limit':'20'})
        self.assertEqual(unread['total'],1)
        self.assertEqual(len(unread['items']),1)
        self.assertEqual(len(self.s.all('notification')),len(rows))

    def test_maintenance_is_bounded_and_checkpoint_survives_new_application(self):
        app=Application({'port':9999},self.s,{'instance_id':'fixture'})
        result=app.maintain()
        self.assertEqual(result['state'],'complete')
        count=len(self.s.all('lifecycle_operation'))
        again=Application({'port':9999},self.s,{'instance_id':'fixture'})
        self.assertIsNone(again.maintain())
        self.assertEqual(len(self.s.all('lifecycle_operation')),count)

    def test_pre_migration_checkpoint_does_not_preserve_limited_body(self):
        source=self.s.get('source','source-fed')
        self.s.update('source',source['id'],{'retention_days':30},source['version'])
        marker='MIGRATION_LICENSE_CONTENT_487d' * 100
        e=knowledge.ingest(self.s,{'title':'隔离期限材料','source_id':source['id'],'excerpt':marker,
            'notes':'研究注释保留','rights':{'store':True,'display':True,'export':True}})
        path=self.s.path
        with patch.object(migrations,'SCHEMA_VERSION',2),patch.object(migrations,'MIGRATIONS',migrations.MIGRATIONS+[(2,['INVALID MIGRATION SQL'])]):
            with self.assertRaises(sqlite3.OperationalError):
                migrations.migrate(self.s.db,path)
        recovery=path.with_name('migration-before-1-to-2.sqlite')
        self.assertTrue(recovery.exists())
        self.assertNotIn(marker.encode(),recovery.read_bytes())
        self.assertEqual(self.s.get('evidence',e['id'])['excerpt'],marker)
        self.assertEqual(migrations.current_version(self.s.db),1)


if __name__=='__main__':unittest.main()
