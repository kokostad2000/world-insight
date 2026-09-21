# GDELT 官方元数据替代通道：有界真实研究

2026-09-21，macOS，UTC 02:02—02:04。只读研究；**恰好 2 次真实 GET、零重试**。没有抓新闻全文、图片，没有凭据、付费或模型调用，没有修改 adapter、域白名单或启用来源。

## 结论

GDELT 官方静态 GKG 更新通道在本机网络可用：索引与压缩批次都 HTTP 200，下载大小和 MD5 一致，解析到 **505 条文档、505 个 URL、134 个来源域**，每行都有提供者给出的 PAGE_TITLE。可以据此设计同一供应商的免费新闻材料发现适配器；本报告证明真实元数据可获取和解析，不等于应用适配器已接通、原文可靠、新闻事实已核验或覆盖完整。

现有 DOC API 仍独立保持失败：root 于 `2026-09-21T01:55:59.513554Z` 用现有 probe 请求 climate，curl 28 超时约 8.115 秒，见主线 `docs/evidence/gdelt-real-20260921.json`。静态 GKG 可达不抹掉 DOC 失败记录。Fed RSS 也不能替代 GDELT 的跨来源发现范围。

## 两次真实 GET

| 次序 | URL | UTC 开始／结束 | 结果 |
|---|---|---|---|
| 1 | [官方 2.0 最近更新索引](https://data.gdeltproject.org/gdeltv2/lastupdate.txt) | 02:02:21.839690／02:02:22.487073 | HTTP 200；319 bytes；0.627723 秒 |
| 2 | [索引对应 GKG 元数据批次](https://data.gdeltproject.org/gdeltv2/20260921020000.gkg.csv.zip) | 02:03:45.337062／02:03:49.176816 | HTTP 200；2,280,577 bytes；3.807820 秒 |

系统 `/usr/bin/curl --disable`，保留 TLS 校验，`--retry 0`，不跟重定向，不更改代理或系统证书。索引上限 64 KiB／20 秒；第二请求上限 4 MiB／25 秒。索引列出的原地址是 http，第二次使用**相同官方主机与精确路径的 HTTPS 地址**，没有访问 HTTP 或其他镜像。

索引原始内容：

```text
43491 e67fe45570e6f3870d0e513c6db1a563 http://data.gdeltproject.org/gdeltv2/20260921020000.export.CSV.zip
49235 93ac9b12d347a9a6adc7eb902b32adfe http://data.gdeltproject.org/gdeltv2/20260921020000.mentions.CSV.zip
2280577 024c131b8737e7ffc70061f6c784cf28 http://data.gdeltproject.org/gdeltv2/20260921020000.gkg.csv.zip
```

没有请求 export、mentions 或任何第三个 URL。

校验：

```text
index SHA256 d4d75071a901c26fd146081dda80d0e4d7dfb19e8179907962fcb45a399bc952
GKG SHA256   f2eb6b77524b89f2914b7433388df5a293ffb7b39957ace5a1421f27b1dace90
GKG MD5      024c131b8737e7ffc70061f6c784cf28  (与索引一致)
ZIP member   20260921020000.gkg.csv
解压字节     7,032,236
行数／列数   505／27（每行均27列）
文档URL数    505
来源域数     134
PAGE_TITLE   505行存在
PAGE_PRECISEPUBTIMESTAMP 273行存在，尚未核实具体语义
TranslationInfo        本批505行均为空，不能据此推定每篇文章语言
```

MD5 仅验证取得的文件与该索引一致，不代替 TLS 身份验证或内容可信度判定。

只保存本次审查的临时原始响应和小型 JSON 分析记录于 `/private/tmp/gdelt-alternative-2ttdowbd`。压缩文件不提交仓库。记录包括 `request1.json`、`request2.json`、`parsed-summary.json`、响应头和 GKG ZIP。

## 可复查的真实发现样本

下列标题完全来自 GKG 的 PAGE_TITLE 元数据。没有打开原网页；存在转载、观点或论坛链接，均只能作为待核查候选。样本不是本系统的事件事实记录。

| GKG record ID | 提供者标题和文档 URL | 来源字段 |
|---|---|---|
| 20260921020000-1 | [US prepares new sweeping Russia sanctions: Who could get hit](http://www.heraldglobe.com/news/279319777/us-prepares-new-sweeping-russia-sanctions-who-could-get-hit) | heraldglobe.com |
| 20260921020000-43 | [Iran and US trade threats after Houthi attacks escalate regional conflict](https://www.asiaone.com/world/iran-and-us-trade-threats-after-houthi-attacks-escalate-regional-conflict) | asiaone.com |
| 20260921020000-84 | [US issues Iran travel warning, urges citizens to leave country amid rising West Asia tensions](http://www.middleeaststar.com/news/279319932/us-issues-iran-travel-warning-urges-citizens-to-leave-country-amid-rising-west-asia-tensions) | middleeaststar.com |

三条记录原始 DATE 均为 `20260921020000`，SourceCollectionIdentifier 为 `1`。本次本地解析还看到主题码，例如 LEGISLATION、EPU_POLICY；主题码和正文语义都不应自动提升为已核实事件。

## 许可和时间边界

许可依据沿用 2026-09-20 已核对的官方 [GDELT 免费使用及署名说明](https://gdeltproject.org/about.html) 与本仓 [来源研究](source-research.md)：GDELT 数据可免费获取、存储、展示和再分发，保留 GDELT 署名/链接；不取得索引新闻全文或图片的再发布许可。本轮严格把网络请求留给索引和文件，没有第三次刷新条款页面；不宣称条款在本轮重新获取过。

因此拟入库只限标题、原链接、来源域、GKG/批次身份、提供者观察时间等元数据；忽略 ZIP 中引语、图片、嵌入媒体等附加字段，不抓原文，不生成正文摘要，AI 继续关闭。来源记录使用明确的元数据权限，不能因为 ZIP 可免费读就给原文章全文授权。

[官方数据入口](https://gdeltproject.org/data.html) 与此前来源核对登记说明 Events/GKG 采用 15 分钟批次；本次只有一个真实批次，未实测连续更新或 SLA。原始 DATE/文件名所带时间应保存为**供应商批次／观察时间**，不能充当事件时间或原始文章发布时间。保守映射为 `provider_seen_at=2026-09-21T02:00:00Z`、`published_at=null`，本地 `collected_at/discovered_at` 另记实际下载/入库时刻。

本批 HTTP 响应头也展示了为何不能混用时钟：索引 Last-Modified 为 `01:49:09 GMT`；ZIP Date 为 `01:49:28 GMT`、Age=859、Last-Modified 为 `01:48:19 GMT`，与批次标识 `02:00:00` 不同。HTTP 缓存时间不解释为文章发布时间。PAGE_PRECISEPUBTIMESTAMP 是提供者额外元数据，未经正式字段语义核对暂不填入 published_at。

## 可实现的适配策略（本报告未实施）

1. 新增明确标记的 `gdelt_gkg` 免费发现能力，默认关闭，供用户选择；与 DOC 来源分别显示状态。固定 `data.gdeltproject.org` HTTPS，仅接受经过格式校验的官方索引和 GKG ZIP 路径，拒绝重定向、带凭据 URL、内网解析。
2. 每个批次全局获取一次，缓存去掉引语/媒体后的允许元数据；按各活动议题的 source_ids/config.topic_ids 范围与明确关键词/排除词在本地分配。没有关键词时不宣称“与该议题相关”。避免每议题重复下载整个文件。
3. 每次真实请求都使用同一 GDELT 提供者的持久日预算和间隔，包括 DOC 请求、索引和 ZIP、失败请求。索引和 ZIP 是两次预算操作，不能把一轮逻辑任务记成一次。配额用尽或过大文件应保留缺口并停止，不切付费服务。
4. 缓存与任务保存 index hash、batch、ZIP hash、阶段和分配进度。下载/校验失败不推进成功检查点；已完整缓存的批次再分配不重复联网。同 URL 在不同批次出现仍按稳定文档身份去重，保留批次出现信息；不能用每批不同 GKG record ID 强行制造新材料或多方证实。
5. 解析器需要固定列数/字段位置，严格限制压缩/解压字节、成员数、路径和压缩格式，防 ZIP 炸弹；不使用任意路径解压。现有通用抓取的 2 MiB 上限不足以容纳本次 2.28 MiB 文件，因此新通道需专属、显式上限而非全局无限放宽。
6. 最近更新索引只给最近批次。本次没验证历史清单、翻页、遗漏批次、翻译数据流或自动补采。30 分钟轮询一个 15 分钟最新批次会遗漏批次；界面应明确“仅最近批次／历史未补齐”，不能呈现连续全球覆盖。后续真正的有界历史补采必须另行验证官方历史索引。
7. 英语关键词只会匹配该字段所含文本，不能假定跨语种翻译检索等同 DOC。当前单批有多个来源，但“134 个域”不是 134 个独立来源链，也不是整体新闻覆盖率。

## 决策状态

可进入正式适配器实现与夹具测试；允许复用**已下载的真实响应**测试解析，但须标明重放，不能称又一次真实联网。完成后仍需要主应用来源配置、预算、缓存、覆盖、真实材料入库和浏览器验收；本报告本身不把 FR-02/AC-01/真实 GDELT 验证整体标为通过。
