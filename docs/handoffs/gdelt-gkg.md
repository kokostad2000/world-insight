# M2：独立 GDELT GKG 免费发现适配

2026-09-21。基础已合 main `0f546fa`。报告 `2796ff9` 先提交；coverage 全失败语义小修 `b22ce42` 已独立提交给 root/web 复验。本批只改 sources 模块、对应测试及本交接，不改平台、契约、web 或已安装数据。

## 接入与行为

- 新 adapter `gdelt_gkg`，种子 ID `source-gdelt-gkg`、默认 `enabled=false`，固定域 `data.gdeltproject.org`，默认间隔 1800 秒、预算 500。不静默替代 `gdelt` DOC，不清除 DOC 失败，不启用付费或 AI。
- `config` 仅接受 `topic_ids`。必须有明确关键词的活动议题；按 `topic.source_ids` 与 `source.config.topic_ids` 的交集分配。没有关键词不采全量新闻、不猜测议题；显式刷新解释拒绝。
- 只请求 `https://data.gdeltproject.org/gdeltv2/lastupdate.txt` 和该索引指定的同域 `YYYYMMDDHHMMSS.gkg.csv.zip`。索引中 HTTP URL 只提升为同域 HTTPS，没有 HTTP 或重定向请求。publisher URL 只作为元数据，从未抓取新闻原页。
- `PAGE_TITLE` 是标题唯一来源；为空则跳过。不提取引文、正文、图片、音视频或 `PAGE_PRECISEPUBTIMESTAMP`。关键词/排除词以不区分大小写的子串方式匹配标题和主题标签；主题标签最多保留 4000 字符，不声明全文语义检索或自动翻译。
- 原发布 URL 交给 knowledge；publisher 为该 URL hostname。`source_record_id` 调用现有公开纯函数 `knowledge.canonical_url`，不使用每批变化的 GKG row ID，避免同稿件因批次/跟踪参数重复。只有 `knowledge.ingest(..., origin='collector')` 写资料域。
- 材料 `published_at=null`、`language=unknown`、`excerpt=''`，store/display/export 权限最高为 `metadata`；源对应权限为 false 时继续收窄。批次时间保存为 `provider_seen_at` / `data_as_of`，界面须同步显示“15 分钟批次时间不是原文发布时间”。
- 成功只证明当前最新批次已读；每个成功快照持续带“仅最新批次，未补齐历史”缺口。因此即使该批无匹配也不是 `complete/no_matches`；睡眠后的处理也不能宣称补齐遗漏批次。

## 调度、预算、缓存

既有 `collection_job` 仍按 source/topic 保存 scope 签名。`checkpoint.phase` 为 index/zip；zip 阶段保存经过校验的 manifest（batch、md5、size、batch_at、固定 https URL）。每次 tick 至多一个上游 GET，索引和 ZIP 分别扣一次。

同 provider 的 `gdelt` 与 `gdelt_gkg` 在 Store 事务中共享预算和最小 6 秒请求间隔：UTC 当日所有 GDELT 来源的请求尝试累加，包括当天停用/删除来源已经消耗的次数；共享预算上限取**当前已启用、可采集 GDELT 来源 budget_daily 的最小值**。不能通过新增第二适配器/第二来源获得额外额度。计数仍保留每源原字段；发送前持久预留，失败尝试也计数，不提供付费回退。缓存本地分配不扣费。

GET `/api/sources` 和 GET `/api/sources/:id` 新增派生字段：

```json
{
  "provider": "gdelt",
  "provider_requests_today": 2,
  "provider_budget_daily": 500,
  "provider_min_interval_seconds": 6,
  "provider_last_attempt": "2026-09-21T02:00:06Z",
  "discovery_note": "GDELT GKG 15 分钟批次时间不是原文发布时间；仅最新批次，未补齐历史；按 PAGE_TITLE 与主题标签匹配关键词及排除词；仅元数据，不抓新闻正文。"
}
```

`discovery_note` 仅 GKG 返回；其他 provider 的派生合计等于自身预算。`requests_today` 仍是本条来源的计数，前端不要把它显示成 GDELT 总额度。

provider 全局缓存位于 `data_dir/sources/gdelt-gkg/`：

- `index.json` 保存最新核对索引；复用期取已启用 GKG 来源配置中最短间隔，跨议题及重复来源配置共享。
- `<batch>-<md5>.json` 只保存解析后的合法元数据，单文件不超过 16 MiB；`cache.lock` 独立 flock 防止并发重复索引/ZIP。每批只下载一次，后续不同议题/查询和重启直接本地重用。真实 ZIP 不落运行缓存。
- `retry.json` 保存 GKG 全局退避，429/超时不会被另一个议题立即重新请求；DOC 自己的失败状态仍独立。
- 写入先临时文件、fsync、原子替换、目录 fsync。网络等待不持 Store 锁。入库事务失败回滚材料，但已验证元数据可重用，不再次下载 ZIP。
- 缓存是可重建的 public metadata，不是研究记录或证据引用真源；备份研究数据不依赖它。若缓存被外部清除，重新获取仍扣预算。当前按 batch/MD5 保留合法元数据供精确重用，没有把内容正文放入该缓存，也没有自动修改用户文件。
- 每次排队和请求前检查 maintenance；请求期间暂停或来源/议题权限范围改变时，不将新响应入缓存或资料库。检查点保持可恢复。

## 安全限制

索引最大 64 KiB；ZIP 传输和解析最大 4 MiB，单成员解压最大 16 MiB；文件名必须恰为该批次 `.gkg.csv`，拒绝多个成员、路径穿越、绝对路径、目录、符号链接、加密和不支持的压缩方法。压缩包长度必须匹配索引、MD5 必须一致。MD5 仅是完整性核对，身份与传输安全来自严格 TLS 校验及固定官方域名。没有关闭证书校验、跟随重定向或新增凭据。

## 实际验证

执行：

```bash
python3 -m unittest tests.test_sources tests.test_sources_policy tests.test_sources_coverage tests.test_sources_gkg tests.test_core_rights -q
```

**84 项 / 0.555 秒 / OK**。其中 sources 原有及本批共 62 项，读取权限领域 22 项。新增 GKG 19 项包括恶意清单、大小/MD5/单成员/ZIP 炸弹/伪造解压长度/符号链接、跨议题缓存与排除词、原 URL 身份稳定性、共享预算和停用后消耗保留、断点重启、重复来源、并发、429 共享退避、最新批次缺口、维护期间暂停、在途范围/权限变化、可靠失败恢复通知，以及入库事务失败后只重放缓存。

原始真实响应来自报告 `docs/evidence/gdelt-alternative-research.md` 已记录的两次 GET。本轮实现及验证 **新增真实上游请求为 0**。

离线重放文件：`/private/tmp/gdelt-alternative-2ttdowbd/gkg.zip`，SHA-256 `f2eb6b77524b89f2914b7433388df5a293ffb7b39957ace5a1421f27b1dace90`。批次 `20260921020000`，压缩 2,280,577 字节、解压 7,032,236 字节；505 行中 4 个 PAGE_TITLE 为空，解析后 **501 条**。原 URL hostname 共 139 个；报告中的 134 是 GKG sourcecommonname 列口径，两者不能混算。

真实响应到 SQLite 的本地重放目录：`/var/folders/xp/3lcwms6n0b71r7k7hmj6gqvc0000gn/T/world-insight-gkg-replay-final-yjgnze1p`，`report.json` 保存实际结果，`replay.sqlite` 与 provider cache 可复查。全部材料/议题标为 fixture，并带“真实响应本地重放”标签。回放器调用 2 次，不是 2 次新网络请求。Iran/Russia/sanctions 议题分别关联 13/15/7 条，合计 **31 条去重材料**；全部 published_at=null、无 excerpt、metadata 权限，三个 coverage 都为 partial。

## root 集成及未验证边界

1. 合入本分支的报告、coverage 修复和 GKG 提交；本批无新 Store kind 或迁移。
2. root 所属 web source 表单增加 `gdelt_gkg`，config 仅 topic_ids，关键词在议题编辑；来源页显示 discovery_note、provider 合计和 min-cap 说明，不能把 GKG 成功解释为 DOC 已恢复。
3. 保持种子默认停用；需要用户/已授权验收操作明确启用 GKG。真实 provider 网络可达性只由先前 2 次 GET 支撑，正式 Scheduler 的新端到端上游请求及来源配置浏览器尚未在本批执行。
4. 本地真实响应重放不是生产联网、完整全球覆盖、历史补采、真实 OS 睡眠或七天观察。没有推送 GitHub。
