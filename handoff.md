# Handoff

本文是 `/Users/regen-bio/project-nlp-hybrid` 的交接说明。当前目标是面试 demo 提交，不是生产级系统上线。

## 当前状态

第一阶段本地 hybrid MVP 已完成：

- Python 继续负责 Workflow 编排、校验、执行和工具链。
- FastAPI 提供服务接口。
- Next.js + TypeScript 提供普通用户 Web 交互。
- 默认 `LLM_MODE=mock`，本地运行不需要真实 API Key。
- Workflow 受 Schema、Step Registry 和 Executor 约束。

已有提交：

- `579d7ef init: scaffold hybrid workspace`
- `da466bc feat: migrate python workflow core`
- `d9aa297 feat: add fastapi workflow service`
- `611eeca feat: add next web app`
- `7198747 docs: add hybrid running guide`

上一阶段已验证：

- `.venv/bin/python -m pytest`：129 passed
- `.venv/bin/python -m compileall backend core tools storage tests examples config.py`：通过
- `npm test --workspace apps/web`：5 passed
- `npm run build --workspace apps/web`：通过
- FastAPI `/api/health` 返回 `{"status":"ok"}`
- Next.js 首页 HTTP 200

本次交接收敛只补文档，不重新运行测试、构建或安装依赖。

## 面试官视角说明

这个 MVP 的核心不是“让 LLM 做一切”，而是 harness-first：

- LLM 或规则 Planner 只产出受约束方案。
- Workflow JSON 必须通过 Schema 和 Registry 校验。
- Executor 只执行已注册步骤，第一版只支持线性流程。
- 表格分析使用声明式筛选、聚合、排序和 chart_spec，不执行模型生成代码。
- 文档问答基于本地文件片段和 citations，无依据时拒答。

这套取舍让 demo 更稳定，也能体现安全、可测试、可复现的工程判断。

## 五个 Demo 场景

1. 上传文档并生成总结
   - 输入：TXT、MD、PDF 或 DOCX 文档。
   - 用户动作：上传文件，描述“帮我总结这份文档”。
   - 系统输出：处理方案、执行结果和稳定 mock 总结。
   - 预期结果：可完成文档读取和总结，不需要真实 LLM。

2. 只基于文件回答问题
   - 输入：包含事实内容的文档。
   - 用户动作：上传文件，提出只应基于文件回答的问题。
   - 系统输出：答案和 citations。
   - 预期结果：有依据时引用来源片段；无依据时拒答并返回空 citations。

3. 分析销售表格
   - 输入：CSV 或 XLSX 销售数据。
   - 用户动作：上传表格，描述统计、筛选、聚合或排序需求。
   - 系统输出：聚合表格、chart_spec 和业务洞察文本。
   - 预期结果：只执行声明式分析，不执行模型生成 Python。

4. 基于 FAQ 模拟客服问答
   - 输入：FAQ 文档。
   - 用户动作：上传 FAQ，提出客服问答类问题。
   - 系统输出：基于 FAQ 的回答和 citations。
   - 预期结果：复用文档问答链路，不新增客服 Agent。

5. 用户要求每周生成报告
   - 输入：文档或表格。
   - 用户动作：要求“每周生成报告”。
   - 系统输出：降级为一次性报告的处理方案。
   - 预期结果：不创建后台定时任务、cron 或 recurrence。

## 当前不支持能力

- 不支持真实联网搜索或浏览器检索。
- 不支持后台定时任务。
- 不支持 DAG，只支持线性 Workflow。
- 不支持多用户权限、云同步或团队协作权限模型。
- 不支持缓存复用或增量执行。
- 默认不调用真实 LLM；OpenAI-compatible API 仅作为可选适配层。
- 不执行模型生成的 Python、`eval`、`exec`、`query`、`lambda` 或 pandas expression。

## 后续建议

Demo 提交前优先确认：

- README、handoff、progress 和 Codex notes 口径一致。
- Web 端五个场景能按普通用户语言讲清楚。
- Git remote 保持为空，未提交真实密钥。
- 所有新增材料只服务于 MVP 交付，不引入新功能范围。

