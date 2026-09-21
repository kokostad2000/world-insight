# 恢复后来源政策持久约束

## 问题与结果

已独立复现：旧备份来源无期限，当前库随后收紧为 7 天；在到期前恢复旧备份时虽省略正文，旧包来源上限仍为 null，材料也未标记到期。到期后同 URL 重采会再次展示正文且无截止日期。一次 snapshot 净化不足以保留这项政策。

本补丁在恢复暂存库添加独立、不可变的 `recovery_source_policy` 事实。它不覆盖旧包 source 配置、adapter、采集频率或任何 source 历史版本，也不重置材料首次时间。有效读取权限、lifecycle 到期评估、后续备份/恢复统一消费此事实。当前库里曾适用于旧材料的较严期限/许可仍生效；历史政策若早已结束，不污染之后的新材料。

来源在恢复后可能再次产生同名版本，例如旧库 source@2 与恢复后新 source@2。恢复事实是独立政策分支，不按 source.version 与原生历史混排。原生历史仍保守检查未知/倒退时间；恢复事实用真实 `policy_effective_at`、可确认的 `policy_end_at` 和 `restored_at` 表示时序。普通名称修改、采集成功状态更新不能结束恢复约束。

明确的人工许可重审才会结束恢复约束对**未来新材料**的适用。依赖 main `bfa3c6b`：人工 source PATCH 显式提交 rights 或 retention_days 时，M2 生成内部 `policy_reviewed_at`、完整 `policy_reviewed_rights` 和 `policy_reviewed_retention_days`。已经存在的旧材料仍保留曾适用的约束。再次备份/再次恢复会保留确认过的结束边界；重复净化不会反复创建同一事实。

## 改动路径与接口

- `ops/backup.py`：暂存库原有 SQLite 事务内仅 INSERT 新 kind 的 records/versions 成对事实，同时完成既有正文净化。不实例化会自动 migrate 的 Store，避免 migration 检查点触发递归迁移。此例外已由 root 明确授权。成功切换前仍经过原有 manifest/hash/版本/引用校验。
- `server/modules/knowledge/policy_period.py`：新增 `RECOVERY_KIND`、`recovery_policy_end(fact, native_history)`；既有 `source_histories` 与 `applicable_source_versions` 合并独立约束分支。未要求每次必须读取全库；root 的定向 policy snapshots 只须返回相关 source/recovery_source_policy 全历史及依赖上下文。
- `server/modules/knowledge/rights.py`：复用 source_histories，公开每条 Evidence 的 `content_policy.recovery_constraints[]`。每项含事实 id、source_id/source_version、生效/结束时间、rights、retention_days 与中文解释。恢复许可导致禁止时 reason code 为 `recovery_source_rights`。合法尚未到期时约束仍可展示，解释信息本身不作为禁读理由。
- `tests/test_core_policy_restore.py`：7 项全新真实 SQLite/归档/领域请求行为测试，全部使用带 fixture 标签的独立临时数据，无上游网络。
- 本交付文档。

新事实字段：source_id、source_version、source_created_at、rights、retention_days、policy_effective_at、policy_end_at、restored_at、policy_hash、reason，以及平台式 id/version/created_at/updated_at。policy_hash 标识原政策；后来得知结束边界时追加独立事实，保留原审计，求值时采用已确认的最早结束边界。缺少政策真实时间时保守保持约束。

备份清单的 content_policy.policy_version 为 2，新增 `recovery_policy_facts_added` 和 `recovery_policy_ids`；原业务记录/版本数量保持，可能新增恢复政策事实，因此 preserved 文案改为 existing_record_counts。旧格式 1 包仍可恢复；包内没有此类事实也不推定新权限或期限。

## 实际验证

已合并 main `bfa3c6b` 后执行：

```sh
python3 -m unittest tests.test_core_policy_restore tests.test_core_policy_period tests.test_ops_retention tests.test_core_rights tests.test_lifecycle tests.test_lifecycle_platform tests.test_core_domain tests.test_platform tests.test_sources_policy -q
```

实际 **103 项通过，2.698 秒，exit 0**。其中新 7 项覆盖：

1. 到期前恢复保存 cap，后续重采、PATCH、原始关联派生材料、普通导出不展示过期正文；notes、精确旧版引用保持；实际 lifecycle 清除所有版本正文并通过 integrity。
2. 采集状态更新和 name-only PATCH 不续期。
3. 两条时间线同为 source@2；通过实际 Application → M2 source PATCH 人工重审，之后新材料可读、旧材料仍隐藏/到期。
4. 新备份及再次恢复最早旧包均保留约束与重审结束边界；再次 sanitize 幂等。
5. 只有 display/export 许可收紧而无期限时，恢复后立即隐藏且解释为恢复许可，不凭空制造截止日期；新重审不使旧材料复活。
6. 当前来源已放宽时，曾适用于旧材料的历史短期限仍保留；之后新材料允许。
7. 缺少历史政策真实时间时不能把继承的 created_at 当作该版本的生效时间，保守保留约束。

另完成 Python 编译及 git diff --check。首轮一个测试错误地对仍打开的 staged Store 调用 sanitizer，SQLite 正确拒绝 journal mode 切换；测试已先关闭自己连接再净化，不放宽产品锁定行为。

## 集成边界与合入顺序

先包含 `bfa3c6b`，再合入本补丁；root 的 Store.policy_snapshots 必须包含相关 recovery_source_policy 事实。Source GET/列表的 UI 仍由 root 接线，需说明旧来源配置与恢复约束并存，不能只显示表面 rights=true。Evidence API 已提供明确恢复约束说明。

**本分支当前真实存储语义：**没有 content_expired 标记、但按政策已经到期的材料，重采/PATCH 的输入正文仍可能短暂写入内部版本；所有受测响应、读取、历史和普通导出会即时隐藏，lifecycle 随后清除全部版本。已有 content_expired 标记的材料会立即阻止重新保存正文。root 正负责 `_prepare_evidence` 的即时有效 store 判定；本补丁未修改由 root 正在优化的 knowledge/__init__.py/research/__init__.py，不声称已经实现所有到期输入即时拒存。

未执行本补丁后的完整 HTTP/浏览器/更新进程回归：8874 正由 root 性能复测使用，按协调仅跑纯领域/真实 SQLite/归档测试。未验证定向索引集成后的性能；上一容量审计是独立 `ad89c67` 交付。未使用真实研究库，未联网采集，未推送。
