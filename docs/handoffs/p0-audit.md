# P0 独立功能审计

审查日期：2026-09-21（Asia/Shanghai）。审查者为 M2 实现者，本轮独立审查对象是其他实现者的 platform、knowledge、research、activity、web 和已合入的 ops。M2 源码和先前 M2 自查不计独立审查成果。

任务起点为 main `bea9f0b`；在来源选择 UI 修复合入后，本 worktree 快进至 **`dd527ab`**。下列行号、失败结果和浏览器行为均以 `dd527ab` 为准。root 已收到发现并表示正在修复，但本报告不把未收到、未复验的新提交标为通过。本轮只提交此报告，未修改被审代码。

## 结论与证据边界

发现 **8 项新增实质问题：3 项 P1、5 项 P2**。P1 是权限或来源链、结论性质失真；P2 是功能入口或过滤、排序失效。与已安排的生命周期、M7 修复和真实 Mac 后续验收分开记录。

- 通读 `docs/PRD.md` 全文、`docs/AGENT_EXECUTION.md`、实施计划、进度、验收矩阵，逐项映射 FR-01—15、AC-01—36。
- 实际使用 Python 3.11、真实 SQLite、Application 公开入口、真实本地 HTTP 与 Edge 页面。浏览器服务只绑定 `127.0.0.1:8873`，禁用调度器。所有材料名称以 `[独立审计夹具]` 标记，测试 URL 使用 `example.com`；未请求其正文。
- 临时隔离目录：`/private/tmp/world-insight-p0-audit-682t4how`；记录 ID 在该目录 `audit-ids.json`。不使用 root 的真实源验收库，也未改用户研究数据。
- 本轮执行 `python3 -m unittest tests.test_audit_regressions tests.test_core_domain tests.test_activity tests.test_platform -v`：**41 项，0.175 秒，OK**。这些绿色测试未覆盖下列失败分支，不是全产品通过证明。
- 未重复请求 GDELT、Fed、World Bank 等上游；未强制操作系统睡眠；未运行七天观察；未把浏览器 DOM/交互检查称为全部视觉布局验收；未重新执行完整 M7 故障矩阵。
- 只读审查允许向本人临时测试应用写入夹具并检查结果；代码和其他人的数据库均不写入。

## 新增问题

### A1 · P1：普通编辑收窄材料权限，不传播依赖重审

对应 FR-03/07、AC-17（并影响依赖简报语义）。位置：`server/modules/knowledge/__init__.py:559` 的 PATCH 分支，尤其 `:581` 发布不带 `dependency_review` 的 `evidence.updated`；`server/modules/research/__init__.py:294` 因此跳过，activity 也不标重审。

复现路径：建立材料 E（rights.store/display/export=true），已审阅判断 J 引用 E@1，生成简报 B；从正常编辑接口 PATCH E，将 display/export 改 false，store 保持 true；消费 outbox。无需改 status，也无需实质更正。

实际结果：

```json
{"case":"normal_patch_rights_restriction","evidence_content_restricted":true,"judgment_status":"reviewed","brief_status":"generated"}
```

材料展示已受限，但判断与简报仍保持已审阅／正常生成。专用 corrections 接口的 restricted 分支测试通过，不能覆盖普通编辑入口。UI 提供 rights 复选框，故这是正常可达路径。

最小修复：统一比较旧、新授权范围；display/store/export 发生影响已保存或已引用内容的收窄时，由 knowledge 处理本域依赖并发布 `dependency_review`，其他所属模块幂等消费。普通字段或格式变更仍不能自动认定事实撤回。同步检查重复人工 ingest 修改 rights 的入口，避免同类绕过。

### A2 · P1：只修改材料备注，也会清空出现渠道元数据

对应 FR-02/03、AC-02/13/19 的出处与历史完整性。位置：`web/app.js:74` 把 channels 对象降为 URL 列表；`:75` 保存时为所有 URL 重建 `{url, source_id:data.source_id}`；knowledge `:67`—`:81` 接受这个完整替换。

实际 Edge 复现：材料 `d3c9359a-b7d4-4f4d-a799-4bd3d13d249e` 有两个 channels。第二渠道为 `source_id=fixture-secondary, source_record_id=fixture-secondary-2, publisher=fixture secondary, title=fixture secondary title, discovered_at=2026-09-20T11:00:00Z`。打开编辑，只增加研究备注，渠道框不动，点击保存。

当前 v2 的两个渠道都变为：

```json
[
 {"source_id":"manual","source_record_id":null,"url":"https://example.com/p0-channel-a","publisher":null,"discovered_at":null,"title":null},
 {"source_id":"manual","source_record_id":null,"url":"https://example.com/p0-channel-b","publisher":null,"discovered_at":null,"title":null}
]
```

页面也从次渠道发布者变成 `manual`。历史 v1 尚在，所以不是所有历史被销毁；但当前来源链被错误改写，后续导出、来源判断和拆分会使用残缺数据。

最小修复：未改渠道时保留原始对象；改 URL 列表时对已存在身份保留 source_id/source_record_id、发布者、原题和发现时间，新渠道才使用明确的新值。同 URL 对应不同来源记录时不能仅以 URL 覆盖。回归必须通过真实备注编辑表单。

### A3 · P1：假设型已审阅判断在首页变化卡丢失缺证据标记

对应 FR-05、AC-22 的“始终显示／首页”要求。位置：research `_payload` 在 `:161` 已发 support_label/evidence_support；activity `:27`—`:34` 创建 change 时丢弃它们以及判断状态；`web/app.js:40` 只检查并不存在的 `c.missing_evidence`。

复现：创建已审阅判断，conclusion 为 `[独立审计夹具] 仅凭假设的已审阅结论`，assumptions 非空，evidence_version_ids 为空；到首页查看新增判断卡。实际 DOM：

```text
新增研究判断
[独立审计夹具] 仅凭假设的已审阅结论
[独立审计夹具] P0边界
事件发生：未知
查看原记录与版本
发现 2026/09/21 09:15
```

卡片没有“缺乏证据支持”，也没有该判断的状态。较下面的议题卡与导出有缺证据标签，不能替代这条独立结论的性质提示。

最小修复：change 固定保存对象事件发生时的 status/evidence_support/support_label/missing_evidence，并渲染。已有 change 需要回填时，取 object_version 对应的不可变判断快照，不能从当前新版本推断过去支持情况。

### A4 · P2：首页情景、影响路径待办错误调用判断接口

对应 FR-06/07、AC-07/21 的可处理性。位置：activity `:100`—`:104` 的 `review_due` 已带 kind；`web/app.js:33` 却统一 `edit('judgments', j)`，另一个“记录复盘”统一进入 `:97` 的 judgment 查询。

复现：创建 needs_review 情景与影响路径，打开首页“研究待办”。临时情景 `72ddbd98-c413-472f-b36c-a730d38dca2f`、路径 `13f82a30-2795-475b-b451-2a12780288ff` 都显示“审阅判断／记录复盘”。真实点击情景的“审阅判断”，页面提示 **记录不存在**，编辑器未打开。

最小修复：按 kind 分派 scenarios、impact-paths、judgments；非判断对象进入其自己的审阅／版本编辑入口，不提交 judgment review。首页“待重审”总数与“到期复查”应按 task_reason 区分，避免两条 needs_review 非判断被计成“待重审 0、到期复查 2”。

### A5 · P2：时间线按 ISO 字符串排序，跨时区顺序错误

对应 FR-04、PRD8.3、AC-04 时间语义。位置：`web/app.js:49` 使用 `String(...).localeCompare(...)`，发布时间的 `.sort()` 也有同类风险；后端时间范围比较已修复，不代表前端排序正确。

复现两个 instant 事件：

| 标题 | 输入 | UTC | 页面显示 |
|---|---|---|---|
| A 较早北京凌晨 | 2026-09-20T00:30:00+08:00 | 09-19 16:30Z | 2026/09/20 00:30 |
| B 较晚 UTC 夜间 | 2026-09-19T18:00:00Z | 09-19 18:00Z | 2026/09/20 02:00 |

真实议题时间线降序却先 A 后 B。最小修复：时刻按真实时间比较；日/月精度单独处理并保留精度，不伪造时分秒。事件和材料发布时间两种模式共用经验证的比较函数。

### A6 · P2：“我的判断”截断 200 条，筛选和统计只覆盖截断结果

对应 FR-08、PRD6.4/10.3；影响 AC-15 的复盘可达性与统计。位置：`web/app.js:63` 固定 GET judgments/reviews `limit=200`，随后在客户端过滤；没有分页，也把 items.length 当总数。

复现：临时库有 **202** 条判断。第一条包含独特词“早期独特判断可检索”，后续再建立 201 条。打开“我的判断”，实际统计“已登记判断 200”，早期记录不在页面，DOM 中无分页控件。前端对旧记录做筛选不会向服务器补取，可能报空。复盘同样只取 200，无法判定数量等统计随截断失真。

此外，PRD6.4 要求的“结论变更”筛选在该页面没有控件或数据过滤；当前仅议题、状态、类型、是否到期。页面也没有判断搜索输入；state.query 并不构成用户可用的检索入口。

最小修复：服务端全库查询过滤、明确分页和真实总数；判断与复盘页各自维护翻页状态；提供结论变更及搜索条件。统计按完整结果集合单独汇总，不能把当前页数量呈现为全库总量。历史引用选择仍固定版本。

### A7 · P2：最近 20 条提醒均已读时，较旧未读提醒无法到达

对应 FR-07、PRD11.4 空状态诚实性；与 AC-18 的“未加载不能变已读”语义相关，但本缺陷没有把旧提醒真正标读。位置：`web/app.js:30` 先取 notifications limit=20，`:33` 后过滤 status；activity `:174` 列表无 status 过滤。

复现：创建 21 条正式更正，因此产生 21 条提醒；把第一页 20 条全部标已读。实际 API 与页面结果：

```json
{"all_total":21,"all_unread":1,"page_total":21,"page_unread":0,"page_length":20}
```

真实 Edge 首页“站内提醒”面板显示“暂无未读提醒”，没有更多／分页入口。remaining unread 仍在数据库，只是正常 UI 无法看到。

最小修复：先按 unread 在服务端过滤再分页，返回 unread_total，提供剩余数量／更多入口。标已读只影响指定提醒，不应清除研究待办。

### A8 · P2：相似候选 API 已有，但候选列表和确认处理没有接到页面

对应 FR-03、PRD7.1 第 3 步、7.2 第 3 步、AC-03 中“建议检查”的产品入口。位置：knowledge `:513`—`:517` 支持 `similar_to`；web 无该请求，也无 candidate_only 的展示和处理。

实际 API 登记两条标题相似、地点日期不同的材料：A=`[独立审计夹具] 某地政策会议 甲国 9月10日`，B=`…乙国 9月12日`，URL 不同。返回不同 ID 正确；GET `/api/evidence?similar_to=A` 返回 B、association_status=candidate_only、total=1。真实打开 A 详情：

```json
{"buttons":["编辑","版本 1","登记更正 / 撤回","拆分误合并"],
 "candidateBShown":false,
 "sections":["原始材料","出处与出现渠道","引用此材料的研究","关联议题","使用范围"]}
```

说明“相似只用于候选检查”的文字以及手工选择原始出处不等于候选列表。此例没有自动误合并；缺的是用户可执行的候选检查、接受／纠正／移除流程。

最小修复：提供按材料上下文取候选的列表，并列原题、日期、出处；明确显示仅建议检查；用户可以登记已确认关系或忽略候选，决定应保存且可撤销。不能把“确认标题相似”直接当成事件合并或独立证实。

## FR 全范围映射

“检查”表示源码／领域／浏览器相应层次，不意味着该 FR 所有 AC 已验收。

| FR | 本轮检查与结论 |
|---|---|
| FR-01 议题 | 公开 CRUD、状态、模板、筛选、source_ids/country_codes 表单；选择 UI 已在 dd527ab 存在，真实编辑页可见 Fed 选中，不再报告缺功能；country 关联整体结果由 root 后续复验。 |
| FR-02 采集与手工 | 手工材料 CRUD、时间、权限、原文与译文；A1/A2。M2 自有实现、真实源请求不计本轮独立验证。 |
| FR-03 去重与引用 | 41 项中精确身份/十转载/历史/拆分/更正测试通过；A1/A2/A8，不能仅据测试判定完整。 |
| FR-04 事件时间线 | 事件/说法并存与已实现状态分离；真实混合时区浏览器排序 A5。 |
| FR-05 首页 | 真首页、变化分页、引用入口、快照读取；A3，且 A4/A7 影响待办提醒。 |
| FR-06 判断情景路径 | 创建、版本、引用、无反证、冲突的领域回归通过；实际首页跨对象操作 A4。 |
| FR-07 关注提醒纠错 | outbox 原子与幂等、已读不清任务；A1/A4/A7。没有新增外部消息能力。 |
| FR-08 复盘导出 | 历史证据、无法判定、合法内容导出测试通过；A6 全库过滤/分页/结论变更遗漏。 |
| FR-09 地图国家 | 国家精度拒绝假坐标、年度指标保留 period 的领域回归通过；国家背景关联由 root 已安排，非本轮新增问题。 |
| FR-10 来源零付费 | 页面配置/未接入语义定位；M2 已交付及先前测试不冒充独立验收；本轮不进行付费、模型或上游请求。 |
| FR-11 启停 | 浏览器审计实际使用独立 Mac 进程；旧报告的 pending 启动修复待集成。Finder 双击整体验收由 root 执行。 |
| FR-12 配置检查 | 检查脚本、脱敏与本地/网络分离位置已审；不重复完整权限/端口/缺依赖故障矩阵。 |
| FR-13 持久化 | Store 不可变版本/重启/迁移回归通过；A2 当前渠道丢失虽历史尚在仍不符合数据保留。生命周期独立任务见下。 |
| FR-14 备份恢复 | 既有 M7 独立报告及 root 已安排修复；恢复后浏览器编辑的实际 Mac 验收待 root，不以包可生成替代。 |
| FR-15 更新回退 | 旧报告附件指纹缺陷已派修；没有再次执行更新/回退；本轮不改共享代码或强制清理工作树。 |

## AC-01—36 审计定位

此表用于给总验收负责人指出覆盖与失败分支，不覆盖 `docs/ACCEPTANCE.md` 的正式结果。领域回归通过与真实 Mac／上游／长时验收严格分开。

| AC | 本轮结论／证据层次 |
|---|---|
| 01 | 无 AI/付费的 Application 与浏览器资料/判断闭环可用；41 项含 closed_loop/export；尚不能据此宣称所有 UI 闭环完成。 |
| 02 | ten_reports_share_one_identified_source_chain 回归通过；A2 普通编辑会破坏当前渠道元数据。 |
| 03 | similar_titles_do_not_merge、split 回归通过；真实候选返回正确，但 A8 无处理入口。 |
| 04 | timezone_event_filter 回归通过、旧报道不推断事件时刻；A5 浏览器排序失败。 |
| 05 | claims 独立状态、conflicting_claims 回归通过；当事方声明不会由领域代码自动提升为事件实施。 |
| 06 | conflicting_claims_stay_separate 回归通过；不合成未确认伤亡单值。 |
| 07 | correction_propagates_idempotently、withdrawn 保持历史回归通过；A4 待办入口失败，A1 同族授权变更另见 AC17。 |
| 08 | format_change_preserves_research_review_state 与 no_substantive_confirmation 回归通过；不声称持续监测未接全文。 |
| 09 | sources 自有既有测试/先前源报告；本轮无独立新网络故障演练，不新增通过结论。 |
| 10 | sources 自有并发预算测试/先前结果；本轮未重新执行，不启用付费回退。 |
| 11 | annual_metrics_preserve_period_and_unknown、distinct_observation_identity 回归通过；不重新请求 WDI。 |
| 12 | country_position_cannot_claim_exact_coordinates 回归通过；真实国家背景/地图联动由 root 继续验收。 |
| 13 | closed_loop_persist_revision_conflict_and_export、固定引用与历史回归通过；A2 当前渠道编辑失真单列。 |
| 14 | reviewed_scenario_can_truthfully_lack_opposition 回归通过，无编造反证门槛。 |
| 15 | indeterminate_review 独立统计领域回归通过；A6 页面截断后的全库数量错误。 |
| 16 | Store 乐观冲突领域回归通过；之前 web 双窗口记录存在，本轮未重做双窗口。 |
| 17 | 专用 corrections restricted 与 history 显示限制回归通过；普通权限 PATCH 的 A1 失败。 |
| 18 | 3 条 activity 已读/更新快照回归及 offset_snapshot 通过；A7 是旧未读提醒不可达而非被标读；来源初始 baseline 上一批已修，本轮不重写。 |
| 19 | 导出权限/secret 过滤领域回归通过；生命周期和 M7 的来源期限备份净化待集成；恢复后浏览器验证本轮未做。 |
| 20 | bootstrap/预留接口与 UI 未接入文案定位；本轮不调用航空船舶或付费 API。 |
| 21 | 路径保存、纠错与幂等领域路径已审；A4 首页待重审路径不可编辑；实际重开整体验收由 root。 |
| 22 | assumption_judgment_mark_survives_review_and_export 与 brief 单测通过；真实首页变化卡 A3 失败。 |
| 23 | sources 自有部分覆盖既有测试；本轮不重复源网络或把其算成独立新通过。 |
| 24 | 隔离服务在当前 Mac 可运行不是全新目录/Finder 准备验收；root 已安排。 |
| 25 | ops 先前独立审查已定位检查范围；本轮未重新执行完整缺依赖/端口/目录故障矩阵。 |
| 26 | 本轮独立服务使用 8873；中文/空格路径、双击及重复启动完整验收由 root，不因已有服务而标通过。 |
| 27 | 代码本地/网络探测分离、可选能力禁用已定位；既有源边界记录，不重复联网。 |
| 28 | Store 重启/版本/原子迁移回归通过；跨程序目录、异常进程恢复整体验收由 root。 |
| 29 | M7 一致性快照实现及旧报告已审；本轮未重跑磁盘不足/中断，不能只凭实现标通过。 |
| 30 | 待 root 真实“备份→空实例→浏览器读取继续编辑”；非本轮已完成。 |
| 31 | 旧独立报告 pending 启动恢复缺陷已派修，待新提交独立复验；不重复记新问题。 |
| 32 | 工作树保护实现在已审 M7 中；本轮仅合并已有提交和写报告，未进行更新演练。 |
| 33 | M7 成对恢复已有故障测试与旧审计；pending 竞争仍待修复复验，不能覆盖成整体通过。 |
| 34 | 附件单独新写入未进 rollback fingerprint 的旧问题已派修；本轮不重复计数。 |
| 35 | `.gitignore`/独立目录/离线本地架构已有；当前没有 GitHub push，不重复网络失败更新演练。 |
| 36 | sources 自有模拟时钟/补采缺口测试不等于真实 OS 睡眠；不强制睡眠用户 Mac，真实试验仍待安排。 |

## 已知并行工作，不重复计入 8 项新增问题

1. **PRD11.3 生命周期**：默认 90 天未引用采集候选、较短来源内容期限、人工研究保留、主动删除影响预览与备份导出、无正文引用占位，均已另派任务。`dd527ab` 已有 provenance、redaction 与 lifecycle_change 基础，并不等于完整入口已交付。尤其历史引用保护与备份正文净化必须在集成后重验。
2. **M7 两项旧缺陷**：附件独立修改未被 rollback fingerprint 检出；runtime.pending 期间 restore 可与尚在初始化的真实服务竞争。原始方法、实际输出与临时暂停注入边界详见 `docs/handoffs/independent-review.md` 的 M7 部分；修复正在 ops worktree，不在本报告基线。
3. **来源选择 UI**：早先静态缺口被 `1a752e6` 修复并进入 dd527ab。真实议题编辑已看到 source_ids 复选框，既有 Fed 选择保持；撤销“尚无入口”判断。未把看到控件等同于完整采集结果验收。
4. **国家背景关联**：country_codes UI 已存在；root 正进行全局 WDI 到议题背景的联动验证，当前不重复当新发现。
5. **Mac GUI／真实源／七天观察**：root 持续执行；真实 Fed/WDI 登记与 GDELT 429 边界沿用源报告，本轮没替代。性能报告中的 API P95 也不等同浏览器首内容 P95。七天、五个真实议题、人工质量抽查和十分钟效率均不得用本轮夹具抵扣。
6. **交付文件**：README、锁定的零第三方 Python 运行依赖、脚本、配置模板、Git 排除、变更与故障文档已定位。验收矩阵尚待总负责人按实际证据更新；这里只报告功能问题，不把缺截图或矩阵旧状态本身列成缺陷。

## 修复后的最小复验清单

- A1：正常 PATCH 的权限收窄，同时检查 claim/event/judgment/scenario/path/brief；重复消费只产生一次依赖处理；旧引用身份保留。补重复 ingest 权限变更入口。
- A2：真实 UI 只改 notes，逐字段比较所有原 channels；再新增／删除一个渠道，其他渠道保持；同 URL 不同来源记录单独覆盖。
- A3：假设型 reviewed 判断在首页新增和修订卡均有标记；判断后来获得证据后，旧卡仍按原版本显示；导出标记保留。
- A4：情景和路径待办都能打开对应编辑器；完成审阅后任务状态正确；不会生成假 judgment review。
- A5：混合 Z/+08:00 事件与引用材料发布时间都按真实顺序；月/日/未知值仍显示原精度。
- A6：至少 202 条判断及超过 200 条复盘；能搜到最早记录，分页可达，筛选总数和无法判定数量正确；结论变更条件实际可用。
- A7：21 条提醒先标读较新 20 条，旧 unread 仍可见或可明确翻页；不会误称暂无未读，也不清除研究待办。
- A8：候选从真实页面可见；不同日期地点仍独立；接受、纠正、忽略决定可回看／撤销；不凭标题相似自动合并事件。

本报告的结论是需要继续修复和复验，不能据 41 项通过报告 P0 全部完成。
