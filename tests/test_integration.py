"""Integrated HTTP + SQLite fixtures. This is not real-source or browser evidence."""
from tests import test_http


class ResearchIntegrationTests(test_http.LocalHttpCase):
    def api(self,path,body=None,method=None):
        status,value=self.request('/api/'+path,method or ('POST' if body is not None else 'GET'),body)
        self.assertEqual(status,200,(path,value))
        return value

    def test_five_topic_research_loop_and_correction_reaches_all_dependents(self):
        for i in range(5):
            topic=self.api('topics',{'question':f'[集成夹具] 议题{i+1}的公开声明是否已经实施？','is_fixture':True})
            tid=topic['id']
            evidence=self.api('evidence',{'topic_id':tid,'title':f'[集成夹具] 官方声明{i+1}','url':f'https://fixture.example/{i}',
                                         'published_at':'2026-09-10','rights':{'store':True,'display':True,'export':True},'excerpt':f'夹具声明{i}，仅用于测试','is_fixture':True})
            ref=evidence['version_id']
            claim=self.api('claims',{'topic_id':tid,'subject':'测试声明方','statement':'声称将实施，但没有实施验证','evidence_version_ids':[ref]})
            event=self.api('events',{'topic_id':tid,'title':'[夹具] 声明发布','claim_ids':[claim['id']],'occurred_at':'2026-09-10','time_precision':'day',
                                     'location':{'name':'中国','country_code':'CHN','precision':'country'}})
            self.assertEqual(event['verification_status'],'unverified')
            self.assertNotIn('lat',event['location'])
            judgment=self.api('judgments',{'topic_id':tid,'conclusion':'[夹具] 有公开声明，实际执行仍未知','status':'reviewed',
                                          'evidence_version_ids':[ref],'assumptions':['后续存在可核验的执行记录'],'confidence':'low',
                                          'confidence_reason':'仅有单方声明','review_date':'2026-10-01','reviewer':'集成验收'})
            scenario=self.api('scenarios',{'topic_id':tid,'title':'[夹具] 条件性执行路径','description':'可能执行，也可能推迟',
                                           'evidence_version_ids':[ref],'assumptions':['主体具有执行能力'],'valid_until':'2026-12-01',
                                           'signals':['正式执行公告'],'invalidation_conditions':'公告被撤回','counterevidence_search':'夹具检索中尚未找到反证',
                                           'review_date':'2026-10-01','status':'reviewed','reviewer':'集成验收'})
            path=self.api('impact-paths',{'topic_id':tid,'title':'[夹具] 影响路径','nodes':[{'id':'a','label':'声明'},{'id':'b','label':'执行'}],
                                          'edges':[{'from':'a','to':'b','status':'assumption','evidence_version_ids':[ref],'note':'尚未证实因果'}]})
            brief=self.api('briefs',{'topic_id':tid})
            # Two browser clients would submit the same old expected_version; exercise real HTTP conflict.
            updated=self.api('judgments/'+judgment['id'],{'expected_version':1,'conclusion':'[夹具] 重读后保留未知项','change_reason':'复核原文'},'PATCH')
            code,error=self.request('/api/judgments/'+judgment['id'],'PATCH',{'expected_version':1,'conclusion':'旧窗口写入','change_reason':'应冲突'})
            self.assertEqual(code,409);self.assertEqual(error['error']['code'],'version_conflict')
            self.api('evidence/'+evidence['id']+'/corrections',{'expected_version':1,'status':'withdrawn','substantive':True,'reason':'[夹具] 官方正式撤回'})
            self.app.drain()
            for collection,record in [('judgments',updated),('scenarios',scenario),('impact-paths',path),('briefs',brief)]:
                self.assertEqual(self.api(collection+'/'+record['id'])['status'],'needs_review')
            self.assertTrue(self.api('impact-paths/'+path['id'])['edges'][0]['needs_review'])
            old=self.api('judgments/'+judgment['id']+'/history')['items'][0]
            self.assertEqual(old['evidence_version_ids'],[ref]);self.assertEqual(old['status'],'reviewed')
            self.assertEqual(self.store.version(ref)['status'],'unverified')
            exported=self.api('exports?topic_id='+tid+'&format=json')
            self.assertIn(ref,str(exported))
            self.assertTrue(self.store.integrity()['ok'])
        self.assertEqual(self.api('topics')['total'],5)

    def test_assumption_review_indeterminate_result_and_reading_remain_honest(self):
        topic=self.api('topics',{'question':'[夹具] 证据不足的议题'})
        judgment=self.api('judgments',{'topic_id':topic['id'],'conclusion':'[夹具] 条件性推测','assumptions':['尚无证据的前提'],
                                       'status':'reviewed','reviewer':'集成验收','confidence_reason':'证据不足','review_date':'2020-01-01'})
        self.assertEqual(judgment['evidence_support'],'assumption_only')
        brief=self.api('briefs',{'topic_id':topic['id']})
        self.assertIn('缺乏证据支持',brief['content'])
        review=self.api('reviews',{'judgment_id':judgment['id'],'judgment_version':1,'outcome':'indeterminate','rationale':'[夹具] 没有足够结果证据'})
        self.assertEqual(review['outcome'],'indeterminate')
        dash=self.api('dashboard?window=unread&limit=1')
        self.api('changes/read',{'snapshot_at':dash['snapshot_at'],'items':[{'id':c['id'],'version':c['version']} for c in dash['items']]})
        self.assertFalse(self.api('bootstrap')['paid_enabled'])
