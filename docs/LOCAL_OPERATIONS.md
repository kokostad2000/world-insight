# 本地运行与故障处理

运行引擎是 CPython 3.11 + SQLite，当前范围为 macOS，未声明 Linux/Windows 或容器验收。所有命令经 `scripts/run-ops.sh` → `ops.cli` 调用。日常双击入口与终端使用同一路径；含中文/空格的目录通过引用参数传递。

## 存放位置与所有权

| 位置 | 内容 | 清理/更新行为 |
|---|---|---|
| 原代码目录 | Git 代码、忽略的 `.env` | 更新不重置、不清理；脏工作区阻断 |
| 外部数据目录 | `world-insight.sqlite`、`instance.json` | 必需研究状态；不自动创建替代既有缺失库 |
| `attachments/` | 允许保存的用户附件 | 一并备份，符号链接拒绝；附件不要放秘密配置 |
| `cache/`、`logs/` | 可重建缓存、脱敏运行/运维日志 | 不纳入默认备份；不会清理研究库 |
| `active-program.json` | 已选程序绝对路径及目标提交 | 更新成功后原目录启动沿此选择 |
| `runtime.json`、`service.lock` | 进程身份、端口、数据目录、实例ID | 正常停止移除 runtime；不凭 PID 单独结束进程 |
| `maintenance.json`、`updates/` | 更新阶段和恢复入口 | 中断保留，显式 recover 后处理 |
| 同级 `World Insight Programs/` | 已准备的独立程序版本 | 不自动删除旧版本 |
| 默认同级 `World Insight Backups/` | `.wibackup`、未完成 `.partial` | 不覆盖旧包，不自动轮转恢复点 |
| 同级 `*-restore-point-*` | 替换前数据库/WAL/附件/实例文件 | 保留可恢复旧状态，由用户自行管理 |

运行中在线备份使用 SQLite backup API；附件在复制前后再次核对集合及哈希，变化时整包拒绝成功。恢复在临时相邻目录校验，目标停止后按文件原子替换，任何替换异常会把已移走文件换回。备份包 `manifest.json` 含程序提交、schema、计数、不可变版本数、文件长度与 SHA256。恢复验证材料版本/说法/判断引用，绝不提取清单外文件。

## 常见故障

- 缺 Python 3.11：完成 README 首次准备，设置 `WORLD_INSIGHT_PYTHON`，重新检查。无 Docker/Node 依赖。
- 数据目录无权限：选择本用户可写目录。检查会真实创建并移除临时探针；不会修改已有研究内容。
- 端口被占用：配置另一端口，或用原端口停止自己确认的实例；脚本不会结束其他程序。
- `instance.json` 有而数据库无：停止，不建新库。核对配置路径或恢复有效备份。
- 源失败/可选 Key 缺失：保留历史阅读，页面显示逐源覆盖。默认配置检查不联网，显式 `--probe-network` 才调用免费源。
- 启动未健康：不打开浏览器；查看数据目录 `logs/server.log` 和 `logs/operations.jsonl`。服务日志不记录完整请求URL/认证头，CLI不输出配置秘密值。
- 备份磁盘不足/中断：保留 `.partial`，不会标成功；原有效包仍在。换输出位置并使用新文件名重试。
- 恢复损坏/不兼容：原库不动。使用校验通过且与程序版本兼容的包。
- 工作区 dirty/untracked：更新拒绝。先自行保存/提交，或另选干净目录；不扩大忽略规则掩盖用户改动。
- 目标依赖不可用或本地目标ref不存在：准备阶段拒绝，不改数据库、不连接GitHub。
- 更新中断：读取 `updates/<ID>.json`，执行 `update.sh --recover <ID>`。维护期间用户写入和采集被暂停，恢复旧程序与数据库后再开放。
- 更新后新增记录：显式 rollback 会先备份当前状态，再拒绝旧快照覆盖；不要手动只改 active-program 而让旧程序读高版本库。

## 验证边界

`tests/test_ops_lifecycle.py` 使用单独临时 Git 仓库、明确标记的虚构材料、中文/空格代码与数据路径、本机端口 8874/8875、禁用采集器。它实际启动 Mac 上 Python 服务、发 HTTP 请求、停止/重启、在线备份、空实例恢复后编辑、准备目标程序、执行故障迁移和健康检查失败回退。故障迁移/磁盘不足等是明确构造的故障条件，不是用户真实事故；真实进程与文件系统路径在该故障条件下运行。

浏览器页面恢复编辑和 Finder 双击交互已由主 Agent单独执行并记录，不以这个HTTP演练替代。实际七天观察、真实来源长期运行和M4使用效率仍需真实试运行。

## 本版运行交付与兼容性

初版运行契约：程序 `0.1.0`、数据库 schema `1`，支持 CPython 3.11.x/macOS。更新器接受明确本地目标 ref，并由目标程序申明数据库最高兼容版本；不假定未来代码可读取较新数据库。当前零第三方 Python 依赖，若未来目标锁文件出现未准备依赖则在准备阶段拒绝更新。

早期17项批次的实际环境与结果：`docs/evidence/ops-environment.json`、`docs/evidence/ops-lifecycle.txt`。其中运行状态、HTTP、SQLite、文件权限和进程中断是真实执行，研究内容及错误场景为显式夹具。这不是当前交付 HEAD 的全套回归结论。

与最新平台严格引用检查合入后的最终记录为 `docs/evidence/ops-strict-integrity-tests.txt`：19 项通过（23.319 秒）。在保留前述 17 项实测基础上，备份/恢复还拒绝孤立材料别名、缺失议题/来源/说法/判断/变化和不存在的已读/判断版本引用；校验阶段不会迁移或写入原目标数据库。

后续Mac与正式页面验收汇总见 `docs/evidence/browser-integration-round-two.md`，包含正常更新、故障迁移回退、回退后浏览器继续编辑、阅读状态、自动打开浏览器及附件核对；`docs/handoffs/mac-acceptance-remaining.md`记录SIGKILL/WAL恢复和被拒回退时生成的当前备份再次恢复。最终收取、恢复权限、容量与272项回归见 `docs/evidence/final-integration-20260921.md`；Finder双击的隔离副本、早期权限阻塞和最终通过见 `docs/evidence/finder-double-click-preparation-20260921.md`；真实合盖睡眠、同实例恢复、预算与缺口见 `docs/evidence/mac-sleep-acceptance-20260922.md`。各报告锁定不同阶段代码，最终交付仍以 `docs/ACCEPTANCE.md` 当前状态为准。

恢复或备份可能依据已登记的来源保存权限与期限省略或清除历史正文；这不删除材料身份、标题、原链接、人工笔记或固定研究引用。恢复旧包也不会重置后来已经收紧的来源约束。具体版本变化与已知限制见 `docs/RELEASE_NOTES.md`。

真实 OS 睡眠唤醒与 Finder 手势均已通过所列 Mac 验收；仍未测试实际断电或物理磁盘耗尽。七天自然运行、结构抽查及效率观察属于 PRD M4，不用上述工程测试替代。
