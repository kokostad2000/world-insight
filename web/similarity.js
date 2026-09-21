/** Human review of title-similarity suggestions; never merges material or event records. */
import {api, esc, safeURL, items, date, badge} from './lib.js';

const PAGE_SIZE = 10;
const DISMISSED_KEY = 'wi-similarity-dismissed-v1';
let uninstallCurrent = null;

const button = (action, text, data = {}, disabled = false) => `<button type="button" class="small" data-similarity-action="${action}" ${Object.entries(data).map(([key, value]) => `data-${key}="${esc(value)}"`).join(' ')} ${disabled ? 'disabled' : ''}>${esc(text)}</button>`;
const materialLink = material => `<a href="#/evidence/${encodeURIComponent(material.id)}">${esc(material.title || '材料标题未知')}</a>`;
const relationLabel = id => id ? `已登记原始稿件 ${id}` : '原始出处与独立性尚未确认';

function dismissed() {
  try {
    const value = JSON.parse(localStorage.getItem(DISMISSED_KEY) || '[]');
    return Array.isArray(value) ? value.filter(item => typeof item === 'string') : [];
  } catch { return []; }
}

function candidateKey(material, candidate) {
  return `${material.id}@${material.version}/${candidate.id}@${candidate.version}`;
}

function saveDismissed(values) {
  try { localStorage.setItem(DISMISSED_KEY, JSON.stringify([...new Set(values)].slice(-1000))); }
  catch { throw new Error('浏览器未允许保存候选偏好。本次忽略未保存，资料与服务器关联保持原样。'); }
}

function metadata(material) {
  const url = safeURL(material.url);
  return `<div class="record-meta"><span>${esc(material.publisher || material.source_id || '来源未知')}</span><span>发布 ${esc(date(material.published_at))}</span><span>发现 ${esc(date(material.discovered_at))}</span><span>v${esc(material.version)}</span>${badge(material.status)}</div><div class="record-meta">${url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(url)} ↗</a>` : '<span>原链接未登记</span>'}</div>`;
}

function candidateCard(material, candidate, ignored) {
  const data = {material: material.id, candidate: candidate.id, version: material.version, 'candidate-version': candidate.version};
  const selected = material.origin_evidence_id === candidate.id;
  return `<article class="record" data-similarity-candidate="${esc(candidate.id)}"><div class="badges">${badge('unknown', selected ? '已登记的原始稿件' : ignored ? '本浏览器已忽略此版本建议' : '标题相似 · 待人工检查')}</div><h3 style="margin-top:10px">${materialLink(candidate)}</h3>${metadata(candidate)}<div class="record-actions">${selected ? '' : button('choose', '核对并选为原始稿件', data)}${button(ignored ? 'unignore' : 'ignore', ignored ? '重新提示此候选' : '忽略此版本建议', data)}</div></article>`;
}

async function renderPanel(material, offset) {
  const scope = {material: material.id};
  if (material.deleted) return `<section class="panel" data-similarity-panel="${esc(material.id)}"><div class="panel-head"><h2>相似材料检查</h2></div><div class="panel-body"><p>材料已在回收站。恢复后可继续核对来源关联，历史引用仍保留。</p></div></section>`;
  try {
    const query = new URLSearchParams({similar_to: material.id, offset: String(offset), limit: String(PAGE_SIZE)});
    const [result, origin] = await Promise.all([
      api('/evidence?' + query),
      material.origin_evidence_id ? api('/evidence/' + encodeURIComponent(material.origin_evidence_id)).catch(() => null) : Promise.resolve(null),
    ]);
    const saved = new Set(dismissed());
    const candidates = items(result).filter(candidate => candidate.id !== material.id);
    const total = Number(result.total) || 0;
    const current = origin ? `${materialLink(origin)}${origin.deleted ? ' · 原始稿件已在回收站' : ''}` : esc(relationLabel(material.origin_evidence_id));
    return `<section class="panel" data-similarity-panel="${esc(material.id)}"><div class="panel-head"><h2>相似材料检查</h2><div class="actions">${button('history', '查看／恢复关联历史', scope)}</div></div><div class="panel-body"><div class="notice">标题相似只是检查建议。请核对原文、日期、地点和转引关系；不同地点或日期的事件保持独立。选择原始稿件只登记转载来源，不合并材料、事件，也不代表多方证实。</div><p>当前原始稿件：${current}</p><div class="actions">${material.origin_evidence_id ? button('clear', '移除当前原始稿件关联', scope) : ''}${button('reset', '恢复本材料的候选提示', scope)}</div><p class="small-text muted" style="margin-top:12px">忽略仅保存在当前浏览器，最多保留最近 1000 项；未改变服务器资料。材料或候选产生新版本后会重新提示。</p></div>${candidates.length ? candidates.map(candidate => candidateCard(material, candidate, saved.has(candidateKey(material, candidate)))).join('') : '<div class="empty"><h3>本页没有标题相似候选</h3><p>这不表示不存在共同出处；仍可核对原文并手工登记来源关系。</p></div>'}<div class="pagination"><span>第 ${Math.floor(offset / PAGE_SIZE) + 1} 页 · 共 ${esc(total)} 条建议（含已忽略项）</span><div class="actions">${button('page', '上一页候选', {...scope, offset: Math.max(0, offset - PAGE_SIZE)}, offset === 0)}${button('page', '下一页候选', {...scope, offset: offset + PAGE_SIZE}, offset + PAGE_SIZE >= total)}</div></div></section>`;
  } catch (error) {
    return `<section class="panel" data-similarity-panel="${esc(material.id)}"><div class="panel-head"><h2>相似材料检查</h2></div><div class="panel-body"><div class="notice danger" role="status">候选检查暂不可用：${esc(error.message)}。现有材料与关联未改变。</div>${button('page', '重试候选检查', {...scope, offset})}</div></section>`;
  }
}

/** Insert the returned section into the current evidence detail, passing its current record. */
export async function similarityPanel(material) {
  if (!material?.id) return '';
  return renderPanel(material, 0);
}

/** Install once; the returned cleanup removes only this module's delegated click listener. */
export function installSimilarity({openDialog, closeDialog, route, toast}) {
  if (![openDialog, closeDialog, route, toast].every(value => typeof value === 'function')) throw new TypeError('相似材料模块需要完整的对话框、路由和提示接口');
  if (uninstallCurrent) uninstallCurrent();

  async function refreshPanel(trigger, offset = 0) {
    const host = trigger.closest('[data-similarity-panel]');
    const material = await api('/evidence/' + encodeURIComponent(trigger.dataset.material));
    const html = await renderPanel(material, offset);
    if (host?.isConnected) host.outerHTML = html;
  }

  async function confirmRelation(materialId, targetId, previousVersion = null) {
    const [material, target] = await Promise.all([
      api('/evidence/' + encodeURIComponent(materialId)),
      targetId ? api('/evidence/' + encodeURIComponent(targetId)) : Promise.resolve(null),
    ]);
    if (material.deleted || target?.deleted) throw new Error('材料或拟选原始稿件已在回收站，请先恢复记录再处理关联。');
    if (material.id === targetId) throw new Error('材料不能将自己登记为原始稿件。');
    if ((material.origin_evidence_id || null) === (targetId || null)) { toast('当前已是该关联，未创建重复版本。'); return; }
    const title = previousVersion !== null ? '恢复历史原始稿件关联' : target ? '确认原始稿件关系' : '移除原始稿件关联';
    const warning = target ? '请确认当前材料确实转引下方原始稿件。标题相似本身不能证明转引关系。' : '移除后，来源独立性回到尚未确认。材料、历史版本和研究引用继续保留。';
    openDialog(title, `<form id="similarity-confirm-form"><div class="dialog-body"><div class="editor-error" role="alert"></div><div class="notice">${esc(warning)}</div><h3>当前材料 · v${esc(material.version)}</h3><p class="prose">${esc(material.title)}</p>${metadata(material)}<p style="margin-top:14px">${esc(relationLabel(material.origin_evidence_id))}</p><h3 style="margin-top:22px">${target ? '拟登记的原始稿件' : '拟恢复为未确认出处'}</h3>${target ? `<p class="prose">${esc(target.title)}</p>${metadata(target)}` : '<p>原始出处与独立性尚未确认</p>'}${previousVersion !== null ? `<p class="small-text muted">恢复材料 v${esc(previousVersion)} 的来源选择；新建当前版本，不回滚正文或旧引用。</p>` : ''}<div class="field" style="margin-top:20px"><label for="similarity-reason">核对依据／修改理由 *</label><textarea id="similarity-reason" name="reason" required maxlength="4000" placeholder="例如：原文明确注明转引某稿件；或核对后发现原关联有误"></textarea></div></div><div class="dialog-footer">${button('close', '取消')}<button type="submit" class="primary">${target ? '确认登记此原始稿件' : '确认移除关联'}</button></div></form>`);
    const form = document.getElementById('similarity-confirm-form');
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const submit = form.querySelector('button[type="submit"]');
      const errorBox = form.querySelector('[role="alert"]');
      const reason = form.querySelector('[name="reason"]').value.trim();
      if (!reason) { errorBox.textContent = '请填写核对依据或修改理由。'; return; }
      submit.disabled = true;
      errorBox.textContent = '';
      try {
        await api('/evidence/' + encodeURIComponent(material.id), {method: 'PATCH', body: {expected_version: material.version, origin_evidence_id: targetId || null, change_reason: reason}});
        closeDialog();
        toast('来源关联已保存为新版本；材料和历史引用保持独立。');
        await route();
      } catch (error) {
        errorBox.textContent = error.status === 409 ? '版本冲突：材料已在另一处修改。你的理由仍保留；请复制理由、关闭对话框并重新核对当前材料后再提交。' : error.message;
        submit.disabled = false;
      }
    });
  }

  async function showHistory(materialId) {
    const [material, history] = await Promise.all([api('/evidence/' + encodeURIComponent(materialId)), api('/evidence/' + encodeURIComponent(materialId) + '/history')]);
    const versions = items(history).slice().sort((a, b) => a.version - b.version);
    const transitions = versions.filter((record, index) => !index || (record.origin_evidence_id || null) !== (versions[index - 1].origin_evidence_id || null)).reverse();
    openDialog('原始稿件关联历史', `<div class="dialog-body"><div class="notice info">只恢复来源关联，不恢复正文、不改变固定证据版本。所有恢复操作需要再次核对并填写理由。</div>${transitions.map(record => `<article class="history-entry"><div class="record-top"><strong>v${esc(record.version)} · ${esc(date(record.updated_at))}</strong>${(record.origin_evidence_id || null) !== (material.origin_evidence_id || null) ? button('restore', '核对并恢复此关联', {material: material.id, origin: record.origin_evidence_id || '', 'history-version': record.version}) : badge('neutral', '与当前关联相同')}</div><p class="prose">${esc(relationLabel(record.origin_evidence_id))}</p><p class="small-text muted">${esc(record.change_reason || '首次登记')}</p>${record.origin_evidence_id ? `<a data-similarity-action="navigate" href="#/evidence/${encodeURIComponent(record.origin_evidence_id)}">查看该原始稿件</a>` : ''}</article>`).join('') || '<p>暂无来源关联历史。</p>'}</div><div class="dialog-footer">${button('close', '关闭')}</div>`);
  }

  const onClick = async event => {
    const trigger = event.target.closest?.('[data-similarity-action]');
    if (!trigger || trigger.disabled) return;
    if (trigger.dataset.similarityAction === 'navigate') { closeDialog(); return; }
    event.preventDefault();
    const data = trigger.dataset;
    trigger.disabled = true;
    try {
      if (data.similarityAction === 'close') closeDialog();
      else if (data.similarityAction === 'choose') await confirmRelation(data.material, data.candidate);
      else if (data.similarityAction === 'clear') await confirmRelation(data.material, null);
      else if (data.similarityAction === 'restore') await confirmRelation(data.material, data.origin || null, Number(data.historyVersion));
      else if (data.similarityAction === 'history') await showHistory(data.material);
      else if (data.similarityAction === 'page') await refreshPanel(trigger, Math.max(0, Number(data.offset) || 0));
      else if (['ignore', 'unignore', 'reset'].includes(data.similarityAction)) {
        const key = candidateKey({id: data.material, version: data.version}, {id: data.candidate, version: data.candidateVersion});
        const values = dismissed();
        saveDismissed(data.similarityAction === 'reset' ? values.filter(value => !value.startsWith(data.material + '@')) : data.similarityAction === 'ignore' ? [...values, key] : values.filter(value => value !== key));
        await refreshPanel(trigger);
        toast(data.similarityAction === 'ignore' ? '此版本建议已在本浏览器忽略；未改变服务器关联。' : '候选提示已恢复。');
      }
    } catch (error) { toast(error.message); }
    finally { trigger.disabled = false; }
  };
  document.addEventListener('click', onClick);
  const uninstall = () => { document.removeEventListener('click', onClick); if (uninstallCurrent === uninstall) uninstallCurrent = null; };
  uninstallCurrent = uninstall;
  return uninstall;
}
