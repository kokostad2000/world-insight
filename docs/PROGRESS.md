# 当前进度（恢复入口）

2026-09-21：工程持续实施。私有 origin 为 https://github.com/kokostad2000/world-insight；仅本地提交，从未推送。Python 3.11 标准库 + SQLite WAL + 原生 ES modules/SVG；运行时无 npm/pip 下载。

## 2026-09-21 恢复后的增量

- 主线已合入 source scope/国家背景选择、collector provenance、M7有限期限备份净化与附件回退保护、生命周期后端及32项运维/期限联合回归。
- 新增 `knowledge.lifecycle` 路由接线和持久化、有限批次自动维护检查点；迁移前恢复点执行合法内容净化。
- 独立审查报告见 `docs/handoffs/p0-audit.md`，八项具体问题。主线修复权限收紧重审传播、历史变化假设标签、渠道元数据保留、时区时间线、全库判断/复盘分页与搜索、旧未读通知、情景/路径待办编辑目标。结论变更筛选比较历史结论而非仅版本号。
- `python3 -m unittest discover -s tests -v` 实际146项通过，31.969秒，Mac隔离进程/SQLite/端口，见 `docs/evidence/integration-audit-round-two.txt`。随后结论筛选与呈现修订的11项针对回归通过0.330秒。自动测试不代替完整浏览器验收。
- 中文/空格路径全新本地clone，启动/重复启动/停止完成；从运行中的真实源库备份恢复到空目录，并在恢复实例8876浏览器修改旧判断v2→v3、议题国家/来源设置v1→v2，显示10条USA年度WDI观测。命令证据 `mac-clean-restore.json`，路径 `mac-gui-paths.json`。Finder GUI受辅助功能/录屏权限阻止，未冒充双击已通过。
- 当前并行：web Agent交付生命周期界面；sources Agent实现相似材料候选界面；ops Agent检查读取/导出时来源级权限及期限。三者独立worktree，root独占app/平台和集成。
- 七天观察仍未开始，10条官方手工复核及全量质量抽查尚未完成；GDELT有效响应尚未通过。AC矩阵仍需按证据逐项刷新。

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
