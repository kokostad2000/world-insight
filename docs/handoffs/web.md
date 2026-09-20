# M6 中文研究工作台交接

2026-09-20；独立 worktree `.worktrees/web` / 分支 `dev/web`；浏览器端口 8872；数据库 `/private/tmp/world-insight-web-qa`，采集器关闭。验收内容全部显式标记“隔离验收样本”，未混入真实研究数据。

## 变更位置

- `web/index.html`：中文、无构建页面入口，语义化导航与原生 dialog。
- `web/styles.css`：深海蓝 / 暖灰桌面工作台，移动端阅读、对比度、可滚动长表单。
- `web/lib.js`：HTML 转义、原链接协议限制、时间精度、国家级位置不生成坐标、可见已读快照。
- `web/forms.js`：10 类领域编辑表单、固定版本证据选择、结构化影响路径编辑、免费来源权限与配额。
- `web/app.js`：变化简报、议题档案、证据详情、我的判断、地图与国家、来源、本地运行 7 个页面及 API 交互。
- `tests/test_web_semantics.py`：可执行 JS 边界检查，不冒充浏览器 E2E。

## 实现与契约

没有修改共享契约或平台。使用 root 既有 CRUD、bundle、history、corrections、split、exports、dashboard、changes/read、briefs、notifications、sources/jobs/coverage/refresh。

- 议题模板来自 bootstrap，不预填当前结论。创建、编辑、关注、暂停、归档均保留历史。
- 议题档案顺序完整：问题范围 → 变化 → 判断 → 时间线 → 证据分歧 → 情景 → 影响路径 → 国家背景 → 版本复盘。
- 不把说法提升为已实施事实；时间线按事件时间或材料发布切换，材料/核查状态筛选。
- 手工材料记录标题、URL、来源、发布时间、摘录、译文、转引渠道和权限。详情显示采集/发现时间、关联记录与固定历史版本。
- 材料移出议题只 PATCH topic_ids；原记录不删除。更正、撤回、访问受限走专用接口，需实质确认。
- 判断 / 情景 / 路径 / 复盘可创建、编辑、保留历史与修订原因。409 不关闭表单，保留本地输入，可查看当前数据库版本并复制草稿。
- `missing_evidence` 遵守实际字符串语义；已审阅无支持材料持续显示缺证据。未知日期不补当前时间，未知指标不显示 0。
- 首页窗口、议题过滤、分页及已读提交使用本次 `snapshot_at` + 实际展示 `{id,version}`；提醒已读与复查完成分离。
- 站内提醒与模板简报入口可用；议题 Markdown / JSON 可下载。
- 地图读取 `/assets/world-countries.geojson`，只绘真实 Natural Earth 轮廓；国家/区域高亮，只有明确 coordinate 精度且有效 lat/lon 才画点。资源失败时显示列表，不画假轮廓。
- 权限 metadata/unknown 不会自动勾为允许摘录。所有外部文本走 HTML escaping，外链只允许 HTTP(S)。

来源 UI config：`feed_url/query/countries/indicators/topic_ids`；adapter `manual/rss/gdelt/worldbank`。预算/间隔/语言/地区/许可证和逐项使用范围可编辑；付费及 AI 适配器无开启入口。

## 已实际执行

1. `node --check web/app.js`, `forms.js`, `lib.js`：通过。
2. `python3 -m unittest tests.test_web_semantics -v`：4 项通过；覆盖外部文本与链接协议、已读仅展示 ID/版本、未知时间/国家精度、所有编辑器类型及权限不扩张、历史证据引用保留。
3. 真实 Mac Codex in-app 浏览器访问 8872、空态截图检查：通过；桌面导航、首页、初次研究引导可正常渲染。
4. 浏览器实际填写并保存：议题 `36042ba9-439a-4604-864d-81e50273ec24` → 材料 `01064f75-4593-478e-b4a5-32e3c1d7e98f` → 引用材料 v1 的主体说法 → 有引用/假设/置信理由/复查日/审阅者的已审阅判断。页面明确展示 9/13 发布时间与 9/20 采集时间。
5. 发现并上报 HTTP keep-alive 导致 SIGTERM 停止阻塞，root 已修复 main `32de65f`。旧隔离实例只能在指定 PID 强制退出；这一段仅记为异常中断恢复。重启同数据目录后浏览器重新打开全部记录、编辑判断为 v2、查看历史确认 v1 原文与 v2 修订原因同时保留：通过。

## 未验证事项 / 下一步

- root 需合并后独立验证完整浏览器闭环和正式 Mac 一键启动/备份/恢复/更新；本次模块验收不替代整体 FR/AC。
- 真实来源、底图资源待 sources 合入后做 UI 联调；本模块不声明实际成功采集。
- 双窗口冲突、材料纠错传播、结构化影响路径、情景、复盘与导出 UI 已实现，须在下一批完整浏览器场景逐项执行。领域自动测试由 core / root 承担。
- 当前编辑器引用选项取最近最多 200 条；大资料库的跨页选材需进一步提供搜索加载入口，不能声称 2 万材料交互性能验收通过。
- 未执行连续七天真实观察，PRD M4 仍待验收。

## 合入顺序

先平台 / activity / core，再此提交；sources 可在此前或之后合入，资源文件无冲突（该 Agent 不改 `web/assets/`）。随后 root 集成 QA；本分支可继续提交 UI 修复。没有推送 GitHub。
