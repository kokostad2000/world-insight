import tempfile
import unittest
from pathlib import Path
from server.platform.store import Store
from server.modules import activity


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Store(Path(self.tmp.name)/'test.sqlite')
        self.t=self.s.create('topic',{'question':'明确标记的测试议题','status':'active','followed':True})
    def tearDown(self):self.s.close();self.tmp.cleanup()
    def event(self,n,kind='evidence.created',payload=None):
        self.s.publish(kind,'evidence-1',{'topic_id':self.t['id'],**(payload or {})},event_id='e'+str(n))
        self.s.drain([activity.on_event])
    def test_only_displayed_versions_marked_read_and_new_changes_remain(self):
        for n in range(4):self.event(n)
        page=activity.dashboard(self.s,{'window':'unread','limit':2})
        self.event(4)
        result=activity.mark_read(self.s,{'snapshot_at':page['snapshot_at'],'items':[{'id':x['id'],'version':x['version']} for x in page['items']]})
        self.assertEqual(len(result['marked']),2)
        self.assertEqual(activity.dashboard(self.s,{'window':'unread'})['total'],3)
        self.assertEqual(self.s.list('change')['total'],5)
    def test_updated_version_not_silently_read(self):
        self.event(0);page=activity.dashboard(self.s,{'window':'unread'});c=page['items'][0]
        self.s.update('change',c['id'],{'detail':'阅读期间的新更正'},1)
        result=activity.mark_read(self.s,{'snapshot_at':page['snapshot_at'],'items':[{'id':c['id'],'version':1}]})
        self.assertEqual(len(result['skipped']),1)
    def test_read_state_does_not_clear_research_todo(self):
        self.s.create('judgment',{'topic_id':self.t['id'],'status':'needs_review','conclusion':'测试','review_date':'2020-01-01'})
        self.event(1,'research.needs_review')
        page=activity.dashboard(self.s,{'window':'unread'})
        activity.mark_read(self.s,{'snapshot_at':page['snapshot_at'],'items':[{'id':c['id'],'version':c['version']} for c in page['items']]})
        self.assertEqual(len(activity.dashboard(self.s,{})['review_due']),1)
    def test_brief_preserves_missing_evidence_and_correction_flag(self):
        self.s.create('judgment',{'topic_id':self.t['id'],'conclusion':'暂定解释','assumptions':['测试假设'],'status':'reviewed','evidence_version_ids':[]})
        brief=activity.make_brief(self.s,{'topic_id':self.t['id']})
        self.assertIn('缺乏证据支持',brief['content']);self.assertTrue(brief['missing_evidence'])
        e=self.s.create('evidence',{'title':'原文'})
        brief2=self.s.create('brief',{'topic_id':self.t['id'],'evidence_version_ids':[e['id']+'@1'],'status':'generated'})
        self.event(2,'evidence.corrected',{'evidence_id':e['id'],'reason':'正式撤回'})
        self.assertEqual(self.s.get('brief',brief2['id'])['status'],'needs_review')
        self.assertEqual(self.s.history('brief',brief2['id'])[0]['status'],'generated')


if __name__=='__main__':unittest.main()
