# 实施计划与技术决定

## 基线

2026-09-20；源需求完整保存在 PRD.md 与 AGENT_EXECUTION.md。项目空目录，无已有修改。私有 origin 已关联；本轮仅本地提交。

## 架构 ADR-001

独立实现领域模型。Python 3.11 标准库 + SQLite WAL + 原生 ES modules/SVG 中文桌面界面，单机单进程，同源提供 API 与页面。无运行期包下载，无 Node 构建依赖；Python 版本与零第三方依赖记在 requirements.lock。Mac 已有 Python 3.11.4。Compose 是 PRD 建议而非强制；本机安装 Docker 会增加准备成本，本版不采用。

World Monitor 可提供观察思路，但研究判断、材料不可变版本、纠错与本地成对回退需要独立契约；复用原项目意味着承担与 P0 无关的数据源和部署依赖。代码与地图资源的许可证需分别核查，未核实前不复制第三方应用代码。来源预研证据随后附录。

HTTP 服务仅回环，校验 Host/Origin、请求体大小；外部内容转义。SQLite事务+乐观版本锁+不可变历史；根负责人独占迁移登记。标准库 HTTP 服务针对个人本机，不声明公网部署能力。跨模块可靠 outbox 事务性重试，禁止跨域直接写表。数据位置与程序目录分离，首次初始化显式确认。

## 七模块与唯一写入权

| 模块 | 目录 | 数据/责任 | 本轮负责 |
|---|---|---|---|
| M1 | packages/contracts、server/platform | 契约、Store、迁移、错误、配置、集成路由 | root 唯一 |
| M2 | server/modules/sources | 来源、配额、采集任务、补采与缺口 | sources worktree |
| M3 | server/modules/knowledge | 材料身份、版本、去重、出处、说法、事件、指标 | core worktree |
| M4 | server/modules/research | 议题、判断、情景、路径、复盘、重审状态 | core worktree |
| M5 | server/modules/activity | 变化、已读、提醒、模板简报 | root 后续 |
| M6 | web | 页面、交互、地图、可访问性 | web worktree |
| M7 | scripts、ops、根启动文件 | 运行、备份恢复、更新回退 | ops worktree 后续 |

具体 API 以 packages/contracts/README.md 为唯一基线；变更先由 root 更新。依赖锁文件与 server/app.py 也只由 root 写入。

## 执行顺序

1. 基线：完整需求、FR/AC映射、契约、物理目录；本地提交后创建独立 worktree。
2. 闭环：root基础设施；core实现 M3/M4；web实现 M6。先集成真实 SQLite 和浏览器创建议题→材料→说法/事件→判断→重启编辑。
3. 补齐：sources采集、activity提醒简报、ops本地运维。每批合并后重新验证。
4. 整体验收：FR/AC逐项行为，浏览器实操，真实免费源，Mac运行/恢复/更新/失败回退，独立审查与性能基准。
5. 试运行入口：五个真实议题/七天记录/抽查/10分钟效率；`scripts/capture_trial_snapshot.py`只读固化每日机器可观测字段，人工用时、遗漏、纠错和逐条抽查仍按`docs/TRIAL.md`真实填写。未真正满七天保持 PRD M4 待观察。

## 隔离与交接

worktree 位于 `.worktrees/<name>`（被忽略），短期分支 `dev/<name>`；数据在各自 `.test-data` 或 `/private/tmp/world-insight-<name>-*`，端口 core 8871/web 8872/sources 8873/ops 8874，root 8766；禁止共享采集实例。主工作区负责集成。

交付 docs/handoffs/<name>.md：文件、API差异、实际测试、未验证、合入顺序。先提交后由 root 合并，保留分支。不推送 GitHub。
