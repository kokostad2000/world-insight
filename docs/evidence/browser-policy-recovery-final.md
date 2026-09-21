# 恢复后来源限制：最终正式页面验收

日期：2026-09-21。环境：macOS 本机、正式 `server.app` 与正式 Web 页面，回环地址 `127.0.0.1:8877`，Scheduler 关闭。保留夹具：`/private/tmp/world-insight-policy-review-fixture-pazar12w/restored-data`。

来源页实际显示“恢复时保留的来源约束”，说明恢复旧备份不会重置原资料的授权期限，后续人工重新核对只影响新材料；页面同时显示来源版本 2、7 天上限及约束生效时间。打开来源编辑器后，未勾选的独立复选框明确写为“我已重新核对来源许可，按下方范围授权今后新材料（旧材料限制保留）”。本轮只读检查后取消编辑，没有改写来源。

恢复材料详情实际显示：

```text
待核查 · 固定版本 v1
此材料展示受限，仅显示允许的元数据。
恢复旧备份不会重置原资料的授权期限。
研究备注：[人工测试笔记] 此笔记、标题及引用必须保留
存储：不允许；展示：不允许；导出：不允许；AI使用：不允许
```

本机 API 同步确认当前 Evidence 的 `excerpt=''`、`translation=''`、`content_fingerprint=null`，固定 ID／版本、标题、原链接、用户笔记和关联议题仍在；`content_policy.recovery_constraints` 保留原库较严限制。页面关闭后 8877 服务正常停止。

这项证据验证恢复后的正式读取与人工重新核对入口，并结合 `tests.test_core_policy_restore`、`tests.test_ops_retention` 的实际 SQLite/备份回归证明限制在写入前及恢复包中执行。它不代表第三方来源重新授权，也不放宽旧材料权限。
