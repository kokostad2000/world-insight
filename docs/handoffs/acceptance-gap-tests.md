# 独立验收缺口补验

2026-09-21；独立 `.worktrees/lifecycle` / `dev/lifecycle`。root 根据验收索引指定四项补验。仅新增 `tests/test_acceptance_gaps.py` 与本文件；没有修改 sources/knowledge/research/ops/platform/app，也没有使用用户实际数据。索引“纯 helper 合入不等于路由已接线”的纠正另已提交 `eec616f`。

## 验证范围与隔离

- AC-06：Application 真实路由与临时 SQLite 中创建两个不同 manual 来源（不同注册 ID、publisher、URL），分别登记 5 人/12 人材料及说法。事件保持两个 claim ID，JSON 保留两组原始来源和固定 `id@1` 引用，没有合成 casualties 单值。不冒充真实来源、页面显示或现实伤亡核查。
- AC-09：两个实际适配器（Fed RSS、GDELT）使用明确注入的上游成功响应，经真实 Scheduler + knowledge 入库两个材料，再各注入一次 timeout。逐源 stale/failed、原 last_success、缓存和失败请求计数均核对；整体严格要求 unavailable，不以“过去成功过”当作当前部分可用。没有外部网络请求。
- AC-29：复制代码到独立中文/空格临时路径，实际 Mac 服务 8877，采集器关闭。生成并验证旧包后，在**另一个实际备份进程**的首 ZIP 成员已经写入并 flush/fsync、尚未关闭/校验/改名时注入受控等待，父测试仅对自己创建的该进程发送 SIGKILL。验证 partial 有字节但不是有效完成 ZIP，无法校验/恢复、正式目标不存在、没有该包的 backup_complete 日志；旧包 SHA256 与稳定清单不变、继续校验通过，原服务 PID/旧议题仍可读。最后正常停止专属服务。它是备份写入中断故障注入，不是物理断电/磁盘塞满。
- AC-36 的一个子分支：实际启动两个**独立 Python 进程**争抢同一专属 SQLite 数据目录的 collector.lock，第二个收到 409/collector_running 且退出 23；首进程 SIGKILL(-9) 后第三个独立进程取得锁并正常退出 0。使用实际 Scheduler loop，来源预先全部停用，无采集任务、无网络。只证明跨进程互斥与异常释放，**没有 Mac 睡眠/唤醒，没有补采或七天观察**。

测试只通过自身 Popen 句柄清理子进程，服务由身份绑定的 runtime.stop 停止；不按端口杀进程。8877 若已被占用，预检失败，不清理占用者。样本临时目录统一 `world-insight-acceptance-gap-fixture-*`，`.env` 只创建在临时复制的代码目录；测试结束移除其自建临时资料，不涉及用户资料目录。

## 精确测试入口

```sh
python3 -m unittest tests.test_acceptance_gaps -v
```

- `tests.test_acceptance_gaps.AcceptanceGapTests.test_two_distinct_sources_keep_five_and_twelve_claims_and_citations`
- `tests.test_acceptance_gaps.AcceptanceGapTests.test_two_news_sources_timeout_preserves_cache_and_last_success_but_is_unavailable`
- `tests.test_acceptance_gaps.AcceptanceGapTests.test_online_backup_sigkill_keeps_previous_package_and_rejects_partial`
- `tests.test_acceptance_gaps.AcceptanceGapTests.test_scheduler_lock_excludes_second_process_and_releases_after_sigkill`

## 首轮真实结果及发现

首轮基于 main `0f546fa`。三个无需端口的用例实际运行 0.224 秒：2 通过、1 失败。原始日志 `/private/tmp/world-insight-acceptance-gaps-initial.txt`。唯一产品失败是 AC-09：两来源本次都 timeout 后仍 partial；两个旧材料与 last_success 均正确保留。root 已明确应改 unavailable，source owner 独占修复；本测试没有放宽断言或修改领域源码。

在线备份用例首次在 8877 实际运行，产品完成预期中断和旧包保护，但测试错误地直接比较两次 `validate_backup` 返回值，包括每次重新计算的 `restoration_content_policy.evaluated_at`，因此测试失败。已改为先比较完整旧包 SHA256，再比较稳定字段 state/files/database/instance_id/created_at；没有忽略真实文件变化，没有修改产品。第二次实际运行 0.957 秒通过，退出 0，原始日志 `/private/tmp/world-insight-acceptance-backup-gap.txt`。该测试编写错误与产品 AC-09 失败分开记录。

首轮关键信息（实际输出节录）：

```text
AC-06: source_count=2, evidence_count=2, claim_count=2, combined_casualty_value=false
AC-09: coverage_status=partial, current_failed_sources=2, cached_records=2
last_success={source-fed:2026-09-20T15:00:00Z, source-gdelt:2026-09-20T15:00:21Z}
AssertionError: 'partial' != 'unavailable'
AC-36-process-lock-only: first_pid=55116, rejected_pid=55117, rejection_code=collector_running,
first_exit=-9, restarted_pid=55120, restarted_exit=0, actual_sleep=false
AC-29: server_pid=56717, interrupted_backup_pid=56724, backup_exit=-9, partial_bytes=116,
previous_package_sha256=e62ba3062bd293f9a6e447555e8d65d6675dcf8e85def9826e419d49bba79002,
previous_still_valid=true, final_package_exists=false, incomplete_restore_rejected=true,
live_topic_readable=true
```

## 最终联合结果

合入 source owner `b22ce42`（当前检查可用性的聚合修复）后执行上述四项联合命令：**4 项通过，1.085 秒，退出 0**。原始日志 `/private/tmp/world-insight-acceptance-gaps-final.txt`。首轮 AC-09 失败仍保留在前节；修复来自 source owner，本测试未放宽断言。`python3 -m py_compile tests/test_acceptance_gaps.py` 和 `git diff --check` 通过。

最终原始 stdout/stderr 合并记录：

```text
test_online_backup_sigkill_keeps_previous_package_and_rejects_partial (tests.test_acceptance_gaps.AcceptanceGapTests.test_online_backup_sigkill_keeps_previous_package_and_rejects_partial) ... AC_GAP_EVIDENCE {"backup_exit": -9, "case": "AC-29", "fault": "SIGKILL after first ZIP member before finalization", "final_package_exists": false, "fixture": true, "incomplete_restore_rejected": true, "interrupted_backup_pid": 65604, "live_topic_readable": true, "partial_bytes": 116, "previous_package_sha256": "e9ae4fbfe3c4f568dd8ac512003aa0057d4a67d66ec56b2a7534ade60cd578c1", "previous_still_valid": true, "server_pid": 65597}
ok
test_scheduler_lock_excludes_second_process_and_releases_after_sigkill (tests.test_acceptance_gaps.AcceptanceGapTests.test_scheduler_lock_excludes_second_process_and_releases_after_sigkill) ... AC_GAP_EVIDENCE {"actual_sleep": false, "case": "AC-36-process-lock-only", "first_exit": -9, "first_pid": 65622, "fixture": true, "rejected_pid": 65625, "rejection_code": "collector_running", "restarted_exit": 0, "restarted_pid": 65626}
ok
test_two_distinct_sources_keep_five_and_twelve_claims_and_citations (tests.test_acceptance_gaps.AcceptanceGapTests.test_two_distinct_sources_keep_five_and_twelve_claims_and_citations) ... AC_GAP_EVIDENCE {"case": "AC-06", "claim_count": 2, "combined_casualty_value": false, "evidence_count": 2, "fixed_citations": ["0f2da6e9-f486-403c-9675-9fe9ef79025e@1", "7d4d0af4-9637-46be-8bd9-dad37465ea53@1"], "fixture": true, "source_count": 2}
ok
test_two_news_sources_timeout_preserves_cache_and_last_success_but_is_unavailable (tests.test_acceptance_gaps.AcceptanceGapTests.test_two_news_sources_timeout_preserves_cache_and_last_success_but_is_unavailable) ... AC_GAP_EVIDENCE {"cached_records": 2, "case": "AC-09", "coverage_status": "unavailable", "current_failed_sources": 2, "fixture": true, "last_success": {"source-fed": "2026-09-20T15:00:00Z", "source-gdelt": "2026-09-20T15:00:21Z"}, "network_calls": 0, "provider_results": "injected"}
ok

----------------------------------------------------------------------
Ran 4 tests in 1.085s

OK
```

最终独立服务 PID 65597 已正常停止；备份子进程 65604 被测试明确 SIGKILL，调度进程 65622 被明确 SIGKILL，第二进程 65625 拒绝启动退出，第三进程 65626 正常退出。Popen 均已 wait/communicate 回收，临时样本目录清理。未操作其他实例。

## 尚未证明与合入顺序

本批没有浏览器检查，AC-06 并列显示/AC-09 首页逐源展示仍需 root 页面验证；AC-36 真睡眠与补采仍未执行。AC-29 补齐实际备份进程中断，与既有磁盘错误注入和在线备份形成组合证据，未扩张成断电保证。

本批无新 API、依赖、迁移。合入顺序：source owner coverage 修复 `b22ce42` → 本补验测试和交接 → root 适当完整回归及正式验收矩阵更新。本分支已合该提交；其中上游已提交的 GDELT 替代来源研究文档随其祖先进入分支，没有带入 source owner 的未提交 GKG 实现。仅本地提交，不推送 GitHub，不启动自动观察。
