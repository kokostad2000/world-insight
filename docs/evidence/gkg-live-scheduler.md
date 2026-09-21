# GDELT GKG 正式 Scheduler 真实接入验收

**结果：通过本次有界接入。** 2026-09-21 02:55:18Z—02:55:30Z，正式 Scheduler 和正式 TLS/curl transport 进行了 **2 次新的真实 GET**，index 与 ZIP 均 HTTP 200，无重试。通过 knowledge.ingest 持久化 **45 条去重材料**，没有创建现实说法、事件或判断。三个议题均为 **partial**，持续明确“仅最新批次，未补齐历史”。这次是新的正式传输入库验收，区别于此前 02:00Z 批次离线重放。

## 代码、调用和隔离边界

- 实现基线：main `a580697a67c105db2ef25886266a92256f189bd8`，已含 GKG `57ad407`。
- 脚本：`scripts/verify_gkg_live.py`，默认 dry-run；仅明确 `--live --data-dir NEW_EMPTY_DIRECTORY` 才联网和建库。旧目录非空即拒绝，避免碰正式研究库或重复上次请求。
- 本次确切命令：

```bash
python3 scripts/verify_gkg_live.py --live --data-dir /private/tmp/world-insight-gkg-live-scheduler-20260921
```

- 单独新目录 `/private/tmp/world-insight-gkg-live-scheduler-20260921`；没有 HTTP 监听，没有打开或操控浏览器。保留 8880 给 root 后续验收，不操作其他任务端口。
- GKG 预算设为 **2**；其他免费来源包括 DOC 在此新验收实例停用，paid/AI 仍禁用。现有其他真实源实例及其 DOC 失败状态未修改。
- 使用真实时钟，Application.dispatch 创建议题与来源配置、refresh 排队；正式 Scheduler.tick(schedule=False) 执行有限轮次，正式 knowledge.ingest(origin='collector') 写入 SQLite；没有替换解析器或注入预录响应。
- transport 外层仅增加审计和最大调用数限制，仍调用原始 adapters.fetch，保持固定官方域、TLS 校验、64 KiB 索引/4 MiB ZIP 传输上限。脚本不启动后台无限采集线程；任一网络/解析/入库/预算失败立即终止下一轮。
- 议题名明确为“真实接入验收 · Iran/Russia/sanctions · 当前批次发现了哪些材料？”，rationale 明确只验收资料元数据，不形成现实结论。材料来自真实响应，因此 `is_fixture=false`，全部 `status=unverified`。

## 两次真实请求

| 请求 | UTC 开始 | 结果 | 字节 | 耗时 |
|---|---|---|---:|---:|
| [lastupdate.txt](https://data.gdeltproject.org/gdeltv2/lastupdate.txt) | 02:55:18.083186Z | HTTP 200 | 319 | 0.635332 秒 |
| [20260921030000.gkg.csv.zip](https://data.gdeltproject.org/gdeltv2/20260921030000.gkg.csv.zip) | 02:55:24.194721Z | HTTP 200 | 2,767,079 | 1.164676 秒 |

两次 GET 开始间隔 **6.111764 秒**；共享来源计数与提供者计数均为 **2/2**。无第三次请求、无 HTTP 明文、无重定向、无新闻原页请求、无付费或 AI 调用。

- index SHA-256：`f2e8b509461ba9b993c98a7bd048ab516370eaf8fa85c2936a1c24950c7d9f2a`。
- index 指定 ZIP MD5：`fe04803c94fe6f4de8f9938370eca451`；本次 ZIP 实算 MD5 **相同**。MD5 只用于索引/文件完整性比对，不作为身份认证。
- ZIP SHA-256：`7e79e3850b2e628877475f995e2cd084de2fef112283d731a82b3a65a466e8eb`。
- index Last-Modified：`Mon, 21 Sep 2026 02:49:15 GMT`；ZIP Last-Modified：`Mon, 21 Sep 2026 02:48:18 GMT`。

**时间语义实际异常保留：** 上游批次名/DATE 标记 `20260921030000`（03:00Z）比本机 GET 02:55Z 约晚 5 分钟。没有把批次名或 HTTP Last-Modified 改写成原文发布时间，也没有推断事件发生时间。SQLite 保存 `provider_seen_at=2026-09-21T03:00:00Z`、`published_at=null`；提供方批次标记不能当作校验过的现实发布时间。

正式解析受单成员、4 MiB 压缩/16 MiB 解压、文件名、MD5、27 列与批次一致性检查；本次没有把原始 ZIP 保存为应用正文缓存。没有另行记录实际解压字节数，不能用压缩大小推断它。

## 入库与检查点实测

解析后 provider cache 有 **623 条**可用元数据、原 URL hostname 共 **160 个**；本地按标题及主题标签分配：

| 议题 | ID | 关联材料数 | 状态 |
|---|---|---:|---|
| 真实接入验收 · Iran | `4f5cce49-05b1-4452-acb8-feaf9d0d342e` | 14 | partial / fresh |
| 真实接入验收 · Russia | `27fa3ceb-33c1-4ed1-8d76-e06022782c12` | 28 | partial / fresh |
| 真实接入验收 · sanctions | `9ba31b5f-f0dc-4246-8032-21a991cc8a0f` | 10 | partial / fresh |

议题间存在交叉，合计 **45 条去重材料**。45 条逐条核对：excerpt 和 translation 为空、published_at 为 null、language=unknown、store/display/export=metadata、ingest_origin=collector、status=unverified。claim/event/judgment 数量均 **0**。

3 个 collection_job 均 `state=complete`，request_count 分别 0/1/1：纯缓存分配任务不计上游请求。执行 index 或 ZIP 的两个任务保存 `checkpoint.phase=zip` 和批次/MD5/字节数/固定 URL manifest；纯缓存任务保留 index phase，完成状态与 data_as_of 指向该批次。source 状态 ready、requests_today=2、provider_requests_today=2、budget_daily=provider_budget_daily=2，last_attempt=`02:55:24.188702Z`、last_success=`02:55:30.381899Z`。

全部 coverage 持续带原始缺口：

> GDELT GKG 15 分钟批次时间不是原文发布时间；仅最新批次，未补齐历史；按 PAGE_TITLE 与主题标签匹配关键词及排除词；仅元数据，不抓新闻正文。

**实际质量边界：** sanctions 议题召回了标题为 “McQueen Spring 2027 Ready-to-Wear Collection” 的 Vogue 材料，因为提供方主题标签含 `SANCTIONS`，标题本身未含关键词。未打开原新闻页核查其语义相关性。本实现按已声明的“标题+主题标签”匹配，但候选相关性和事实质量不由本次技术验收证明；全部保留待核查状态，不生成相关性或现实结论。

## 可复查产物与停止状态

数据目录保留：`/private/tmp/world-insight-gkg-live-scheduler-20260921`。

- `world-insight.sqlite`：真实材料、议题、来源、任务、历史版本及 outbox。
- `instance.json`：正式实例身份，供后续浏览器连接同一数据。
- `live-report.json`：完整请求结果、每次 tick 的原始 source/jobs 快照、最终覆盖、45 条材料元数据。
- `transport.jsonl`：每次请求开始/完成的持久审计，含 URL、真实时刻、状态、大小、哈希与许可范围内响应头。
- `live-index.txt`：本次官方批次索引；`sources/gdelt-gkg/index.json` 及 `<batch>-<md5>.json` 是正式合法 metadata 缓存。

进程在 **2026-09-21T02:55:30.428001Z** 正常结束，退出码 **0**；没有 runtime.json，没有监听或后台采集线程。完成后以 SQLite `mode=ro` 独立重开，`PRAGMA integrity_check=ok`，再次确认 45 条、无正文/译文、发布时间全未知、状态全部 unverified。

root 后续只启动浏览器展示时使用同目录且禁用调度，避免本次两请求验收之外的自动采集：

```bash
python3 -m server.app --data-dir /private/tmp/world-insight-gkg-live-scheduler-20260921 --port 8880 --no-scheduler
```

脚本默认 dry-run 已实际执行：network_requests=0、database_created=false；`py_compile` 和 `git diff --check` 通过。本批只新增脚本和本文，不修改实现。未推送 GitHub。

本次通过的边界是“官方最新索引与 ZIP → 正式 transport → Scheduler → knowledge → SQLite → 只读重开”。浏览器来源页、真实 OS 睡眠、完整全球覆盖、历史补采、候选质量抽查和七天观察均不由本次证明。来源许可沿用先前官方 GDELT 元数据许可审核；本次两 GET 预算未用于重新访问许可页面。
