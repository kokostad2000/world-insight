# 来源正式页面验收：AC09 / AC10 / AC23 / AC27

2026-09-21，macOS 本机 Edge 后台独立标签 `1006907404`，真实应用端口 `8891`。本批四个指定分支通过；AC09 首次发现首页缺少逐源上次成功时间，应用 root 的一行修复后精确复验通过。该修复由 root 提交，本交付不包含产品文件。

## 归属、版本与边界

- 只新增 `tests/source_browser_fixture.py` 与本文件。无 API 变更，无产品实现改动。
- 正式浏览器服务使用 `c40306e` 已加载的 Python，实现仍为真实 `server.app.serve`、静态页面、路由、领域函数、SQLite、outbox 和 `sources.Scheduler`。只在测试入口注入上游响应和 Store 时钟，不生成替代页面，不加入测试 HTTP 路由。
- AC09 修复复验只将 root 工作区的 `coverageNotice` 函数替换到本 worktree；复验后逐字还原原行。原行与修复行保留在隔离证据目录。仅替换静态文件没有被当作 Python 已升级。
- 随后合入 `main 309da31`（含 GKG 及共享提供者配额重构），另建空库回放四组真实 Scheduler 条件，全部断言通过。该次是新版后端回归，**不是新版本浏览器验收**。
- 所有材料、议题、判断都显示 `[隔离验收]`，上游响应和超时是注入样本，不是真实联网。调度时钟推进 60 秒、60 秒及 86400 秒只修改 fixture 内 Store 时钟，没有修改系统时间，不是系统睡眠或七天观察证据。
- 不访问外部材料链接，不用 Finder，不触碰 root 的 8877 实例或浏览器标签。AI/付费来源始终关闭。

## 原始证据位置

正式浏览器数据目录：`/private/tmp/world-insight-source-browser-20260921c`。

| 文件 | 保存内容 |
|---|---|
| `fixture-warm.json` | 两新闻源成功预热、请求清单、来源状态、两条材料固定版本与整体摘要 |
| `fixture-ac09.json` | 初次两个新闻源均 timeout 后的真实调度状态 |
| `fixture-ac23.json` | RSS 成功空结果、GDELT timeout 后的 partial |
| `fixture-ac10.json` | RSS 4/4 后连续三次额外手动点击，仍只有 4 次适配器调用 |
| `fixture-after_invalid.json` | 无效来源表单提交后，原配置及调用数未变 |
| `fixture-ac27-judgment.json` | 浏览器保存后的判断 v2 原始记录 |
| `fixture-ac09_recheck.json` | 修复复验：两源再次 timeout，成功时间与旧缓存保留 |
| `coverageNotice-original.txt` / `coverageNotice-root-fix.txt` | 临时静态修复前后的精确函数行 |
| `verification.log` | 对上述保存事实逐项执行断言的输出 |

议题 ID：`2afc1825-c724-4cc0-8526-b84ddc994ac5`。判断 ID：`2692322b-35ee-404c-ad2f-a59792fefce2`。

缓存固定版本：`92f52b89-d73d-4dfb-959a-17f16923b87f@1`（RSS），`5b0e4f90-c175-4f0d-9525-87929c86cecd@1`（GDELT）。以上各阶段证据总数始终 2；完整材料记录 JSON 的 SHA-256 始终为：

```text
e3630531f7bcc4d8cdc90529aa1c9fa007aaaa15811522a069366d8a0ceec376
```

## 正式浏览器操作与实际观察

### AC09：全部启用新闻源超时

1. 实际来源页确认 Fed RSS 与 GDELT DOC 启用并各有缓存。WDI 停用，AI/付费未配置。
2. 控制注入 `timeout_all`，调度时间前进 60 秒，在来源页分别点击 GDELT、RSS 的“检查来源”。真实 Scheduler 处理 UI 产生的任务。
3. 来源页两者显示“失败”，最后尝试为 2026/09/21 10:53，最后成功仍为各自 10:52；缓存两条不变。
4. 首页显示“不可用”和“本轮来源检查未完成或不可用，无法判断新增，已有历史缓存仍可阅读。”没有显示全范围无变化。但首页初版没有上次成功时间，故初次结论为失败并报 root，未以来源页有时间替代首页要求。
5. root 修复 `coverageNotice` 后临时加载同一行。为覆盖**两源均 timeout + 修复后的首页**精确组合，在完成其余分支后将 fixture 时钟前进一天，真实调度器重试两项积压任务；没有改机器时间。JSON 两源均 `failed`，最新尝试为 `2026-09-22T02:54:54.913807Z`，两次调用都来自 `timeout_all`。
6. 正式首页实际 DOM 文字：

```text
不可用
本轮来源检查未完成或不可用，无法判断新增，已有历史缓存仍可阅读。
美国联邦储备委员会 RSS · 上次成功：2026/09/21 10:54
GDELT 新闻发现 · 上次成功：2026/09/21 10:52
```

来源页复查两者均“失败”，最后尝试 9/22 10:54、最后成功分别 9/21 10:54 和 10:52。RSS 在中间 AC23/10 分支曾成功，因此此处不是错误地要求两者都保持预热值。`fixture-ac09_recheck.json` 对照 `fixture-ac10.json`，逐 ID 的 `last_success` 完全相同；两条缓存与版本也完全相同。

结论：指定故障注入分支通过，依赖 root 将已实测的首页修复保留到主线。

### AC23：一个来源成功空结果，另一个仍失败

注入 `empty_rss_timeout_gdelt`，只将 fixture 时钟推进 60 秒，由真实调度器执行原有重试任务。RSS `last_result_count=0`、`data_status=fresh`，GDELT `failed/stale`；总覆盖 `partial`、`empty_reason=null`。

来源页和首页实际显示：

```text
部分覆盖
部分来源检查失败、陈旧或存在采集缺口，无法确认全范围没有变化。
```

来源页 RSS 显示可用、3/30、最后成功 10:54；GDELT 显示失败、6/30、最后成功 10:52。首页仍能看到旧 RSS/GDELT 缓存条目，没有把空结果说成全范围没有变化。通过。

### AC10：边界配额与重复点击

1. 实际打开 RSS“设置”，当日已有 3 次调用，通过正式表单将“每日免费请求上限”从 30 保存为 4。
2. 注入恢复 `success`，在来源页点一次“检查来源”，完成第 4 次适配器调用。
3. 在同一来源卡片连续另外点击三次“检查来源”。每次操作后重新读取正式卡片；三次都显示：

```text
免费配额已用尽
免费请求 4 / 4 次 / 日
下次检查 2026/09/22 08:00
本地每日免费请求预算已用尽。
```

4. 实际调用总数仍为 RSS 4、GDELT 6，未出现第 5 次 RSS 请求。任务保持重试和检查点，UI 提示已有排队任务，未重复增加请求。AI/付费保持 disabled，未发生付费回退。
5. 从真实首页打开 `[隔离验收] RSS 历史缓存通告`，详情可读、固定版本 v1、发布时间 9/18 23:00、采集时间 9/21 10:52；没有点击外部原文链接。两条缓存摘要不变。通过。

### AC27：无效来源配置被拒后继续人工研究

1. 来源页打开 RSS 设置 v12，把 RSS 地址填写成 `https://example.org/unapproved.xml` 并点“保存来源”。这是提交给本机表单的无效配置，未访问该地址。
2. 实际对话框保留输入，显示 alert：

```text
P0 RSS 仅支持已核对许可的 Federal Reserve /feeds/ 地址；其他来源先用人工链接登记。
```

3. 点击“取消”，`fixture-after_invalid.json` 与 `fixture-ac10.json` 中来源记录逐字段相同，RSS 仍为 v12、正式 Fed feed URL；实际适配器调用仍 4/6。
4. 进入“我的判断”，编辑原草稿 v1，填写结论 `[隔离验收] 无效来源配置被拒后，人工研究仍可保存` 和修订原因，点“保存判断”。页面提示保存成功，出现“版本 2”。实际重新加载页面后，结论和 v2 保留。
5. 只读 SQLite 核对判断 v2，并确认 v1 仍保留原结论。通过本次“错误来源配置 + 核心编辑可用”分支；AC27 的全部其他启动/网络探测分支仍引用各自独立证据，不由本次扩大认定。

## 实际计数与校验日志

`python3 -m tests.source_browser_fixture --data-dir /private/tmp/world-insight-source-browser-20260921c --verify-acceptance` 实际退出 0。该命令校验保存的后端事实，不冒充再次操作浏览器。

```text
warm          complete     rss=1 gdelt=4 cache=2
ac09          unavailable  rss=2 gdelt=5 cache=2
ac23          partial      rss=3 gdelt=6 cache=2
ac10          unavailable  rss=4 gdelt=6 cache=2
after_invalid unavailable  rss=4 gdelt=6 cache=2
ac09_recheck  unavailable  rss=5 gdelt=7 cache=2
PASS: captured AC09/10/23/27 backend assertions; browser observations are recorded separately
```

第一次临时断言误按来源列表位置比较成功时间，因列表按更新时间重排而失败；改为按来源 ID 对照后严格断言通过，没有放宽状态或时间要求。该问题只在验收脚本，不是产品丢失成功时间。

## 主线 GKG 合入后的增量回归

浏览器完成后检测到主线含 GKG 与共享配额改动，合并 `309da31` 后另在空目录执行：

```bash
python3 -m tests.source_browser_fixture \
  --data-dir /private/tmp/world-insight-source-scheduler-replay-309da31 \
  --replay-scheduler
python3 -m unittest tests.test_sources tests.test_sources_coverage tests.test_sources_gkg -v
```

Scheduler 回放退出 0，四组状态及 1/4→2/5→3/6→4/6→5/7 计数严格相同，人工判断 v2/旧 v1 均保留，新 GKG 来源明确停用。新库材料 SHA-256（ID/采集时间不同，不能与上一库比较）为 `bbb0f10c9234158827540d1bcc9f04dfc9a79ee65e1b1e91b93264eb789c95bf`，在该库全部阶段保持不变。原始输出 `/private/tmp/world-insight-source-scheduler-replay-309da31.log`；各阶段 JSON 在同名目录。

来源回归实际 `Ran 53 tests in 0.361s / OK`，进程退出 0；完整逐测试名称和结果见 `/private/tmp/world-insight-source-browser-regression-309da31.log`。`python3 -m py_compile tests/source_browser_fixture.py` 退出 0，`git diff --check` 无输出。

## 重跑与清理

必须使用新且明确隔离的数据目录；脚本检测已有 `world-insight.sqlite` 时拒绝复用，不清空现有数据：

```bash
python3 -m tests.source_browser_fixture --data-dir /private/tmp/world-insight-source-browser-new --port 8891
python3 -m tests.source_browser_fixture --data-dir /private/tmp/world-insight-source-browser-new \
  --control --mode timeout_all --advance-seconds 60
```

浏览器步骤完成后可单独发 `--control --label ac09` 等命令保存阶段；控制命令先保存当时快照再运行 tick，因此应在浏览器已经显示任务完成后保存最终 label，不能把切换模式前的状态冒充完成状态。`--replay-scheduler` 是不启动 HTTP/浏览器的独立回归入口；它会创建新库并调用真实领域入口及 Scheduler。

原正式服务 PID `88317`、instance `d2d99b3f-9276-4ac4-bf2d-168e74e336fc`，只属于 8891 的本次 fixture。root 曾要求保留至修复复验完成；复验结束后关闭自己的 Edge 标签，重新核对 runtime 的 PID、端口、数据目录及 instance 后仅向该 PID 发 SIGTERM，原 exec session `48306` 实际退出 0。保留隔离证据目录，不删数据库或原始输出。合入顺序：已有 `309da31` → 本验收提交；root 同时提交 `coverageNotice` 的已验证修复。无 GitHub 推送。
