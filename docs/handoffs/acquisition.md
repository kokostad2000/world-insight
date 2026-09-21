# M3 采集凭据辅助边界

2026-09-21。前置独立验收提交 `df32978` 记录 AC04 跨周重复采集缺口；本批在 sources worktree 合入 main `3dec08c` 后，由 root 明确授权只新增 M3 helper、对应测试及本交接。未修改 `knowledge/__init__.py`、Scheduler、页面、迁移或共享契约。没有外部 GET、监听服务或浏览器操作。

## 语义和实体

新增 `server/modules/knowledge/acquisition.py`，M3 独占 Store kind `evidence_acquisition`。主键就是 `evidence_id`，每份材料一条当前凭据；Store 不可变版本保留过去接受过的来源/任务凭据。它表示“本地成功收取这份材料”，不表示新发现、事实变化、正文已保存或新的上游请求。重复收取不修改 Evidence 的 `collected_at`、`discovered_at`、`first_collected_at`、版本、既有研究引用或内容到期锚点，不发布 outbox。

凭据字段：`evidence_id`、`evidence_version_id`、`source_id`、`source_version`、`job_id`、`job_version`、`collected_at`、`received_at`、`is_fixture`，另有 Store 自带 id/version/created_at/updated_at。不复制标题、链接、正文、译文、指纹、笔记或授权字段。

- `collected_at` 是可信采集流程提供的成功收取时刻；默认本次 `store.now()`。必须为带时区的精确时刻，保存为 UTC 六位小数格式。不能传材料首次时间、发布日或供应商批次时间。
- `received_at` 是 helper 此次登记凭据的本地时刻。相同收取时刻、材料版本、来源/任务版本的重复调用直接返回原凭据，不因再次登记而刷新时间或增版。较旧收取时刻不能覆盖最近凭据；这不是完整的所有乱序请求审计日志。
- `source_version` 与 `job_version` 固定到凭据产生当下的已保存快照；任务随后标完成不会改旧凭据。不同来源或任务即使收取时刻相同，也保留新的凭据版本。
- 未登记的旧来源、未提供的 job 保留显式 `null`，不虚构来源版本或任务。明确给出的 job 必须存在，且来源必须相符；来源还必须在当前材料主来源或 channels 内。
- 被删除/抑制的登记直接返回 `None`；当前材料 tombstone 也会再检查。原材料受限、正文被剥离时仍可记录真实元数据收取；凭据不授予正文权限。

## 公开 API 与主线接线

```python
record_acquisition(store, ingest_result, *, origin, source_id,
                   job_id=None, collected_at=None) -> dict | None
latest_acquisition(store, evidence_id) -> dict | None
acquisition_index(store) -> dict[evidence_id, receipt]
```

`record_acquisition` 只接受 `origin='collector'` 写入，`manual` 直接返回 `None`。ingest_result 为成功入库后带 id/version 的材料响应；材料版本必须与当前版本相同，避免事务外接线产生错位。helper 自身使用 Store.transaction 并加入外层事务；**调用者必须把材料入库与凭据记录放在同一外层事务里**，错误要继续抛出，不能记录后吞掉错误。事务回滚测试已确认材料和凭据一起恢复。

root 接线建议：

1. `knowledge.ingest` 新增 keyword-only `acquisition_job_id=None, acquired_at=None`，不要把它们放进可编辑 Evidence body。使用本次准备后输入的 `item['source_id']`，不能使用去重后原材料的主 source_id，后者可能不同于本次渠道。
2. 在 ingest 的新建、无变更去重、产生字段/渠道版本三个成功返回分支中，**仍在同一个 with store.transaction 内**，将返回响应交给 helper；删除抑制分支可以直接跳过。只有成功入库才记录，失败/304未实际 ingest 不产生凭据。
3. `_succeed` 已通过当前来源/任务 scope 和许可检查后，取得一次 `acquired_at=self.store.now()` 作为该批成功收取时间，default evidence sink 给 ingest 传 `current_job['id']` 和该时间。现有 `_succeed(..., now)` 的 now 来自 tick 开始、在网络请求之前，不能混称响应成功收取时间。自定义 fixture sink 维持现有双参数兼容即可。
4. 人工 POST/PATCH/corrections 不用 collector origin，不刷新采集凭据。只关联不同 topic 的本地 GKG 缓存元数据仍是真实本地收取，但 **不意味着新上游 GET 或覆盖补齐**；source/job `data_as_of`、批次说明和 coverage gap 继续独立展示。
5. 读层为当前材料添加 `last_collected_at=receipt['collected_at'] if receipt else None` 和 `acquisition_receipt`，不回写 Evidence；历史固定引用仍保持原版本。不要用 receipt 改 change.discovered_at 或“今天发生”统计。文案使用“最近收取/采集”，不能称“新发现”。
6. 普通分页每个已显示材料调用一次 `latest_acquisition`（按主键读取）；仅需要 `time_field=last_collected_at` 跨库筛选时使用 `acquisition_index` 一次读取当前凭据，不做全局缓存。两者不从 Evidence 首次时间推导旧材料凭据；缺凭据就是未知。
7. `latest_acquisition` 只吞 `status=404, code=not_found`；其它 Store 错误继续抛出，不冒充没有凭据。

组合示意（均位于 ingest 外层事务内）：

```python
response = _ingest_response(store, saved_evidence, origin)
record_acquisition(store, response, origin=origin,
    source_id=item['source_id'], job_id=acquisition_job_id,
    collected_at=acquired_at)
return response
```

该实体使用现有泛型 Store，无新数据库表/迁移。契约和所有正式 callsite 由 root 接线；此提交本身不会改变正式采集行为。

## 已运行验证与边界

新增 `tests/test_knowledge_acquisition.py`，临时 SQLite 库前缀 `world-insight-acquisition-fixture-`，所有材料显式 fixture。9 项通过（0.249 秒）：跨周重复收取只改凭据、首次时间/历史/到期策略/无 outbox/重启持久化；UTC 时区等价重试幂等和乱序不倒退；真实 knowledge.ingest 与 helper 事务组合；人工编辑/删除抑制；批处理中途失败整体回滚；来源/任务/材料固定版本及错配拒绝；未知 provenance 保持 null；受限材料凭据不复制内容；读帮助器不造历史且不吞其它错误。

```text
python3 -m unittest tests.test_knowledge_acquisition -q
Ran 9 tests in 0.249s — OK

python3 -m unittest tests.test_knowledge_acquisition tests.test_core_domain \
  tests.test_core_rights tests.test_core_policy_period \
  tests.test_core_policy_restore tests.test_policy_projection -q
Ran 74 tests in 1.664s — OK
```

未声称本批已关闭 AC04：主线仍须完成 ingest/Scheduler/读取/UI 接线，再使用实际应用路由复现上周首次入库、今天重复收取、今天收取筛选有结果而今天发生统计为零；失败重试不能刷新凭据。浏览器验收由 root/Web 另做。本批没有新增真实来源联网证据。
