# 当前进度（恢复入口）

2026-09-22：PRD 工程 M1—M3 已完成验收。私有 origin https://github.com/kokostad2000/world-insight 已确认，远端没有这份实现；只有本地提交，未推送。Python 3.11标准库 + SQLite WAL + 原生ES modules/SVG；运行时无npm/pip下载。

## 当前增量（取代下方历史状态）

- 收取凭据已完整接线：同一材料跨周重复成功收取只推进独立 `evidence_acquisition`，不改首次采集、发布时间、材料版本或变化事件；正式页面分列首次采集与最近收取，失败/304不推进。AC-04现通过。
- 恢复政策已完成写前、备份及恢复三处净化；正式恢复页面确认旧材料正文仍受限、固定版本/笔记/引用保留，人工重新核对只影响未来新材料。AC-19现通过。
- 10条真实官方材料已在新隔离库经正式HTTP人工登记、读回与history复核；8条Fed当前页成功，2条WDI保留当前页失败并只沿用既有真实API缓存。全部元数据权限、无正文，不冒充用户判断。
- 最终容量复测通过：20,000材料、5,000事件/说法、5并发；常用筛选API P95 0.360秒，5浏览器标签首可用P95 0.704秒。预跑发现并修复旧来源记录缺预算字段导致的500，正式40样本DOM全部有效且控制台0错误。
- 最新完整回归 **274项/41.455秒全部通过**（2026-09-22，含 M4 快照身份/绑定与真实 GKG 大小边界新增回归）；此前 272 项收束证据仍见 `docs/evidence/final-integration-20260921.md`。
- AC-26已在提交`00e5a5a`的中文／空格路径隔离副本完成真实Finder双击：启动PID 74719并由Edge自动打开8896正式页面；重复双击复用同一PID且只有一个监听/采集锁；双击停止后无监听，7来源/2任务/40材料保留。见`docs/evidence/finder-double-click-preparation-20260921.md`。
- AC-36 已在提交 `c3a5fc7` 的隔离数据目录完成真实合盖睡眠：同一 PID 28062、同一 instance_id 跨越 23,946 秒，醒后仍为单监听/单采集锁；调度器在有限预算内恢复，记录 23,276 秒与 1,155 秒两段 RSS 历史缺口。16 条材料/16 条收取凭据保持 v1、0 事件，正式页面与正常停止均已核对。见 [真实睡眠验收](evidence/mac-sleep-acceptance-20260922.md)。
- M4 本轮已建立专用持久库和5个非fixture候选议题，固定 instance_id、端口及显式来源范围；旧临时采集器正常停止且数据保留。正式 T0、实际检查人和用户议题确认仍缺，因此准备期请求、Fed/WDI成功与GKG失败/恢复均不计入七天。见 [试运行清单](evidence/m4-trial-20260922/README.md)。
- 试运行快照工具升级为同一 SQLite 读事务边界、运行健康身份、干净运行提交、历史fixture阻断、跨议题精确引用闭包和来源/任务版本历史；T0不得回填超过15分钟，daily/end必须绑定同一start快照，end在168小时前拒绝。机器证据仍不能替代每日真人用时/遗漏和50/20/10逐条抽查。
- 2026-09-22真实GKG批次为6,578,603 B压缩、20,389,639 B解压；有界上限调整为8/32 MiB，真实文件离线解析1,549条元数据，五题仅UNGA匹配4条、其余0条。见 [大小边界与验证](evidence/gkg-live-size-boundary-20260922.md)；成功不代表召回完整或达到M4数量门槛。
- M4试运行新增只读、不覆盖旧文件的`scripts/capture_trial_snapshot.py`：强制恰好五个非fixture议题，记录实例/提交/来源预算/任务/版本与时间引用，明确保留人工用时、遗漏、纠错和逐条50/20/10复核。[合成隔离验证](evidence/trial-snapshot-tool-validation-20260921.md)成功且数据库SHA-256前后不变；真实五议题和七天记录仍未开始。
- 主线已集成生命周期删除/备份预览/恢复、相似材料人工关联/移除/历史恢复、完整读取/历史/搜索/导出权限、source.policy_changed可靠传播、WDI国家范围交集，以及GKG默认关闭的免费备用元数据通道。
- 真实GKG正式Scheduler两次GET成功，间隔6.111764秒，623条元数据形成45条去重材料；全部待核查、无正文、发布时间未知，三个议题partial/latest-only。脚本默认dry-run不联网。正式8880浏览器确认共享预算2/2、6秒、上次成功、缺口说明及45材料。不能据此声称DOC已恢复或元数据召回语义准确。见gkg-live-scheduler及第二轮浏览器证据。
- 全历史权限每次扫描曾使5并发筛选P95达4.429秒；现以完整相关历史事实索引加每请求权限/期限判定降至最终筛选0.360秒、搜索0.489秒、bundle1.629秒。最终浏览器五标签40样本首可用P95为0.704秒，实际DOM与控制台已核对。见policy-performance-targeted.md与最终原始JSON。
- 备份恢复发现旧source配置会丢失后来更严格的期限后，已合入独立recovery_source_policy事实、写入前有效store剥离和备份/恢复渠道正文副本清理。SQLite字节级回归与正式页面均通过；常规改名不重新授权，显式重新核对仅影响新材料。
- Mac真实SIGKILL前后全records/versions/read_state/settings/附件清单一致；成功更新后新写入阻止回退，保留的当前恢复包又实际恢复至空目录。root运行start.sh（没有no-browser）后Edge自动打开8877，浏览器7条变化中的2条已读保持，判断v2→v3继续编辑，固定材料v1与3附件校验正确。已正常停止8877保留资料。见mac-browser-readstate-restore.json、mac-acceptance-remaining.md。
- 8878正式页面已验：11转载记录/1来源链/1未知；5和12并列争议；单方停火仅说法；已审阅假设标签保留；205判断与202复盘全量分页；来源收紧后旧版/搜索/实际JSON与Markdown均不泄漏正文，人工笔记固定引用保留。见browser-integration-round-two.md。
- 本轮并行开发已收束并合入本地主线；保留各worktree与隔离数据作为证据，不清理用户或代理文件。

## 当前剩余

1. AC-01—AC-36 与第 11.6 节 Mac 演练均已通过，PRD 工程 M1—M3 完成；Finder 与睡眠隔离实例均已正常停止并保留数据。
2. 50材料/20事件说法/10判断结构抽查仍未执行；空表和机器数量不抵扣逐条人工检查，且结构可追溯性与内容语义正确性分别解释。
3. 五个真实候选议题已在专用实例准备，但用户确认、实际检查人、正式T0、连续七天观察和约十分钟真实用时仍未开始；PRD M4保持待观察，不能用准备期或fixture替代。

下方早期进度保留作历史；当前状态以上述增量与Git/进程实测为准。

## 已合入

- 基线、PRD原稿、七模块共享契约、平台/研究/资料库/活动、真实免费来源、中文页面均已合入。
- main 37bd113：独立审查九项领域修复，73项自动回归通过（docs/evidence/independent-review-regressions.txt）。
- main a4622f9：web第二批浏览器验证，包含双窗口冲突保留草稿、全库引用搜索、真实底图及纠错依赖。
- main 0e4bba7：M7启动/检查/停止、备份恢复、独立目录更新与成对回退。19项真实Mac隔离进程测试通过；Finder GUI和恢复后浏览器仍待root验证。
- root新增生命周期基础、只读全历史扫描、已授权内容到期清理原语、采集provenance、人工重复登记笔记、阅读基线；46项领域与SQLite字节级测试通过，尚待完整生命周期模块和UI接线。

## 实际运行与证据

- root 真实来源隔离数据 /private/tmp/world-insight-real-acceptance；端口8766，当前进程6113，exec session54751。实际来源20条Fed RSS +20条WDI材料，非模拟；GDELT未通过（429/不合法响应），界面显示部分覆盖。
- root真实浏览器已创建议题7b3852f6-ae75-4a48-81d5-2a4e13ce60fe、登记官方FOMC材料、说法和有固定v2引用的人工判断。PID76571正常SIGTERM退出0，重启同数据为6113后判断成功编辑v2。审阅者明确为开发Agent元数据验收，不冒充用户判断或政策实施事实。
- web Agent 8872拥有独立 /private/tmp/world-insight-web-qa，全部标注隔离样本。root不得误停其他实例。
- docs/evidence/performance-capacity.json：2万材料/5千事件/5并发实际HTTP基准，dashboard API P95约0.93s、筛选0.37s；不等于浏览器首内容P95。
- 真实接入许可/时间/十条官方材料候选见 docs/evidence/source-research.md；十条人工复核登记尚未完成。七天观察未开始。

## 当前分工与未合入

- .worktrees/sources dev/sources：来源选择交集、scope状态、retention_days、collector标记已提交326f003；依赖root新ingest签名后合入验证。独立报告0ed7eba，措辞修正6727925。正在独立审查M7。
- .worktrees/ops dev/ops：M7首批e432214已合入。追加备份/恢复的source期限净化，并修独立审查发现的附件新写入回退漏洞与pending启动恢复漏洞。
- .worktrees/lifecycle dev/lifecycle：web Agent负责新增knowledge/lifecycle.py+tests+handoff；回收站预览/备份/确认、90天候选和来源较短正文期限。Store/app/共享契约root独占。
- .worktrees/web dev/web：9801ab8四处UI修复待合入。
- 子Agent出现过用量限制，已在本轮恢复运行；保留全部worktree，不重建。

## 下一步与验收边界

1. 合入来源新契约、生命周期和M7修复，跑完整集成回归。
2. 接通删除/保留UI和自动有限批次维护；补议题国家背景选择与全局WDI关联。
3. root实际Mac：全新中文/空格代码目录、Finder启动、配置阻断、恢复到空目录后浏览器继续编辑、干净代码目录更新/故障回退，保留证据。
4. 全量FR/AC审计并填写证据；当前AC矩阵仍待更新，不可因源码或局部测试宣称全通过。
5. 工程M1—M3尚未全部验收；PRD M4保持待观察。真实睡眠、五个真实议题连续七天、质量抽查及十分钟效率不能用fixture替代。

恢复时先检查 git status、worktree、实际运行句柄和交接，保留未提交工作。无购买、绑卡、公网发布、GitHub推送权限。
