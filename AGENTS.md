# AGENTS.md

本仓库是 `/Users/regen-bio/project-nlp-hybrid`，是一个独立的新 hybrid MVP 项目。旧项目 `/Users/regen-bio/project-nlp` 已提交给面试官，只能作为历史背景，默认不要读取、扫描或修改。

## 项目目标

本项目目标是提交一个小而完整的自然语言 Workflow Builder MVP demo。它强调本地可运行、可复现、可解释和可控执行，而不是生产级平台能力。

面试讲解重点：

- 用户用自然语言描述任务，系统生成受约束的处理方案。
- Workflow 不是任意代码，而是受 Schema、Step Registry 和 Executor 约束的 JSON。
- LLM 默认 mock，本地运行不依赖真实 API Key。
- 表格分析只执行声明式操作，不执行模型生成 Python。
- 用户反馈会生成新版本并完整重跑，不做增量执行。

## 架构边界

保持现有模块职责，不要为了小改动重构整体架构：

- `apps/web`：Next.js App Router 前端，只展示普通用户概念。
- `backend/python_service`：FastAPI API 层。
- `core`：Orchestrator、Planner、Executor、Schema、Registry、LLM 适配。
- `tools`：文档、检索、问答、表格分析、文本生成工具。
- `storage`：SQLite 与文件存储。
- `examples`：示例数据、Workflow JSON 和本地 demo runner。

核心约束：

- 单一 Orchestrator 负责状态流转。
- Planner 第一版使用规则 + 模板生成或修改处理方案。
- Executor 执行前校验 Workflow，第一版只支持线性步骤。
- 步骤只能来自 Step Registry。
- 前端默认不暴露 Agent、Tool、Step、Registry、Executor 或 Workflow JSON 等内部概念。

## 开发规则

- 不要修改 `/Users/regen-bio/project-nlp`。
- 不要在未确认前设置 GitHub remote，不要 push。
- 不要提交真实 `.env`、token、SSH key、API key 或其他密钥。
- 默认不要读取 `.venv`、`node_modules`、`data`、`logs`、`outputs`、`.pytest_cache`、`__pycache__`。
- 修改代码时保持模块任务边界，优先小改动。
- 不破坏已有合理逻辑；修复或扩展时保持原功能完整。
- 注释要少而有用，重点解释非显然的工程取舍。

## Demo 交付优先级

这个仓库当前优先级是让面试官 10 分钟内看懂并能跑通 MVP：

1. 文档清楚说明项目目标和边界。
2. Demo 场景可按固定步骤演示。
3. 运行命令集中在 README。
4. 风险和不支持能力主动说明。
5. 不为了展示复杂度加入 DAG、定时任务、多用户权限或默认真实 LLM。

