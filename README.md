# Natural Language Workflow Builder Hybrid

本仓库是 `project-nlp` 的本地混合架构实验版本，目标是用 FastAPI + Next.js 替代 Streamlit 产品层，同时保留 Python Workflow 核心能力。

## 当前阶段

- Python 后端负责 Orchestrator、Planner、Executor、工具链和 SQLite。
- TypeScript 前端负责普通用户交互。
- 默认 `LLM_MODE=mock`，不需要 API Key。
- 本仓库当前只做本地实验，不配置 GitHub remote，不 push。

## 本地环境

- Python 3.9.6
- Node.js 20+
- npm workspace

## 计划能力

- 文档总结
- 文档问答 / FAQ
- 表格分析
- 用户反馈后生成新版本并完整重跑

## 安全边界

- 不提交 `.env`。
- 不提交 token、SSH key、API key。
- 上传文件只保存到 `data/uploads/`。
- 普通用户界面不暴露 Agent、Tool、Step、Registry、Executor、Workflow JSON 等内部概念。
