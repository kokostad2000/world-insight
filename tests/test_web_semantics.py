"""Executable front-end boundary checks. These do not replace browser acceptance."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('node'), 'Node only needed for developer JS checks')
class WebSemanticsTests(unittest.TestCase):
    def run_js(self, body):
        result = subprocess.run(['node', '--input-type=module', '-e', body], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_untrusted_text_and_link_protocols(self):
        self.run_js("""
          import assert from 'node:assert/strict';
          import {esc,safeURL} from './web/lib.js';
          assert.equal(esc('<img src=x onerror="alert(1)">'), '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
          assert.equal(safeURL('javascript:alert(1)'), '');
          assert.equal(safeURL('data:text/html,<script>'), '');
          assert.equal(safeURL('https://example.com/a'), 'https://example.com/a');
        """)

    def test_read_marks_only_displayed_versions(self):
        self.run_js("""
          import assert from 'node:assert/strict';
          import {visibleReadPayload} from './web/lib.js';
          const loaded = [{id:'visible',version:2,title:'x'}];
          assert.deepEqual(visibleReadPayload('2026-09-20T10:00:00Z',loaded), {
            snapshot_at:'2026-09-20T10:00:00Z',items:[{id:'visible',version:2}]
          });
          assert.deepEqual(visibleReadPayload('snapshot',[]), {snapshot_at:'snapshot',items:[]});
        """)

    def test_unknown_time_and_country_have_no_invented_precision(self):
        self.run_js("""
          import assert from 'node:assert/strict';
          import {eventCoordinates,date} from './web/lib.js';
          assert.equal(eventCoordinates({location:{precision:'country',lat:35,lon:110}}),null);
          assert.equal(eventCoordinates({location:{precision:'coordinate',lat:null,lon:null}}),null);
          assert.equal(eventCoordinates({location:{precision:'coordinate',lat:95,lon:180}}),null);
          assert.deepEqual(eventCoordinates({location:{precision:'coordinate',lat:0,lon:0}}),[0,0]);
          assert.equal(date(null),'未知'); assert.equal(date('2025-04','month'),'2025-04');
          assert.equal(date('2025-04-10','day'),'2025-04-10');
        """)

    def test_all_editor_types_render_and_permission_unknown_is_not_consent(self):
        self.run_js("""
          import assert from 'node:assert/strict';
          import {schemas,renderField,referenceOptions} from './web/forms.js';
          const context={topics:[],sources:[],evidence:[],claims:[],judgments:[]};
          for(const [kind,fields] of Object.entries(schemas)){
            const html=fields.map(field=>renderField(field,{},context)).join('');
            assert.ok(html.length>100,kind);
          }
          const field={key:'rights.display',title:'展示',type:'checkbox'};
          assert.ok(!renderField(field,{rights:{display:'metadata'}},context).includes(' checked'));
          assert.ok(!renderField(field,{rights:{display:'unknown'}},context).includes(' checked'));
          assert.ok(renderField(field,{rights:{display:'excerpt'}},context).includes(' checked'));
          const refs=referenceOptions([{id:'e',version:2,title:'current'}],['e@1']);
          assert.ok(refs.some(([id])=>id==='e@1')); assert.ok(refs.some(([id])=>id==='e@2'));
        """)


if __name__ == '__main__':
    unittest.main()
