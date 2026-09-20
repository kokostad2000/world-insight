# 当前进度（恢复入口）

2026-09-21：工程持续实施。私有 origin 为 https://github.com/kokostad2000/world-insight；仅本地提交，从未推送。Python 3.11 标准库 + SQLite WAL + 原生 ES modules/SVG；运行时无 npm/pip 下载。

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
