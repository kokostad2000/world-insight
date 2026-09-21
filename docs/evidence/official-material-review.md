# 10 条真实官方材料：开发验收登记与元数据复核

2026-09-21。产品基线 `39e5901`。已在独立新 SQLite 中通过正式 HTTP 人工登记 10 条真实官方材料，并逐条 GET 及 history 读回。**8 条 Fed 材料完成本次官方页面核对；2 条 WDI 材料仅完成既有真实 API 缓存复核，本次指标页面分别 504、超时。** 这是开发 Agent 依授权进行的元数据复核，不是用户本人的研究判断，也不代表政策执行、预测或统计值已被独立证实。

10 条分属 8 个登记类型：货币政策声明、经济预测发布、会议纪要发布、监管征求意见、监管规则发布、机构申请批准发布、执法措施终止发布、统计数据集。两个会议纪要归为同类，GDP/人口同属数据集；没有用子标题冒称 10 种互斥类型。本批没有讲话、证词或独立的数据方法说明文档。

## 数据与复核范围

- 原库只读：`/private/tmp/world-insight-real-acceptance/world-insight.sqlite`；使用 SQLite `mode=ro`、`query_only` 和一致性读事务选材，不修改其材料/来源/任务。缓存中有 20 条真实 Fed 发布材料、20 条 WDI 观测材料。
- 新隔离目录：`/private/tmp/world-insight-official-review-20260921`；数据库 `world-insight.sqlite`。新实例没有启动 Scheduler；全部来源停用，3 个议题暂停且不关注。
- 真实官方 GET：2026-09-21 **06:35:43.382517Z—06:36:25.745105Z**，恰好 10 次，每个选定 URL 一次；严格 TLS、连接 8 秒/总计 20 秒、响应 1 MiB 上限、不重试、不跟随重定向、不加载子资源。未访问第三方新闻，也未取正文附件或会议纪要 PDF。
- HTTP 页面响应只在内存中提取标题、标题元标签、发布日期与许可链接，不保存 HTML/正文。保留每次 URL、状态、字节数、SHA256、TLS 结果和抽取的元数据。所有 8 条成功页 `ssl_verify_result=0`。
- 逐条复核决定写入于 **06:38:49Z**（微秒时刻分别保留在 `review-decisions.json`）；复核者明确为“Codex 开发 Agent（授权的开发验收元数据复核，不代表用户本人研究判断）”。
- 正式应用 HTTP 登记及读取：**06:39:18.322945Z—06:39:18.401039Z**，使用随机空闲端口 **63340**，共 42 次本地 API 请求，全部 HTTP 200。完成后关闭服务；06:40:54Z 再检查确认该监听已关闭。

复核方法 **F**：对照只读原缓存与本次官方页面的 `og:title`、页内标题、Board of Governors 发布者标识及页内发布日期。8 条标题逐字相符、日期一致。精确 UTC 时分秒来自原先官方 RSS `pubDate`；本次页面只复核到日期，不能把页面日期声称成独立时分核验。

复核方法 **W**：只读核对既有真实 WDI API 材料及其关联 observation 的指标、国家、观测年、单位与未知发布时间，保留本次页面访问失败。中文材料标题由系统用指标名称/国家/年份组成，不是官方网页标题逐字抄录。没有再次请求 WDI API。

发布者 **FRB** = Federal Reserve Board（官方承载页面为 Board of Governors of the Federal Reserve System）；联合新闻稿不据此声称 FRB 是唯一联合发布机构。**WDI** = World Bank / World Development Indicators。

## 逐条核对与登记结果

以下发布时间均为 UTC；每条具体复核结论、原库 ID/版本、当前 ID/版本和复核时间均写入新材料 notes 与 JSON 报告。材料状态 `reviewed` 仅表达这次元数据审阅，不表达事实已证实；notes 明确限定开发验收。

| # | 官方材料标题与 URL | 登记类型 / 发布者 | 发布时间及精度 | 议题 / 方法 / 当前页结果 |
|---|---|---|---|---|
| 1 | [Federal Reserve issues FOMC statement](https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm) | 货币政策声明 / FRB | 2026-09-16 18:00:00，RSS 精确时刻；页面日期 09-16 | 货币与会议 / F / 200 |
| 2 | [Federal Reserve Board and Federal Open Market Committee release economic projections from the September 15-16 FOMC meeting](https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916b.htm) | 经济预测发布公告 / FRB | 2026-09-16 18:00:00，RSS 精确时刻；页面日期 09-16 | 货币与会议 / F / 200 |
| 3 | [Minutes of the Board's discount rate meetings on July 20 and July 29, 2026](https://www.federalreserve.gov/newsevents/pressreleases/monetary20260825a.htm) | 贴现率会议纪要发布 / FRB | 2026-08-25 18:00:00，RSS 精确时刻；页面日期 08-25；不作会议发生日 | 货币与会议 / F / 200 |
| 4 | [Minutes of the Federal Open Market Committee, July 28–29, 2026](https://www.federalreserve.gov/newsevents/pressreleases/monetary20260819a.htm) | FOMC 会议纪要发布 / FRB | 2026-08-19 18:00:00，RSS 精确时刻；页面日期 08-19；不作会议发生日 | 货币与会议 / F / 200 |
| 5 | [Agencies seek comment on proposed third-party risk management guidance and issue statement on community bank engagement with core service providers](https://www.federalreserve.gov/newsevents/pressreleases/bcreg20260911a.htm) | 监管指导征求意见公告 / FRB，页面标 Joint Press Release | 2026-09-11 14:00:00，RSS 精确时刻；页面日期 09-11 | 银行监管 / F / 200 |
| 6 | [Agencies reduce regulatory burden for community banks, increase eligibility for 18-month exam cycle](https://www.federalreserve.gov/newsevents/pressreleases/bcreg20260910a.htm) | 检查周期规则公告 / FRB，页面标 Joint Press Release | 2026-09-10 20:00:00，RSS 精确时刻；页面日期 09-10 | 银行监管 / F / 200 |
| 7 | [Federal Reserve Board announces approval of application by National Westminster Bank Plc](https://www.federalreserve.gov/newsevents/pressreleases/orders20260820a.htm) | 银行机构申请批准公告 / FRB | 2026-08-20 20:00:00，RSS 精确时刻；页面日期 08-20 | 银行监管 / F / 200 |
| 8 | [Federal Reserve Board announces termination of enforcement action with SNB Bancshares and Bank of Eufaula](https://www.federalreserve.gov/newsevents/pressreleases/enforcement20260918b.htm) | 执法措施终止公告 / FRB | 2026-09-18 15:00:00，RSS 精确时刻；页面日期 09-18 | 银行监管 / F / 200 |
| 9 | [GDP（现价美元）· CHN · 2025](https://data.worldbank.org/indicator/NY.GDP.MKTP.CD?date=2025&locations=CHN) | 年度统计数据 / WDI | 发布未知 `null`；观测年 2025；数据集更新日 2026-07-13，不能替代发布日期 | 国家背景 / W / 504，15.800 秒，无重试 |
| 10 | [人口总数 · CHN · 2025](https://data.worldbank.org/indicator/SP.POP.TOTL?date=2025&locations=CHN) | 年度统计数据 / WDI | 发布未知 `null`；观测年 2025；数据集更新日 2026-07-13，不能替代发布日期 | 国家背景 / W / curl 28，20.039 秒，无 HTTP 响应、无重试 |

第 2 条仅是预测发布，未下载预测附件或验证预测。第 3、4 条复核的是纪要**发布页**，未声称审阅纪要全文。第 5 条是 proposed / seek comment，不称最终规则已实施。第 6 条不推断法律生效和执行情况。第 7、8 条不把发布页当法律文件全文。

WDI 本地交叉核对：GDP observation `21bfa148-13d7-4552-a43c-04ddfac08ece@1` 引用原材料 `c14fe656-58e4-49ed-8e84-740c2734f207@1`，CHN/2025/19498039388042.6 USD；人口 observation `d141e17b-46c2-405d-b71b-6e91c58da993@1` 引用 `6821b1c4-55d3-4a6a-a41f-9ceddcb62137@1`，CHN/2025/1406585000 persons。仅核对缓存一致性，不构成经济或人口统计的独立核实。

## 许可与可保存范围

本次没有额外 GET 许可全文，沿用 [2026-09-20 来源预研](source-research.md)中已经登记的出处；未以“官方”自动推出所有正文/图片都能保存。

- **第 1—8 条**：依据来源登记的 [FRB disclaimer](https://www.federalreserve.gov/disclaimer.htm)，既有预研区分 Board 自有信息与第三方内容/标志。本次未审阅附件及第三方标注，全部按更保守元数据范围处理。
- **第 9—10 条**：既有预研记录两指标页的 CC BY 4.0 及 [World Bank 使用条款](https://data.worldbank.org/summary-terms-of-use)。本次页面失败，未重新确认页面许可；仍只保存标明 World Bank/WDI 的指标身份、出处与时间元数据，不拓展到其它指标/第三方数据或正文。
- **全部 10 条实际保存授权**：`fetch=false, store=metadata, display=metadata, export=metadata, ai=false`；`excerpt=''`、`translation=''`，无图片、全文或正文指纹。保存开发 Agent 自写的复核笔记、真实原始链接、标题、发布者和来源声明时间。人工登记没有触发抓取。

## 新库身份与正式接口验证

| # | 新材料 ID，均 `@1` | 类型字段 |
|---|---|---|
| 1 | aa75a5c9-57fd-45b3-a71a-2ed4ddc8e12b | official_statement |
| 2 | 07cb5927-a78f-4229-aa63-86d6452aa3b9 | economic_projections_release |
| 3 | 953c9e61-7960-456f-939a-834732781571 | meeting_minutes_release |
| 4 | 7d5c3651-cf87-4880-8a7a-8ff353a9039b | meeting_minutes_release |
| 5 | 5844e3f6-cd72-4198-a417-a3efcee3c91e | consultation_release |
| 6 | 48d6b9d9-1696-409d-ae7a-2a5b8ef299d2 | regulatory_rule_release |
| 7 | 4b09269d-2067-4e84-b65a-59dcda76d52d | approval_release |
| 8 | d1c32fd5-f670-4da1-bff9-7bdb373a35db | enforcement_release |
| 9 | 92e7d0d9-b32a-4645-bd27-b56fdb796b3a | dataset |
| 10 | e74971bf-89c4-4f23-bb8f-01d06aa4634b | dataset |

三个议题均明确以“开发验收复核”命名：货币政策与会议发布 `e9328d30-e42a-4b3f-af44-ddfef332c48b`、银行监管发布 `42faa590-63c6-4a5f-a2ab-520383043f73`、WDI 国家背景数据 `42079632-3adf-472e-be2b-22222ae1a584`。前两者指定 source-fed/USA，后者 source-world-bank/CHN；均 paused、followed=false。

真实 `POST /api/evidence` 使用默认 `origin=manual`，不向 body 伪造内部 origin 字段；逐条 `GET /api/evidence/<id>`、`.../history` 验证：

```text
material_count=10
all_manual=true; all_real=true; all_metadata_only=true; all_single_version=true
claims=0; events=0; judgments=0
acquisition_receipts=0; collection_jobs=0
SQLite=ok; foreign_key_errors=0; version_errors=0; reference_errors=[]
```

停止后的只读检查：全部来源 disabled、provider requests_today 均 0、63340 无监听、无 runtime.json、SQLite integrity=ok。这里的 10 次外部 GET 是验收脚本的明示只读页面核对，不是应用自动采集；未把它们写成提供者采集任务或假借 manual 登记刷新采集凭据。

## 可复查脚本与证据文件

脚本 [verify_official_review.py](../../scripts/verify_official_review.py) 默认只读原缓存，输出候选报告，零网络、零数据库登记。两个执行阶段必须分别显式选择：

```bash
python3 scripts/verify_official_review.py
# 新的空目录，最多10次GET；已执行本批，勿为复核重复联网：
python3 scripts/verify_official_review.py --check-official --data-dir NEW_EMPTY_DIRECTORY
# 先逐条核对生成的元数据并准备 review-decisions.json，之后才登记：
python3 scripts/verify_official_review.py --register --data-dir REVIEW_DIRECTORY \
  --review-decisions REVIEW_DIRECTORY/review-decisions.json
```

网络阶段拒绝非空目录；登记阶段必须有 10 条明确的逐项决定及复核者、时间、方法和结果，拒绝既有数据库。默认只读路径、本地解析器“不复制正文”和首个标题不被图标 `<title>` 覆盖的检查已实际通过。

本批最初的 HTML 提取器 `title` 字段取到最后一个 `<title>`（值为 `Lock`），所以逐条核对实际使用了 **og:title 与可见标题**，没有把 `Lock` 当新闻标题。已修复脚本保留首个标题并用本地样例验证；原请求报告保留原提取值，没有为了修提取器重发 GET，也没有伪造新响应。

保留目录中的可复查文件：

| 文件 | 内容 | SHA256 |
|---|---|---|
| `official-checks.json` | 原缓存身份、10 次 GET 状态/校验值、页面元数据；无正文 | `168b515c4dfa0b493d7ba30fb8701bc4c147afdab6083764672f9cb25c900d88` |
| `review-decisions.json` | 逐条复核时间、方法、结论、8 条页面成功/2 条缓存降级 | `0c509dbab652fff699b666c5fe0db133b6f3aa5d3625f3896ea36506dc4460dc` |
| `registration-report.json` | 42 次真实 HTTP 状态、3 议题、10 条登记与读回、完整性结果 | `193a677f3c7aafa9201344a2222d8c2aadb980e9618812ec3fa3bf2064dfdacc` |
| `post-stop-check.json` | 停止、来源关闭、请求为零及只读完整性检查 | `cdc51523a0e77dcdc124417039543693197790bdd71dc0275812de7764625684` |

这些文件和 SQLite 保留在 `/private/tmp/world-insight-official-review-20260921`，未自动删除。后续如需浏览器查看，由 root 在确认空闲端口后以 `--no-scheduler` 打开该目录；本批不占用其它任务服务，也不声称浏览器验收或七天真实研究观察通过。
