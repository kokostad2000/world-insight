# AC04 / AC08 / AC18 时间与已读路由验收

2026-09-21；基线 main `e1c39c7`。本批只新增 `tests/test_acceptance_temporal_read.py` 与本交接，不改实现。

## 验证层次与结果

通过真实 `ThreadingHTTPServer` → `handler_class(Application)` → 模块路由 → SQLite/outbox，监听 OS 分配的随机回环端口。独立 `world-insight-temporal-read-fixture-*` 临时目录、明确夹具记录及受控 Store 时钟，结束即正常关服务和清理本测试目录；未监听 8874/8877/8878/8880/8891，未碰其他任务浏览器。

默认 provider transport 被测试保护层禁止；AC04 只给正式 Scheduler 注入明确的本地 RSS 夹具，不发外部 GET。测试不是正式网页浏览器、真实来源或真实睡眠验收。

实际执行：

```bash
python3 -m unittest tests.test_acceptance_temporal_read -v
# 4 项，0.153 秒，OK

python3 -m unittest tests.test_acceptance_temporal_read tests.test_activity tests.test_audit_regressions tests.test_lifecycle_platform tests.test_core_domain -q
# 46 项，0.356 秒，OK
```

初次在默认沙箱内运行被 loopback bind 权限阻止；获准的本机网络执行环境重跑后通过。首次 HTTP 试跑还发现测试夹具缺少正式判断要求的 confidence_reason，补齐夹具后通过，不是应用缺陷。`git diff --check` 通过。

## 少量新增组合场景

### AC04：今日发现旧报道，与事件发生过滤分开

需求原文（PRD AC-04）：今天重新采集上周发布的事件报道，应显示今天发现／采集、上周发生或发布，不进入“今天发生”的事件统计。

`test_ac04_old_publication_collected_today_stays_outside_today_events`：通过 HTTP 启用隔离来源、创建 topic 和 refresh；正式 Scheduler 接收 pubDate=2026-09-14T08:00Z 的 RSS 夹具，采集时钟为 09-21T09:00Z。HTTP 材料读回的 published_at 是上周，collected_at/discovered_at 为今天。随后经 POST events 分别登记上周明确发生和未知发生时间事件。

精确查询路径：

- GET `/api/events?topic_id=<id>&since=2026-09-21T00:00:00%2B08:00&until=2026-09-21T23:59:59%2B08:00` 返回 0。
- GET `/api/evidence?...&time_field=collected_at` 同范围返回 1；`time_field=published_at` 返回 0。
- GET `/api/dashboard?window=24h&topic_id=<id>` 包含新材料和两个新登记事件的发现记录，明确事件仍带上周 occurred_at，未知事件保持 null。
- 同日再刷新相同材料只保留一个身份，不自动创建事件，也不使旧事件进入今天发生范围。

这补充已有 RSS 日期/GDELT seen time/时区领域测试的组合路由证据，**不覆盖下方确认缺口中的跨周重复获取已有记录**。

### AC08：格式候选经过完整路由仍不撤回、不重审

`test_ac08_format_candidate_does_not_create_retraction_or_review_alerts`：HTTP 创建合法夹具材料、已审阅判断、模板简报；再 POST 同 URL，仅将摘录的一处换行改为空行。材料形成 v2/change_candidate，dashboard 出现“尚未确认实质更正”的 evidence.updated；没有 evidence.corrected/research.needs_review，判断仍 reviewed、简报仍 generated、未读通知为 0。以 substantive=false 尝试 withdrawn 返回 400；历史 v1/v2 原文及固定引用 v1 保留。

已有 core_domain 覆盖格式变化和缺实质确认阻断；本测试新增的是 HTTP/完整 Application outbox/dashboard/通知/简报一致性，不再次模拟领域内部判断。

### AC18：过滤、未加载分页、加载后新增和真实更正竞态

`test_ac18_filtered_page_snapshot_then_real_correction_leaves_hidden_and_new_unread`：两个议题，A 有 3 材料及引用最新材料的判断，B 有过滤隐藏材料。A 的 unread 第一页 limit=2 只返回最新材料与判断，较早两材料未加载。保存该页 snapshot_at + 两个 change ID/version 后，另一窗口语义的 HTTP 操作新增 A 材料并实质撤回已展示材料，随后 POST `/api/changes/read` 仍提交旧页两个 ID/version。

结果仅两条旧页变化标为已读；较早两材料、B 的过滤隐藏材料、加载后新增材料及新 evidence.corrected 仍未读。撤回导致的判断 needs_review 和固定旧引用仍保留，未读提醒没有被读变化操作清除。真实 corrections 路由创建新变化记录；直接改 change.version 的防御分支已有 test_activity 覆盖，本测试不重复注入该内部写法。

`test_ac18_first_run_baseline_history_and_later_correction_use_real_routes`：空库 GET dashboard 返回 first_run=true/window=24h；初始议题建立不可编辑的 reading_baseline。上周全局材料在 unread 不出现，custom 历史窗口仍可读且 read=false/before_reading_baseline=true，没有伪造 read_state。PATCH 基线返回 400；基线后经真实 corrections 路由确认更正，则该新变化进入 unread。

## 确认待修：AC04 已有材料再次采集缺少最近收取凭据（P2）

root 已确认属于本批应补的语义缺口，不能用上面的“今天首次发现旧文”通过结果替代。

触发：用同一 RSS URL/正文，09-14T09:00Z 首次采集；09-21T09:00Z 再通过 HTTP refresh + 正式 Scheduler 获取相同响应。只读复现输出：

```json
{
  "same_evidence_id": true,
  "version": 1,
  "published_at": "2026-09-14T08:00:00Z",
  "collected_at": "2026-09-14T09:00:00.000000Z",
  "discovered_at": "2026-09-14T09:00:00.000000Z",
  "first_collected_at": "2026-09-14T09:00:00.000000Z",
  "last_collected_at": null,
  "last_seen_at": null,
  "source_last_success": "2026-09-21T09:00:00.000000Z",
  "today_collected_count": 0,
  "today_dashboard_changes": 0,
  "versions": 1
}
```

来源成功时间只能证明该来源本轮成功，不能证明具体哪条旧材料今天再次收取。材料详情“采集时间”仍只显示上周，缺少 AC04 的本材料今日采集凭据。

最小修复方向：M3 独立 acquisition receipt 保存 collector 实际入库/重复获取的 source/job/收取时间，不改 Evidence 的首次时间、发布时间或不可变材料版本，不把 last_seen 当新发现，不发事实变化事件；人工编辑及失败采集不刷新凭据。root 授权下一批由 sources agent 只新增 `knowledge/acquisition.py` helper 和针对测试，root 接 ingest/读取、页面与契约。此报告提交时尚未接线，**缺口仍未关闭**。

精确复现可直接复用本测试类：setUp → now=09-14 → topic(source_ids=['source-fed'],keywords=['fixture']) → collect_old_rss(topic) → now=09-21 → collect_old_rss(topic)，再 GET `/api/evidence/<id>`、`/api/sources/source-fed` 及 `time_field=collected_at` 的今日过滤，最后 tearDown。全程只有隔离夹具与本机 HTTP。

## 后续正式浏览器验收边界

root/Web 仍需实际展示：旧发布日期/事件时间与今天采集凭据；格式变化候选与历史记录；两个窗口中保存页面快照后新增/更正，点击“将本页已展示变化标为已读”再重载，确认未载、隐藏、新变化和待办。本次路由通过不能写成浏览器通过，首次引导的视觉呈现也仍由页面验收确认。
