# PRD 11.6 交付审计

## 2026-09-21 最终主线复核

本节基于 `main 00e5a5a` 及随后仅更新本审计证据的工作区，取代下方 `8d2e3d4` 时点关于“root草稿未提交”和“恢复净化仍在整合”的判断；下方原审计保留为历史过程。

九类交付文件均已纳入Git：README、双击/终端启动停止、配置检查、`.env.example`/`.gitignore`、`requirements.lock`、备份恢复、更新/迁移、发布/故障说明和本地验收报告。所有命令入口实际为`-rwxr-xr-x`。最终提交范围审计没有跟踪数据库、附件、备份、日志、`.env`或常见凭据签名；Markdown本地链接0缺失。最终272项回归、恢复后权限页面、跨周收取页面、10条官方材料和容量结果见[最终整合验证](../evidence/final-integration-20260921.md)。

Finder分支已进一步建立提交`00e5a5a`的中文／空格路径无硬链接副本、独立数据目录和8896端口，并完成正式初始化与正常停止。两次Computer Use复核仍显示macOS辅助功能与屏幕录制未授权，所以没有执行Finder双击、重复双击和双击停止。精确状态见[Finder准备与权限阻塞](../evidence/finder-double-click-preparation-20260921.md)。因此第11.6节文件清单已齐，Mac交付演练整体状态从“未执行”收窄为“仅Finder手势受权限阻塞”；AC-36真实睡眠仍是独立未执行分支。PRD M3仍不能提前宣告完成，M4七天观察和质量/效率门槛仍待真实执行。

审计日期：2026-09-21。已提交基线：`main 8d2e3d4`。只读核对主线文件、脚本入口、Git 状态、已合入证据，以及 root 尚未提交的 README/TRIAL/RELEASE_NOTES 草稿；本次只新增本文，不运行服务、不联网、不打开浏览器、不修改实现或主验收矩阵。

**结论：本地工程预览已经具备主要运行文件和多份真实 Mac 证据，但第 11.6 节尚不能整体标为交付通过，PRD M3/M4 均不能由此提前完成。** 代码取得和发布说明的文档缺口已有 root 草稿修补，尚需提交并核对实际交付版本；Finder 双击、真实睡眠及尚未完成的真实数据门槛仍独立保留。七天未观察是未完成验收，不能表述为“工程已经完成，所以可以忽略”。

## 逐项交付清单

以下按 [PRD 11.6](../PRD.md#116-本地交付清单) 九项逐条核对。状态描述限定为文件与证据现状，不替代 [ACCEPTANCE](../ACCEPTANCE.md) 的全部行为判定。

| 产物 | 当前已提交现状与精确依据 | 缺口与建议 |
|---|---|---|
| README | [README](../../README.md) 已覆盖 Python 3.11.x/Git/curl、首次 `--init`、启动停止、8766、独立数据目录、可选 Key、网络探测、备份恢复、更新回退。`README.md:11` 的旧文字只有“下载完整代码后”。 | 已提交版缺少现在可取得完整实现的步骤。root 草稿已改为明确本机路径与 `git clone --local --no-hardlinks --branch main`，并警示远端未推送；合入前仍不能把这项算完整。取得新副本后应记录 HEAD，明确其只含已提交内容。 |
| start.command / start.sh / stop.sh | 根双击入口及 `scripts/*.sh` 均存在；本次 `stat` 实测为 `-rwxr-xr-x`。中文/空格目录初始化、复用原 PID、正常停止见 [mac-clean-restore.json](../evidence/mac-clean-restore.json)；终端启动后自动打开 Edge 见 [mac-browser-readstate-restore.json](../evidence/mac-browser-readstate-restore.json)。 | 可执行位、终端和自动打开浏览器不能证明 Finder 双击。AC26 仍因电脑控制权限阻塞；需实际允许的 Finder 操作或由用户完成并记录。不得另换自动化绕过权限后宣称双击通过。 |
| check-config.sh | 文件与分级检查存在，[运维交接](ops.md)、[Mac 补验](mac-acceptance-remaining.md) 记录实际缺 Python、端口占用、权限/目录/磁盘/兼容性检查；README 明确本地检查默认不联网、显式免费源探测另列。 | 主要文件/命令说明齐备。应在最终交付版本保留实际命令及退出码索引，不能只引用通配文字 `docs/evidence/ops-*`；root README 草稿已加入具体 Mac 汇总链接。 |
| .env.example / .gitignore | [配置模板](../../.env.example) 无秘密值，解释数据/备份目录和 AI/付费关闭；[忽略规则](../../.gitignore) 覆盖 .env、工作树、运行目录、数据库、附件和日志等。 | 忽略规则只能证明默认规则存在，不能证明所有已追踪证据文件绝无敏感内容。最终提交范围审查仍需单独完成；依 [AC35](../ACCEPTANCE.md) 保留其未完成分支，勿把 `.gitignore` 存在当脱敏通过。 |
| 运行描述与依赖锁定 | [IMPLEMENTATION_PLAN](../IMPLEMENTATION_PLAN.md) 明确采用原生 Python stdlib/SQLite，不采用 Compose；[requirements.lock](../../requirements.lock) 列出 Python 3.11.x、已验 3.11.4/Darwin arm64、系统 curl 8.7.1，零第三方 Python 包。 | Compose/容器文件不适用，不是遗漏。应在发布说明明确“实际验收 macOS 15.6.1 / Apple M1 / arm64”；Intel Mac、其他 OS/浏览器未由这些记录证明。Python 3.11.x 是声明的范围，3.11.4 是实际记录的基线，不宜混称所有补丁版均已实测。 |
| backup.sh / restore.sh | 文件、清单校验、默认排除密钥与恢复前预览有文档；[正式恢复浏览器](../evidence/mac-browser-readstate-restore.json) 核对 7 总变化/2 已读/5 未读，判断 v2→v3、固定材料 v1、3 附件；[Mac 补验](mac-acceptance-remaining.md) 证明被拒回退时保存的新包可找回新增内容。 | 不能说恢复能力未测；但当前 [PROGRESS](../PROGRESS.md) 仍列“写前有效 store 剥离与备份渠道正文副本清理”整合中，必须待其最终验证。文档还应解释期限/权限净化可能合法省略正文，备份不是承诺恢复每个历史正文；现 README 只概括“允许保存的附件”。 |
| update.sh / 迁移记录 | 更新器使用明确本地 ref、保护 dirty/untracked、先备份、失败成对恢复；[正常更新](../evidence/mac-normal-update.json)、[迁移失败](../evidence/mac-migration-failure.json)、[阅读进度回退](../evidence/mac-reading-rollback.json) 已提交。`server/platform/migrations.py:6` 为 schema1，有校验和与版本登记。 | 程序仍为 0.1.0/schema1，但功能和权限事实已演进；不能凭同 schema 推断任意旧提交都能安全读新数据。root 发布草稿已说明此边界。`ops/update.py:148` 计划返回 current/target/database 等，未提供人可读功能变更说明的入口；至少在更新文档显式引导先读对应发布说明，再 dry-run。 |
| 发布与故障处理说明 | [LOCAL_OPERATIONS](../LOCAL_OPERATIONS.md) 已有缺依赖、权限、占用端口、磁盘不足、损坏备份、中断维护和新写入拒绝回退等排查；第43节有 0.1.0/schema1 简介。 | 主线没有逐版功能变化/限制汇总。不是强制要求文件必须叫 RELEASE_NOTES，而是现已提交内容未齐。root 新增 `docs/RELEASE_NOTES.md` 草稿覆盖功能、兼容性、状态和限制，需提交并用可点击相对链接指向 README、LOCAL_OPERATIONS、ACCEPTANCE、PROGRESS。 |
| 本地运行验收报告 | [环境 JSON](../evidence/ops-environment.json) 有 macOS 15.6.1/build24G90、arm64、Python3.11.4、SQLite3.42.0；[第二轮正式页面/Mac报告](../evidence/browser-integration-round-two.md) 已在 8d2e3d4 合入，含真实资料恢复、更新、故障回退后浏览器编辑及已读状态、自动浏览器与附件核对。 | 这项不是“没有报告”。缺的是一个面向本交付提交的统一索引：列明哪批代码/数据库/数据性质/命令/结果/限制，不把不同提交的证据拼成“最终 HEAD 全验收”。LOCAL_OPERATIONS:47—49 仍以早期17/19项作为本轮/最终描述，需链接后续报告并明确那只是当时批次。 |

## 代码取得与发布草稿复核

[PROGRESS](../PROGRESS.md) 的主线记录已明确“远端空仓，只有本地提交，未推送”。本审计只读本地 origin 和 refs，不联网重新验证远端；没有执行 push、发布或制作下载包。不能建议用户当前从 GitHub clone 后就能得到这份实现。

root 工作区本次实际状态为：`README.md`、`docs/TRIAL.md` 已修改，`docs/RELEASE_NOTES.md` 未跟踪。只读复核得到：

| 草稿 | 已修补内容 | 合入前/合入后的剩余事项 |
|---|---|---|
| README:9—17 | 具体 Mac 证据/版本说明链接；本机代码路径；本地 clone 命令；明确远端未推送且复制不包含未提交工作/研究数据。 | 文案方向正确，不能仍将“远端下载步骤缺失”判为尚未处理，但当前主线尚未取得这段。提供副本时核对目标 HEAD；先提交 docs 再复制，否则副本不含这些说明。 |
| RELEASE_NOTES:1—24 | 标为工程预览；0.1.0/schema1；主要功能、权限/恢复边界、Mac 实测范围、Finder/sleep/M4限制、DOC失败与GKG最新批次限制。 | 仍应加证据的可点击入口，并记录最终交付 commit 或明确获取它的方法。当前已有 `git rev-parse HEAD` 提示，足以避免只拿0.1.0当精确构建。没有 Git 标签不单独视为不合规，明确提交同样可追溯。 |
| TRIAL:14、28—40 | 每日表已加“重复收取/延迟”；五行真实议题登记表；明确创建议题入口、空ID/未开始时间；要求记录commit/data_dir/instance_id/许可/预算，允许本地文档记录。 | 仍是准备协议，不是五议题已选或试运行已开始。建议补直接可操作的每日取证步骤与口径；此项不要求额外实现一套试运行平台。 |

对当前这台 Mac，可用已有本地 Git 仓库与 root 草稿里的本地副本路径作为实际交付方式。对其他机器，尚未提供可取得的私有代码包或已上传版本；若后续有此交付需求，应先准备限定已提交代码的包/提交清单，再按授权交付。此处不据需求清单自行推送。

## 五个真实议题与七天记录方式

现有正式入口确实存在：`议题档案 → 新建议题 → 从研究模板开始`；`web/app.js` 的 topic-template 选择器使用 `/api/bootstrap.templates`。`server/app.py:21—26` 实际为四个通用问题模板（地区冲突与外交、制裁与贸易政策、能源与航道、主要国家政策变化），不预填当前结论。**四个模板不是要求五个真实议题的缺陷本身；用户可多次使用或自建。真正缺口是尚未登记五个已选研究问题及各自 ID、来源范围和开始时间。**

已有 [美国货币政策真实元数据议题](../evidence/browser-integration.md) 和 [GKG 三个真实接入议题](../evidence/gkg-live-scheduler.md) 可供核对入口，不能把它们自动加总为五个用户研究议题，更不能把一次接入计作持续观察。GKG 的 Iran/Russia/sanctions 三项是限定批次采集验收，45条待核查材料、0说法/事件/判断；材料相关性尚未核实。

目前 TRIAL 和设置页均明示 M4 待观察，但 README 没有直接链接 TRIAL；`web/app.js` 的“七天真实试运行”卡片只显示文字，不提供记录表位置。建议 README 增加一次清晰入口，设置页至少说明“项目 docs/TRIAL.md”；不必把私有试运行记录上传 GitHub。

root 的 TRIAL 草稿已解决五行登记和重复/延迟表头问题。要让这份协议可连续执行，建议补以下最小步骤：

1. **启动清单**：实际选定五个问题，保存 topic_id、来源ID/国家/关键词/排除词，核对每个议题至少有一个明确的人工或自动材料通道；记录真实开始时间、时区、检查人、commit/schema、data_dir/instance_id。采集验收库、fixture库与真实试运行库分开，未创建的ID保留未登记。
2. **每日同一口径留证**：检查开始时保存来源管理逐源状态、任务/覆盖缺口及日期；检查结束时保存五议题变化窗口、已读范围、当天修订/纠错记录及导出文件位置。涉及列表时说明完整分页范围，不能只把第一页20条当全量。可人工截图/本地表格加合法导出，不要求新增自动化产品功能。
3. **指标定义**：成功/失败按实际请求/任务分列，缓存分配成功不等于一次新网络请求；原返回条数、唯一材料新增、重复收取分别记录。`last_result_count` 不宜直接当新增去重条数。延迟必须说明比较的是发布时间→采集/发现还是任务等待；未知发布时间写未知。GKG批次时间不是发布时间，不能拿它冒充真实新闻延迟。
4. **连续性与缺口**：每日填写进程停机、Mac睡眠、网络不可用及补采范围；GKG仅最新批次，不把恢复后一次请求说成补齐停机历史。若当天未检查，保留缺记原因，不能补写虚拟成功记录或修改时钟凑满七天。
5. **使用效率**：由实际检查人记录“开始查看→找出关注议题关键新增”的实际用时、发现的变更ID及遗漏如何在之后核对；不得以API响应秒数或Agent自动化耗时代替约十分钟的用户研究任务。
6. **结束复核**：保留七日原始行、汇总口径及证据索引，同时完成十条不同类型官方材料登记复核和50材料/20说法事件/10判断抽查。抽查表应逐条列ID/版本/来源/时间/关联/未知/判定/复核人；缺数量时如实保留缺口。

当前没有上述真实开始清单和七天填写记录。按 TRIAL 现有启动条件还需先完成工程 M3 的精确验收分支；如果未来调整试用进入条件，必须显式记录，而不能把“可以准备试用”改写成“已满足PRD”。PRD12.1明确要求未完成时标“尚未完成真实数据验收”，该状态应同时出现在试运行和最终交付说明中。

## Mac 证据整合与剩余分支

以下均已在 `8d2e3d4` 可读，不再沿用本轮早先“root未提交”的判断：

| 已有证据 | 能证明什么 | 不能由此推断什么 |
|---|---|---|
| [环境](../evidence/ops-environment.json)、[新目录运行/恢复](../evidence/mac-clean-restore.json) | macOS15.6.1 arm64、Python3.11.4、SQLite3.42.0；中文/空格目录、初始化、重复启动与正常停止。 | 远端当前可下载完整代码；Finder双击。新目录代码来自本地 clone。 |
| [正常更新](../evidence/mac-normal-update.json)、[故障迁移](../evidence/mac-migration-failure.json)、[浏览器报告](../evidence/browser-integration-round-two.md) | 明确本地目标更新，schema2注入失败后恢复ad5e32f/schema1，随后浏览器旧判断v4→v5、固定材料v2可用。 | 任意未来schema/依赖兼容；真实断电。故障SQL是隔离副本注入。 |
| [已读回退](../evidence/mac-reading-rollback.json)、[空目录恢复浏览器](../evidence/mac-browser-readstate-restore.json) | 20条read_state回退前后相同；另恢复实例7总变化/2已读/5未读，判断v2→v3、固定v1、3附件哈希。 | 仅health通过就等于恢复通过；七天自然阅读行为。 |
| [网络失败](../evidence/mac-update-network-failure.json) | 单次git命令使用不可达回环代理，fetch退出128，研究指纹/旧程序不变。 | 整机断网、当前远端发布状态。本次命令故障不能冒充OS级网络切断。 |
| [Mac补验](mac-acceptance-remaining.md)、[进程/备份补验](acceptance-gap-tests.md) | 真正SIGKILL/WAL恢复、运行中备份被中断、进程级采集锁、当前恢复包可恢复新增内容。 | 真实睡眠/唤醒、物理磁盘满、Finder手势。 |

尚欠 Finder 双击的实际许可范围内操作、真实 OS 睡眠/唤醒精确验收；这两项不能因为已有众多自动测试而划为不适用。原生方案的容器重建/容器引擎未启则确属不适用，应保持两种情况的区别。

建议最终报告以“交付提交 → 相关证据批次 → 当前通过/失败/未执行/阻塞 → 残余风险”汇总。保存已有原始错误说明，例如故障脚本曾把预期退出码1误断言为2，真实产品回退依据来自更新日志与随后浏览器保存；无需重新把原始报告改写为无错误过程。

## 建议收尾顺序与本次验证

1. root 提交 README、RELEASE_NOTES、TRIAL 草稿，并补 TRIAL 的可发现入口、每日口径和发布说明链接。此为文档工程工作，能现在完成。
2. 将最终权限/收取凭据改动与回归结果纳入交付版本，刷新正式验收矩阵/报告索引，保留精确未完成分支。本审计不改其状态。
3. 在正常许可范围内完成 Finder/真实睡眠分支；若仍阻塞就发布为有明确限制的本地工程预览，不能声称 PRD M3 已全部完成。
4. 确定真实试运行研究清单和可执行记录办法，再按实际日期累积七天及质量/效率证据。M4 待观察始终是剩余工作，不是可删除的验收项。

本次只执行只读文件/代码/证据核对、Git状态与本地主线同步、脚本文件权限检查；没有运行应用、网络请求或浏览器，也没有重复宣称执行既有测试。新审计文件执行 `git diff --check`，只提交 `docs/handoffs/delivery-audit.md`。建议合入顺序：`8d2e3d4` → 本审计；root草稿另行提交。GitHub未推送。
