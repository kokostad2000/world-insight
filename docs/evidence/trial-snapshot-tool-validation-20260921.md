# 七天试运行快照工具验证

日期：2026-09-21。验证对象为`scripts/capture_trial_snapshot.py`。本报告只验证快照工具的只读、安全和边界行为，不是七天试运行记录，也不抵扣五个真实议题或50/20/10人工抽查。

## 隔离数据

- 数据目录：`/private/tmp/world-insight-trial-snapshot-validation-20260921-1`
- instance_id：`e4093186-61e4-49b1-a4a7-e71ccaee62fa`
- 五个议题及其材料、说法和判断均在标题中标为“快照工具合成验证，不是试运行”。为覆盖成功路径，这套专用测试库的`is_fixture`字段设为false；它没有被登记进`docs/TRIAL.md`，不能作为真实议题证据。
- 数据库执行前SHA-256：`e98b7aa97889fcb49c4042be0b276172b00f541a55ceec6b97874cdd4f7bc8d8`

## 实际结果

最终脚本以`--phase daily`、五个不同议题ID、实际验证者名及匹配instance_id运行成功，生成`/private/tmp/trial-snapshot-validation-20260921-3.json`：

- 文件权限`-rw-------`，13,601字节，JSON可解析；schema为`world_insight_trial_snapshot/v1`。
- 记录5材料、5说法、5判断，0事件；三个50/20/10数量就绪值均为false。
- `actual_seven_day_trial_complete=false`，保留6类必须人工填写的实际睡眠/网络区间、重复/延迟解释、纠错、用时、遗漏和结束逐条复核。
- selected_state SHA-256为`2877eaf0f276068e25a280551e5027e63cedcdaecf1a603c36ac60735840ec95`。
- 运行后数据库SHA-256仍为`e98b7aa97889fcb49c4042be0b276172b00f541a55ceec6b97874cdd4f7bc8d8`，证明本次隔离验证没有改数据库文件。

对同一输出路径再次运行时，脚本以退出码1拒绝覆盖。对容量库中的五个`fixture-topic-*`运行时，脚本列出五个fixture ID、退出码1且不创建目标文件。Python编译、`git diff --check`及全仓40个Markdown文件的本地链接检查均通过。

这些检查不证明真实研究数据语义正确，也不证明连续七天、真实用户约十分钟效率或结构抽查完成。真实运行必须使用独立试运行库、五个用户确认的非fixture议题和每日新文件名。
