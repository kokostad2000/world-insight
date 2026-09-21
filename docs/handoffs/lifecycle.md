# P0 生命周期模块交接

分支 dev/lifecycle，独立工作树 .worktrees/lifecycle。基于 main 87e3802（含 Store/领域接口 c2c7b22、来源期限和 M7 净化 f47ead5）。只写三个约定文件：

- server/modules/knowledge/lifecycle.py
- tests/test_lifecycle.py
- docs/handoffs/lifecycle.md

## 接口和接线

root 在 app API dispatch 中先调用 `knowledge.lifecycle.handle(store, method, segments, body, query)`；模块返回 None 表示非本模块路由。公共路由沿用契约末节：

- GET /api/retention 返回 `{candidate_days:90,candidate_retention_enabled:true,batch_limit:100,id:'default',version:0}`；PATCH 必须 expected_version，可改三个策略字段。来源期限不受候选开关影响。首次保存 version=0，随后常规版本递增。
- GET /api/retention/preview 返回 actions/protected/evaluated_at/settings/total；HTTP 每类最多 200 条，内部纯评估器不截断。
- POST /api/retention/run 只接受可选 operation_id。批次上限 1—200，每批事务内重新扫描全部历史。状态 complete 或 compaction_pending，失败收缩不会伪装成功；相同 operation_id 幂等重试，后续批次也重试挂起收缩。
- POST /api/deletions/preview `{targets:[{kind,id,expected_version}],cascade:false}`，最多 100 个。支持 topic/evidence/claim/event/observation/judgment/scenario/impact_path/review/brief 及 HTTP 复数别名。返回 plan 含 id、targets、dependencies、plan_hash、expires_at、mode=recoverable_trash、warning；预览只写自身 plan 元数据，不修改研究记录。
- POST /api/deletions/<plan>/prepare-recovery 返回更新 plan。`recovery` 含 id、backup_path、backup_sha256、export_path、export_sha256、instance_id、content_omissions、verified。恢复包和 JSON 导出落在配置 backup_dir；实际解包/SQLite 完整性验证，核对目标版本，失败阻断删除。
- POST /api/deletions/<plan>/commit 必须 `{confirm:true,reason,plan_hash,recovery_id,expected_versions:plan.targets}`。先复核两个文件 SHA256、恢复包、实例身份，事务内复核全历史影响图及目标版本；有新引用、权限/期限变化、版本变化、30 分钟过期均 409。无级联，全部目标成功或全部回滚；同 plan 重试返回原结果。
- GET /api/trash 支持 kind/limit/offset，最多 200 条；仅元数据，不返回受限正文。
- POST /api/trash/<kind>/<id>/restore `{expected_version,reason}`，使用 owner.lifecycle_change。恢复不会清除重审标记，也不会恢复已过期正文；人工恢复候选视作保留决定，不再次被 90 天自动清理。

领域修改始终调用 knowledge/research/activity 的 lifecycle_change；授权内容到期调用 knowledge.expire_content，批次提交后 Store.compact。仅自身 retention_settings/lifecycle_plan/lifecycle_operation 使用 Store.create/update。

## 策略语义

纯函数 `evaluate_retention(snapshots, sources, settings=None, now=None)` 已供 ops 净化器导入，返回 actions:[{kind:'evidence',id,expected_version,action:'source_content_expiry'|'candidate_expiry',reason,expires_at,redact_content:true,move_to_trash:bool}], protected:[{id,reason}], evaluated_at。now 接受 UTC ISO/datetime，公开 HTTP 不接受伪造时钟。

期限从首次采集/最早保存时间计算，重复采集不续期。来源所有历史版本与转载渠道中已登记的最短 retention_days 优先；未知/null 不臆造期限。来源期限适用于人工与引用材料，清除所有历史 excerpt/translation/content_fingerprint，保留 notes、版本 ID、引用和原因。来源期限未到时，候选更短期限仍生效。

90 天仅明确 ingest_origin=collector、全部历史没有人工触碰/笔记/确认/恢复、仍为 unverified、没有任何历史领域引用的候选。历史引用取消或引用对象进回收站也不放开保护。legacy 未知来源保守保留。系统 change 发现索引不算人工引用；brief/claim/event/observation/判断/路径等引用均保护。

人工删除是可恢复回收站，历史正文仍按权限保存，不称物理删除。自动候选到期进入回收站前会清除正文；其可恢复范围仅元数据与笔记。来源授权到期即使仍被引用也清除正文并传播待重审。

JSON 导出包含选中目标、入向领域依赖及出向引用历史，源配置仅公共白名单；按历史/当前材料和来源权限过滤，有限来源正文提前省略，到期候选正文省略。用户笔记和引用 ID 保留。恢复包依赖 M7 同时净化正文，恢复包省略内容不能宣称可恢复原文。

## 实际验证

`python3 -m unittest tests.test_lifecycle tests.test_lifecycle_platform tests.test_ops_retention -v`

28 项真实 SQLite / ZIP 备份测试通过（本模块 16 项 + 平台 6 项 + M7 6 项）。覆盖期限边界、重复采集不续期、人工/legacy/历史引用保护、来源期限胜过保护、全部版本与数据库字节正文清理、批次上限与幂等、收缩失败重试、真实恢复包及权限导出、损坏包/导出拒绝、依赖变化拒绝、到期 plan、跨目标事务回滚、恢复保留重审、转载渠道旧期限、人工恢复不重删。全部临时数据明确隔离，不算真实七天观察。

## 未验证与合并顺序

1. 本提交依赖 main 87e3802，之后由 root 合入。ops 可直接导入纯评估器；未新增依赖或迁移。
2. root 负责 app 路由、后台有限批次调度、页面删除/回收站/保留设置。这里未修改共享文件，尚未进行 HTTP 或浏览器删除流程验证。
3. 大库全历史扫描与删除备份耗时未做本模块专门基准。维护应作为后台任务，避免阻塞页面读请求。
4. 备份路径为本机真实文件；root UI 应显示路径、内容省略说明和版本确认，不把路径显示当作浏览器下载成功。
