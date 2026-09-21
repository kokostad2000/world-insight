# AC-36 真实 Mac 睡眠验收：已准备，未执行

日期：2026-09-21。此文档是实际睡眠验收的执行入口，不是通过证据。模拟时钟、SIGKILL和进程锁测试继续单列，不能替代真实睡眠。

## 隔离准备

`scripts/build_sleep_acceptance_fixture.py`只创建新的隔离数据目录，默认端口8897，外部请求为0。它把Fed RSS设为唯一自动采集器，关闭GDELT/GKG/WDI自动采集；手工来源仍可用但不会被Scheduler请求。免费预算设为每日4次、间隔设为允许的最小值300秒，并创建一个明确标记为隔离睡眠验收的活动议题。脚本拒绝非空目录，不读取或修改用户研究库。

准备命令：

```bash
python3 scripts/build_sleep_acceptance_fixture.py \
  /private/tmp/world-insight-sleep-ac36-prepared-20260921 --port 8897
```

2026-09-21本地准备验证使用新目录`/private/tmp/world-insight-sleep-ac36-prepared-20260921-2`成功：instance_id为`1d40d5d7-9a7b-4a40-93c1-dca61a911916`，议题ID为`e8af7a3c-b120-4b13-8651-bed7bbbe0fc3`，Fed预算4、间隔300秒，未生成`runtime.json`且外部请求为0。对同一非空目录再次运行时以退出码1拒绝。此结果只证明隔离准备可重复执行和防误覆写，不证明Scheduler、真实睡眠或唤醒恢复。

实际执行需按以下顺序完成：

1. 启动该目录且保留Scheduler，等待Fed RSS首个任务成功；记录PID、instance_id、source/job版本、`requests_today`、`last_success`、`covered_until`和材料ID/发布时间/首次采集时间。
2. 在下一动作确实会让Mac睡眠时取得用户确认，再执行真实睡眠至少660秒。睡眠会中断当前交互和本机任务，因此不能预先代替用户决定。
3. 唤醒后确认原PID恢复且只有一份采集器；等待一次到期检查，记录预算增量、任务重试/完成、`coverage_gaps`和最近收取凭据。
4. 页面核对旧材料发布时间/事件时间没有被改为唤醒时间，RSS不支持补齐的停机区间明确显示为缺口；重复材料不得产生虚假新事件或版本。
5. 正常停止并确认`data_preserved=true`。保存服务日志、脱敏API快照和浏览器页面结果；若上游失败，保留失败与缓存状态，不能把失败写成通过。

判定要求：真实睡眠时长、睡前/睡后系统时间、PID/实例身份、唯一调度锁、请求预算、缺口、材料时间字段和页面均有可复查记录。任何一步缺失时AC-36继续保持未执行或失败。
