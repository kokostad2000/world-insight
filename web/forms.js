import {esc, lines, items, label, csvOptions, versionId, splitLines} from './lib.js';
const f = (key, title, type='text', more={}) => ({key,title,type,...more});
const section = title => ({type:'section',title});
const topic = () => f('topic_id','所属议题','topic',{required:true});
const refs = (key='evidence_version_ids', title='支持材料 · 固定版本') => f(key,title,'refs',{full:true,hint:'引用固定的材料版本，后续材料更正不会改写当时依据。'});
const statuses = () => f('status','审阅状态','select',{options:csvOptions(['draft','reviewed','needs_review','withdrawn'])});
const reason = () => f('change_reason','修订原因','textarea',{full:true,hint:'编辑已有研究记录时必须填写，保留作出变更时的理由。'});
const commonResearch = [f('valid_until','适用期限','date'),f('review_date','下次复查日期','date'),f('assumptions','假设（每行一项）','lines',{full:true}),refs(),refs('opposing_evidence_version_ids','反对材料 · 固定版本')];
export const titles = {topics:'议题',evidence:'材料',claims:'说法',events:'事件',judgments:'判断',scenarios:'情景','impact-paths':'影响路径',reviews:'复盘',sources:'来源',metrics:'背景指标'};
export const schemas = {
 topics:[f('question','研究问题','textarea',{required:true,full:true,placeholder:'例如：某项政策将如何影响地区贸易？'}),f('regions','地区（逗号或换行分隔）','lines'),f('actors','参与方（逗号或换行分隔）','lines'),f('time_range','研究时间范围','text',{placeholder:'例如：2026 年下半年'}),f('status','议题状态','select',{options:csvOptions(['active','paused','archived'])}),f('keywords','关键词','lines'),f('exclude_keywords','排除词','lines'),f('rationale','关注理由','textarea',{full:true}),f('followed','关注此议题，纳入变化简报','checkbox')],
 evidence:[topic(),f('source_id','来源','source'),f('title','原文标题','text',{required:true,full:true}),f('url','原文链接','url',{full:true,placeholder:'https://…'}),f('publisher','发布机构'),f('author','作者（若有）'),f('language','原始语言','text',{placeholder:'zh / en / …'}),f('material_type','材料类型','select',{options:csvOptions(['article','official','statement','data','excerpt'])}),section('明确区分发布时间与采集时间'),f('published_at','材料发布时间','text',{placeholder:'2026-09-20 或带时区的 ISO 时间'}),f('source_updated_at','来源更新时间','text',{placeholder:'未知则留空'}),f('excerpt','允许保存的人工摘录','textarea',{full:true,hint:'仅登记有权保存的内容。许可不明确时只保存原链接和允许的元数据。'}),f('notes','研究备注','textarea',{full:true}),f('translation','人工译文（与原文分开）','textarea',{full:true}),f('status','核查状态','select',{options:csvOptions(['unverified','reviewed','disputed','corrected','withdrawn','inaccessible','restricted'])}),f('origin_evidence_id','已识别的原始出处','evidence'),f('channels','出现渠道 URL（每行一项）','lines',{full:true}),f('source_record_id','来源记录 ID'),section('材料使用范围 · 未知权限保持关闭'),f('rights.store','允许存储摘录','checkbox'),f('rights.display','允许展示摘录','checkbox'),f('rights.export','允许导出摘录','checkbox'),f('rights.ai','允许用于 AI（当前功能关闭）','checkbox')],
 claims:[topic(),f('subject','作出说法的主体','text',{required:true}),f('statement','具体说法','textarea',{required:true,full:true}),f('attribution','来源归属／引述位置','text',{full:true}),f('dispute_status','分歧状态','select',{options:[['unverified','待核查'],['disputed','与其他说法冲突'],['reviewed','用户已审阅'],['needs_review','待重审']]}),refs('evidence_version_ids','该说法的材料出处')],
 events:[topic(),f('title','事件标题','text',{required:true}),f('event_type','事件类别','text',{placeholder:'外交 / 政策 / 行动 / …'}),f('actors','参与方','lines'),f('time_precision','发生时间精度','select',{options:csvOptions(['unknown','month','day','instant'])}),f('occurred_at','事件发生时间','text',{placeholder:'未知留空；月 YYYY-MM；日 YYYY-MM-DD',hint:'精确时刻请填写带时区 ISO 时间，不使用采集时间代替。'}),f('location.name','地点名称'),f('location.country_code','国家代码','text',{placeholder:'ISO3，如 CHN、USA'}),f('location.precision','位置精度','select',{options:csvOptions(['unknown','country','region','city','coordinate'])}),f('location.lat','纬度（仅精确坐标）','number',{step:'any'}),f('location.lon','经度（仅精确坐标）','number',{step:'any'}),f('verification_status','核查状态','select',{options:csvOptions(['unverified','reviewed','disputed','needs_review'])}),f('claim_ids','关联说法（并列保留不同说法）','claims',{full:true}),refs()],
 judgments:[topic(),f('judgment_type','判断类型','select',{options:csvOptions(['explanation','prediction'])}),f('conclusion','当前判断','textarea',{required:true,full:true}),...commonResearch,f('missing_evidence','缺证据说明／假设型暂定判断','textarea',{full:true,hint:'没有证据时说明具体缺口；审阅不会消除此标记。'}),f('confidence','分析置信度','select',{options:csvOptions(['low','medium','high'])}),f('confidence_reason','置信理由','textarea',{full:true,hint:'说明证据质量、独立性、争议与关键假设；置信度不等于发生概率。'}),f('outcome_criteria','结果判定条件（预测必填）','textarea',{full:true}),statuses(),f('author','作者'),f('reviewer','审阅者'),reason()],
 scenarios:[topic(),f('title','情景名称','text',{required:true}),f('description','可能的发展路径','textarea',{required:true,full:true}),...commonResearch,f('counterevidence_search','反证检索说明','textarea',{full:true,hint:'未找到反证时如实写“尚未找到”，说明检索过哪些范围。'}),f('signals','观察信号（每行一项）','lines',{full:true}),f('invalidation_conditions','失效条件','textarea',{full:true}),statuses(),f('reviewer','审阅者'),reason()],
 'impact-paths':[topic(),f('title','路径名称','text',{required:true}),{type:'path',key:'path',full:true},statuses(),reason()],
 reviews:[topic(),f('judgment_id','复盘判断','judgment',{required:true}),f('judgment_version','判断版本','number',{required:true,min:1}),f('next_review_date','下次复查日期（可留空）','date'),f('outcome','结果','select',{options:csvOptions(['indeterminate','meets','does_not_meet','partly_meets'])}),f('rationale','结果依据与原因','textarea',{required:true,full:true,hint:'无法判定单独记录，不能当作预测失败或成功。'}),refs('evidence_version_ids','结果材料'),f('author','复盘人')],
 metrics:[topic(),f('indicator','指标代码／名称','text',{required:true}),f('country_code','国家代码','text',{required:true}),f('value','数值（未知留空）','number',{step:'any'}),f('unit','单位'),f('period','观测期','text',{required:true,placeholder:'例如：2025'}),f('published_at','发布时间','text',{placeholder:'未知则留空'}),f('frequency','频率','select',{options:[['annual','年度'],['quarterly','季度'],['monthly','月度'],['daily','日度'],['unknown','未知']]}),f('source_id','来源','source'),refs()],
 sources:[f('name','来源名称','text',{required:true}),f('adapter','接入方式','select',{options:[['manual','人工链接登记'],['rss','官方 RSS'],['gdelt','GDELT 新闻发现'],['worldbank','World Bank WDI']]}),f('domain','来源域名'),f('enabled','启用此免费来源','checkbox'),f('languages','语言覆盖','lines'),f('regions','地区覆盖','lines'),f('budget_daily','每日免费请求上限','number',{min:0,required:true}),f('interval_seconds','刷新间隔（秒）','number',{min:60,required:true}),f('config.feed_url','RSS 地址','url',{full:true,hint:'批量采集只允许已经审核的来源。其他来源仍可人工登记链接。'}),f('config.query','GDELT 查询（留空使用议题关键词）','text',{full:true}),f('config.countries','WDI 国家 ISO3 代码','lines'),f('config.indicators','WDI 白名单指标','lines',{hint:'NY.GDP.MKTP.CD、SP.POP.TOTL'}),f('config.topic_ids','采集关联议题 ID（每行一项）','lines',{full:true}),section('授权与使用范围'),f('license_url','授权依据链接','url',{full:true}),f('checked_at','许可核对日期','date'),f('rights.fetch','允许获取','checkbox'),f('rights.store','允许存储','checkbox'),f('rights.display','允许展示','checkbox'),f('rights.export','允许导出','checkbox'),f('rights.ai','允许用于 AI（功能关闭）','checkbox')],
};
export function getPath(value,key) { return key.split('.').reduce((o,k) => o?.[k],value); }
function setPath(value,key,v) { const parts=key.split('.'); let cursor=value; parts.slice(0,-1).forEach(k => cursor=cursor[k] ||= {});cursor[parts.at(-1)]=v; }
function optionHtml(options,value) { return options.map(([v,t]) => `<option value="${esc(v)}" ${String(value ?? '')===String(v)?'selected':''}>${esc(t)}</option>`).join(''); }
export function referenceOptions(records, selected=[]) {
 const mapped=records.map(x=>[versionId(x),`${x.title} · v${x.version}`]);
 for(const id of selected) if(!mapped.some(x=>x[0]===id)) mapped.unshift([id,`历史引用 ${id}`]);
 return mapped;
}
export function renderField(field, record, context) {
 if(field.type==='section')return `<div class="form-section">${esc(field.title)}</div>`;
 if(field.type==='path')return renderPathEditor(record,context);
 const rawValue=getPath(record,field.key); const value=field.type==='checkbox'&&field.key.startsWith('rights.')?[true,'excerpt','full','allowed'].includes(rawValue):rawValue; const id=`f-${field.key}`; const required=field.required?'required':''; const attrs=`id="${esc(id)}" name="${esc(field.key)}" ${required} ${field.placeholder?`placeholder="${esc(field.placeholder)}"`:''}`;
 if(field.type==='section')return `<div class="form-section">${esc(field.title)}</div>`;
 if(field.type==='path')return renderPathEditor(record,context);
 let control;
 if(field.type==='checkbox')control=`<div class="check-field"><input type="checkbox" ${attrs} ${value?'checked':''}><label for="${esc(id)}">${esc(field.title)}</label></div>`;
 else if(['textarea','lines'].includes(field.type)) control=`<textarea ${attrs} rows="${field.type==='lines'?2:3}">${esc(field.type==='lines'?lines(value):value)}</textarea>`;
 else if(['refs','claims'].includes(field.type)){
   const selected=Array.isArray(value)?value:[];
   const options=field.type==='refs'?referenceOptions(context.evidence,selected):context.claims.map(x=>[x.id,`${x.subject}：${x.statement}`]);
   selected.forEach(id=>{if(!options.some(x=>x[0]===id))options.unshift([id,`历史说法 ${id}`]);});
   control=`<div class="refs">${options.length?options.map(([v,t])=>`<label><input type="checkbox" name="${esc(field.key)}" value="${esc(v)}" ${selected.includes(v)?'checked':''}><span>${esc(t)}</span></label>`).join(''):'<span class="muted small-text">尚无可引用记录。可先保存草稿，再补充材料。</span>'}</div>`;
 }else if(['select','topic','source','evidence','judgment'].includes(field.type)){
   let options=field.options;
   if(field.type==='topic')options=[['','请选择议题'],...context.topics.map(x=>[x.id,x.question])];
   if(field.type==='source')options=[['manual','人工登记'],...context.sources.filter(x=>x.id!=='manual').map(x=>[x.id,x.name])];
   if(field.type==='evidence')options=[['','独立性／原始出处尚未确认'],...context.evidence.filter(x=>x.id!==record.id).map(x=>[x.id,x.title])];
   if(field.type==='judgment')options=[['','请选择判断'],...context.judgments.map(x=>[x.id,`${x.conclusion} · v${x.version}`])];
   control=`<select ${attrs}>${optionHtml(options,value)}</select>`;
 }else control=`<input type="${field.type}" ${attrs} value="${esc(field.type==='date'?String(value||'').slice(0,10):value)}" ${field.min!==undefined?`min="${field.min}"`:''} ${field.step?`step="${field.step}"`:''}>`;
 return `<div class="field ${field.full?'full':''}">${field.type==='checkbox'?'':`<label for="${esc(id)}">${esc(field.title)}${field.required?'<span class="required">*</span>':''}</label>`}${control}${field.hint?`<div class="hint">${esc(field.hint)}</div>`:''}</div>`;
}
export function readForm(form,schema) {
 const data=new FormData(form),result={};
 for(const field of schema){
   if(!field.key||field.type==='path')continue;
   let value=data.get(field.key);
   if(['refs','claims'].includes(field.type)) value=data.getAll(field.key);
   else if(field.type==='checkbox') value=value==='on';
   else if(field.type==='lines') value=['regions','actors','keywords','exclude_keywords','languages','config.countries','config.indicators','config.topic_ids'].includes(field.key)?splitLines(value):String(value||'').split('\n').map(v=>v.trim()).filter(Boolean);
   else if(field.type==='number') value=value===''||value===null?null:Number(value);
   else value=String(value||'').trim()||null;
   setPath(result,field.key,value);
 }
 return result;
}
export function renderPathEditor(record,context){
 const nodes=record.nodes?.length?record.nodes:[{id:'n1',label:''},{id:'n2',label:''}];
 const edges=record.edges?.length?record.edges:[{from:nodes[0].id,to:nodes[1]?.id,status:'unverified',evidence_version_ids:[],note:''}];
 return `<div class="path-editor"><div class="notice info">每一段单独记录关系、证据与验证状态。已观察到的关联不等于因果关系。</div><h3>节点</h3><div id="path-nodes">${nodes.map((n,i)=>renderPathNode(n,i)).join('')}</div><button type="button" data-action="add-node" class="small">＋ 添加节点</button><h3 style="margin-top:20px">关系</h3><div id="path-edges">${edges.map((e,i)=>renderPathEdge(e,i,nodes,context.evidence)).join('')}</div><button type="button" data-action="add-edge" class="small">＋ 添加关系</button></div>`;
}
export function renderPathNode(node,i){return `<div class="repeat-row path-node" data-node-id="${esc(node.id||`n${i+1}`)}"><div class="repeat-row-head"><strong>节点 ${i+1}</strong><button type="button" data-action="remove-row" class="small ghost">移除</button></div><label class="sr-only" for="node-${i}">节点 ${i+1} 名称</label><input id="node-${i}" data-node-label value="${esc(typeof node==='string'?node:node.label||node.title||'')}" required placeholder="如：运输时间变化"></div>`;}
export function renderPathEdge(edge,i,nodes,evidence){return `<div class="repeat-row path-edge-edit"><div class="repeat-row-head"><strong>关系 ${i+1}</strong><button type="button" data-action="remove-row" class="small ghost">移除</button></div><div class="form-grid"><div class="field"><label>起点</label><select data-edge-from>${optionHtml(nodes.map(n=>[n.id,n.label||n.id]),edge.from)}</select></div><div class="field"><label>终点</label><select data-edge-to>${optionHtml(nodes.map(n=>[n.id,n.label||n.id]),edge.to)}</select></div><div class="field full"><label>关系状态</label><select data-edge-status>${optionHtml([['unverified','待验证'],['assumption','有证据支持的分析假设'],['observed','已观察到的关联']],edge.status)}</select></div><div class="field full"><label>证据版本</label><div class="refs">${referenceOptions(evidence,edge.evidence_version_ids||[]).map(([v,t])=>`<label><input type="checkbox" data-edge-ref value="${esc(v)}" ${(edge.evidence_version_ids||[]).includes(v)?'checked':''}>${esc(t)}</label>`).join('')||'<span class="muted small-text">尚无材料</span>'}</div></div><div class="field full"><label>关系说明与口径差异</label><textarea data-edge-note>${esc(edge.note||'')}</textarea></div></div></div>`;}
export function readPath(form){return {nodes:[...form.querySelectorAll('.path-node')].map(n=>({id:n.dataset.nodeId,label:n.querySelector('[data-node-label]').value.trim()})),edges:[...form.querySelectorAll('.path-edge-edit')].map(e=>({from:e.querySelector('[data-edge-from]').value,to:e.querySelector('[data-edge-to]').value,status:e.querySelector('[data-edge-status]').value,evidence_version_ids:[...e.querySelectorAll('[data-edge-ref]:checked')].map(n=>n.value),note:e.querySelector('[data-edge-note]').value.trim(),needs_review:false}))};}
