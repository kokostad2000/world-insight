/** Executable module behaviors using controlled DOM seams, not a browser substitute. */
import assert from 'node:assert/strict';
import test from 'node:test';
import {similarityPanel, installSimilarity} from '../web/similarity.js';

const material = {id: 'material-a', version: 3, title: '[夹具] 甲国发布', published_at: '2026-09-10', status: 'unverified', origin_evidence_id: null};
const candidate = {id: 'material-b', version: 2, title: '[夹具] 乙国发布', published_at: '2026-09-12', status: 'unverified', publisher: 'fixture publisher', url: 'https://example.com/b'};
const response = (body, status = 200) => ({ok: status < 400, status, json: async () => body});

function environment(responder) {
  const calls = [], listeners = new Set(), notices = [], dialogs = [], storage = new Map();
  let form = null, closed = 0, routed = 0;
  globalThis.localStorage = {getItem: key => storage.get(key) || null, setItem: (key, value) => storage.set(key, value)};
  globalThis.fetch = async (url, options = {}) => {
    const call = {url, method: options.method || 'GET', body: options.body ? JSON.parse(options.body) : undefined};
    calls.push(call);
    return responder(call, calls);
  };
  globalThis.document = {
    addEventListener: (name, fn) => { assert.equal(name, 'click'); listeners.add(fn); },
    removeEventListener: (name, fn) => listeners.delete(fn),
    getElementById: id => { assert.equal(id, 'similarity-confirm-form'); return form; },
  };
  const hooks = {
    openDialog: (title, html) => {
      dialogs.push({title, html});
      form = {reason: {value: ''}, submit: {disabled: false}, alert: {textContent: ''}, submitHandler: null,
        querySelector(selector) { return ({'[name="reason"]': this.reason, 'button[type="submit"]': this.submit, '[role="alert"]': this.alert})[selector]; },
        addEventListener(name, fn) { assert.equal(name, 'submit'); this.submitHandler = fn; },
      };
    },
    closeDialog: () => { closed++; },
    route: async () => { routed++; },
    toast: message => notices.push(message),
  };
  const uninstall = installSimilarity(hooks);
  return {
    calls, notices, dialogs, storage, listeners, hooks, uninstall,
    get form() { return form; }, get closed() { return closed; }, get routed() { return routed; },
    async click(action, data = {}) {
      const host = {isConnected: true, outerHTML: ''};
      const trigger = {dataset: {similarityAction: action, material: material.id, ...data}, disabled: false, closest: selector => selector === '[data-similarity-panel]' ? host : null};
      for (const handler of listeners) await handler({target: {closest: () => trigger}, preventDefault() {}});
      return host.outerHTML;
    },
    async submit(reason) { form.reason.value = reason; await form.submitHandler({preventDefault() {}}); },
  };
}

function standard(call) {
  if (call.url === '/api/evidence/material-a') return response(material);
  if (call.url === '/api/evidence/material-b') return response(candidate);
  if (call.url.startsWith('/api/evidence?')) return response({items: [candidate], total: 1});
  throw new Error('Unexpected request ' + call.url);
}

test('candidate reads preserve separate titles and dates and make no writes', async () => {
  const env = environment(standard);
  const html = await similarityPanel(material);
  assert.match(html, /标题相似 · 待人工检查/);
  assert.match(html, /乙国发布/);
  assert.match(html, /2026-09-12/);
  assert.match(html, /不合并材料、事件/);
  assert.ok(env.calls.every(call => call.method === 'GET'));
  assert.equal(env.dialogs.length, 0);
});

test('external title, publisher and unsafe links never become executable markup', async () => {
  const env = environment(() => response({items: [{...candidate, title: '<img src=x onerror=alert(1)>', publisher: '<script>fixture</script>', url: 'javascript:alert(1)'}], total: 1}));
  const html = await similarityPanel(material);
  assert.match(html, /&lt;img/);
  assert.match(html, /&lt;script/);
  assert.ok(!html.includes('<img') && !html.includes('<script') && !html.includes('href="javascript:'));
  assert.ok(env.calls.every(call => call.method === 'GET'));
});

test('source unavailable differs from no candidates, with bounded paginated requests', async () => {
  const env = environment(call => call.url.includes('similar_to') ? response({error: {message: 'fixture offline'}}, 503) : standard(call));
  const html = await similarityPanel(material);
  assert.match(html, /暂不可用/); assert.match(html, /重试候选检查/);
  assert.ok(!html.includes('本页没有标题相似候选'));
  assert.match(env.calls[0].url, /limit=10/);
  const pageEnv = environment(call => call.url.includes('similar_to') ? response({items: [candidate], total: 11}) : standard(call));
  await pageEnv.click('page', {offset: '10'});
  assert.ok(pageEnv.calls.some(call => call.url.includes('offset=10')));
  assert.ok(pageEnv.calls.every(call => call.method === 'GET'));
});

test('choosing opens explicit comparison and requires reason before a minimal versioned PATCH', async () => {
  const env = environment(call => call.method === 'PATCH' ? response({...material, version: 4, origin_evidence_id: candidate.id}) : standard(call));
  await env.click('choose', {candidate: candidate.id});
  assert.equal(env.calls.filter(call => call.method === 'PATCH').length, 0);
  assert.match(env.dialogs[0].html, /甲国发布/); assert.match(env.dialogs[0].html, /乙国发布/);
  await env.submit('   ');
  assert.match(env.form.alert.textContent, /填写/);
  assert.equal(env.calls.filter(call => call.method === 'PATCH').length, 0);
  await env.submit('[夹具] 原文明确标注转载');
  const patch = env.calls.find(call => call.method === 'PATCH');
  assert.deepEqual(patch.body, {expected_version: 3, origin_evidence_id: candidate.id, change_reason: '[夹具] 原文明确标注转载'});
  assert.equal(env.closed, 1); assert.equal(env.routed, 1);
});

test('409 keeps reason and original expected version without retry or silent overwrite', async () => {
  const env = environment(call => call.method === 'PATCH' ? response({error: {message: 'fixture conflict'}}, 409) : standard(call));
  await env.click('choose', {candidate: candidate.id});
  await env.submit('[夹具] 理由不得丢失');
  assert.match(env.form.alert.textContent, /版本冲突/);
  assert.equal(env.form.reason.value, '[夹具] 理由不得丢失');
  assert.equal(env.form.submit.disabled, false);
  assert.equal(env.calls.filter(call => call.method === 'PATCH').length, 1);
  assert.equal(env.closed, 0); assert.equal(env.routed, 0);
});

test('ignored candidate is browser-local, version-specific, and can be restored', async () => {
  const env = environment(standard);
  await env.click('ignore', {candidate: candidate.id, version: '3', candidateVersion: '2'});
  assert.match(await similarityPanel(material), /本浏览器已忽略此版本建议/);
  assert.ok(!(await similarityPanel({...material, version: 4})).includes('本浏览器已忽略此版本建议'));
  await env.click('unignore', {candidate: candidate.id, version: '3', candidateVersion: '2'});
  assert.ok(!(await similarityPanel(material)).includes('本浏览器已忽略此版本建议'));
  assert.ok(env.calls.every(call => call.method === 'GET'));
});

test('blocked local storage reports failure instead of claiming preference was saved', async () => {
  const env = environment(standard);
  globalThis.localStorage.setItem = () => { throw new Error('fixture privacy mode'); };
  await env.click('ignore', {candidate: candidate.id, version: '3', candidateVersion: '2'});
  assert.match(env.notices.at(-1), /本次忽略未保存/);
  assert.equal(env.calls.length, 0);
});

test('history restoration changes origin only and preserves record content and citations', async () => {
  const linked = {...material, origin_evidence_id: candidate.id};
  const env = environment(call => {
    if (call.method === 'PATCH') return response({...linked, version: 4, origin_evidence_id: null});
    if (call.url.endsWith('/history')) return response({items: [{...material, version: 1}, {...linked, version: 2}, linked]});
    if (call.url.endsWith('/material-a')) return response(linked);
    return standard(call);
  });
  await env.click('history');
  assert.match(env.dialogs[0].html, /核对并恢复此关联/);
  await env.click('restore', {origin: '', historyVersion: '1'});
  assert.match(env.dialogs[1].html, /不回滚正文或旧引用/);
  await env.submit('[夹具] 恢复未确认出处');
  assert.deepEqual(env.calls.find(call => call.method === 'PATCH').body, {expected_version: 3, origin_evidence_id: null, change_reason: '[夹具] 恢复未确认出处'});
});

test('deleted target and self reference are rejected before opening a write form', async () => {
  const env = environment(call => call.url.endsWith('/material-b') ? response({...candidate, deleted: true}) : standard(call));
  await env.click('choose', {candidate: candidate.id});
  assert.match(env.notices.at(-1), /回收站/); assert.equal(env.dialogs.length, 0);
  await env.click('choose', {candidate: material.id});
  assert.match(env.notices.at(-1), /自己/); assert.equal(env.dialogs.length, 0);
  assert.ok(env.calls.every(call => call.method === 'GET'));
});

test('reinstall has one delegated listener and cleanup is isolated', async () => {
  const env = environment(standard);
  const stop = installSimilarity(env.hooks);
  assert.equal(env.listeners.size, 1);
  env.uninstall(); assert.equal(env.listeners.size, 1);
  stop(); assert.equal(env.listeners.size, 0);
});

test('following a historical origin closes the dialog and permits normal navigation', async () => {
  const env = environment(standard);
  let prevented = false;
  const link = {dataset: {similarityAction: 'navigate'}};
  for (const handler of env.listeners) await handler({target: {closest: () => link}, preventDefault() { prevented = true; }});
  assert.equal(env.closed, 1);
  assert.equal(prevented, false);
  assert.equal(env.calls.length, 0);
});
