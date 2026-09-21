# AC-01—AC-36 验收证据索引（独立复核）

审查日期：2026-09-21。审查者：web/lifecycle 子任务。只新增本文件，不修改 `ACCEPTANCE.md` 的状态、不修改实现、不启动服务、不重跑测试。逐项比对 PRD、实施计划、当前进度、实际测试代码、原始运行日志和交接中的浏览器记录；“有实现”“测试名像某场景”都不单独作为通过依据。

审查快照：子任务 `4af5756`；root 主线初查 `5e321fc`，结束复查到 `b88a8b6`（含权限策略、相似材料/生命周期接线及 WDI 范围修复）；只读 root 编写中的新增证据文件。原始 146 项全量日志对应较早的 `ad5e32f` 基线附近，不能宣称刚合入的所有代码都跑过该轮全量测试。本文件是证据判读和补验清单，正式验收矩阵仍由 root 更新。

“可据证据通过”仅指对应 AC 已有相符的行为证据；“部分，暂不可完整认定”指至少一个明确预期尚缺证明，并不等于已发现产品失败。模拟时间、注入失败、隔离样本、真实网络、实际 Mac 进程、真实浏览器分开记。各 AC 的工程验证可以用明确标记的样本；PRD 12.1 的真实资料和七天门槛不能用它替代。

## 可复查证据与时间边界

| 标记 | 证据、已运行结果与边界 |
|---|---|
| T | [全量原始日志](../evidence/integration-audit-round-two.txt)：`python3 -m unittest discover -s tests -v`，146 项、31.969 秒、OK（149/151 行）。下文 `T:行号` 对应精确测试结果。包含实际 SQLite、HTTP 和 Mac 子进程，也包含 mock/时钟注入，须按用例区分。 |
| F | [后续针对回归](../evidence/audit-round-two-focused.txt)：11 项、0.386 秒、OK（14/16 行）。以原始日志为准，旧进度文档的 0.330 秒不覆盖这个结果。 |
| U | [新界面联合回归](../evidence/ui-companion-tests.txt)：13 项、0.595 秒、OK；4 相似材料、4 生命周期、5 既有前端。审查时是 root 未提交文件，合入索引时需一起保存。 |
| W | [web 交接](web.md)：真实浏览器 8872、独立 SQLite `/private/tmp/world-insight-web-qa`，均为隔离样本。两真实标签页 409、路径/情景/撤回传播、206 条材料搜索、正常重启实操。不是生产资料观察。 |
| B | [root 浏览器记录](../evidence/browser-integration.md)：8766 真实 RSS 元数据议题；正常重启、版本修订；8876 从真实库备份恢复后浏览器判断 v2→v3、USA 年度指标。官方元数据登记不等于读过全文或证实实施效果。 |
| B2 | [root 第二轮正式页面记录](../evidence/browser-integration-round-two.md)：8876 正常更新后判断 v4，真实迁移失败成对回退后浏览器保存 v5，固定材料 v2；真实 JSON 下载。8878 正式页面回收/恢复、情景待办、204 判断搜索及相似关系往返；样本与真实来源副本明确分开。审查结束时文件已写入，仍未提交。 |
| L | [生命周期及实际导出记录](lifecycle.md)：Edge 8877，临时宿主验证回收站及保留操作；其后标准 app 验证 JSON/Markdown 真实文件下载并逐项比对后端。固定证据 v1，当前材料 v3；文件大小、时间、SHA256 均有记录。下载事件超时与实际落盘并存，不能因此声称导出失败，也未证明工具内部原因。 |
| S | [真实免费源记录](../evidence/source-research.md)：Fed RSS HTTP 200/20 条，WDI HTTP 200/10 条 CHN 年度观测；真实 app 后续合计 20 RSS +20 WDI 的记录见 B/PROGRESS。GDELT 429/无效响应；[9 月 21 日重试](../evidence/gdelt-real-20260921.json) curl 28 超时 8.115 秒，仍无有效 GDELT 数据。后者审查时未提交。 |
| O | [运维交接](ops.md)、[环境](../evidence/ops-environment.json)、[19 项日志](../evidence/ops-strict-integrity-tests.txt)、[29 项日志](../evidence/ops-retention-review-tests.txt)：实际 Mac 15.6.1/arm64、Python 3.11.4、SQLite 3.42.0，隔离代码/数据库/端口。测试通过不等于 Finder 或浏览器已操作。最新 T 包含进一步运维回归。 |
| C | [新目录启动与空目录恢复](../evidence/mac-clean-restore.json)：实际中文/空格路径，本地 clone，初始化/重复启动/停止/恢复；`--no-browser --no-scheduler`，因此不证明自动打开浏览器或真实调度恢复。 |
| N | [正常更新](../evidence/mac-normal-update.json)：实际 dd527ab→ad5e32f、schema 1→1，418 个版本、完整性 OK，使用本地 Git fetch，`network_used:false`。审查时未提交；不证明 GitHub 断网分支或新的第三方依赖升级。 |
| R | [实际迁移失败](../evidence/mac-migration-failure.json)：目标 6434834 迁移失败，记录 rolled_back，恢复 ad5e32f/schema 1，临时表不存在，旧判断 v4 和固定材料 v2 可读，maintenance 清除。产品退出 1；外围 harness 曾误期待 2，文件已明确此差异，不把 harness 失败隐去。审查时未提交。 |
| H | [权限策略交接](rights.md)：22 个新增纯策略/SQLite 测试；联合 54 项、1.397 秒、退出 0 是交接记录，尚未在本索引所读证据中见同轮完整原始 stdout。root 2abb081 仅合入纯 helper，读取/普通导出路由截至审查仍待 core 接线；不能从合并标题推断集成已完成。不能据纯 helper 通过推导全部 HTTP/搜索/浏览器不泄漏。 |
| Y | [相似材料交接](similarity.md)：4 项自动测试 + 实际 Edge 8873 临时宿主。不同国家日期的两条样本经忽略、恢复提示、关联、移除、历史恢复后仍 2 材料/0 事件，版本 1—4，notes/channels 保留。root 已合模块；正式 app 页面点击追加证据现见 B2。 |

第二轮增量以 B2 已写入文件为准，取代编写期间的现场消息。其正式相似关系操作后材料 v6、仍 2 材料/0 事件/204 判断；正常更新后 v4、回退后 v5 都已实际保存。root 真实议题 JSON 276673 B、SHA256 `f22b2405ffd7084c0112683d12f8ed058403e01da1a64af01e62329d9e8dda8b` 已解析核对。新文件尚未提交属于证据保全待办，不能把 Git 状态误作行为未执行。

## 逐项 AC

### AC-01 无模型、无收费密钥的研究闭环

- 已运行测试：`test_core_domain.CoreDomainTests.test_closed_loop_persist_revision_conflict_and_export`（T:21）；`test_integration.ResearchIntegrationTests.test_assumption_review_indeterminate_result_and_reading_remain_honest`（T:47）；`test_sources.SourceTests.test_seed_is_local_idempotent_preserves_config_and_disables_paid`（T:132）。
- 真实操作：W 已创建议题→材料→说法/事件→人工判断→修订→复盘；L 从标准 app 下载 JSON/Markdown 并比对；B 有真实官方元数据建档及重启编辑。环境未配置模型或付费调用。
- 尚缺/适用边界：全流程证据分布在几个明确隔离实例，不是一个真实议题连续七天；这不影响本 AC 功能闭环，但不能据此通过 PRD 12.1。
- 能否通过：**可据现有组合证据通过功能闭环**。

### AC-02 十篇转载与来源独立性

- 已运行测试：`test_core_domain.CoreDomainTests.test_ten_reports_share_one_identified_source_chain`（T:40）；`test_core_domain.CoreDomainTests.test_transitive_reposts_share_one_origin_chain`（T:41）；`test_core_domain.CoreDomainTests.test_precise_dedup_keeps_channels_and_multi_topic_unlink`（T:31）。
- 真实操作：自动测试确有 10 记录/1 已识别来源链；W 有转载编辑功能实操，Y 验证两记录关联仍独立保留。
- 尚缺/适用边界：未见正式页面同时展示 10 报道、1 链及另一条无法判定来源链的记录；需核对独立性未知单列及文案不把篇数当证实方数。
- 能否通过：**部分，暂不可完整认定**。

### AC-03 相似标题不自动合并、关系可恢复

- 已运行测试：`test_core_domain.CoreDomainTests.test_similar_titles_do_not_merge_and_cannot_infer_event_time`（T:38）；`test_core_domain.CoreDomainTests.test_split_preserves_history_and_marks_dependents`（T:39）；`tests.test_similarity.SimilarityTests.test_associate_clear_restore_keeps_history_channels_and_fixed_citation`（U:1）；`tests.test_similarity.SimilarityTests.test_candidate_read_does_not_merge_or_mutate`（U:2）；`tests.test_similarity.SimilarityTests.test_cycle_and_stale_version_cannot_overwrite_relationship`（U:3）；`tests.test_similarity.SimilarityTests.test_executable_frontend_behaviors`（U:4）。
- 真实操作：Y 的真实 Edge 临时宿主走完不同日期/国家候选、忽略、关联、移除、历史恢复；2 材料/0 事件，未自动合并。B2 又在正式 8878 材料详情完成关联 v4→移除 v5→恢复 v6，仍两独立材料/0 事件，笔记保留。
- 尚缺/适用边界：原 A8 缺入口已修复且正式页面实操完成；Y 的不同日期/国家样本与 B2 的集成入口结果共同覆盖本场景。相似建议不等于内容或来源独立性被确认。
- 能否通过：**可据模块与正式页面组合证据通过**。

### AC-04 新发现不冒充今天发生

- 已运行测试：`test_sources.SourceTests.test_rss_dates_conditional_requests_and_304_keep_cache_count`（T:127）；`test_sources.SourceTests.test_gdelt_seen_time_not_publication_and_200_html_is_failure`（T:118）；`test_core_domain.CoreDomainTests.test_similar_titles_do_not_merge_and_cannot_infer_event_time`（T:38）；`test_audit_regressions.AuditRegressions.test_timezone_event_filter_uses_actual_instant`（T:11）。
- 真实操作：B/W 页面已经分列旧发布日期与今日采集；S 有真实 RSS 旧发布时间。
- 尚缺/适用边界：需用有明确上周发生时间的事件重新采集一次，在正式页面“今天发生”筛选确认排除，再核对新发现列表仍显示；未知发生时间测试和时区 API 测试不能替代这整个页面场景。
- 能否通过：**部分，暂不可完整认定**。

### AC-05 单方宣布不等于停火实施

- 已运行测试：`test_core_domain.CoreDomainTests.test_closed_loop_persist_revision_conflict_and_export`（T:21）；`test_integration.ResearchIntegrationTests.test_five_topic_research_loop_and_correction_reaches_all_dependents`（T:48）。
- 真实操作：B 正式页面保存“只确认 FOMC 发布、不据此认定实施”的说法，显示说法不等于已证实事实；W 有待核查说法/事件。
- 尚缺/适用边界：通用说法边界已证实，但未见精确“甲方宣布停火”样本的正式页面/导出检查；补一条明确样本，核对未自动生成“停火已实施”结论。
- 能否通过：**通用机制通过；精确验收场景待补**。

### AC-06 5 与 12 的冲突数字

- 已运行测试：`test_core_domain.CoreDomainTests.test_conflicting_claims_stay_separate`（T:22）。
- 真实操作：SQLite 用例保留两说法，事件含两个 claim ID，没有合成 casualties 单值。未见此数字场景的浏览器记录。
- 尚缺/适用边界：现有用例两说法引用同一材料，未覆盖题设的两个来源；需两独立材料/来源，正式事件页面并列 5/12、出处及分歧，导出不产生任意总数。
- 能否通过：**部分，暂不可完整认定**。

### AC-07 正式撤回传播且保留历史

- 已运行测试：`test_core_domain.CoreDomainTests.test_correction_propagates_idempotently_and_preserves_history`（T:23）；`test_integration.ResearchIntegrationTests.test_five_topic_research_loop_and_correction_reaches_all_dependents`（T:48）；`test_audit_regressions.AuditRegressions.test_opposing_evidence_and_access_restriction_mark_brief`（T:8）；`test_audit_regressions.AuditRegressions.test_withdrawn_judgment_stays_withdrawn_after_correction`（T:13）。
- 真实操作：W 在真实浏览器确认撤回材料后，判断、情景、影响路径及段、简报均 needs_review，旧 v1 引用仍保留；接口集成覆盖跨模块 outbox。
- 尚缺/适用边界：此结论限已登记依赖，不声称发现未登记的现实世界依赖；不是自动判定真实材料撤稿。
- 能否通过：**可据证据通过**。

### AC-08 格式变化不误作撤回

- 已运行测试：`test_core_domain.CoreDomainTests.test_format_change_preserves_research_review_state`（T:26）；`test_core_domain.CoreDomainTests.test_no_substantive_confirmation_no_retraction`（T:29）。
- 真实操作：真实 Store 测试执行格式变更和缺实质确认的撤回阻断，保留研究审阅状态。未见浏览器执行该分支。
- 尚缺/适用边界：需实际展示一次格式变化/候选检查记录，确认界面没有“正式撤回”或错误重审；不扩展成监控未接入网页正文。
- 能否通过：**领域规则可通过；页面展示待补**。

### AC-09 全部启用新闻源超时

- 已运行测试：`test_sources.SourceTests.test_all_failed_unavailable_with_stale_cache_preserved`（T:110）；`test_sources.SourceTests.test_failure_notifications_only_transition_recovery_once`（T:116）。
- 真实操作：B 首页实际显示部分覆盖与 GDELT 失败；9 月 21 日 S 又记录真实 GDELT 超时。
- 尚缺/适用边界：命名 all_failed 的用例实为一个 RSS 先成功后失败、缓存保留，不足证明多新闻源全部超时和逐源 last_success 页面；须注入全失败并核对冷缓存/旧缓存、上次成功及无全局无异常文案。真实 GDELT 失败也不等于全部新闻源失败。
- 能否通过：**部分，暂不可完整认定**。

### AC-10 配额、重复刷新与缓存

- 已运行测试：`test_sources.SourceTests.test_shared_budget_includes_failures_and_restart`（T:134）；`test_sources.SourceTests.test_concurrent_manual_refresh_deduplicates_durable_job`（T:113）；`test_sources.SourceTests.test_gdelt_source_wide_spacing_and_upstream_retry_after`（T:119）；`test_sources.SourceTests.test_unreviewed_rss_and_paid_ai_activation_rejected`（T:139）。
- 真实操作：测试计入失败请求、重启不重置当日预算、并发刷新去重；W 实际修改 world_bank 配额 20→18 并重启保留。
- 尚缺/适用边界：需在浏览器把明确样本源推到预算边界，连续刷新、看缓存/暂停文案并比对请求计数；现有真实操作未耗尽额度，不应消耗真实上游额度来制造验收。
- 能否通过：**后台预算规则通过；完整交互待补**。

### AC-11 年度指标与采集时间分离

- 已运行测试：`test_core_domain.CoreDomainTests.test_annual_metrics_preserve_period_and_unknown`（T:19）；`test_sources.SourceTests.test_world_bank_year_null_value_units_and_durable_pagination`（T:140）；`test_core_domain.CoreDomainTests.test_same_indicator_url_distinct_observation_identity`（T:37）；`test_lifecycle_platform.LifecyclePlatformTests.test_topic_country_background_reuses_observation_without_rewriting_identity`（T:69）。
- 真实操作：S 真实 WDI 年度数据；B 恢复实例正式页面展示 USA 2021—2025 的 GDP/人口 10 条，观测年份与 9 月 20 日采集日期分列。
- 尚缺/适用边界：未知值未当零；当前国家/来源筛选范围另有独立待查（见补验队列），不改变本 AC 的年份证据。
- 能否通过：**可据证据通过**。

### AC-12 国家精度不伪造点坐标

- 已运行测试：`test_core_domain.CoreDomainTests.test_country_position_cannot_claim_exact_coordinates`（T:24）；`tests.test_web_semantics.WebSemanticsTests.test_unknown_time_and_country_have_no_invented_precision`（U:12）。
- 真实操作：W 实际浏览器用 Natural Earth v5.1.2 真底图显示 CHN 国家区域，事件仅国家精度，无精确点；S 保存 177 个国家要素来源/许可。
- 尚缺/适用边界：不是根据假想坐标绘图，也未宣称支持更高精度事件定位。
- 能否通过：**可据证据通过**。

### AC-13 判断修订固定历史证据

- 已运行测试：`test_core_domain.CoreDomainTests.test_closed_loop_persist_revision_conflict_and_export`（T:21）；`test_core_domain.CoreDomainTests.test_indeterminate_review_is_separate_and_references_old_judgment`（T:28）；`test_platform.PlatformTests.test_version_conflict_and_restart`（T:108）。
- 真实操作：B 正式页面显示 v1/v2 的时间、操作者、理由及固定材料 v2；恢复后保存判断 v3。L 下载文件的材料当前 v3、判断/引用仍 v1，历史未混入最新正文。B2 更新后 v4、迁移回退后 v5 的页面保存均已完成，仍引用材料 v2。
- 尚缺/适用边界：权限收紧时历史正文可能合法省略，版本 ID/用户记录仍留，不应把省略误判为历史丢失。
- 能否通过：**可据证据通过**。

### AC-14 没有反证仍可如实建情景

- 已运行测试：`test_core_domain.CoreDomainTests.test_reviewed_scenario_can_truthfully_lack_opposition`（T:36）。
- 真实操作：W 实际保存 reviewed 情景：无反对材料，填写真实的未找到说明/检索范围、假设、信号与失效条件。
- 尚缺/适用边界：这证明能表达检索缺口，不证明已进行全面现实反证检索。
- 能否通过：**可据证据通过**。

### AC-15 无法判定与统计单列

- 已运行测试：`test_core_domain.CoreDomainTests.test_indeterminate_review_is_separate_and_references_old_judgment`（T:28）；`test_integration.ResearchIntegrationTests.test_assumption_review_indeterminate_result_and_reading_remain_honest`（T:47）。
- 真实操作：W 正式表单保存无法判定及原因，固定判断 v4；测试断言 indeterminate=1、decidable=0。
- 尚缺/适用边界：仍缺修复后的正式复盘总览统计核对，尤其超过 200 条后的全量分母/分页；B2 的 204 判断全库搜索不等于复盘统计验收。
- 能否通过：**单条保存与后端统计通过；总览分支待补**。

### AC-16 两个真实窗口编辑冲突

- 已运行测试：`test_core_domain.CoreDomainTests.test_closed_loop_persist_revision_conflict_and_export`（T:21）；`test_platform.PlatformTests.test_version_conflict_and_restart`（T:108）。
- 真实操作：W 两真实浏览器标签页同时持有判断 v2：A 保存 v3，B 提交收到 409，保留输入草稿、未覆盖 A；不是仅模拟两个请求。
- 尚缺/适用边界：当前角色为单用户本地研究，没有多人权限系统承诺。
- 能否通过：**可据证据通过**。

### AC-17 失效链接、权限收紧与保留依赖

- 已运行测试：`test_core_domain.CoreDomainTests.test_restriction_propagates_without_erasing_metadata`（T:34）；`test_core_domain.CoreDomainTests.test_history_endpoint_obeys_current_display_restriction`（T:27）；`test_audit_round_two.AuditRoundTwo.test_rights_narrowing_normal_edit_propagates_to_judgment_and_brief`（T:17）；`test_audit_regressions.AuditRegressions.test_translation_cannot_bypass_storage_rights`（T:12）。
- 真实操作：领域回归覆盖元数据、历史限制和重审；H 另有实际 SQLite 的来源当前/历史策略与到期策略；L 真实下载确认受限历史正文省略。
- 尚缺/适用边界：H 已运行 `tests.test_core_rights.EvidenceRightsTests.test_source_narrowing_applies_immediately_to_every_version`、`tests.test_core_rights.EvidenceRightsTests.test_source_export_restriction_is_distinct_from_display` 和 `tests.test_core_rights.EvidenceRightsTests.test_due_untouched_collector_is_hidden_before_physical_cleanup`（54 项交接记录，无同轮原始 stdout）；新增 helper 不等于最终 HTTP 路由和搜索已验。需正式详情/历史/JSON/Markdown/搜索逐一验证 source 级 display/export 收紧和链接不可达仍保留出处。
- 能否通过：**部分，暂不可完整认定**。

### AC-18 引导、分页、筛选和已展示版本已读

- 已运行测试：`test_activity.ActivityTests.test_only_displayed_versions_marked_read_and_new_changes_remain`（T:2）；`test_activity.ActivityTests.test_updated_version_not_silently_read`（T:4）；`test_audit_regressions.AuditRegressions.test_offset_read_snapshot_cannot_read_later_changes`（T:7）；`test_activity.ActivityTests.test_read_state_does_not_clear_research_todo`（T:3）；`test_lifecycle_platform.LifecyclePlatformTests.test_reading_baseline_limits_unread_without_faking_read_history`（T:68）；`tests.test_web_semantics.WebSemanticsTests.test_read_marks_only_displayed_versions`（U:10）；`test_audit_round_two.AuditRoundTwo.test_unread_notification_filter_precedes_pagination`（T:18）。
- 真实操作：W 看过首次空态/引导；真实首页有分页及已展示版本按钮。自动测试覆盖读 v1 时新增 v2、后来新变化、未加载项、待办不清除及旧未读先筛再分页。
- 尚缺/适用边界：需正式浏览器两个窗口制造“加载后新增/更正”，同时有筛选隐藏、第二页未载项；实际点已读再重载逐项核对。A7 修复没有正式旧未读 >20 的结果文件。
- 能否通过：**规则回归通过；完整竞态页面场景待补**。

### AC-19 导出、备份、恢复的完整与合法内容

- 已运行测试：`test_core_domain.CoreDomainTests.test_export_filters_rights_and_secrets`（T:25）；`test_ops_lifecycle.OperationsTests.test_running_backup_and_empty_restore_continue_edit`（T:86）；`test_ops_retention.BackupRetentionTests.test_bounded_source_all_versions_omitted_in_archive_not_live_database`（T:96）；`test_ops_retention.BackupRetentionTests.test_actual_due_candidate_legacy_restore_and_refetch_cannot_revive_body`（T:94）；`test_lifecycle.LifecycleTests.test_export_finite_source_omits_body_but_keeps_notes_and_citations`（T:53）。
- 真实操作：L 标准页面 JSON/Markdown 实际落盘，逐项比对 API；C 真源库 415 版本备份恢复、B 浏览器继续编辑；O 运行中备份与合法附件/阅读状态恢复实测。
- 尚缺/适用边界：普通研究导出与恢复包策略不同：H 允许未到期且有 export 授权的有限期正文，恢复包提前省略。新 source 级纯策略已合入，实际读取/普通导出接线仍待交付，随后需 HTTP/浏览器回归，不能沿用旧导出证明所有新分支；B2 已补 root 真源 JSON 文件核验；本条剩余问题是最新策略的完整响应矩阵。
- 能否通过：**主要闭环通过；最新权限矩阵待补后完整认定**。

### AC-20 航空/船舶未接入不冒充空结果

- 已运行测试：`test_http.LocalHttpTests.test_health_and_disabled_capabilities`（T:43）。
- 真实操作：真实 HTTP 返回 tracks/AI/market-data 未配置；W 设置页预留能力禁用、地图没有航空船舶数据演示。
- 尚缺/适用边界：没有真航空/船舶接入承诺；当前证据以接口未接入状态和真实地图无虚构轨迹为限。
- 能否通过：**可据当前预留范围通过**。

### AC-21 结构化路径重开与段级纠错

- 已运行测试：`test_core_domain.CoreDomainTests.test_correction_propagates_idempotently_and_preserves_history`（T:23）；`test_integration.ResearchIntegrationTests.test_five_topic_research_loop_and_correction_reaches_all_dependents`（T:48）。
- 真实操作：W 保存并重开 2 节点/1 段路径及假设、固定引用；撤回后路径与受影响段待重审。领域测试有 2 段并确认只标受影响段。
- 尚缺/适用边界：路径的可视呈现不代表因果关系已被证明，待验证语义保留。
- 能否通过：**可据证据通过**。

### AC-22 审阅后的假设判断仍缺证据

- 已运行测试：`test_core_domain.CoreDomainTests.test_assumption_judgment_mark_survives_review_and_export`（T:20）；`test_audit_round_two.AuditRoundTwo.test_change_preserves_hypothesis_label_at_its_saved_version`（T:14）；`test_activity.ActivityTests.test_brief_preserves_missing_evidence_and_correction_flag`（T:1）；`test_integration.ResearchIntegrationTests.test_assumption_review_indeterminate_result_and_reading_remain_honest`（T:47）。
- 真实操作：实际 API/SQLite 覆盖 reviewed 后缺证据标记及导出；root 针对原 A3 修复历史变化的 support_label。
- 尚缺/适用边界：尚无修复后正式首页 + 该条 JSON/Markdown 下载的成对页面记录。通用 L 下载文件并不自动证明假设-only 条目的标签。
- 能否通过：**领域与回归通过；首页/产物精确分支待补**。

### AC-23 无匹配与局部失败不可混淆

- 已运行测试：`test_sources.SourceTests.test_one_empty_one_failed_is_partial_not_no_matches`（T:125）；`test_sources.SourceTests.test_last_empty_page_does_not_erase_snapshot_matches`（T:121）；`test_sources.SourceTests.test_topic_coverage_does_not_reuse_other_topic_success_or_etag`（T:138）。
- 真实操作：测试明确一个 RSS 成功空列表、WDI 504，partial 而非 no_matches；B 真源首页显示 partial。
- 尚缺/适用边界：真实 B 是 RSS/WDI 有内容 + GDELT 失败，不是题设“成功空 + 关键失败”；需受控页面演练核对逐源状态和未完成提示。
- 能否通过：**聚合规则通过；精确页面场景待补**。

### AC-24 全新 Mac 代码目录初始化和打开页面

- 已运行测试：`test_ops_lifecycle.OperationsTests.test_real_start_reuse_stop_and_restart_edit`（T:82）；`test_ops_lifecycle.OperationsTests.test_new_code_directory_reopens_existing_data_and_normal_stop_is_safe`（T:81）。
- 真实操作：C 真 Mac 中文/空格新 clone，check-config/init/start/reuse/stop 成功；B 已实际浏览器打开恢复实例。
- 尚缺/适用边界：C 与相关脚本测试显式 --no-browser，手动打开不证明“健康后自动打开”；需正常入口不传该参数，记录自动打开及可选 Key 为空。
- 能否通过：**部分，暂不可完整认定**。

### AC-25 依赖、权限、端口阻断与脱敏

- 已运行测试：`test_ops_lifecycle.OperationsTests.test_local_preflight_port_occupied_and_missing_data_identity`（T:80）；`test_ops_lifecycle.OperationsTests.test_directory_permission_and_tampered_manifest_are_blocked`（T:76）；`test_ops_lifecycle.OperationsTests.test_secret_config_not_echoed_and_missing_dependency_blocks`（T:88）。
- 真实操作：O 实际占用 socket、实际 chmod 无写权限、实际秘密值错误输出检查；都拒绝误启动且不终止占端口者。Python 缺失/过旧分支是 sys.version_info 注入。
- 尚缺/适用边界：实现方案为 stdlib 原生，不使用容器引擎；“引擎未启动”应在最终报告标不适用，不是通过。补隔离 PATH 的真实启动入口缺 Python/curl 检查，勿卸载系统依赖；确认有修复指引。
- 能否通过：**实际权限/端口分支通过；入口缺依赖分支待补**。

### AC-26 中文空格路径、Finder、幂等启停

- 已运行测试：`test_ops_lifecycle.OperationsTests.test_script_and_command_entrypoints_in_chinese_space_path`（T:87）；`test_ops_lifecycle.OperationsTests.test_real_start_reuse_stop_and_restart_edit`（T:82）；`test_http.LocalHttpTests.test_browser_keep_alive_does_not_block_service_shutdown`（T:42）。
- 真实操作：O/C 用 shell 执行 .command 和 .sh、重复 PID 复用；W 修复后浏览器仍打开，SIGTERM 0.15 秒退出 0，重启数据保留。
- 尚缺/适用边界：Finder Computer Use 权限明确未获授予，原生双击未执行；mac-gui-paths.json 仅路径，不是 GUI 操作结果。不得用脚本或其他控制方式绕过权限替代。
- 能否通过：**终端部分通过；Finder 分支阻塞**。

### AC-27 可选配置与联网失败隔离

- 已运行测试：`test_sources.SourceTests.test_seed_is_local_idempotent_preserves_config_and_disables_paid`（T:132）；`test_sources.SourceTests.test_unreviewed_rss_and_paid_ai_activation_rejected`（T:139）；`test_sources.SourceTests.test_changed_query_requires_new_snapshot_before_complete`（T:112）；`test_http.LocalHttpTests.test_health_and_disabled_capabilities`（T:43）。
- 真实操作：C 本地预检与网络检查分开、可选能力警告；B/S 真实 GDELT 失败时 RSS/WDI 及核心编辑仍可用；无收费/模型调用。
- 尚缺/适用边界：需从正式来源设置保存一项无效/不完整配置并确认仅该来源受限、其他工作继续；现有 API 拒绝配置用例不等于页面明确停用/降级。
- 能否通过：**真实网络失败隔离通过；坏配置页面分支待补**。

### AC-28 退出、异常、迁移代码位置后的持久化

- 已运行测试：`test_ops_lifecycle.OperationsTests.test_real_start_reuse_stop_and_restart_edit`（T:82）；`test_ops_lifecycle.OperationsTests.test_new_code_directory_reopens_existing_data_and_normal_stop_is_safe`（T:81）；`test_platform.PlatformTests.test_version_conflict_and_restart`（T:108）；`test_ops_lifecycle.OperationsTests.test_local_preflight_port_occupied_and_missing_data_identity`（T:80）。
- 真实操作：B 正常退出/重启真实议题可编辑；W 早期 keepalive 故障后异常结束仍恢复记录，随后正常启停已补；O 真正换代码目录读同一数据库，缺原 DB 拒绝造空库。
- 尚缺/适用边界：需一次明确异常终止前/后全对象清单，包含 read_state 和 settings，并在浏览器逐项打开；现有散落记录未完整对齐这些对象。容器重建不适用当前原生方案，未宣称通过容器平台。
- 能否通过：**正常/迁目录通过；异常全对象核对待补**。

### AC-29 在线备份及磁盘失败/中断

- 已运行测试：`test_ops_lifecycle.OperationsTests.test_running_backup_and_empty_restore_continue_edit`（T:86）；`test_ops_lifecycle.OperationsTests.test_backup_disk_failure_keeps_previous_valid_package`（T:73）；`test_ops_lifecycle.OperationsTests.test_upgrade_backup_failure_aborts_before_migration`（T:93）。
- 真实操作：O/C 实际在线一致备份、验证后恢复；磁盘错误用 _snapshot 抛 OSError 注入，保留旧有效包；升级前备份失败阻断。
- 尚缺/适用边界：未见备份写入中实际杀掉备份进程的记录；updater 迁移中 SIGKILL 不是备份中断。可在临时专属进程受控阻断，不需填满用户磁盘；核对 partial 不报成功、旧包仍校验通过。
- 能否通过：**在线/注入失败通过；备份进程中断分支待补**。

### AC-30 恢复到空实例后浏览器继续编辑

- 已运行测试：`test_ops_lifecycle.OperationsTests.test_running_backup_and_empty_restore_continue_edit`（T:86）；`test_ops_lifecycle.OperationsTests.test_restore_rejects_missing_read_state_version_before_touching_target`（T:85）；`test_ops_retention.BackupRetentionTests.test_default_unbounded_source_preserves_all_legal_content`（T:98）。
- 真实操作：C 真实资料库恢复空目录；B 正式浏览器旧判断 v2→v3，固定材料 v2、议题仍可读。O 实际 HTTP 恢复后编辑、合法附件、read_state、历史均保留，默认包不含 .env。
- 尚缺/适用边界：B 真实库清单没有 read_state，需补浏览器核对已有阅读状态及附件入口；当前默认源均免 Key，不能为了“重填密钥”启用付费源。对未来凭据来源的重配路径应列不适用/未测，不宣称已通过。
- 能否通过：**恢复编辑通过；完整阅读/附件页面核对待补**。

### AC-31 损坏包、兼容性与明确替换

- 已运行测试：`test_ops_lifecycle.OperationsTests.test_corrupt_and_incompatible_backup_never_replace_existing`（T:75）；`test_ops_lifecycle.OperationsTests.test_directory_permission_and_tampered_manifest_are_blocked`（T:76）；`test_ops_lifecycle.OperationsTests.test_restore_does_not_treat_unbound_personal_files_as_empty`（T:83）；`test_ops_lifecycle.OperationsTests.test_restore_rejects_maintenance_and_actual_pending_start`（T:84）。
- 真实操作：O 真 Mac 临时目录中损坏 ZIP、清单校验篡改、不兼容 schema 被拒绝；现有数据不变；有效显式 replace 保留备份与恢复点，未绑定个人文件不强行覆盖。
- 尚缺/适用边界：界面为文档规定的 CLI 运维流程，此 AC 不要求 Web 恢复按钮；结论限已验证 schema 及当前包格式。
- 能否通过：**可据实际 Mac 行为测试通过**。

### AC-32 脏工作区与未跟踪文件保护

- 已运行测试：`test_ops_lifecycle.OperationsTests.test_dirty_and_untracked_update_protection`（T:77）。
- 真实操作：O 实际独立 Git repo 中同时修改 VERSION 和创建中文未跟踪文件，更新拒绝、两者与 DB 指纹保持；非单纯 mock git status。
- 尚缺/适用边界：不需要在用户当前脏工作区重新冒险执行更新来证明；隔离真实 Git 进程足以覆盖该机制。
- 能否通过：**可据实际 Mac 行为测试通过**。

### AC-33 迁移中断、健康失败与成对回退

- 已运行测试：`test_ops_lifecycle.OperationsTests.test_interrupted_update_recovers_and_does_not_duplicate_migrations`（T:79）；`test_ops_lifecycle.OperationsTests.test_failing_migration_restores_program_data_and_attachments`（T:78）；`test_ops_lifecycle.OperationsTests.test_target_health_failure_rolls_back_and_download_failure_is_safe`（T:91）；`test_ops_lifecycle.OperationsTests.test_successful_schema_migration_can_explicitly_roll_back_without_new_writes`（T:89）。
- 真实操作：O 实际 updater 在受控迁移暂停点 SIGKILL、recover 后原议题/附件/旧程序可用、二次 recover 阻断；另有真正无效迁移及目标健康失败。R 真源恢复副本故障目标回退 schema 1、临时表无、旧判断 v4 可读。
- 尚缺/适用边界：本 AC 的进程/数据回退行为已充分证明；PRD 12.2 另要求回退后浏览器读阅读状态并继续保存。B2 的 v5 继续保存已完成；仍没有回退前后阅读状态的浏览器对照，别因这个更细文档门槛将已有回退测试误记未执行。
- 能否通过：**AC 行为可通过；PRD 12.2 的阅读状态对照仍待补**。

### AC-34 升级后有新写入时不覆盖

- 已运行测试：`test_ops_lifecycle.OperationsTests.test_successful_update_selection_and_new_write_rollback_guard`（T:90）；`test_ops_lifecycle.OperationsTests.test_attachment_only_edits_and_new_paths_block_rollback`（T:72）；`test_ops_lifecycle.OperationsTests.test_attachment_change_during_stop_is_rechecked_before_replacement`（T:71）；`test_ops_lifecycle.OperationsTests.test_unreadable_attachment_fingerprint_blocks_rollback`（T:92）。
- 真实操作：O 真实更新后写新判断/议题内容，回退拒绝、现有数据保留；附件修改/新增及停止时变化均拒绝；交接明确先保留当前恢复包。
- 尚缺/适用边界：可复查的新写入测试主要断言当前数据不变；建议补读取“拒绝前新保存的当前恢复包”并校验其中新增记录/附件，完整证明可找回，不只留在原库。
- 能否通过：**防覆盖可通过；新恢复点可用性待补后完整认定**。

### AC-35 离线历史、更新失败与 Git 范围

- 已运行测试：`test_ops_lifecycle.OperationsTests.test_target_health_failure_rolls_back_and_download_failure_is_safe`（T:91）；`test_ops_lifecycle.OperationsTests.test_new_code_directory_reopens_existing_data_and_normal_stop_is_safe`（T:81）。
- 真实操作：N 实际本地 Git 更新不使用网络；审查对 root `5e321fc` 的 `git ls-files` 111 路径只读筛查，未见 .env/.db/.sqlite/.sqlite3/.wibackup 或 backups/attachments/.test-data/.worktrees 路径被跟踪。
- 尚缺/适用边界：测试名 download_failure 实际传不存在的本地目标，不等于真实 GitHub fetch 失败；尚缺禁止外网时浏览器读旧议题、一次受控拉取失败后旧版仍可用。路径筛查不是秘密内容扫描或全部历史扫描，须对当前 Git 内容再做脱敏审查，不输出秘密值。
- 能否通过：**部分，暂不可完整认定**。

### AC-36 真实睡眠/唤醒后的补采与缺口

- 已运行测试：`test_sources.SourceTests.test_rss_sleep_gap_preserved_without_fabricated_history`（T:128）；`test_sources.SourceTests.test_gdelt_recovery_policy_and_saturated_windows_report_gaps`（T:117）；`test_sources.SourceTests.test_scheduler_lock_prevents_duplicate_process_instances`（T:129）；`test_sources.SourceTests.test_shared_budget_includes_failures_and_restart`（T:134）。
- 真实操作：用例覆盖模拟时钟跳跃、预算、窗口饱和/历史缺口；scheduler-lock 用例为同进程两个 Scheduler 对象配合替换 loop，不是实际睡眠后跨进程实操。
- 尚缺/适用边界：尚无真 Mac sleep/wake 事件、前后 PID/锁、请求预算、补采区间和页面旧事件时间核对。此项属 M3 工程验收，不能全推到七天观察或把测试名当实证；须由负责人协调不打断其他工作的实际睡眠窗口。
- 能否通过：**尚不能通过；真实睡眠分支未执行**。

## 专项补验队列：可独立执行的工程检查

以下是尚缺的检查建议，不是已执行结果。每项应使用隔离代码/数据/端口、显式样本标记、保留 before/after 与原始日志；不占用或停止别的任务进程。常规纯回归通过后无需反复跑同一套测试代替缺失行为。

1. **正式页面语义与竞态包（AC-02—06、08、15、18、22）**：在同一独立样本库建立 10 转载+未知来源、不同日期/国家同题、甲方宣布停火、两个独立出处 5/12、上周发生今日采集、格式变化、假设型判断、>200 判断/复盘。真实浏览器完成相似关系往返、首页过滤/翻页/读后新更正、旧未读 >20、两页复盘统计；导出精确样本并核对固定版本。A4 情景编辑、>200 判断搜索、A8 正式相似材料入口已由 B2 持久化证明，不能据此省略其余分支。
2. **来源状态包（AC-09/10/23/27）**：只在隔离适配器响应中安排全部超时、一个空一个失败、额度边界、无效配置，保留请求计数、预算跨重启、缓存及 last_success；实际页面要同时解释范围与逐源失败。不要耗尽真实免费源或把真实网络失败当成所有组合都覆盖。
3. **最新权限路线包（AC-17/19，PRD 11.2/11.3）**：对有当前/历史正文和中文笔记的引用材料，收紧 source display/export、移除旧渠道、到期但维护尚未运行；分别读取列表/详情/指定旧版本/历史/议题 bundle/citations/JSON/Markdown，并搜索隐藏正文的唯一词，确认没有旁路泄漏；元数据/笔记/固定引用仍可读。H 已测 helper，root 路由接线后此包是独立必要检查。合法未到期普通导出与提前省略正文的恢复包需分别核对。
4. **正式生命周期集成（PRD 11.3，关联 AC-17/19）**：B2 已记录正式回收/恢复保持 needs_review，完整页面接线这条已完成。还需在正式 settings 保存保留设置但不清理、预览、明确确认后运行；本模块 L 临时宿主已通过，整页后台维护/操作交互和大库耗时不是同一验收。精确 U 测试：`tests.test_web_lifecycle.WebLifecycleTests.test_click_preview_then_recovery_does_not_delete_until_confirmed_submit`、`test_confirmation_requires_validated_recovery_reason_and_consent`、`test_panel_load_and_settings_save_never_trigger_cleanup`。
5. **Mac 剩余入口包（AC-24/25/26/28）**：正常 start 不带 --no-browser 自动打开；以隔离 PATH 模拟真实入口缺依赖，禁止删除系统程序；中文/空格路径 Finder 双击需正常获得 UI 权限后执行，权限未授予就如实阻塞。独立实例异常终止前后核对对象、版本、read_state、settings 清单及页面。当前原生 stdlib 架构没有容器/引擎分支，应明确适用性，不能静默记通过。
6. **备份/回退最后分支（AC-29/30/33/34）**：备份中断专属进程后旧包仍有效；回退拒绝前保留的新包确可还原新增记录/附件；恢复和回退后的浏览器读旧议题、指定证据版本、判断、阅读状态并保存下一版。R/B2 已证明真实迁移失败、旧数据与浏览器保存 v5，尚需阅读状态/附件页面对照；不要重复无必要的破坏性故障。
7. **离线与跟踪范围（AC-35）**：不改用户全局网络设置，在独立运行环境限制外网后读本地旧议题；受控 Git 拉取失败保留旧版本。当前 updater 接收本地 ref 而不主动 fetch，测试应覆盖 README 的拉取+更新完整操作边界。只读核查 tracked 文件与必要历史的敏感内容，输出仅是否发现及安全位置，不回显密钥。
8. **真睡眠/唤醒（AC-36）**：由 root 协调真实 Mac 睡眠，记录系统 sleep/wake 时间、实例/collector 数、预算前后、补采上限、coverage_gaps、事件发生/采集时间。其机制可在一天内工程验收；连续七天稳定性仍另算。
9. **合并后的性能与国家范围**：现有 [性能原始结果](../evidence/performance-capacity.json) 是 2 万材料/5 千事件/5 并发的暖 SQLite/HTTP：dashboard P95 0.930405 秒、筛选 0.373495 秒，未测首个可用页面内容 P95。权限策略刚加入全历史扫描，需在最终代码真实浏览器/五并发测首可用内容 ≤3 秒，API 筛选 ≤1 秒。Y 交接还报告 topic.country_codes=USA 时 WDI CHN/USA 配置导致背景混入 CHN；root 在 bd8162a/b88a8b6 已修请求/响应国家交集及全局缓存；bundle 过滤截至本审查仍待 core 接线，交付后需正式页面重验，不能用 AC-11 的时间正确掩盖国家范围问题。

## M1—M3 工程与 M4 真实观察分别结账

- **PRD M1**：已有 PRD、页面实现、契约、ADR 与首批来源方案。本次仅索引证据，未重新逐条审计 §11.6 文档字段/线框完备性，不替 root 宣告 M1 全部完成。这里的里程碑不同于代码七模块 M1—M7。
- **PRD M2**：真实 RSS/WDI、手工元数据登记、全新代码启动、重启保留均有实际证明；GDELT 仍没有有效数据，相似关系主页面已由 B2 完成；国家采集范围已修，bundle 过滤仍待接线与最终页面重验。不能仅因源适配器测试通过把真实接入状态改成功。
- **PRD M3**：要求 AC-01—36 行为通过与 §11.6 文件齐全。目前有多项可确认通过，但 Finder、真实睡眠、备份进程中断、精确页面状态/竞态和最新权限路由等仍缺。它们是工程待办，不是必须等七天才可检查，也不能统一标为 M4 待观察而宣布 M3 完成。
- **真实来源门槛**：GDELT 2026-09-21 又真实超时；Fed RSS 明确许可、WDI 有有效数据。PRD 允许不可用来源记录原因并采用同类免费源等效验证且更新登记，但已有 Fed 新闻不自动等同 GDELT 的全球多源检索。尚无等效范围验收记录，不能宣布已满足该替代条款。
- **真实内容门槛**：S 的 10 条官方材料是候选清单，不是 10 条已人工登记和复核。B 有一个官方声明元数据闭环，仍需 10 条不同类型实际复核；50 材料/20 事件说法/10 判断的出处、时间、关联抽查没有完整报告。
- **PRD M4**：5 个真实议题连续 7 天成功/失败、重复、延迟、预算、人工纠错，以及每日约 10 分钟找出新增变化和遗漏记录尚未完成。`test_five_topic_research_loop_and_correction_reaches_all_dependents` 是 5 个样本；模拟时钟不能变成真实经过 7 天。真实预测准确性也不在这些结构检查的结论内。
- **本地交付报告**：C/N/R 已覆盖真正新目录、空目录恢复、正常更新、迁移失败回退；O 有真实脏工作区保护。仍应把 root 新增原始文件和 B2 最终浏览器保存结果提交为可复查证据，标清 Finder/平台/升级路径限制，并使 README 示例与实际入口一致。未验证 Linux/Windows/容器、未来第三方依赖升级不能表述已支持。

## 本文件交付与复核方法

仅新增 `docs/handoffs/acceptance-evidence-index.md`；无 API/实现变更，无服务启动，无网络调用。编写时检查每个列出的 T/F/U 精确测试名确实存在于对应成功原始日志，AC-01—36 各出现一个主条目；追加检查 Markdown 链接在 root 主工作区存在。审查时新增的未提交证据由 root 保留/提交，本文件不越权移动它们。

合入顺序：root 保留/提交本次新增原始日志与浏览器记录，再合入此文档（或同次集成）；随后根据新行为证据更新正式 `ACCEPTANCE.md`。当前搜索交互已提交 22d2b89，B2 有正式页面实操，但不能扩大为复盘统计、分页竞态等未测分支“通过”。无需重跑旧全量测试来证明这份只读文档；最终实现集成仍由 root 运行适当回归。
