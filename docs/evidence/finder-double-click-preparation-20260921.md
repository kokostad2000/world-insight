# Finder 双击验收准备与权限阻塞

日期：2026-09-21。目标是补验 AC-26 的 Finder 双击分支；没有用终端启动结果冒充双击。

## 已完成的真实准备

- 从本地主线提交 `00e5a5ab8ac5466004199a3eeb2eaf0a1b38cc6a` 创建无硬链接副本：`/private/tmp/世界洞察 Finder 验收 20260921`。路径同时含中文与空格。
- 副本的 `start.command`、`stop.command` 均为 `-rwxr-xr-x`。
- 独立配置使用数据目录 `/private/tmp/world-insight-finder-ac26-data-20260921`、备份目录 `/private/tmp/world-insight-finder-ac26-backups-20260921`、本机端口 8896；AI 与付费能力关闭。
- 先以正式 `scripts/start.sh --init --no-browser` 初始化，返回程序 `0.1.0`、schema `1`、instance `83f7edf3-48bf-4327-8490-3419d5f081fd`，实际 PID 28726，程序根目录正确指向中文／空格副本。
- 随后正式 `scripts/stop.sh` 正常停止 PID 28726并返回 `data_preserved=true`。再次执行 `scripts/status.sh` 显示 `runtime=null`、`maintenance=null`，数据目录和所选程序仍正确绑定。

这些步骤使 Finder 双击的下一动作只需打开该目录并双击 `start.command`；不需要创建数据、输入凭据或改系统配置。

## 当前阻塞

通过 Computer Use 请求 Finder 可访问状态时，macOS 返回“Accessibility and Screen Recording permissions are not granted”。第一次请求显示权限仍待完成，第二次复核仍明确未授予，因此没有执行双击，也没有把 shell、AppleScript 或其它自动化方式替代为 Finder 手势。

当前状态安全：验收实例已停止，端口8896没有由该实例运行的服务，隔离数据和副本均保留，未删除任何文件。用户授予 Codex/ChatGPT Computer Use 的辅助功能与屏幕录制权限后，可从这一状态继续；也可以由用户本人双击并把实际结果记录回本报告。

本报告只证明可复查的前置准备和权限阻塞。AC-26 在真实 Finder 双击、页面健康、重复双击复用同一 PID、再双击停止且数据保留全部实际观察前，继续保持阻塞。
