# M2 来源与采集交接

## 位置与归属

独立 worktree `.worktrees/sources` / 分支 `dev/sources`。仅修改 `server/modules/sources/**`、`tests/test_sources.py`、本交接、`docs/evidence/source-research.md` 和 `web/assets/world-countries.geojson` / 对应许可说明。平台、迁移、依赖锁未改。依赖 main 的 Store 与 knowledge 公开接口；合并后由 root 完成 HTTP/页面/真实采集入库整体验收。

## 公开接口

- `handle(store, method, segments, body, query)`：标准 source GET/POST/PATCH/history；GET `sources/coverage`、`sources/jobs`；POST `sources/<id>/refresh` 接收 `{topic_id?}`，只持久排队，返回 `{status:queued|already_queued,job}`。
- `seed_sources(store)`：幂等，纯本地；预置 GDELT、Fed RSS、WDI、人工来源和关闭的 AI/付费占位。
- `coverage(store, topic_id=None)`：`{coverage_status,sources,empty_reason,explanation}`。complete 仅表示配置范围检查完成，空结果与部分/失败分开；有陈旧缓存不称正常无结果；分窗任务未完及历史缺口不称完整。
- `start_scheduler(store, evidence_sink=None, observation_sink=None, fetcher=None)` → Scheduler；`stop_scheduler(scheduler)`。默认 sink 是 `knowledge.ingest(store,data,origin='collector')` / `knowledge.upsert_observation(store,data)`；线程单一、按数据目录 flock 独占。
- `Scheduler.tick(schedule=True)`：测试/诊断用一次有界处理；不从 HTTP 路由直接调用。root 应在服务启动/正常退出调用 start/stop。启动时将未完成 running 任务恢复为 retry；默认不会创建无查询 GDELT 任务。
- `python3 -m server.modules.sources.probe --sources rss,world_bank`：显式免费连通性检查，各源单次、无自动重试、不写研究数据库。不应放进默认本地配置检查。

Source `config`：`feed_url, query, countries[], indicators[], topic_ids[]`；目前 RSS 只接受已核对许可的 `https://www.federalreserve.gov/feeds/*`；其他域先用 manual，维护者另审核。WDI 白名单 NY.GDP.MKTP.CD、SP.POP.TOTL。预算以 UTC 日计、并发排队幂等、定时/刷新/失败重试共用持久计数。所有网络等待在 Store 事务外。

运行字段：requests_today/budget_date/last_error/last_error_code/etag/last_modified/last_result_count。collection_job 保存分页/分窗检查点、尝试次数、下一次重试、覆盖缺口、covered_until。没有增加新的数据库 kind 或私有表。

`maintenance.json` 存在时禁止新排队、请求和入库；在途请求遇到维护时留下原检查点，恢复后可重试。root 运维应先建立维护标记再正常停止，等待有界网络请求退出之后备份/迁移；这才能排除开始维护与正在提交事务的竞争。

## 实际验证

2026-09-20，Mac 原生 Python 3.11，独立临时 SQLite，无真实用户数据库：

```
python3 -m unittest tests.test_sources -v
Ran 21 tests in 0.115s
OK
```

附加交叉验证：`python3 -m unittest tests.test_sources tests.test_core_domain tests.test_platform -v`，48 tests / 0.251s / OK；`git diff --check` 通过。

覆盖：并发手动刷新合并；失败/重启/跨日共用预算；网络不锁读取；RSS pubDate/ETag/304；GDELT seendate 分离/200文本错误/429退避/90天策略与250条上限缺口；World Bank 年份/null/单位/跨重启分页；全失败与部分空结果；失败/恢复事件幂等；批次事务回滚；RSS睡眠缺口；重复实例锁；XML实体与非公网DNS阻断；版本冲突；维护标记；真实 knowledge 回调中的证据精确去重、指标历史修订和引用完整性。上游故障/睡眠场景是明确标注的模拟，不是实际关机或七天观察。

真实网络：交付的安全 curl 适配器调用 Fed RSS / WDI，均 HTTP 200，分别解析 20 条材料和 10 条指标记录。请求时间、URL、SHA256、样本和十条官方材料清单在 `docs/evidence/source-research.md`。GDELT 得到两次 429 和一次 200 文本参数错误；未获得真实 GDELT 材料，不宣称该源验收成功。Natural Earth v5.1.2 真正公共领域底图已下载并校验。

## 边界及合入顺序

1. main 平台 Store、core knowledge 先合入（本分支已合并 main 至 621f0f7）。
2. 合并本 sources 提交；root 把调度器接入服务生命周期，dashboard 复用 sources.coverage。
3. Web 使用 `/assets/world-countries.geojson`，国家精度高亮区域而非精确事件点；Map 许可就近保留。
4. 用隔离真实源验收库跑 HTTP/浏览器、真实源入库后重启、维护停止、备份恢复、实际睡眠与更新；本交接未替代这些集成验收。

GDELT 深历史/完整新闻覆盖、Feed 滚动窗口外的完整性、本机真正睡眠恢复、七天观察均未证明。当前自动补采上限 90 天是本版安全预算政策，不是声称上游历史仅 90 天。查询命中 250 条会显式记录缺口；不做未授权全文补采或付费回退。未推送 GitHub。

## 2026-09-21：WDI 国家范围与来源权限事件补充

本批基础已合并 `ad5e32f`；修改 sources 模块、新增 `tests/test_sources_policy.py`，不改 knowledge/research、平台或前端共享文件。

WDI 自动采集行为：

- 对议题任务，将明确的 `topic.country_codes ∩ source.config.countries` 保存为 `collection_job.country_codes`。国家选择进入任务签名；查询范围改变后旧任务取消、旧成功状态失效，分页从新范围起点开始。
- URL 只请求交集中的国家；响应再次过滤国家与配置指标，即使上游返回额外国家也不自动入库。
- 议题国家为空或与来源无交集时，不猜测国家、不排队、不消耗预算；显式刷新解释拒绝，coverage 不报已检查无结果。完全没有议题时仍可按来源明确配置进行全局缓存采集。
- WDI 自动材料和观测保持全局背景缓存（新记录 topic_id=null），不把任务议题变成永久的人工研究关联。议题通过 research.bundle 的明确国家选择读取背景。再次采集不会覆盖已经存在的人工作品 topic_id/topic_ids。
- M2 不跨域清理过去错误关联；root/core 负责 bundle 在显式国家选择下过滤背景展示，同时保留被研究引用材料的 citations。该读取修复需与本批合入验证。

新增可靠事件 `source.policy_changed`：在来源 PATCH 的同一事务中，先保存来源新版本，再发布；仅 store/display/export 的 true→false 或 retention_days 从 null→有限／变短时触发，改名、同值和权限放宽不触发。

```json
{
  "source_id": "source-world-bank",
  "source_version": 2,
  "version": 2,
  "previous_version": 1,
  "old_rights": {"fetch":true,"store":true,"display":true,"export":true,"ai":false},
  "new_rights": {"fetch":true,"store":true,"display":false,"export":true,"ai":false},
  "old_retention_days": null,
  "new_retention_days": 30,
  "rights_narrowed": ["display"],
  "retention_shortened": true,
  "reason": "来源授权或内容保留期限收紧，请重新核对相关研究。"
}
```

事件 ID 为 `source-policy:<source_id>@<source_version>`；publish 失败时来源版本也回滚。本模块只写 source 与 outbox，M3 owner 消费后再按所属域传播依赖重审。

**合入顺序**：与 core/root 的 knowledge.on_event 接线一同集成后再在真实数据目录启用。旧消费者会忽略未知事件类型后仍标记投递，不能先部署只有事件发布端的版本。消费者重投幂等和按全历史渠道定位的测试由 core/root 负责。

实际执行：`python3 -m unittest tests.test_sources tests.test_sources_policy -v`，**42 项／0.227 秒／OK**。新增 9 项覆盖国家请求/响应双过滤、空与无交集、修改后的失效和在途取消、跨重启分页、人工关联保护、权限事件紧缩条件、期限事件条件和 outbox/source 版本原子回滚。均使用真实 SQLite 与明确的夹具响应；没有新上游请求，也没有用夹具声明真实 WDI 联网或睡眠验收。
