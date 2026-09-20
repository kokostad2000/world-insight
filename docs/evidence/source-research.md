# 免费来源接入核对与真实请求证据

日期：2026-09-20；本机 macOS arm64；无凭据、无付费服务。研究先只读，随后在独立 `dev/sources` worktree 实现适配器。尚未完成 GDELT 材料读取、七天连续观察或生产级覆盖验收。

## 许可及字段边界

| 来源 | 官方依据 | 允许范围及本版边界 |
|---|---|---|
| GDELT | [许可](https://gdeltproject.org/about.html)、[DOC API](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/) | GDELT 数据可免费获取、存储、展示及再分发，需署名和链接；不延伸到原新闻全文/图片。本版只采标题、链接、语言、来源及提供者观察时间，AI 关闭。 |
| Federal Reserve Board RSS | [Feed 说明](https://www.federalreserve.gov/feeds/feeds.htm)、[版权](https://www.federalreserve.gov/disclaimer.htm) | Board 自有信息通常公共领域，按要求署名；第三方标注内容及标志不在此默认范围。本版采 RSS 标题、链接、pubDate、description，不抓图片或正文。 |
| World Bank GDP / Population | [GDP 指标许可](https://data.worldbank.org/indicator/NY.GDP.MKTP.CD)、[人口指标许可](https://data.worldbank.org/indicator/SP.POP.TOTL)、[总体条款](https://data.worldbank.org/summary-terms-of-use) | 两个指标页明确 CC BY 4.0；按 World Bank / WDI / 数据提供者署名，可存储、展示、导出。新指标须重新核对第三方条款，不能从 API 免费推导全部数据开放。 |
| Natural Earth | [公共领域条款](https://www.naturalearthdata.com/about/terms-of-use/)、[110m 国家层](https://www.naturalearthdata.com/downloads/110m-cultural-vectors/110m-admin-0-countries/) | 可固定发布、修改和再分发。下载 v5.1.2 GeoJSON；177 features；许可和 SHA256 在 `web/assets/world-countries.LICENSE.md`。静态离线底图，不调用瓦片服务。 |

未默认加入 UN RSS：本轮已找到许可明确且真实可达的 Fed feed，未核对的新闻源不因“官方”自动获得全文许可。任意 URL 登记不触发下载。新增采集域须由维护者审核许可和代码白名单；现有用户可先登记人工链接。

## 刷新、时间与历史含义

- GDELT：建议每议题 30 分钟、全源请求间隔至少 6 秒。真实 HTTP 429 返回要求每 5 秒最多一请求。ArticleList 默认 75/最大 250 条，无普通分页；返回上限时记录覆盖缺口，不能称完整。2018 官方[窗口更新](https://blog.gdeltproject.org/doc-2-0-updates-1-5-year-searching-and-updated-mobile-interface/)说明可查 2017-01-01 起、非 timeline 模式只考虑所给窗口最后 3 个月；本轮未验证深历史。本版自动补采策略最多 90 天，按 6 小时窗口推进检查点；超出本版上限显式记缺口，并不声称 90 天是供应商永久历史极限。DOC 返回 seendate 保留为 `provider_seen_at`；无法核实原文发布时间时 `published_at=null`。GDELT Event/GKG 15 分钟更新说明不能当 DOC 请求 SLA。
- RSS：每 30 分钟检查，已实测 ETag/Last-Modified，支持条件请求。`pubDate` 为源声明发布时间；本地 collected/discovered 是本地获取时间。Feed 只保留当前可见条目，无承诺历史窗口；睡眠后补读 feed 并记录无法保证完整的停机区间。304 保留缓存和原材料计数。
- WDI：每周检查。[V2 API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392)无需 Key，[查询文档](https://datahelpdesk.worldbank.org/knowledgebase/articles/898581)支持 source=2、分页、日期及 MRV。本版 20 国家以内、两白名单指标、近 5 年；null 不转为 0。响应 date 为观测年，lastupdated 是源数据集更新日，HTTP Last-Modified 和本地下载日不充当单项发布日期。没有逐条发布日期则保存 null。未找到明确固定免费请求配额，采用本地每日预算 20、周刷新和退避。
- 本地预算按 UTC 日重置。定时、手动和失败重试共用同一持久计数，先扣预算再联网；收费/AI 适配器始终禁用。刷新 API 只排队，网络请求不持有 SQLite 事务。

## 本机真实 GET

初始受限 sandbox 的 Python urllib 六域 DNS 失败，提权后 urllib 失败为本地 CA issuer 缺失；这不是上游故障证据。系统 `/usr/bin/curl` 保留 TLS 验证可连接，适配器因此使用系统 curl，绝不设置 insecure。固定域名白名单、解析公网地址、禁止重定向、20 秒上限和 2 MiB 上限；不读取 `.curlrc`。不修改系统代理或证书设置。

| UTC 时间 | 请求 | 实际结果 |
|---|---|---|
| 14:50:24 | GDELT query=climate, timespan=1d, maxrecords=5 | HTTP 429，正文要求每 5 秒最多一请求。未获得材料。 |
| 14:51:23 | GDELT climate change, timespan=15min, maxrecords=5 | HTTP 200，但正文 `Timespan is too short.`，不是 JSON；不得当正常空结果。 |
| 第三次（未单独记录时刻） | GDELT climate change, timespan=1h, maxrecords=5 | HTTP 429；此后停止重试，未绕过限流。 |
| 15:06:46 开始 | 交付的 `python3 -m server.modules.sources.probe --sources rss,world_bank` | 两源各一次真实 GET；无需 Key。见以下元数据。 |

Fed RSS：`https://www.federalreserve.gov/feeds/press_all.xml`，HTTP 200，14853 bytes，0.742 秒，20 条。ETag `"2a27c06a7e47dd1:0"`，Last-Modified `Fri, 18 Sep 2026 15:00:17 GMT`，最新 pubDate `2026-09-18T15:00:00Z`。响应 SHA256 `bdb248554aec56ffd75e93baae7b8096ffa7abe199cc8a5d7a2f4bb773541ad5`。

WDI：`https://api.worldbank.org/v2/country/CHN/indicator/NY.GDP.MKTP.CD;SP.POP.TOTL?source=2&format=json&mrv=5&per_page=200&page=1`，HTTP 200，2094 bytes，4.417 秒，10 条（两指标 × 2021—2025 年），数据集 lastupdated `2026-07-13`。响应 SHA256 `bf6850802ec6179e2caaccbeb492271d1839ec7f9a7d9920dc7b933d3586090d`。示例：CHN GDP 2025 = 19498039388042.6 USD；人口 2025 = 1406585000 persons。这是上游数值读取证据，不是独立经济统计复核。publication=null，period=2025。

上述已验证网络获取和适配器解析，尚不能代替应用入库/浏览器/重启验收，须由集成验收补齐。GDELT 网络限流情况须保留，不能用模拟数据称该源接入成功；Fed 官方新闻提供同类免费新闻通道，但不等价于 GDELT 的全球覆盖。

## 供人工登记复核的十条真实官方材料

来源均为上述真实 Feed。下列类别是按标题和原链接路径人工归类，不是正文事实已核实。用户/集成验收需要通过应用登记，并复核出处与时间；本表本身不宣称已经完成十条人工通道验收。

| # | 原文标题与 URL | 发布时刻 UTC | 材料类别 |
|---|---|---|---|
| 1 | [Federal Reserve Board announces termination of enforcement action with SNB Bancshares and Bank of Eufaula](https://www.federalreserve.gov/newsevents/pressreleases/enforcement20260918b.htm) | 2026-09-18 15:00 | 执法措施终止公告 |
| 2 | [Federal Reserve Board issues enforcement actions with former employee of Northstar Bank, former employee of American Express Travel Related Services Company, Inc., and former employee of Regions Bank](https://www.federalreserve.gov/newsevents/pressreleases/enforcement20260918a.htm) | 2026-09-18 15:00 | 执法措施公告 |
| 3 | [Federal Reserve issues FOMC statement](https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm) | 2026-09-16 18:00 | 货币政策声明 |
| 4 | [Federal Reserve Board and Federal Open Market Committee release economic projections from the September 15-16 FOMC meeting](https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916b.htm) | 2026-09-16 18:00 | 经济预测发布 |
| 5 | [Agencies seek comment on proposed third-party risk management guidance and issue statement on community bank engagement with core service providers](https://www.federalreserve.gov/newsevents/pressreleases/bcreg20260911a.htm) | 2026-09-11 14:00 | 监管指导征求意见 |
| 6 | [Agencies reduce regulatory burden for community banks, increase eligibility for 18-month exam cycle](https://www.federalreserve.gov/newsevents/pressreleases/bcreg20260910a.htm) | 2026-09-10 20:00 | 监管规则变更公告 |
| 7 | [Minutes of the Board's discount rate meetings on July 20 and July 29, 2026](https://www.federalreserve.gov/newsevents/pressreleases/monetary20260825a.htm) | 2026-08-25 18:00 | 贴现率会议纪要 |
| 8 | [Federal Reserve Board announces approval of application by National Westminster Bank Plc](https://www.federalreserve.gov/newsevents/pressreleases/orders20260820a.htm) | 2026-08-20 20:00 | 机构申请批准令 |
| 9 | [Minutes of the Federal Open Market Committee, July 28–29, 2026](https://www.federalreserve.gov/newsevents/pressreleases/monetary20260819a.htm) | 2026-08-19 18:00 | FOMC 会议纪要 |
| 10 | [Federal Reserve Board requests comment on a proposal to modernize rules for mutual banking organizations](https://www.federalreserve.gov/newsevents/pressreleases/bcreg20260731a.htm) | 2026-07-31 14:00 | 规则修订征求意见 |

## World Monitor 固定提交选型核对

实际 GET 了固定提交 `82e9e070e165b9a66d4df64ef690ef0bc9aa301b` 的 [LICENSE](https://github.com/koala73/worldmonitor/blob/82e9e070e165b9a66d4df64ef690ef0bc9aa301b/LICENSE) 与 [package.json](https://github.com/koala73/worldmonitor/blob/82e9e070e165b9a66d4df64ef690ef0bc9aa301b/package.json)，均 HTTP 200。LICENSE 是 GNU AGPL v3；package 声明 AGPL-3.0-only、版本 2.10.0，48 个直接依赖与 36 个开发依赖，含多套地图、Transformers/ONNX、Clerk、Convex、Upstash、S3、支付相关 SDK 和 Tauri 工具链。build 还串联 blog/pro/crawlable/sitemap 子构建。

这些依赖并非都必须购买服务，但裁剪和持续升级有实质维护成本；而本项目核心是不可变证据版本、人工研究和本地回退。建议保持独立领域实现，不复制该项目代码；AGPL 条件仅作为复用决策依据，具体分发/网络提供时另按许可证执行。本模块没有复制 World Monitor 代码或安装它的依赖。
