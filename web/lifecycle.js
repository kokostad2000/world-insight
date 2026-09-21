/** Local recovery-first deletion and retention controls. Uses the host dialog and styles. */
import {api,esc,date,items} from './lib.js';

const kinds={topic:'议题',evidence:'材料',claim:'说法',event:'事件',observation:'指标',judgment:'判断',scenario:'情景',impact_path:'影响路径',review:'复盘',brief:'简报'};
const collections={topic:'topics',evidence:'evidence',claim:'claims',event:'events',observation:'metrics',judgment:'judgments',scenario:'scenarios',impact_path:'impact-paths',review:'reviews',brief:'briefs'};
const kindFor=collection=>Object.keys(collections).find(kind=>collections[kind]===collection)||collection;
const titleOf=row=>row.question||row.title||row.conclusion||row.statement||row.indicator||row.rationale||'未命名记录';
const button=(action,text,attrs='',css='')=>`<button type="button" data-action="lifecycle-${action}" ${attrs} class="${css}">${esc(text)}</button>`;
const cancel=()=>button('close','取消');
const errorBox=()=>'<div class="editor-error" data-lifecycle-error role="alert"></div>';
const field=(id,title,content,hint='')=>`<div class="field full"><label for="${id}">${esc(title)}</label>${content}${hint?`<p class="hint">${esc(hint)}</p>`:''}</div>`;
const state={host:null,flow:null,trashOffset:0,settings:null,installed:false};

export function deleteButton(collection,record){
 const kind=kindFor(collection);
 if(!kinds[kind]||!record?.id||!Number.isInteger(record.version)||record.deleted)return '';
 return button('delete','移入回收站',`data-kind="${esc(kind)}" data-id="${esc(record.id)}" data-version="${record.version}" data-title="${esc(titleOf(record))}"`,'small danger');
}

export function deletionConfirmation(plan,reason,confirmed){
 if(plan?.state!=='recovery_ready'||!plan.recovery?.verified||confirmed!==true||!String(reason||'').trim())throw new Error('请先验证恢复文件，填写原因并勾选确认。');
 return {confirm:true,reason:String(reason).trim(),plan_hash:plan.plan_hash,recovery_id:plan.recovery.id,expected_versions:plan.targets};
}

export function dependencySummary(dependencies=[]){
 const groups=new Map();
 for(const dependency of dependencies){
  const key=dependency.kind+':'+dependency.id;
  if(!groups.has(key))groups.set(key,{...dependency,versions:[]});
  groups.get(key).versions.push(dependency.version);
 }
 return [...groups.values()].map(row=>({...row,versions:[...new Set(row.versions)].sort((a,b)=>a-b)}));
}

async function namesFor(rows){
 const names=new Map();
 // Names are supplemental; unavailable/deleted objects remain visible by stable ID.
 for(let offset=0;offset<Math.min(rows.length,40);offset+=6){
  await Promise.all(rows.slice(offset,Math.min(offset+6,40)).map(async row=>{
   const collection=collections[row.kind];if(!collection)return;
   try{const record=await api(`/${collection}/${encodeURIComponent(row.id)}`);names.set(row.kind+':'+row.id,titleOf(record));}catch{}
  }));
 }
 return names;
}

function dependencyList(plan,names){
 const groups=dependencySummary(plan.dependencies);
 if(!groups.length)return '<div class="notice info">未发现其他研究记录引用本项。已有历史版本仍会保留。</div>';
 return `<p><strong>${groups.length} 条相关记录</strong>引用了本项，涉及 ${plan.dependencies.length} 个历史版本。它们会保留，不随本项删除。</p><div class="refs" style="max-height:240px">${groups.map(row=>`<div class="history-entry"><strong>${esc(kinds[row.kind]||'相关记录')} · ${esc(names.get(row.kind+':'+row.id)||({change:'已有变化记录',notification:'已有站内提醒'})[row.kind]||'记录编号 '+row.id)}</strong><p class="small-text muted">引用出现在版本 ${esc(row.versions.join('、'))}；当前版本 ${esc(row.current_version)}</p></div>`).join('')}</div><p class="small-text muted" style="margin-top:10px">引用材料的可用性改变后，相关判断可能需要重新审阅。恢复记录不会自动完成重审。</p>`;
}

function targetSummary(flow){
 return `<div class="history-entry"><div class="badges"><span class="badge">${esc(kinds[flow.kind]||'研究记录')}</span><span class="badge">当前版本 ${esc(flow.version)}</span></div><h3 style="margin-top:10px">${esc(flow.title)}</h3><p class="small-text muted">本次仅处理这一项；相关议题与其他研究记录保留。</p></div>`;
}

function previewDialog(flow){
 state.host.openDialog('移入回收站 · 1 / 3 查看影响',`<div class="dialog-body">${errorBox()}${targetSummary(flow)}<div class="notice info">移入回收站后可从“本地运行与数据”恢复。已有历史和引用保留；来源授权到期的正文仍会按期限清理。</div>${dependencyList(flow.plan,flow.names)}<p class="small-text muted" style="margin-top:16px">下一步会在本机保存并核验恢复包和可导出的内容，成功后才可确认删除。预览有效至 ${esc(date(flow.plan.expires_at))}。</p></div><div class="dialog-footer">${cancel()}${button('prepare','下一步：准备恢复文件','','primary')}</div>`);
}

function preparedDialog(flow){
 const recovery=flow.plan.recovery;
 state.host.openDialog('移入回收站 · 2 / 3 恢复文件已核验',`<form data-lifecycle-form="commit"><div class="dialog-body">${errorBox()}${targetSummary(flow)}<div class="notice info"><strong>恢复文件已保存并核验。</strong>请记下位置。回收站恢复不需要替换整份资料库；下面的恢复包用于另行恢复实例。</div><h3>本地恢复包</h3><div class="pre-text">${esc(recovery.backup_path)}</div><h3 style="margin-top:15px">允许导出的研究内容</h3><div class="pre-text">${esc(recovery.export_path)}</div><p class="small-text muted" style="margin-top:10px">${Number(recovery.content_omissions)||0} 个材料版本的正文已从导出中省略。有限来源内容可能也从恢复包中省略；笔记、版本和引用仍保留。这些文件不能恢复已经到期或无权保留的正文。</p>${dependencyList(flow.plan,flow.names)}<div class="form-grid" style="margin-top:20px">${field('lifecycle-delete-reason','移入回收站的原因','<textarea id="lifecycle-delete-reason" name="reason" required maxlength="2000" placeholder="例如：重复建立了议题，保留另一份研究档案"></textarea>')}<div class="field full check-field"><input id="lifecycle-delete-confirm" name="confirmed" type="checkbox" required><label for="lifecycle-delete-confirm">我已查看影响和恢复文件位置，确认将上述记录移入回收站。</label></div></div></div><div class="dialog-footer">${cancel()}<button type="submit" class="danger">确认移入回收站</button></div></form>`);
}

function retentionForm(settings){
 return `<form data-lifecycle-form="settings" data-version="${esc(settings.version)}">${errorBox()}<div class="form-grid"><div class="field full check-field"><input id="lifecycle-retention-enabled" type="checkbox" name="candidate_retention_enabled" ${settings.candidate_retention_enabled?'checked':''}><label for="lifecycle-retention-enabled">按期限清理未引用、未人工处理的采集候选</label></div>${field('lifecycle-candidate-days','候选保留天数',`<input id="lifecycle-candidate-days" type="number" name="candidate_days" min="1" max="36500" step="1" required value="${esc(settings.candidate_days)}">`,'人工登记、人工笔记、曾被研究引用和人工恢复的记录会保留。')}${field('lifecycle-batch-limit','每次最多处理',`<input id="lifecycle-batch-limit" type="number" name="batch_limit" min="1" max="200" step="1" required value="${esc(settings.batch_limit)}">`,'一次处理有限数量，剩余记录可在下一次继续。')}<div class="field full actions"><button type="submit">保存保留设置</button>${button('retention-preview','查看当前到期记录','','primary')}</div></div></form>`;
}

function trashRecords(result){
 if(!result.items.length)return '<div class="empty"><h3>回收站为空</h3><p>移入回收站的研究记录会显示在这里，可查看原因并恢复。</p></div>';
 return result.items.map(row=>`<article class="record"><div class="record-top"><div><div class="badges"><span class="badge">${esc(kinds[row.kind]||'研究记录')}</span>${row.content_expired?'<span class="badge warn">正文已到期</span>':''}</div><h3 style="margin-top:10px">${esc(row.title)}</h3></div>${button('restore','恢复',`data-kind="${esc(row.kind)}" data-id="${esc(row.id)}" data-version="${esc(row.version)}" data-title="${esc(row.title)}" data-expired="${row.content_expired?'true':'false'}"`,'small')}</div><div class="prose small-text">${esc(row.deleted_reason||'未记录原因')}</div><p class="record-meta">移入时间：${esc(date(row.deleted_at))} · 版本 ${esc(row.version)}</p></article>`).join('');
}

export async function lifecyclePanel(){
 const [settings,recycled]=await Promise.all([api('/retention'),api(`/trash?limit=20&offset=${state.trashOffset}`)]);
 state.settings=settings;
 return `<div id="lifecycle-panel"><section class="panel"><div class="panel-head"><div><h2>保留期限与到期处理</h2><p>保持研究记录可追溯，并按来源许可处理正文。</p></div></div><div class="panel-body"><div class="notice">来源约定的正文保留上限优先，即使材料已被引用也须遵守。关闭候选清理不会关闭来源期限处理。到期正文会从所有历史版本中移除，笔记和引用仍保留。</div>${retentionForm(settings)}</div></section><section class="panel"><div class="panel-head"><div><h2>回收站</h2><p>共 ${esc(recycled.total)} 项 · 人工恢复不会清除待重审任务</p></div>${button('refresh','刷新','','small')}</div>${trashRecords(recycled)}<div class="pagination"><span>${recycled.total?`${Math.min(state.trashOffset+1,recycled.total)}—${Math.min(state.trashOffset+recycled.items.length,recycled.total)} / ${recycled.total}`:'暂无记录'}</span><div class="actions">${button('trash-page','上一页',`data-offset="${Math.max(0,state.trashOffset-20)}" ${state.trashOffset===0?'disabled':''}`,'small')}${button('trash-page','下一页',`data-offset="${state.trashOffset+20}" ${state.trashOffset+recycled.items.length>=recycled.total?'disabled':''}`,'small')}</div></div></section></div>`;
}

async function refreshPanel(){
 const panel=document.getElementById('lifecycle-panel');
 if(panel)panel.outerHTML=await lifecyclePanel();else await state.host.route();
}

function showError(error,scope=document){
 const box=(scope===document?document.querySelector('dialog[open] [data-lifecycle-error]'):null)||scope.querySelector('[data-lifecycle-error]');
 const conflict=error.status===409;
 const text=conflict?'记录、引用或恢复文件已变化。你的输入仍保留，请重新预览后确认。':error.message||'操作未完成，请重试。';
 if(box){box.innerHTML=`<div class="notice danger">${esc(text)}</div>${conflict?button('restart','重新读取并预览','','small'):''}`;box.scrollIntoView?.({block:'nearest'});}
 else state.host.toast(text);
}

async function beginDelete(dataset){
 const flow={type:'delete',kind:dataset.kind,id:dataset.id,version:Number(dataset.version),title:dataset.title||'研究记录',names:new Map()};
 state.flow=flow;
 state.host.openDialog('正在检查删除影响',`<div class="dialog-body">${errorBox()}<div class="loading">正在核对当前记录及历史引用</div></div><div class="dialog-footer">${cancel()}</div>`);
 const plan=await api('/deletions/preview',{method:'POST',body:{targets:[{kind:flow.kind,id:flow.id,expected_version:flow.version}],cascade:false}});
 const names=await namesFor(dependencySummary(plan.dependencies));
 if(state.flow!==flow)return;
 Object.assign(flow,{plan,names});previewDialog(flow);
}

async function retentionPreview(){
 const flow={type:'retention',operationId:null};state.flow=flow;
 state.host.openDialog('正在查看到期记录',`<div class="dialog-body">${errorBox()}<div class="loading">正在检查保留期限与历史引用</div></div><div class="dialog-footer">${cancel()}</div>`);
 const preview=await api('/retention/preview');
 const names=await namesFor(preview.actions);
 if(state.flow!==flow)return;
 flow.preview=preview;
 const actions=items(preview.actions),limit=preview.settings.batch_limit;
 state.host.openDialog('到期处理 · 先核对，再执行',`<form data-lifecycle-form="retention-run"><div class="dialog-body">${errorBox()}<div class="notice danger">执行后，到期摘录和译文会从所有历史版本中移除，不能从回收站恢复正文。笔记、来源和引用保留。人工记录不会因候选期限被清理。</div><p><strong>${esc(preview.total)} 项已到期</strong>，本次最多处理 ${esc(limit)} 项。检查时间：${esc(date(preview.evaluated_at))}。</p>${actions.length?`<div class="refs" style="max-height:300px">${actions.map(row=>`<div class="history-entry"><strong>${esc(names.get('evidence:'+row.id)||'材料编号 '+row.id)}</strong><p class="small-text">${esc(row.reason)}</p><p class="small-text muted">到期：${esc(date(row.expires_at))} · ${row.move_to_trash?'正文清理后移入回收站':'清理正文，保留研究记录'}</p></div>`).join('')}</div>`:'<div class="empty"><h3>当前没有到期记录</h3><p>本次检查未执行任何清理。</p></div>'}${preview.truncated?'<p class="small-text muted">这里展示前 200 项；每次仍只处理设置中的数量上限。</p>':''}<p class="small-text muted" style="margin-top:14px">有人工处理或历史引用的候选会受到保护。执行时会再次检查；若刚有记录发生变化，本次结果可能与预览不同。</p>${actions.length?'<div class="check-field"><input id="lifecycle-run-confirm" type="checkbox" name="confirmed" required><label for="lifecycle-run-confirm">我已查看到期记录，确认执行这一批内容清理。</label></div>':''}</div><div class="dialog-footer">${cancel()}${actions.length?'<button type="submit" class="danger">确认处理这一批</button>':''}</div></form>`);
}

function restoreDialog(dataset){
 const flow={type:'restore',kind:dataset.kind,id:dataset.id,version:Number(dataset.version),title:dataset.title,expired:dataset.expired==='true'};state.flow=flow;
 state.host.openDialog('恢复研究记录',`<form data-lifecycle-form="restore"><div class="dialog-body">${errorBox()}${targetSummary(flow)}<div class="notice ${flow.expired?'':'info'}">${flow.expired?'正文保留期限已到，只能恢复现存元数据、笔记与引用；已清理的正文不会重新出现。':'恢复后记录重新出现在研究列表，原历史和引用继续保留。'} 已有待重审任务仍需单独完成。</div>${field('lifecycle-restore-reason','恢复原因','<textarea id="lifecycle-restore-reason" name="reason" required maxlength="2000" placeholder="说明为何继续保留此记录"></textarea>')}</div><div class="dialog-footer">${cancel()}<button type="submit" class="primary">确认恢复</button></div></form>`);
}

function resultDialog(result){
 const pending=result.state==='compaction_pending';
 state.host.openDialog(pending?'内容处理已提交，清理尚未完全完成':'这一批处理已完成',`<div class="dialog-body">${errorBox()}<div class="notice ${pending?'':'info'}">${pending?'到期正文已停止展示，但存储空间清理尚未完成。请重试完成清理；不会重复处理已经完成的记录。':`已处理 ${items(result.results).length} 项记录。笔记、来源和引用继续保留。`}</div><p>本次之后还有 ${esc(result.remaining??0)} 项待处理。</p></div><div class="dialog-footer">${button('close','关闭')}${pending?button('retention-retry','重试完成清理','','primary'):button('retention-preview','重新查看到期记录','','primary')}</div>`);
}

async function handleClick(buttonElement){
 const action=buttonElement.dataset.action.slice('lifecycle-'.length),flow=state.flow;
 if(action==='close'){state.flow=null;state.host.closeDialog();return;}
 if(action==='delete')return beginDelete(buttonElement.dataset);
 if(action==='prepare'){
  if(flow?.type!=='delete'||!flow.plan)throw new Error('请先重新查看删除影响。');
  const plan=await api(`/deletions/${encodeURIComponent(flow.plan.id)}/prepare-recovery`,{method:'POST',body:{}});
  if(state.flow===flow){flow.plan=plan;preparedDialog(flow);}return;
 }
 if(action==='restart'){
  if(flow?.type==='delete'){
   const current=await api(`/${collections[flow.kind]}/${encodeURIComponent(flow.id)}`);
   return beginDelete({kind:flow.kind,id:flow.id,version:current.version,title:titleOf(current)});
  }
  state.flow=null;state.host.closeDialog();return refreshPanel();
 }
 if(action==='refresh')return refreshPanel();
 if(action==='trash-page'){state.trashOffset=Math.max(0,Number(buttonElement.dataset.offset)||0);return refreshPanel();}
 if(action==='restore')return restoreDialog(buttonElement.dataset);
 if(action==='retention-preview')return retentionPreview();
 if(action==='retention-retry'){
  if(flow?.type!=='retention'||!flow.operationId)throw new Error('请重新查看到期记录。');
  const result=await api('/retention/run',{method:'POST',body:{operation_id:flow.operationId}});
  if(state.flow===flow)resultDialog(result);return;
 }
}

async function submitForm(form){
 const task=form.dataset.lifecycleForm,flow=state.flow;
 if(task==='settings'){
  const data={expected_version:Number(form.dataset.version),candidate_days:Number(form.elements.candidate_days.value),batch_limit:Number(form.elements.batch_limit.value),candidate_retention_enabled:form.elements.candidate_retention_enabled.checked};
  await api('/retention',{method:'PATCH',body:data});state.host.toast('保留设置已保存；本次保存没有执行内容清理。');return refreshPanel();
 }
 if(task==='commit'){
  if(flow?.type!=='delete')throw new Error('请重新查看删除影响。');
  const body=deletionConfirmation(flow.plan,form.elements.reason.value,form.elements.confirmed.checked);
  await api(`/deletions/${encodeURIComponent(flow.plan.id)}/commit`,{method:'POST',body});
  state.flow=null;state.host.closeDialog();state.host.toast('已移入回收站。可在“本地运行与数据”中恢复；相关研究和历史仍保留。');
  location.hash='#/settings';return state.host.route();
 }
 if(task==='restore'){
  if(flow?.type!=='restore')throw new Error('请从回收站重新选择记录。');
  await api(`/trash/${encodeURIComponent(flow.kind)}/${encodeURIComponent(flow.id)}/restore`,{method:'POST',body:{expected_version:flow.version,reason:form.elements.reason.value}});
  state.flow=null;state.host.closeDialog();state.host.toast('记录已恢复；已有待重审任务仍保留。');return refreshPanel();
 }
 if(task==='retention-run'){
  if(flow?.type!=='retention'||!flow.preview||!form.elements.confirmed.checked)throw new Error('请先查看到期记录并勾选确认。');
  flow.operationId=flow.operationId||crypto.randomUUID();
  const result=await api('/retention/run',{method:'POST',body:{operation_id:flow.operationId}});
  if(state.flow===flow)resultDialog(result);await refreshPanel();
 }
}

export function installLifecycle({openDialog,closeDialog,route,toast}){
 state.host={openDialog,closeDialog,route,toast};
 if(state.installed)return;
 state.installed=true;
 document.addEventListener('click',async event=>{
  const target=event.target.closest?.('[data-action]');
  if(!target?.dataset.action?.startsWith('lifecycle-')){
   if(target?.dataset.action==='close-dialog')state.flow=null;
   return;
  }
  event.preventDefault();event.stopImmediatePropagation();if(target.disabled)return;
  const scope=target.closest('dialog')||document.getElementById('lifecycle-panel')||document;
  target.disabled=true;const original=target.textContent;
  if(!['lifecycle-close','lifecycle-restore'].includes(target.dataset.action))target.textContent='正在处理…';
  try{await handleClick(target);}catch(error){showError(error,scope.isConnected===false?document:scope);}finally{target.disabled=false;target.textContent=original;}
 },true);
 document.addEventListener('submit',async event=>{
  const form=event.target;if(!form.matches?.('[data-lifecycle-form]'))return;
  event.preventDefault();event.stopImmediatePropagation();if(!form.reportValidity())return;
  const submit=form.querySelector('button[type="submit"]');if(submit?.disabled)return;
  if(submit)submit.disabled=true;
  try{await submitForm(form);}catch(error){showError(error,form);}finally{if(submit)submit.disabled=false;}
 },true);
 document.addEventListener('cancel',event=>{if(event.target.matches?.('dialog'))state.flow=null;},true);
}
