# Codex Notes

本文记录后续 Codex 协作规则，避免把 MVP 收敛任务扩大成新功能开发。

## 当前任务口径

目标是把 `project-nlp-hybrid` 收敛成可提交 demo：

- 文档要让面试官快速理解项目目标、架构边界、运行方式和风险控制。
- 代码保持现状，不为交接收敛改 API、Schema、前端流程或工具实现。
- 旧项目 `/Users/regen-bio/project-nlp` 只作为历史背景，不读取、不修改。

## 默认不要做的事

- 不要扫描旧项目全仓。
- 不要修改 `/Users/regen-bio/project-nlp`。
- 不要读取 `.venv`、`node_modules`、`data`、`logs`、`outputs`、`.pytest_cache`、`__pycache__`。
- 不要运行测试、构建或安装依赖，除非用户明确要求。
- 不要设置 GitHub remote，不要 push。
- 不要提交真实 `.env`、token、SSH key 或 API key。

## 修改代码时的原则

如果后续确实需要改代码：

- 先读当前模块实现，再决定最小修改点。
- 保持 Python core、FastAPI API、Next.js Web、tools、storage 的任务边界。
- 不要让 LLM 输出直接变成可执行代码。
- 新增 Step 前先确认 Registry、Schema、Executor 和前端展示是否都需要同步。
- 表格能力继续优先使用声明式操作。
- 用户可见文案应保持普通用户语言，不暴露内部 Agent/Tool/Workflow 细节。

## Demo 讲解主线

推荐讲解顺序：

1. 这是一个自然语言 Workflow Builder 的本地 hybrid MVP。
2. 用户只看到上传、描述需求、确认方案、执行、结果、反馈修改。
3. 内部通过 Orchestrator 控制状态，通过 Planner 生成受约束方案。
4. Workflow 必须经过 Schema 和 Registry 校验。
5. Executor 只执行已注册步骤，默认线性执行。
6. mock LLM 是为了保证 demo 本地可复现；真实 LLM 是可选适配层，不是 MVP 前提。

## 后续可选方向

这些不是当前交付必须项：

- 接入真实 LLM 并补输出校验、失败重试和成本边界。
- 增强运行可观察性，在 Web 展示 run 和 step 摘要。
- 扩展 Planner，让自然语言到处理方案的覆盖面更广。
- 引入 DAG，但要先补 workflow schema、executor 调度和错误恢复策略。
- 增加权限、部署、队列和任务调度能力。

