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
- `server/modules/knowledge/__init__.py`：`_prepare_evidence` 在持久化前对候选版本执行有效 store 策略。精确去重仅用瞬时输入身份；最终新建/合并、PATCH、更正和 split 两边都先剥离不允许保存的正文。保留元数据与人工笔记，不把历史时间重置为本次采集时间。
- `rights.strip_licensed_content(record)`：纯辅助函数，拷贝并只清顶层和历史 channels 中的 `excerpt`、`translation`、`content_fingerprint`；备份/恢复与读序列化复用，标题、notes 和固定引用保留。平台 Store 的同类历史清理由 root 在 `3dec08c` 独立交付。
- `tests/test_core_policy_restore.py`：共 16 项真实 SQLite/归档/领域/HTTP 行为测试，全部使用带 fixture 标签的独立临时数据，无上游网络。
- `tests/test_ops_retention.py`：仅给两条本来要验证“合法正文完整备份”的合成来源补显式 store/display/export 许可，不放宽产品未知许可行为，原断言全部保留。
- `tests/test_core_access_http.py`：写前策略与保存后响应是不同候选，更新仪器计数：采集收据 1 次、普通手工新建 2 次、split 两次写前检查加共享响应 3 次。所有功能断言保留；采集路径增加定向 policy_snapshots 调用断言，禁止调用 Store.snapshots。读请求仍为一次 context。
- 本交付文档。

新事实字段：source_id、source_version、source_created_at、rights、retention_days、policy_effective_at、policy_end_at、restored_at、policy_hash、reason，以及平台式 id/version/created_at/updated_at。policy_hash 标识原政策；后来得知结束边界时追加独立事实，保留原审计，求值时采用已确认的最早结束边界。缺少政策真实时间时保守保持约束。

最终备份清单 content_policy.policy_version 为 **3**、mode 为 `licensed-content-omitted`，除 `recovery_policy_facts_added`/`recovery_policy_ids` 外，增加 `storage_restricted_evidence_ids`/`storage_restricted_version_count`。保存许可不足或到期会净化相关全部历史版本及渠道正文；有限期限仍提前省略正文以防未来复活。只有 export=false、store=true 的合法内容可以进入备份；trash/访问状态本身不会撤销合法备份保存权。原业务记录/版本数量保持，可能新增恢复政策事实，因此 preserved 使用 existing_record_counts。旧格式 1 包仍可恢复；包内没有此类事实不推定新权限或期限。

## 实际验证

最终已合并 main **8d2e3d4**，包含 root 的来源审核、定向索引、平台渠道清理和新增 HTTP 验收用例，执行：

```sh
python3 -m unittest discover -s tests -q
```

实际 **261 项通过，41.267 秒，0 失败，exit 0**。涵盖真实 8874/8877 回环 HTTP、SQLite/WAL 字节检查、运维子进程、备份恢复、正常更新与失败回退。之前同版增量 focused 47 项通过（2.938 秒）。本文件中的 16 项覆盖：

1. 到期前恢复保存 cap，后续重采、PATCH、原始关联派生材料、普通导出不展示过期正文；notes、精确旧版引用保持；实际 lifecycle 清除所有版本正文并通过 integrity。
2. 采集状态更新和 name-only PATCH 不续期。
3. 两条时间线同为 source@2；通过实际 Application → M2 source PATCH 人工重审，之后新材料可读、旧材料仍隐藏/到期。
4. 新备份及再次恢复最早旧包均保留约束与重审结束边界；再次 sanitize 幂等。
5. 只有 display/export 许可收紧而无期限时，恢复后立即隐藏且解释为恢复许可，不凭空制造截止日期；新重审不使旧材料复活。
6. 当前来源已放宽时，曾适用于旧材料的历史短期限仍保留；之后新材料允许。
7. 缺少历史政策真实时间时不能把继承的 created_at 当作该版本的生效时间，保守保留约束。
8. 外部来源的十次连续采集状态更新不重复创建相同许可区间的政策事实；只保留实际政策变化，避免按 source 版本膨胀。
9. 来源 store 未登记时，新输入正文不落库，metadata/人工笔记仍保存。
10. store 撤回后，metadata-only 写入也不会把旧正文复制到新的持久版本。
11. 历史 channels 三个正文键在备份/恢复中清除，SQLite 文件中不残留相应字节；渠道标题/人工注释保留，新提交的渠道也不能携带正文副本。
12. 真实 HTTP PATCH 在到期后成功保存人工笔记，但输入正文/译文及指纹既不入业务记录，也未进入 SQLite/WAL 字节。
13. 已过期但尚未维护清理的材料执行 split，两边新版本均无正文，旧判断引用不改。
14. 没有 retention_days、但当前有效 store=false 的旧包，全部受限历史顶层及渠道正文物理清除。
15. store=metadata 的旧包执行同样清理；不把元数据许可推定为摘录许可。
16. export=false、store=true 的正文在普通导出隐藏，但本地备份/恢复仍完整保留；材料在 trash 中也不会被误当作撤销存储权。

另完成 Python 编译及 git diff --check。写前检查首轮暴露两条备份来源未登记许可的测试前提，以及旧 HTTP 仪器计数；均按上面的最小调整修正，未删除行为断言。最初恢复测试错误地对仍打开的 staged Store 调用 sanitizer，SQLite 正确拒绝 journal mode 切换；测试已先关闭自己连接再净化，不放宽产品锁定行为。

## 集成边界与合入顺序

先包含此前 `2d73107`/`ceaa638` 恢复事实提交及主线 `8d2e3d4`，再合入本次写前/恢复净化提交。root 的 Store.policy_snapshots 已包含相关 recovery_source_policy 事实；Source GET/UI 的恢复说明与显式审核入口由 root 实现。本次未写 README、TRIAL、平台、research 或其他根负责人文档。

**最终持久化语义：**输入的新正文在有效保存许可不足/到期时先剥离，metadata/notes 正常保存；不会先写入再等待维护。去重合并会无条件使用已净化的正文三字段和 channels，防止 metadata-only patch 沿用旧正文。split 保留首次时间，两边各自检查。直接提交与材料显式 store=metadata/false 冲突的正文仍保持原有 400 rights_restricted 校验；仅改笔记时允许清除旧正文并保存。既有历史合法内容的期限清理由生命周期/平台负责，备份恢复按本说明独立净化。

保留给 root 浏览器验收的目录：`/private/tmp/world-insight-policy-review-fixture-pazar12w/restored-data`。上级目录有 FIXTURE_ONLY.md；全部为合成内容，未启动服务。source_id=`98b031f9-6271-43a1-aacf-7636a0fc4de7`，topic_id=`f2a3e3d4-1f64-47f7-a75c-286325871c19`。建议使用 8877、--no-scheduler、--no-browser。完整测试结束后 8874/8877 已释放。

未执行本次补丁的浏览器人工验收、写入吞吐容量基准或真实七日运行。此前读性能由 root 单独测量并留证，本次不把旧指标冒充新测量。未使用真实研究库，未联网采集，未推送。
