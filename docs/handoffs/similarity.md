# 相似材料候选检查交付

2026-09-21；合并基础为主线 `3c944d2`，随后已合并 `ad5e32f`。只新增 `web/similarity.js`、`tests/test_similarity.py`、`tests/similarity_behavior.mjs` 和此交接，不修改 app/lib/平台共享文件。

## 集成点（root）

```js
import {similarityPanel, installSimilarity} from './similarity.js';

// openDialog / closeDialog / route / toast 均为 app.js 的现有函数，启动时安装一次。
installSimilarity({openDialog, closeDialog, route, toast});

// evidenceDetail() 中，取得当前材料 current 后加入主栏；传 current，不传请求的旧版本 e。
const similarity = await similarityPanel(current);
// 将 similarity 插入材料详情的“出处与出现渠道”之后。
```

`similarityPanel(material)` 异步返回 section HTML。`installSimilarity` 使用独立的 `data-similarity-action` 委托事件，与主应用 `data-action` 无冲突；返回卸载函数，重复安装自动卸载旧监听器。

## 行为与边界

- GET `/api/evidence?similar_to=<id>&offset=&limit=10`，有分页和失败/空结果区分。标题相似只做建议，展示原题、日期、发布者、出处链接和状态，不生成确认事实或事件。
- 明确确认对话框并列当前材料与拟选原始稿件，核对理由必填；只 PATCH `{expected_version, origin_evidence_id, change_reason}`。不合并记录，不改正文、渠道、引用或事件。
- 当前关联可移除；`GET /api/evidence/:id/history` 展示关联发生变化的版本，可核对并恢复旧关系。恢复创建新版本，不回滚正文与固定历史引用。
- 409 保留理由，提示重新核对，不自动读取新版本重试覆盖；循环关系由现有 knowledge 校验，已回收材料/目标在确认前拒绝。
- 忽略仅写浏览器 localStorage 的 `wi-similarity-dismissed-v1`，按材料 ID@版本与候选 ID@版本生效，最多最近 1000 项；忽略项留在列表并明确标记，可恢复提示，绝不改服务器来源关联。存储失败明确报错；新版本重新提示。
- 安全链接只允许 http/https；外部标题、发布者与错误均转义；无外部采集、模型或收费调用。
- 候选算法仍为现有后端标题相似度，不声称语义判断、自动查原文、独立性确认或全面发现转载。非相似的原始稿件仍可用现有材料编辑器手动选择。

## 实际验证

`python3 -m unittest tests.test_similarity -v`：4 项 unittest（3 项真实 Application/SQLite，加 1 项执行 Node 行为测试），通过。

Node 行为测试覆盖 11 个分支：只读候选、转义与危险链接、失败与分页、显式理由后最小 PATCH、409 保留输入、本地忽略及版本失效、浏览器存储受限、历史恢复、已删除/自身目标、监听器幂等安装、历史链接关闭对话框。DOM seam 测试不冒充浏览器验收。

真实 Edge + HTTP + SQLite：独立端口 `8873`，临时目录 `/private/tmp/world-insight-similarity-browser-nbdv1op6`，所有记录均为 `[隔离夹具]`、example.com 链接且未访问外部原文。使用临时 HTML harness 导入未经替换的 similarity/lib 模块与现有 CSS；受现有 CSP 约束，未放宽安全策略。这是独立模块实操，不是已经写入 app.js 的主页面集成验收。

实际操作：查看不同国家日期的候选 → 忽略 → 恢复提示 → 明确核对并关联 → 移除 → 查看历史 → 核对并恢复 v2 关系。

真实数据库结果：

```json
{"evidence_count":2,"event_count":0,"versions":[1,2,3,4],
 "origins":[null,"00310f97-db33-4684-b97b-a0df5e2dccd7",null,"00310f97-db33-4684-b97b-a0df5e2dccd7"],
 "notes_preserved":true,"channels_preserved":true}
```

A8 的主应用接线和集成后浏览器重验由 root 完成；本任务未重新完整浏览器验证 A4—A7。

## 后续待查（不影响本模块范围）

root 报告：议题 country_codes=USA、允许 Fed/WDI 时，自动 WDI 采集把来源配置的 CHN/USA 全部直接关联到该议题，导致国家背景由 10 条 USA 变为 20 条含 CHN。本次只记录，未修改 sources；后续 M2 应核对 `topic.country_codes` 与 source.config.countries 的请求/关联交集及全局缓存规则，不能静默改变人工关联或观测期。
