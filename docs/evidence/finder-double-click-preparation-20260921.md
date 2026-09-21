# Finder 双击验收：准备、早期权限阻塞与最终通过

日期：2026-09-21。目标是补验 AC-26 的 Finder 双击分支；没有用终端启动结果冒充双击。

## 已完成的真实准备

- 从本地主线提交 `00e5a5ab8ac5466004199a3eeb2eaf0a1b38cc6a` 创建无硬链接副本：`/private/tmp/世界洞察 Finder 验收 20260921`。路径同时含中文与空格。
- 副本的 `start.command`、`stop.command` 均为 `-rwxr-xr-x`。
- 独立配置使用数据目录 `/private/tmp/world-insight-finder-ac26-data-20260921`、备份目录 `/private/tmp/world-insight-finder-ac26-backups-20260921`、本机端口 8896；AI 与付费能力关闭。
- 先以正式 `scripts/start.sh --init --no-browser` 初始化，返回程序 `0.1.0`、schema `1`、instance `83f7edf3-48bf-4327-8490-3419d5f081fd`，实际 PID 28726，程序根目录正确指向中文／空格副本。
- 随后正式 `scripts/stop.sh` 正常停止 PID 28726并返回 `data_preserved=true`。再次执行 `scripts/status.sh` 显示 `runtime=null`、`maintenance=null`，数据目录和所选程序仍正确绑定。

这些步骤使 Finder 双击的下一动作只需打开该目录并双击 `start.command`；不需要创建数据、输入凭据或改系统配置。

## 早期权限阻塞（已解除）

早期通过 Computer Use 请求 Finder 可访问状态时，macOS 返回“Accessibility and Screen Recording permissions are not granted”。当时没有执行双击，也没有把 shell、AppleScript 或其它自动化方式替代为 Finder 手势。用户随后为ChatGPT开启辅助功能与屏幕录制权限并重启应用，Computer Use成功读取Finder，原权限阻塞解除。

## 最终 Finder 双击结果

Computer Use在Finder中打开上述中文／空格目录并完成三次实际双击，原始字段见[结构化验收记录](finder-double-click-acceptance-20260921.json)：

1. 双击`start.command`后，实例以PID `74719`启动；`/api/health`返回同一instance_id、schema 1和正确中文／空格程序根目录。Edge于`2026-09-21T15:39:38.259Z`自动打开`http://127.0.0.1:8896/`，正式“变化简报”显示本地资料库已连接，AI与付费默认关闭。
2. 再次双击`start.command`后PID仍为`74719`，操作日志没有第二条started记录；`lsof`只显示这一PID监听`127.0.0.1:8896`，独立非阻塞锁检查确认`collector.lock`仍被运行实例占有。
3. 双击`stop.command`后，操作日志于`2026-09-21T15:41:08.326113Z`记录同一PID停止；status返回`runtime=null`，8896无监听且`runtime.json`已移除。停止前后均为7来源、2采集任务、40材料、0议题，数据保留。

当前验收实例已停止，隔离数据和副本均保留，未删除任何文件。Computer Use安全策略不允许读取终端窗口内容，因此以运行身份、健康接口、Edge页面、端口监听、采集锁、操作日志和只读记录数交叉验证结果。AC-26的双击、幂等、单采集器和停止保留数据分支现已通过。
