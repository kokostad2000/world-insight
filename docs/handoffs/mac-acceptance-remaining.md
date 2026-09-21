# Mac 剩余工程验收补验

2026-09-21；独立 `.worktrees/lifecycle` / `dev/lifecycle`。本批仅新增 `tests/test_mac_acceptance_remaining.py` 与本文件，不修改实现、共享文件或正式验收矩阵。最终运行前已合入 root 最新 `cd8e766`（含 `4737611` 权限期间/读取/备份净化修复）。使用实际 macOS 15.6.1 arm64、Python 3.11.4、SQLite 3.42.0，独立临时代码、Git repo、数据目录与端口 8877。

## 实际执行与精确入口

```sh
python3 -m unittest tests.test_mac_acceptance_remaining -v
```

三个用例联合 **3 项通过，4.120 秒，退出 0**。实际最终命令额外设置 `WORLD_INSIGHT_MAC_ACCEPTANCE_RETAIN=/private/tmp/world-insight-root-browser-readstate-20260921`，明确保留一份停止状态的恢复副本供 root 后续浏览器；正常不设此变量时所有测试自身临时目录会清理。原始日志 `/private/tmp/world-insight-mac-remaining-final.txt`，完整输出见下方。

- `tests.test_mac_acceptance_remaining.MacAcceptanceRemainingTests.test_actual_scripts_with_python_absent_from_isolated_path_block_with_guidance`
- `tests.test_mac_acceptance_remaining.MacAcceptanceRemainingTests.test_sigkill_restart_preserves_all_records_versions_read_state_settings_and_attachments`
- `tests.test_mac_acceptance_remaining.MacAcceptanceRemainingTests.test_rejected_rollback_current_backup_restores_new_records_attachments_and_read_state`

此前缺 Python 单项在尚未合最后权限修复时也实际通过（1 项，1.440 秒），日志 `/private/tmp/world-insight-mac-missing-python.txt`；正式结论采用上面的最新联合结果。`python3 -m py_compile tests/test_mac_acceptance_remaining.py` 与 `git diff --check` 通过。

## AC-25：真实脚本入口缺 Python

不是修改 `sys.version_info` 或模拟返回值。测试为单次子进程构造仅含 `/usr/bin/dirname` 链接的隔离 PATH，移除该子进程环境的 `WORLD_INSIGHT_*` 覆盖值，确保找不到 `python3.11`/`python3`，随后实际执行复制到中文/空格目录的 `scripts/start.sh` 和 `scripts/check-config.sh`。两者均退出 1，stdout 为空，stderr 明确“未找到 Python 3.11”，提示 README 首次准备和 `WORLD_INSIGHT_PYTHON`；未创建数据目录、未启动服务。

系统 Python、系统 PATH 和用户环境均未改变；没有卸载或删除依赖。当前是 Python stdlib 原生方案，容器引擎未启动/容器重建为不适用，不把未使用的运行方案写成验证通过。

## AC-28：实际 SIGKILL 与全清单恢复

通过实际 HTTP 建立明确“隔离验收”议题、材料两版本、说法、旧日期/国家精度事件、判断两版本、情景、结构化路径、旧判断复盘、年度未知值指标、简报；同时改来源配置、保留设置，标记两个已展示变化版本已读，写两个自编合法附件。来源全部关闭且启动 `--no-scheduler`，没有外网采集。

清单在只读 SQLite 事务内抓取**当前库所有** `records(kind,id,version,data)` 与 `versions(kind,id,version,data)`，并记录 schema 与全部附件相对路径、大小、SHA256。没有只比较条数或省去版本正文，也没有把某几个示例对象称作整个库。最终当前库含 16 类记录、32 个历史版本、2 个 read_state、2 个附件；每个保存的数据字段都参与清单比较。并非声称所有可选实体类型都建立了样本（本库没有采集任务）。

仅在 `runtime.own_runtime` 再次证明 PID/数据目录所有权后，对本次专属服务 PID 75289 发送 SIGKILL。退出后立即读原库清单一致；重启新 PID 75303 后再读清单仍完全一致，清单 SHA256 前后都是 `14e0547e146c755ea4070d03979becacda325a07d05b7b96d7c0482380d179d1`。再经 HTTP 逐一读取 10 类研究对象、证据 v1/v2 历史、判断固定 v1 引用、首页已读状态、Fed 来源 enabled=false/budget=3、保留 enabled=false/batch=7，最终保存判断 v3。

这是实际异常终止/WAL 恢复和 HTTP 继续使用；没有真实 OS 睡眠，没有断电，也没有浏览器实操声明。首次端口如果被其他程序占用会正常阻断，测试不按端口杀进程。

## AC-34：被拒回退的新恢复包确可恢复新增内容

仅在临时本地 Git repo 建立同 schema 的有效新版本提交，执行真实 `update.update`。升级健康后，经 HTTP 新建一个议题与材料，写一个升级后新增附件，保留原资料的两条 read_state。随后请求回退，明确收到“新写入”拒绝；选定程序不变，当前所有 records/versions/附件清单不变。

测试从实际 `rollback_refused_new_writes` 运维日志读取 `current_backup`，验证这正是 `before-requested-rollback` 包；不是误拿升级前旧包或另手工生成包。该包含两个议题、两条 read_state，以及升级后新增资料。正常停止原实例，将包恢复到独立空目录，先直接比对恢复数据库的全部当前/历史行与全部附件，再在同一专属端口 8877 启动恢复实例，实际 HTTP 读取原对象/历史/阅读状态/配置和新增议题/材料，新增附件 SHA256 也一致，继续编辑新增议题成功 v2。

因此本批补齐 AC-34 的“拒绝前保留的当前状态确可找回”，超过只断言原库没有被覆盖。恢复属于同 schema 的已验证路径，不声称验证将来不同依赖或任意旧 schema 的兼容性。AC-30 的后端/HTTP、附件、阅读状态分支也得到覆盖，但正式浏览器步骤留给 root。

## 提供给 root 的停止状态浏览器实例

明确保留的样本目录：`/private/tmp/world-insight-root-browser-readstate-20260921`。其中 `browser-fixture.json` 包含启动参数、ID、固定引用、两个已读项、来源/保留配置及附件哈希；代码为实际更新后的 `0.1.1-mac-acceptance-fixture`，数据从回退拒绝所保留的新包再次恢复，没有引用即将清理的临时代码目录。原包另外复制到该目录供复查。

准备完毕状态为 **restored_and_stopped**，本子任务不启动额外浏览器。root 可执行清单中的 `start_command` 在 8877 打开既有实例；这不是初始化空库，不加 `--init`。所有材料、域名和国际事件文字均为显式隔离样本，没有访问 example.org 原文。

待 root 实际页面核对：旧议题/材料历史 v1/v2/判断固定引用；首页 24h 中清单所列两个条目的已读标记（未读窗口应排除）；来源与保留设置；升级后新增议题/材料与附件路径；编辑原判断或新增议题保存下一版。未由 root 实际操作前，不能用此准备清单宣称 AC-30 浏览器已通过。

具体关键 ID：

- `original_topic_id`：`3c2be804-c097-4754-a89e-a74f0e821bbf`
- `evidence_id`：`d79a0c25-05cf-4c3c-95d2-3307245e1291`
- `fixed_evidence_version`：`d79a0c25-05cf-4c3c-95d2-3307245e1291@1`
- `judgment_id`：`721b41b4-a143-48c2-938a-97a7cceebaa4`
- `judgment_version`：`2`
- `new_topic_id`：`97e1e883-712c-480d-9101-b6568da471c0`
- `new_evidence_id`：`3f17d94a-60b2-419c-b7d3-8e7742064180`

两个已读项：

```json
[
  {
    "id": "change-0e9a07c7-ad49-406e-afab-0ddc0082174d",
    "version": 1
  },
  {
    "id": "change-f9876b3e-558c-4b02-83ac-1798fdb0d26e",
    "version": 1
  }
]
```

## 联合运行原始输出

```text
test_actual_scripts_with_python_absent_from_isolated_path_block_with_guidance (tests.test_mac_acceptance_remaining.MacAcceptanceRemainingTests.test_actual_scripts_with_python_absent_from_isolated_path_block_with_guidance) ... MAC_ACCEPTANCE_EVIDENCE {"case": "AC-25-real-entrypoint", "data_created": false, "fixture": true, "isolated_path_has_python": false, "scripts": [{"entry": "start.sh", "exit_code": 1, "stderr": "阻断：未找到 Python 3.11。请完成 README 首次准备，或设置 WORLD_INSIGHT_PYTHON。"}, {"entry": "check-config.sh", "exit_code": 1, "stderr": "阻断：未找到 Python 3.11。请完成 README 首次准备，或设置 WORLD_INSIGHT_PYTHON。"}], "system_dependencies_modified": false}
ok
test_rejected_rollback_current_backup_restores_new_records_attachments_and_read_state (tests.test_mac_acceptance_remaining.MacAcceptanceRemainingTests.test_rejected_rollback_current_backup_restores_new_records_attachments_and_read_state) ... MAC_ACCEPTANCE_EVIDENCE {"backup_label": "before-requested-rollback", "case": "AC-34-and-AC-30-HTTP", "fixture": true, "original_active_program_unchanged": true, "refusal": "new_writes", "restored_exact_current_and_history_rows": true, "restored_new_attachment_sha256": "029c6146b542b95cb6e64df8a2865b4ab01a54f2451739e1b6ddb0a02f2c52b7", "restored_new_evidence_id": "3f17d94a-60b2-419c-b7d3-8e7742064180", "restored_new_topic_id": "97e1e883-712c-480d-9101-b6568da471c0", "restored_read_states": 2, "resumed_topic_version": 2}
MAC_ACCEPTANCE_EVIDENCE {"actual_browser_steps": false, "case": "AC-30-browser-fixture-ready", "fixture": true, "fixture_status": "restored_and_stopped", "manifest": "/private/tmp/world-insight-root-browser-readstate-20260921/browser-fixture.json"}
ok
test_sigkill_restart_preserves_all_records_versions_read_state_settings_and_attachments (tests.test_mac_acceptance_remaining.MacAcceptanceRemainingTests.test_sigkill_restart_preserves_all_records_versions_read_state_settings_and_attachments) ... MAC_ACCEPTANCE_EVIDENCE {"after": {"attachment_count": 2, "record_counts": {"brief": 1, "change": 6, "claim": 1, "event": 1, "evidence": 1, "evidence_alias": 1, "impact_path": 1, "judgment": 1, "knowledge_index": 1, "observation": 1, "read_state": 2, "retention_settings": 1, "review": 1, "scenario": 1, "source": 6, "topic": 1}, "sha256": "14e0547e146c755ea4070d03979becacda325a07d05b7b96d7c0482380d179d1", "version_count": 32}, "all_rows_and_attachments_identical": true, "before": {"attachment_count": 2, "record_counts": {"brief": 1, "change": 6, "claim": 1, "event": 1, "evidence": 1, "evidence_alias": 1, "impact_path": 1, "judgment": 1, "knowledge_index": 1, "observation": 1, "read_state": 2, "retention_settings": 1, "review": 1, "scenario": 1, "source": 6, "topic": 1}, "sha256": "14e0547e146c755ea4070d03979becacda325a07d05b7b96d7c0482380d179d1", "version_count": 32}, "case": "AC-28", "container": "not_applicable_native_stdlib", "fixture": true, "http_objects_read": 10, "killed_signal": "SIGKILL", "original_pid": 75289, "restarted_pid": 75303, "resumed_judgment_version": 3}
ok

----------------------------------------------------------------------
Ran 3 tests in 4.120s

OK
```

## 结束状态、边界与合入顺序

本次所有运行中的专属服务都已正常停止，SIGKILL 的专属进程已由 runtime 子进程回收线程 wait；其他实例未触碰。常规测试临时目录已清理，只有上述明确要求保留的浏览器样本目录留存。请由 root 接手该目录，不自动删除用户选择保留的验收产物。

本批没有新增 API、依赖或迁移。合入顺序：root `cd8e766` → 本测试/交接提交 → root 浏览器操作与正式验收矩阵更新。不要把自动打开浏览器（由 root 另验）、Finder 权限受阻、真实 sleep/wake、七天/十分钟观察写成本批通过。三个测试足以证明所列 Mac 进程/数据行为；浏览器可用性和真实源内容质量仍由对应证据支持。
