/** Pure presentation helpers. Every external value is escaped before HTML insertion. */
export function esc(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
export function safeURL(value) { try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) ? url.href : ''; } catch { return ''; } }
export function items(value) { return Array.isArray(value) ? value : value?.items || []; }
export function lines(value) { return Array.isArray(value) ? value.join('\n') : value ?? ''; }
export function splitLines(value) { return String(value || '').split(/[\n,，]/).map(x => x.trim()).filter(Boolean); }
export function date(value, precision) {
  if (!value) return '未知';
  if (precision === 'month' || /^\d{4}-\d{2}$/.test(value)) return String(value).slice(0, 7);
  if (precision === 'day' || /^\d{4}-\d{2}-\d{2}$/.test(value)) return String(value).slice(0, 10);
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:false});
}
export const labels = {
 active:'进行中',paused:'已暂停',archived:'已归档',draft:'草稿',reviewed:'用户已审阅',needs_review:'待重审',withdrawn:'已撤回',
 unverified:'待核查',disputed:'存在分歧',corrected:'已更正',inaccessible:'原链接不可访问',restricted:'展示受限',
 ready:'可用',not_configured:'未配置',disabled:'已停用',manual:'人工登记',quota_exhausted:'免费配额已用尽',failed:'失败',stale:'数据陈旧',
 fresh:'已更新',unknown:'未知',unavailable:'不可用',complete:'已配置来源检查完成',partial:'部分覆盖',
 explanation:'局势解释',prediction:'可判定预测',low:'低',medium:'中',high:'高',
 meets:'符合',does_not_meet:'不符合',partly_meets:'部分符合',indeterminate:'无法判定',
 observed:'已观察到的关联',assumption:'有证据的分析假设',unverified_link:'待验证',
 country:'国家',region:'区域',city:'城市',coordinate:'精确坐标',instant:'时刻',day:'日',month:'月',
 article:'报道',official:'官方文件',statement:'公开声明',data:'数据记录',excerpt:'人工摘录',
 'evidence.created':'新材料','evidence.updated':'材料更新','evidence.corrected':'证据更正','event.created':'新事件',
 'claim.created':'新说法','judgment.created':'新判断','judgment.revised':'判断修订','research.needs_review':'研究待重审',
 'source.failed':'来源失效','source.recovered':'来源恢复',read:'已读',unread:'未读',
 generated:'模板生成',pending:'待处理',queued:'等待采集',running:'采集中',succeeded:'成功',success:'成功',error:'失败',cancelled:'已取消',
};
export function label(value) { return labels[value] || value || '未知'; }
export function badge(value, text) { const tone = ['failed','withdrawn','needs_review','unavailable'].includes(value) ? 'danger' : ['unverified','disputed','stale','partial','quota_exhausted','unknown','draft'].includes(value) ? 'warn' : ['reviewed','ready','fresh','active','complete','succeeded','success'].includes(value) ? 'good' : 'neutral'; return `<span class="badge ${tone}">${esc(text || label(value))}</span>`; }
export function paragraphs(value, fallback = '尚未记录') { return value ? `<div class="prose">${esc(value)}</div>` : `<span class="muted">${esc(fallback)}</span>`; }
export function versionId(evidence) { return evidence.version_id || `${evidence.id}@${evidence.version}`; }
export function visibleReadPayload(snapshot, changes) { return {snapshot_at:snapshot,items:changes.map(x => ({id:x.id,version:x.version}))}; }
export function eventCoordinates(event) { const l = event.location || {}; return l.precision === 'coordinate' && Number.isFinite(l.lat) && Number.isFinite(l.lon) && l.lat >= -90 && l.lat <= 90 && l.lon >= -180 && l.lon <= 180 ? [l.lon,l.lat] : null; }
export function timeOrder(value) {
  if(!value)return Number.NEGATIVE_INFINITY;
  const normalized=/^\d{4}-\d{2}$/.test(value)?value+'-01T00:00:00Z':/^\d{4}-\d{2}-\d{2}$/.test(value)?value+'T00:00:00Z':value;
  const instant=Date.parse(normalized);return Number.isFinite(instant)?instant:Number.NEGATIVE_INFINITY;
}
export function reviewTarget(record) {
  return record.kind==='scenario'?{collection:'scenarios',label:'审阅情景',canReview:false}:record.kind==='impact_path'?{collection:'impact-paths',label:'审阅路径',canReview:false}:{collection:'judgments',label:'审阅判断',canReview:true};
}
export function preserveChannels(previous, urls, sourceId) {
  const selected=new Set(urls.map(url=>String(url).trim()).filter(Boolean));
  const kept=previous.filter(channel=>!channel.url||selected.has(channel.url)).map(channel=>({...channel}));
  for(const url of selected)if(!kept.some(channel=>channel.url===url))kept.push({url,source_id:sourceId});
  return kept;
}
export async function api(path, options = {}) {
  const response = await fetch('/api' + path, {...options, headers:{'Content-Type':'application/json',...options.headers}, body:options.body === undefined ? undefined : JSON.stringify(options.body)});
  const data = await response.json();
  if (!response.ok) { const error = new Error(data.error?.message || `请求失败 (${response.status})`); error.status = response.status; error.details = data.error?.details; error.code = data.error?.code; throw error; }
  return data;
}
export function csvOptions(values) { return values.map(value => [value,label(value)]); }
