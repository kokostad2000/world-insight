# 当前进度（恢复入口）

2026-09-20：工程持续实施。初始 Git main 无提交、无现有文件；origin 私有 kokostad2000/world-insight。Mac Darwin arm64，Python 3.11.4，Node 24.2.0（非运行依赖）。PRD原稿与执行指令已读取并原样纳入。

- 已完成：环境检查、需求定位、七模块分工、共享 API/数据/事件契约、独立实现技术方案；基线379a9c9、平台762b89a、活动1187750均本地提交。
- 已实现：SQLite WAL事务、不可变版本、乐观冲突、原子迁移、持久outbox重试、回环HTTP/同源保护、变化/精确版本已读/模板简报。尚未据此声称完整FR/AC通过。
- 实际测试：`python3 -m unittest tests.test_platform tests.test_activity -v` 9项通过；`tests.test_http` 4项真实本地HTTP测试通过。前者证据见 docs/evidence/platform-activity-tests.txt。平台迁移测试为故障注入，不等于整套Mac更新回退验收。
- 实际运行：root隔离服务 `python3 -m server.app --data-dir /private/tmp/world-insight-platform-smoke --port 8766 --no-scheduler`，健康和空首页API实际200；页面尚待合入，不等于浏览器验收。
- 并行任务：`.worktrees/core` dev/core负责knowledge/research；`.worktrees/web` dev/web负责中文界面；`.worktrees/sources` dev/sources负责免费源。测试数据和端口独立。其尚未交付功能需合并后整体重测。
- 下一步：核心首批合入→Web真实浏览器闭环→重启编辑；来源/运维/完整边界继续补齐。运维scripts尚未实现，不能宣布可一键交付。
- 权限边界：允许本地开发、依赖和服务；不推送 GitHub/付费/公网发布。
- PRD 里程碑：M1 进行中（页面待审查）；M2/M3 实施中未验收；M4 待观察（七天未开始）。
- 证据：docs/evidence/；子任务交付：docs/handoffs/。

恢复时先检查 git status、git worktree list、各交付和实际进程，再续做，不重建已完成工作。
