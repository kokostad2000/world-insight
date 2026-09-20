"""Changes, exact-version read state, local reminders and evidence-bound briefs."""
import datetime as dt
from server.platform.errors import ApiError


def _get(store, kind, record_id):
    try: return store.get(kind,record_id)
    except ApiError as exc:
        if exc.status==404:return None
        raise


def on_event(store,event):
    payload=event['payload']; event_type=event['type']
    if event_type not in {'evidence.created','evidence.updated','evidence.corrected','event.created','event.updated','claim.created','claim.updated','observation.updated',
                          'judgment.created','judgment.revised','research.needs_review','source.failed','source.recovered','record.deleted','record.restored'}:
        return
    record_id='change-'+event['id']
    if _get(store,'change',record_id):return
    needs_review=event_type in ('evidence.corrected','research.needs_review','record.deleted') or bool(payload.get('dependency_review'))
    titles={'evidence.created':'新增材料，待核查','evidence.updated':'材料字段变化，尚未确认实质更正',
            'evidence.corrected':'材料已确认更正或撤回','event.created':'新增事件记录','claim.created':'新增主体说法',
            'judgment.created':'新增研究判断','judgment.revised':'判断已修订','research.needs_review':'相关研究需要重新审阅',
            'source.failed':'来源检查失败，覆盖存在缺口','source.recovered':'来源恢复可用'}
    titles.update({'event.updated':'事件或政策状态更新','claim.updated':'主体说法更新','observation.updated':'指标修订，观测期保持不变'})
    titles.update({'record.deleted':'记录已移入回收站，引用保留待检查','record.restored':'记录已恢复，原待复查状态保留'})
    if event_type=='evidence.updated' and needs_review:titles[event_type]='材料访问或授权变化，相关研究待检查'
    topics=payload.get('topic_ids') or [payload.get('topic_id')]
    store.create('change',{'event_id':event['id'],'type':event_type,'aggregate_id':event['aggregate_id'],
                          'topic_id':payload.get('topic_id') or (topics[0] if topics else None),'topic_ids':topics,
                          'title':titles[event_type],'detail':payload.get('title') or payload.get('reason') or '',
                          'reason':payload.get('reason'),'discovered_at':event['created_at'],
                          'occurred_at':payload.get('occurred_at'),'priority':0 if needs_review else (1 if event_type=='source.failed' else 2),
                          'needs_review':needs_review,'evidence_version_ids':payload.get('evidence_version_ids',[]),
                          'object_version':payload.get('version'),'unverified':event_type in ('evidence.created','claim.created','event.created')},record_id)
    if needs_review or event_type=='source.failed':
        store.create('notification',{'event_id':event['id'],'topic_id':payload.get('topic_id'),
                                    'reason':titles[event_type],'status':'unread','related_id':event['aggregate_id']},'notification-'+event['id'])
    if needs_review:
        evidence_id=payload.get('evidence_id') or event['aggregate_id']
        for brief in store.all('brief'):
            affected=any(ref.split('@')[0]==evidence_id for ref in brief.get('evidence_version_ids',[]))
            if event_type=='research.needs_review' and event['aggregate_id'] in brief.get('judgment_ids',[]):affected=True
            if event_type=='record.deleted' and payload.get('object_kind')=='judgment' and event['aggregate_id'] in brief.get('judgment_ids',[]):affected=True
            if event_type=='record.deleted' and payload.get('object_kind')=='topic' and event['aggregate_id']==brief.get('topic_id'):affected=True
            if affected and event['id'] not in brief.get('review_event_ids',[]):
                store.update('brief',brief['id'],{'status':'needs_review','review_reason':payload.get('reason') or '引用材料发生更正或访问限制',
                                                'review_event_ids':brief.get('review_event_ids',[])+[event['id']]},brief['version'])


def _date(value):
    if not value:return None
    try:
        parsed=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)
    except (ValueError,TypeError):raise ApiError(400,'invalid_time','时间筛选格式无效')


def _coverage(store,topic_id=None):
    from server.modules import sources
    if hasattr(sources,'coverage'):return sources.coverage(store,topic_id=topic_id)
    return {'coverage_status':'not_configured','sources':[],'message':'尚未配置自动来源，人工资料可用'}


def dashboard(store,query):
    snapshot=store.now(); end=_date(snapshot); window=query.get('window','24h')
    if window not in ('unread','24h','7d','custom'):raise ApiError(400,'invalid_window','阅读窗口无效')
    start=end-dt.timedelta(days=7 if window=='7d' else 1)
    if window=='custom':
        start=_date(query.get('since'));end=_date(query.get('until')) or end
        if start and start>end:raise ApiError(400,'invalid_range','开始时间不可晚于结束时间')
    if window=='unread':start=None
    topics=store.all('topic'); followed={t['id'] for t in topics if t.get('followed',True) and t.get('status','active')=='active'}
    baselines={t['id']:_date(t.get('reading_baseline')) for t in topics}
    topic_id=query.get('topic_id') or None
    states={(s['change_id'],s['change_version']) for s in store.all('read_state')}
    items=[]
    for change in store.all('change',topic_id=topic_id):
        associated={t for t in change.get('topic_ids',[]) if t}
        if change.get('topic_id'):associated.add(change['topic_id'])
        if not topic_id and associated and not associated.intersection(followed):continue
        discovered=_date(change.get('discovered_at') or change['created_at'])
        if start and discovered<start:continue
        if end and discovered>end:continue
        read=(change['id'],change['version']) in states
        # A baseline defines the initial unread window; it is not a fabricated read action.
        scoped_topics={topic_id} if topic_id else (associated.intersection(followed) if associated else followed)
        before_baseline=bool(scoped_topics) and all(baselines.get(t) and discovered<baselines[t] for t in scoped_topics)
        # A newly revised change must become visible even if its original discovery predates the baseline.
        if before_baseline and change['version']>1:
            before_baseline=all(baselines.get(t) and _date(change['updated_at'])<baselines[t] for t in scoped_topics)
        if window=='unread' and before_baseline:continue
        if window=='unread' and read:continue
        items.append({**change,'read':read,'before_reading_baseline':before_baseline})
    items.sort(key=lambda c:c['discovered_at'],reverse=True)
    try:limit=min(200,max(1,int(query.get('limit',20))));offset=max(0,int(query.get('offset',0)))
    except (ValueError,TypeError):raise ApiError(400,'invalid_pagination','分页参数必须为整数')
    visible=items[offset:offset+limit]
    due=[];today=store.now()[:10]
    for kind in ('judgment','scenario','impact_path'):
        for record in store.all(kind,topic_id=topic_id):
            if record.get('status')=='needs_review' or (record.get('review_date') and record['review_date'][:10]<=today and record.get('status')!='withdrawn'):
                due.append({**record,'kind':kind,'task_reason':'待重审' if record.get('status')=='needs_review' else '已到复查日期'})
    coverage=_coverage(store,topic_id)
    coverage_status=coverage.get('coverage_status','not_configured')
    summary='所选范围未发现新增记录' if not items else f'所选范围有 {len(items)} 条变化'
    if coverage_status=='unavailable':summary='来源检查失败，无法判断是否有新变化；已有研究仍可阅读'
    elif coverage_status=='partial':summary+='；部分来源未完成检查，覆盖存在缺口'
    elif coverage_status=='not_configured':summary+='；自动来源尚未配置，不代表现实没有变化'
    return {'items':visible,'changes':visible,'total':len(items),'offset':offset,'limit':limit,'snapshot_at':snapshot,
            'coverage':coverage,'coverage_status':coverage_status,'topics':topics,'review_due':due,'summary':summary,
            'first_run':not bool(topics),'window':window,'priority_rule':'证据更正、到期复查优先处理；关注规则其次；新闻量不自动升级风险',
            'empty_reason':'no_matches' if not items and coverage_status=='complete' else None,'data_status':'fresh'}


def mark_read(store,body):
    snapshot=body.get('snapshot_at');_date(snapshot)
    if not snapshot or _date(snapshot)>_date(store.now()):raise ApiError(400,'invalid_snapshot','需提交页面加载时的快照上界')
    items=body.get('items',[])
    if not isinstance(items,list) or len(items)>200:raise ApiError(400,'invalid_items','单次只能标记最多200个已展示版本')
    marked=[];skipped=[]
    with store.transaction():
        for item in items:
            if not isinstance(item,dict):raise ApiError(400,'invalid_item','已读项目需包含ID与版本')
            current=_get(store,'change',item.get('id',''))
            if not current or current['version']!=item.get('version') or _date(current['updated_at'])>_date(snapshot) or _date(current['created_at'])>_date(snapshot):
                skipped.append(item);continue
            record_id=current['id']+'@'+str(current['version'])
            if not _get(store,'read_state',record_id):
                store.create('read_state',{'change_id':current['id'],'change_version':current['version'],'snapshot_at':snapshot,
                                          'topic_id':current.get('topic_id'),'read_at':store.now()},record_id)
            marked.append(item)
    return {'marked':marked,'skipped':skipped,'message':'仅标记已展示的当前版本；复查与核查待办保持原状态'}


def make_brief(store,body):
    topic_id=body.get('topic_id');topic=store.get('topic',topic_id)
    judgments=store.all('judgment',topic_id);changes=store.all('change',topic_id)[:20]
    citations=[];sections=[f'# {topic.get("question",topic.get("title","议题"))}',f'生成于 {store.now()}','模板简报；用户审阅不代表事实得到证明。']
    for judgment in judgments:
        refs=judgment.get('evidence_version_ids',[])
        citations.extend(refs + judgment.get('opposing_evidence_version_ids',[]))
        missing=judgment.get('missing_evidence') or not refs
        sections.append(f'\n## 判断 v{judgment["version"]} · {judgment.get("status","draft")}\n{judgment.get("conclusion","")}')
        if missing:sections.append('假设型暂定判断／缺乏证据支持')
        sections.append('假设：'+'；'.join(judgment.get('assumptions',[])))
        sections.append('证据版本：'+(', '.join(refs) or '无；未知项仍需研究'))
    if not judgments:sections.append('尚未形成判断。')
    sections.append('\n## 最新变化')
    sections.extend(f'- {c["title"]} · 发现 {c["discovered_at"]} · 发生 {c.get("occurred_at") or "未知"}' for c in changes)
    needs_review=any(j.get('status')=='needs_review' for j in judgments)
    return store.create('brief',{'topic_id':topic_id,'content':'\n'.join(sections),'evidence_version_ids':list(dict.fromkeys(citations)),
                                 'judgment_ids':[j['id'] for j in judgments],'judgment_versions':[{ 'id':j['id'],'version':j['version']} for j in judgments],
                                 'status':'needs_review' if needs_review else 'generated','generated_at':store.now(),
                                 'missing_evidence':any(not j.get('evidence_version_ids') for j in judgments)})


def lifecycle_change(store,kind,record_id,expected_version,deleted,reason):
    if kind!='brief' or not isinstance(reason,str) or not reason.strip():
        raise ApiError(400,'invalid_deletion','只能通过此入口处理简报，且需说明原因')
    return store.update(kind,record_id,{'deleted':bool(deleted),'deleted_at':store.now() if deleted else None,
        'deleted_reason':reason,'restored_at':None if deleted else store.now()},expected_version)


def handle(store,method,segments,body,query):
    if not segments:return None
    name=segments[0]
    if name=='dashboard' and len(segments)==1 and method=='GET':return dashboard(store,query)
    if segments==['changes','read'] and method=='POST':return mark_read(store,body)
    kinds={'changes':'change','notifications':'notification','briefs':'brief'}
    if name not in kinds:return None
    kind=kinds[name]
    if len(segments)==1:
        if method=='GET':return store.list(kind,topic_id=query.get('topic_id') or None,limit=query.get('limit',20),offset=query.get('offset',0))
        if method=='POST' and name=='briefs':return make_brief(store,body)
    if len(segments)==2:
        if method=='GET':return store.get(kind,segments[1])
        if method=='PATCH' and name=='notifications':
            if body.get('status') not in ('read','unread'):raise ApiError(400,'invalid_status','提醒状态无效')
            return store.update(kind,segments[1],{'status':body['status']},body.get('expected_version'))
    if len(segments)==3 and segments[2]=='history' and method=='GET':return {'items':store.history(kind,segments[1])}
    raise ApiError(405,'method_not_allowed','该变化或简报操作不受支持')
