# 国际局势研究看板 · World Insight

在自己的 Mac 上整理议题、材料、说法、事件和研究判断。所有研究数据保存在本机；付费数据、云端 AI、航空和船舶能力默认关闭。已审阅表示用户完成审阅，不表示系统证明了真相。

项目需求与验收边界分别见 [PRD](docs/PRD.md)、[验收矩阵](docs/ACCEPTANCE.md)、[当前进度](docs/PROGRESS.md)。七天真实试运行属于 PRD M4；工程测试不会替代七天观察。私有代码仓为 [kokostad2000/world-insight](https://github.com/kokostad2000/world-insight)；此前开发阶段仅本地提交，本次许可变更按用户授权推送到 `main`。

## 许可与项目关系

除另有说明的第三方代码、地图资源、数据源和素材外，本项目原创代码采用 [MIT License](LICENSE)。第三方项目、资源和数据来源见 [第三方许可清单](THIRD_PARTY_NOTICES.md)；它们各自的条款不因本项目采用 MIT 而被扩大。

本项目是面向本地研究使用的独立实现，受 [World Monitor](https://github.com/koala73/worldmonitor) 的信息整合、地理关联和局势观察思路启发，但不是 World Monitor 官方版本。本仓库不重新分发 World Monitor 主项目源代码；如未来引入其代码，应按对应文件的原始许可证重新审查，不能直接套用本项目的 MIT License。

## 首次准备（macOS）

需要 CPython **3.11.x**、Git，以及支持 ES Modules/Fetch/SVG 的 Safari 或 Chrome。无需 Node、Docker 或第三方 Python 包。系统 curl 用于免费源联网；缺失时人工研究与历史阅读仍可运行。已核对的运行基线见 `requirements.lock`；实际Mac与浏览器证据汇总见 [本地验收记录](docs/evidence/browser-integration-round-two.md)，发布状态见 [版本说明](docs/RELEASE_NOTES.md)。

当前完整代码位于本机 `/Users/zhanglike/Desktop/world-insight`。GitHub 私有仓库尚未推送，**现在不能从远端下载到这份实现**。可直接使用当前目录；需要独立的代码副本时，先核对 `git status` 和 `git log -1`，以下命令只复制已提交的 main，不包含未提交工作或研究数据：

```bash
git clone --local --no-hardlinks --branch main "/Users/zhanglike/Desktop/world-insight" "/你选择的新目录/world-insight"
```

在终端进入取得的完整代码目录（包含中文或空格的路径也可以）：

```bash
cd "/你的目录/world-insight"
python3.11 --version
./scripts/check-config.sh --init
./scripts/start.sh --init
```

`--init` 明确同意创建新的研究数据目录，**不覆盖**已有 `.env` 或数据库。已有研究应先在 `.env` 指定原数据目录，使用不带 `--init` 的启动命令；不存在的原数据库不会被静默替换为空库。第一次启动依据 `.env.example` 创建配置，未填写可选密钥也可运行。

如果 Python 3.11 使用不同命令名，可先设置 `export WORLD_INSIGHT_PYTHON=/完整路径/python3.11`。所有脚本都使用同一个解释器；检查失败会显示具体阻断原因和修复方式。

默认地址是 `http://127.0.0.1:8766`。只有本地核心健康检查通过后才打开浏览器；第三方来源离线不阻止已有资料阅读。

## 日常启动、停止与数据位置

双击 `start.command` 启动并打开页面；双击 `stop.command` 正常停止。等价终端命令：

```bash
./scripts/start.sh
./scripts/status.sh
./scripts/stop.sh
```

重复启动复用同一个实例，不创建第二个服务或采集器。停止只针对实例身份、数据目录和进程均匹配的本项目服务，不停止占用相同端口的其他程序。端口冲突时在 `.env` 设置 `WORLD_INSIGHT_PORT` 后重试。

默认研究目录：`~/Library/Application Support/World Insight`。默认备份目录位于其同级 `World Insight Backups`。数据库、附件、缓存、日志分开保存；程序更新不删除研究数据。更换代码目录后继续指定原数据目录即可，必须核对其 `instance.json` 和数据库均存在。

```bash
./scripts/start.sh --data-dir "/明确选择的研究目录" --port 8766
```

`.env`、数据库、附件、日志、缓存与备份均被 Git 忽略。GitHub 管理代码，不能替代研究数据备份。不要将真实密钥写进研究文本或手工纳入 Git。应用不会发送外部邮件或公开发布看板。

## 配置检查与网络

```bash
./scripts/check-config.sh
# 用户明确选择后，另行探测免费源；默认检查不联网：
./scripts/check-config.sh --probe-network --probe-sources rss,world_bank,gdelt
```

本地检查分为通过、警告、阻断，核对 Python、Git/curl、端口、目录可写性、磁盘空间、实例绑定和数据库兼容性；阻断退出码非零。网络结果单独显示。源失败、额度耗尽或未配置会在页面标记，现有研究和人工登记继续可用，不回退到付费提供者。

离线开发验收可用 `--no-scheduler --no-browser`；它只作用于本次进程，不伪造采集成功。实际连接来源、部署网络覆盖和七天观察分别记录，不能从单元测试推断。

## 备份与恢复

运行中可备份。使用 SQLite 一致性快照，复制允许保存的附件并校验 SHA256、记录数量和版本引用。成功前只有 `.partial` 文件；失败不会覆盖以前的有效备份。

```bash
./scripts/backup.sh
# 或选择尚不存在的输出路径：
./scripts/backup.sh --output "/备份位置/研究资料.wibackup"
```

默认备份**不包含密钥、认证凭据、完整 `.env`、缓存或运行日志**。来源非敏感配置和研究记录随数据库保存；恢复到另一机器后需自行重新填写可选凭据。备份目录与恢复点不自动轮转删除。

先停止目标实例；恢复默认只验证并显示预览，已有数据必须额外明确选择替换：

```bash
./scripts/stop.sh
./scripts/restore.sh "/备份位置/研究资料.wibackup" --data-dir "/恢复后的研究目录"
# 恢复到空目录：
./scripts/restore.sh "/备份位置/研究资料.wibackup" --data-dir "/恢复后的研究目录" --apply
# 替换已有目录：先核对预览，再明确选择；自动保留当前备份及直接恢复点：
./scripts/restore.sh "/备份位置/研究资料.wibackup" --data-dir "/已有研究目录" --apply --replace
./scripts/start.sh --data-dir "/恢复后的研究目录"
```

损坏、清单不一致、不安全路径或高于程序兼容版本的备份均被拒绝。恢复不覆盖当前机器 `.env`。恢复后应在页面检查原议题、材料历史、判断和阅读状态，并继续编辑确认；压缩包能生成本身不足以证明恢复可用。

## 更新、失败恢复与回退

更新需要**本地已有的明确 Git 提交或标签**；脚本不自动拉取、不推送、不切换原工作区。需要下载新代码时由用户自行授权并获取。工作区存在已修改或未跟踪文件时默认暂停；先保存/提交自己的改动，或使用另一个干净代码目录，不执行强制重置或清理。

```bash
./scripts/update.sh --target <明确提交或标签> --dry-run
./scripts/update.sh --target <明确提交或标签>
```

目标代码先在数据目录同级 `World Insight Programs/<提交>` 准备，检查依赖与数据库兼容性；准备失败不修改研究数据。随后进入维护、停止采集和写入、建立升级前备份、运行目标迁移、实际健康检查和旧议题读取。通过后将当前选择保存在数据目录 `active-program.json`；以后从原目录双击启动也会运行这一已选版本，绑定同一数据目录。

迁移或切换前健康检查失败时恢复旧数据库、附件及旧程序选择。更新中被断电/终止时保留维护状态及 `updates/<更新ID>.json`，按记录恢复：

```bash
./scripts/update.sh --recover <更新ID>
```

已成功更新后的显式回退：

```bash
./scripts/update.sh --rollback <更新ID>
```

回退前保存当前状态并检查更新后是否产生新写入。存在新记录或修订时拒绝用旧快照覆盖，保留当前备份，需另行核对兼容性或迁移新记录。程序和数据库兼容性不能只靠“退代码”解决。

详细目录、故障处理、维护状态及验证范围见 [本地运行说明](docs/LOCAL_OPERATIONS.md)。


## 七天试运行入口

从页面“议题档案 → 新建议题 → 从研究模板开始”选择研究问题，再填自己的范围、关键词、国家与来源。模板不预填国际事件结论，也不会自动启动七天计时。按 [七天试运行记录](docs/TRIAL.md) 登记五个真实议题的固定ID、数据目录、实际开始时间和每日证据；当前仍待观察。Finder双击和 [真实 Mac 睡眠恢复](docs/evidence/mac-sleep-acceptance-20260922.md) 已实际通过，工程 M1—M3 已结账；五议题七天观察、结构抽查和效率记录仍属于 PRD M4，不能用隔离样本填充真实运行日志。
