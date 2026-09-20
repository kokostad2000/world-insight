"""Regressions reproduced by the independent reviewer; isolated synthetic data."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from server.app import Application
from server.platform.config import load_config
from server.platform.errors import ApiError
from server.platform.store import Store
from server.modules import sources,knowledge


class AuditRegressions(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.config=load_config(data_dir=self.tmp.name)
        self.s=Store(self.config['db_path']);sources.seed_sources(self.s)
        self.app=Application(self.config,self.s,{'instance_id':'audit-fixture'})
        self.topic=self.api('topics',{'question':'[独立审查回归夹具] 研究问题'})
    def tearDown(self):self.s.close();self.tmp.cleanup()
    def api(self,path,body=None,method=None,query=None):
        result=self.app.dispatch(method or ('POST' if body is not None else 'GET'),'/api/'+path,body or {},query or {})
        self.app.drain();self.app.drain();return result
    def evidence(self,name,**patch):
        return self.api('evidence',{'title':'[夹具] '+name,'url':'https://fixture.example/'+name,'topic_id':self.topic['id'],**patch})
    def judgment(self,**patch):
        return self.api('judgments',{'topic_id':self.topic['id'],'conclusion':'[夹具] 条件性判断','assumptions':['待核验前提'],**patch})

    def test_opposing_evidence_and_access_restriction_mark_brief(self):
        support=self.evidence('support');opposition=self.evidence('opposition')
        self.judgment(evidence_version_ids=[support['version_id']],opposing_evidence_version_ids=[opposition['version_id']])
        brief=self.api('briefs',{'topic_id':self.topic['id']})
        self.assertIn(opposition['version_id'],brief['evidence_version_ids'])
        self.api('evidence/'+opposition['id']+'/corrections',{'expected_version':1,'status':'restricted','substantive':False,'reason':'[夹具] 权限变化'})
        self.assertEqual(self.s.get('brief',brief['id'])['status'],'needs_review')
        self.assertEqual(self.s.history('brief',brief['id'])[0]['status'],'generated')

    def test_timezone_event_filter_uses_actual_instant(self):
        event=self.api('events',{'title':'[夹具] 北京时间凌晨事件','occurred_at':'2026-09-20T00:30:00+08:00','time_precision':'instant'})
        self.assertEqual(self.api('events',query={'since':'2026-09-20T00:00:00Z'})['total'],0)
        self.assertEqual(self.api('events',query={'since':'2026-09-19T23:00:00+08:00','until':'2026-09-20T01:00:00+08:00'})['items'][0]['id'],event['id'])

    def test_offset_read_snapshot_cannot_read_later_changes(self):
        self.evidence('later')
        change=self.s.all('change')[0]
        older=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(minutes=1)).astimezone(dt.timezone(dt.timedelta(hours=8))).isoformat()
        result=self.api('changes/read',{'snapshot_at':older,'items':[{'id':change['id'],'version':change['version']}]})
        self.assertEqual(result['marked'],[]);self.assertEqual(len(result['skipped']),1)

    def test_translation_cannot_bypass_storage_rights(self):
        with self.assertRaises(ApiError) as caught:
            self.evidence('restricted',translation='[夹具] 受限内容的译文',rights={'store':'metadata','display':True,'export':True})
        self.assertEqual(caught.exception.code,'rights_restricted')
        self.assertEqual(self.s.list('evidence')['total'],0)

    def test_withdrawn_judgment_stays_withdrawn_after_correction(self):
        evidence=self.evidence('withdrawn-support')
        judgment=self.judgment(status='withdrawn',evidence_version_ids=[evidence['version_id']],review_date='2020-01-01')
        self.api('evidence/'+evidence['id']+'/corrections',{'expected_version':1,'status':'withdrawn','substantive':True,'reason':'[夹具] 正式撤回'})
        current=self.s.get('judgment',judgment['id'])
        self.assertEqual(current['status'],'withdrawn');self.assertTrue(current['needs_review'])
        self.assertFalse(any(j['id']==judgment['id'] for j in self.api('dashboard')['review_due']))

    def test_partial_excerpt_and_distinct_source_records_do_not_merge(self):
        common={'source_id':'source-world-bank','excerpt':'value=null;period=2025;unit=USD','rights':{'store':True,'display':True,'export':True}}
        first=self.evidence('AAA',source_record_id='GDP:AAA:2025',**common)
        second=self.evidence('BBB',source_record_id='GDP:BBB:2025',**common)
        self.assertNotEqual(first['id'],second['id'])
        third=self.evidence('CCC',source_record_id='GDP:CCC:2025',content_scope='full',**common)
        fourth=self.evidence('DDD',source_record_id='GDP:DDD:2025',content_scope='full',**common)
        self.assertNotEqual(third['id'],fourth['id'])
        self.assertEqual(self.s.list('evidence')['total'],4)

    def test_event_update_is_visible_in_changes(self):
        event=self.api('events',{'title':'[夹具] 政策','event_type':'announced','topic_id':self.topic['id']})
        self.api('events/'+event['id'],{'expected_version':1,'event_type':'reported_implementation','change_reason':'新材料说明'},'PATCH')
        changes=self.s.all('change',self.topic['id'])
        self.assertTrue(any(c['type']=='event.updated' for c in changes))

    def test_metric_revision_keeps_both_topic_associations(self):
        other=self.api('topics',{'question':'[夹具] 第二议题'})
        data={'indicator':'GDP','country_code':'CHN','period':'2025','unit':'USD','source_id':'manual','topic_id':self.topic['id'],'value':None}
        first=knowledge.upsert_observation(self.s,data)
        second=knowledge.upsert_observation(self.s,{**data,'topic_id':other['id'],'value':0})
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(len(self.s.all('observation',self.topic['id'])),1)
        self.assertEqual(len(self.s.all('observation',other['id'])),1)
        self.assertIsNone(self.s.history('observation',first['id'])[0]['value'])

    def test_restore_integrity_detects_non_evidence_orphans(self):
        self.s.create('event',{'title':'[夹具] 损坏导入','topic_id':'missing-topic','claim_ids':['missing-claim']})
        report=self.s.integrity()
        self.assertFalse(report['ok'])
        self.assertTrue(any(r.get('reference')=='missing-claim' for r in report['reference_errors']))


if __name__=='__main__':unittest.main()
