"""Executed ES module interaction tests; actual browser checks are documented separately."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('node'), 'Node is a developer-only check')
class WebLifecycleTests(unittest.TestCase):
    def run_js(self, body):
        completed = subprocess.run(['node', '--input-type=module', '-e', body], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_escaped_buttons_and_unsupported_types(self):
        self.run_js('''
          import assert from 'node:assert/strict';
          import {deleteButton} from './web/lifecycle.js';
          const html=deleteButton('topics',{id:'" onfocus="bad',version:3,question:'<script>bad</script>'});
          assert.ok(!html.includes('<script>'));assert.ok(html.includes('&lt;script&gt;'));
          assert.ok(html.includes('data-kind="topic"'));assert.ok(html.includes('data-version="3"'));
          assert.equal(deleteButton('sources',{id:'s',version:1}), '');
          assert.equal(deleteButton('evidence',{id:'e',version:1,deleted:true}), '');
        ''')

    def test_confirmation_requires_validated_recovery_reason_and_consent(self):
        self.run_js('''
          import assert from 'node:assert/strict';
          import {deletionConfirmation,dependencySummary} from './web/lifecycle.js';
          const p={state:'recovery_ready',plan_hash:'h',recovery:{id:'r',verified:true},targets:[{kind:'evidence',id:'e',expected_version:2}]};
          assert.throws(()=>deletionConfirmation(p,'reason',false));
          assert.throws(()=>deletionConfirmation({...p,state:'previewed'},'reason',true));
          assert.throws(()=>deletionConfirmation(p,' ',true));
          assert.deepEqual(deletionConfirmation(p,' reason ',true),{confirm:true,reason:'reason',plan_hash:'h',recovery_id:'r',expected_versions:p.targets});
          const groups=dependencySummary([{kind:'judgment',id:'j',version:1,current_version:4},{kind:'judgment',id:'j',version:3,current_version:4}]);
          assert.equal(groups.length,1);assert.deepEqual(groups[0].versions,[1,3]);
        ''')

    def test_click_preview_then_recovery_does_not_delete_until_confirmed_submit(self):
        self.run_js('''
          import assert from 'node:assert/strict';
          import {installLifecycle} from './web/lifecycle.js';
          const listeners={},requests=[],dialog=[],errors={innerHTML:'',scrollIntoView(){}};
          globalThis.document={addEventListener:(type,fn)=>listeners[type]=fn,querySelector:()=>errors,getElementById:()=>null};
          globalThis.location={hash:'#/evidence/e'};
          const plan={id:'p',state:'previewed',plan_hash:'h',targets:[{kind:'evidence',id:'e',expected_version:2}],dependencies:[],expires_at:'2099-01-01'};
          let rejectCommit=true;
          globalThis.fetch=async(url,opts)=>{
            const body=opts.body?JSON.parse(opts.body):null;requests.push({url,body});
            let data=plan,ok=true;
            if(url.endsWith('prepare-recovery'))data={...plan,state:'recovery_ready',recovery:{id:'r',verified:true,backup_path:'/tmp/恢复包',export_path:'/tmp/合法导出',content_omissions:1}};
            if(url.endsWith('/commit')&&rejectCommit){ok=false;data={error:{message:'changed',code:'plan_changed'}};}
            return {ok,status:ok?200:409,json:async()=>data};
          };
          let closed=0,refreshed=0;
          installLifecycle({openDialog:(title,html)=>dialog.push({title,html}),closeDialog:()=>closed++,route:()=>refreshed++,toast:()=>{}});
          async function click(action,extra={}){
            const b={dataset:{action:'lifecycle-'+action,...extra},disabled:false,textContent:'label',closest:()=>null};
            await listeners.click({target:{closest:()=>b},preventDefault(){},stopImmediatePropagation(){}});
          }
          await click('delete',{kind:'evidence',id:'e',version:'2',title:'<img src=x>'});
          assert.deepEqual(requests.map(x=>x.url),['/api/deletions/preview']);
          assert.ok(dialog.at(-1).html.includes('&lt;img src=x&gt;'));
          await click('prepare');assert.equal(requests.length,2);
          assert.ok(dialog.at(-1).html.includes('/tmp/合法导出'));
          const submit={disabled:false};
          const form={dataset:{lifecycleForm:'commit'},elements:{reason:{value:'my draft'},confirmed:{checked:false}},matches:()=>true,reportValidity:()=>true,querySelector:s=>s.includes('submit')?submit:errors};
          const event={target:form,preventDefault(){},stopImmediatePropagation(){}};
          await listeners.submit(event);assert.equal(requests.length,2);
          form.elements.confirmed.checked=true;
          await listeners.submit(event);assert.equal(requests.length,3);assert.equal(closed,0);
          assert.equal(form.elements.reason.value,'my draft');assert.equal(submit.disabled,false);
          assert.ok(errors.innerHTML.includes('重新预览'));
          rejectCommit=false;await listeners.submit(event);
          assert.deepEqual(requests.at(-1).body,{confirm:true,reason:'my draft',plan_hash:'h',recovery_id:'r',expected_versions:plan.targets});
          assert.equal(closed,1);assert.equal(refreshed,1);assert.equal(location.hash,'#/settings');
        ''')

    def test_panel_load_and_settings_save_never_trigger_cleanup(self):
        self.run_js('''
          import assert from 'node:assert/strict';
          import {installLifecycle,lifecyclePanel} from './web/lifecycle.js';
          const requests=[],listeners={},errors={innerHTML:''};
          const settings={id:'default',version:4,candidate_days:90,batch_limit:20,candidate_retention_enabled:true};
          globalThis.document={addEventListener:(k,f)=>listeners[k]=f,getElementById:()=>null,querySelector:()=>errors};
          globalThis.fetch=async(url,opts)=>{requests.push({url,method:opts.method||'GET',body:opts.body});return {ok:true,json:async()=>url.includes('/trash')?{items:[{kind:'evidence',id:'e',title:'<unsafe>',version:2,deleted_reason:'<script>',content_expired:true}],total:1}:settings};};
          installLifecycle({openDialog(){},closeDialog(){},toast(){},route(){}});
          const html=await lifecyclePanel();assert.ok(html.includes('&lt;unsafe&gt;'));assert.ok(html.includes('正文已到期'));
          const submit={disabled:false};
          const form={dataset:{lifecycleForm:'settings',version:'4'},elements:{candidate_days:{value:'45'},batch_limit:{value:'10'},candidate_retention_enabled:{checked:false}},matches:()=>true,reportValidity:()=>true,querySelector:s=>s.includes('submit')?submit:errors};
          await listeners.submit({target:form,preventDefault(){},stopImmediatePropagation(){}});
          assert.deepEqual(requests.map(r=>r.method),['GET','GET','PATCH']);
          assert.ok(!requests.some(r=>r.url.endsWith('/run')));
          assert.deepEqual(JSON.parse(requests.at(-1).body),{expected_version:4,candidate_days:45,batch_limit:10,candidate_retention_enabled:false});
        ''')


if __name__ == '__main__':
    unittest.main()
