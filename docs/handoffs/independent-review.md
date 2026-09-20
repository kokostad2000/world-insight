# 独立领域与平台审查

审查人：sources 模块开发者；被审实现为 root/core 编写的平台、knowledge、research、activity。固定基线 `5e91a85`，2026-09-20。本报告只记录该基线的发现；root 随后报告的 `37bd113` 修复尚未在本报告提交时复验。来源选择问题属于本人模块自查，单独标注，不计独立审查。

所有复现使用 `tempfile.TemporaryDirectory` 中真实 SQLite Store、明确 `is_fixture=True` 的夹具与模块公开函数；未改用户数据库、未进行网络请求、未强制 Mac 睡眠。审查没有修改被审模块。

## 已运行的验证

`python3 -m unittest tests.test_core_domain tests.test_activity tests.test_platform -v`：32 项通过，0.138 秒。既有测试之外，下述独立脚本真实复现缺陷；绿色测试不能证明这些分支正确。

复现通用步骤：使用 `Store(temp_path / 'test.sqlite')`；通过 research.handle 创建 topic，通过 knowledge.ingest 创建 evidence；研究判断使用 `status=reviewed, reviewer=fixture, confidence_reason=fixture, review_date=2026-10-01`；调用 `store.drain([research.on_event, activity.on_event])` 至无待消费事件。时间测试仅覆盖 `store.now`，未改操作系统时间。

## 可复现问题

### 1. P1：不同供应商记录被相同短摘录误合并

- 位置：`server/modules/knowledge/__init__.py:173-198`，尤其指纹分支 194-197。对应 FR02/03/09、AC03/11。
- 复现：同一 `source_id=wb`，分别输入 `source_record_id=GDP:AAA:2025` 与 `GDP:BBB:2025`，使用不同国家 URL、标题，摘录均为 `json.dumps({'value':None,'period':'2025','unit':'USD'})` 且允许存储。
- 实际：两次 ingest 返回相同 ID；第二条标题仍是 A 国，channels 混入 A、B 两国。不同来源记录已经被 URL 分支排除，仍在指纹回退合并。
- 最小修复：明确不同供应商记录 ID 不得由指纹回退合并；短摘录不代表完整材料。只有明确取得许可的完整内容才能直接指纹合并，部分摘录只能形成待复核候选。

### 2. P1：简报遗漏反证引用与访问限制传播

- 位置：`server/modules/activity/__init__.py:36-40,120-139`；knowledge 的非实质限制事件在 `:342-345`。对应 FR05/07、AC07/17。
- 复现 A：判断引用 E，生成 brief；执行 `knowledge.correct(E, {expected_version,reason:'fixture',status:'restricted',substantive:False})`，消费 outbox。
- 实际 A：判断为 needs_review，brief 仍为 generated。
- 复现 B：判断支持证据 E、反对证据 O，生成 brief；将 O 实质撤回并消费事件。
- 实际 B：brief.evidence_version_ids 只存 E；判断需要复核，brief 仍为 generated。
- 最小修复：快照纳入支持与反对引用；通过引用或 judgment_id/version 传播 evidence.updated 的 dependency_review 和 research.needs_review，幂等标记，保留历史简报原文。

### 3. P1：时区字符串比较误筛选并越过已读快照

- 位置：knowledge `:412-440` 中 431-433；activity `:100-117` 中 110。对应 AC04/18、PRD8.3。
- 复现 A：事件 `occurred_at=2026-09-20T00:30:00+08:00`、precision instant，按 `since=2026-09-20T00:00:00Z` 查询。
- 实际 A：该事件返回；其 UTC 时间为前一天 16:30，应在范围外。
- 复现 B：change.created_at=`2026-09-20T04:00:00.000000Z`；提交该 id/version 与 snapshot_at=`2026-09-20T08:00:00+08:00`（00:00Z）。
- 实际 B：创建时间晚于快照四小时的记录被标为已读。
- 最小修复：使用统一 aware datetime 比较或规范化 UTC；日/月精度保持原语义，不伪造时刻；检查所有时间过滤和到期逻辑。

### 4. P1：translation 绕过正文存储限制

- 位置：knowledge `:82-113`，仅 excerpt 在 90-91 检查权限。对应 AC17/19。
- 复现：`knowledge.ingest(store, {'title':'夹具','url':'https://example.org/no-store','translation':'禁止保存的第三方内容夹具','rights':{'store':'metadata','display':True,'export':True},'is_fixture':True})`。
- 实际：translation 正文被保存并返回。
- 最小修复：translation 受同样的存储范围约束，验证类型/长度；权限不足不可把内容写进当前记录或历史快照。

### 5. P1：事件更新不进入变化中心

- 位置：activity `:15-17` allowlist；knowledge 事件 PATCH 发布在 `:496`。对应 FR05/07。
- 复现：创建政策事件“政策已宣布夹具”并消费 outbox；PATCH expected_version/title 为“政策已实施夹具”、change_reason 后再次消费。
- 实际：event 已更新，event.updated outbox 已投递；changes 数量仍从 3 到 3，没有更新条目。
- 最小修复：消费 event.updated，保留对象版本、准确时间和核验状态，稳定事件 ID 保证重投幂等。claim/observation 更新也应按产品范围检查，不能把新声称直接当成已核实事实。

### 6. P1：完整性检查漏掉非材料引用

- 位置：`server/platform/store.py:164-186`，只递归检查 evidence_version_ids。对应备份恢复的引用完整性要求；本项仅审平台，未审尚未合入的 M7。
- 复现：`store.create('event', {'title':'破损引用夹具','claim_ids':['missing-claim'],'topic_id':'missing-topic'})` 后调用 `store.integrity()`。
- 实际：`ok=True, reference_errors=[]`。
- 最小修复：注册并检查 topic/claim/judgment+version/alias 等逻辑外键，明确全局、nullable、内置人工来源例外；否则 SQLite 与校验和完好仍可能恢复出断引用图。

### 7. P2：被撤回判断被材料纠错重新激活

- 位置：`server/modules/research/__init__.py:285-298`，294 无条件设置 needs_review。对应 FR06/08。
- 复现：创建 withdrawn 判断引用 E；将 E 实质撤回并消费事件。
- 实际：判断从 withdrawn 变为 needs_review，并重新出现在 review_due。
- 最小修复：生命周期保持 withdrawn；用独立 dependency_review_required/历史原因表达依赖变化。同样规则适用于情景、路径。

### 8. P2：指标修订悄然迁移议题

- 位置：knowledge `:292-309`，身份匹配 297，整体 patch 304。对应 FR09/13。
- 复现：upsert_observation 来源 wb/指标 GDP/国家 AAA/期 2025、value=100、topic A；同身份 value=105、topic B。
- 实际：记录 ID 相同，A 的指标列表变空，B 有一条。相同值的第二议题关联也未被加入。
- 最小修复：保留原 topic_id，并按 evidence 一样维护 topic_ids 并集；纯来源修订不可改变用户研究归属。

### 9. P2：初次阅读基线未用于“自上次阅读”

- 位置：research `:18-30` 只保存 reading_baseline；activity `:57-98` 的 unread 分支 64 把 start 设为 None。对应 AC18。
- 复现：topic.reading_baseline=`2026-09-20T15:30:00Z`；已有全局 source.failed 变化 discovered_at=`2026-08-01T00:00:00Z`；查询该议题 unread。
- 实际：返回基线之前的旧变化。reading_baseline 未参与消费。
- 最小修复：首次 unread 按所关注议题/范围基线筛选，保留历史窗口查询，不伪造阅读记录。

## P0 缺口：保留策略和用户主动删除

PRD11.3（本地 PRD 第 434-435 行）明确：主动删除要有影响预览及备份导出；未引用候选默认保留 90 天、可配置且更严格的来源期限优先。基线中没有 retention/tombstone/purge/删除影响预览实现，领域 DELETE 一律 405。这不是应立即清理用户数据的授权，而是产品能力尚缺。

最小语义方案：

1. 所属模块提供删除影响预览，列出当前和历史引用、受影响对象、保留占位与删除正文范围，绑定对象版本；导出/备份后由明确确认动作执行。
2. 历史被引用记录保留身份、时间、引用与删除原因的无正文占位，不静默级联删除；说明隐藏与物理清除的区别。
3. 自动留存只处理采集器来源、未核验、未人工注释、未引用的候选；手工录入研究记录不作为普通新闻缓存清理。
4. 引用检查包含当前和历史判断/情景/路径/声称/事件/复盘/简报，支持和反对证据均算引用。
5. 以本地首次发现时间计龄；默认 90 天可配置，并采用更短许可期限。不得以旧出版日期把刚发现材料立即清除。
6. 到期不允许继续存储的源内容必须实际清除，包括不可变历史 JSON 中的正文；只隐藏最新 excerpt 不符合权限语义。以专门、可审计的红删机制保留非正文引用元数据。

## M2 自查补充（不计独立审查）

topic.source_ids 未约束调度与 coverage。夹具议题仅选 `['source-fed']` 且关键词 fixture，调用 Scheduler._schedule_due（无网络）后仍产生 GDELT 议题任务、Fed/WDI 全局任务；该议题 coverage 仍列三种源。

修复边界由 root 明确：空数组表示默认启用免费源；非空表示仅所选源，并与 source.config.topic_ids 取交集；调度、排队、执行和议题 coverage 统一约束，显式手动刷新越界返回可解释拒绝。历史检查成功不能伪称新配置范围已经检查完成。

## 范围与未覆盖

已读平台 Store/outbox/HTTP 本地访问及维护边界、knowledge CRUD/去重/指标/纠错/引用、research 历史/导出/纠错传播、activity 变化/阅读/简报。事务中的 outbox 消费与确认、重复事件总体结构正确；未发现跨模块擅自写其他实体的新增问题。

未执行浏览器 E2E、真实 OS 睡眠、七日观察；未审尚未合入的 M7 更新/恢复代码；未把自己实现的来源模块计作独立审查；没有重跑 root 后续修复。本报告不代表项目已完成所有验收。
