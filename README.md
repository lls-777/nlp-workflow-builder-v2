# Natural Language Workflow Builder Hybrid

本仓库是 `project-nlp` MVP 的本地混合架构演进版本：Python 继续负责 Workflow 编排、校验、执行和工具链，FastAPI 提供服务接口，Next.js + TypeScript 提供普通用户 Web 交互。

当前仓库只做本地开发、本地测试和本地 commit。不要在未确认前设置 GitHub remote，不要 push。

## 架构说明

```text
apps/web                    Next.js App Router 前端
backend/python_service       FastAPI API 层
core/                        Orchestrator、Planner、Executor、Schema、Registry、LLM 适配
tools/                       文档、检索、问答、表格分析、文本生成工具
storage/                     SQLite 与文件存储
examples/                    示例数据、Workflow JSON 和本地 demo runner
```

核心边界保持不变：

- 单一 Orchestrator 负责状态流转。
- Planner 第一版使用规则 + 模板生成或修改处理方案。
- Workflow 是受约束 JSON，步骤只能来自 Step Registry。
- Executor 执行前校验 Workflow，第一版只支持线性步骤。
- 表格分析只执行声明式操作，不执行模型生成 Python。
- 默认 `LLM_MODE=mock`，本地运行不需要 API Key。

## 运行环境

- Python：按 3.9.6 兼容实现和验证。
- Node.js：建议 20+。
- 包管理：npm workspace。
- 前端框架：Next.js App Router。
- 后端框架：FastAPI。

## 安装

```bash
cd /Users/regen-bio/project-nlp-hybrid
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
npm install
```

环境变量可从 `.env.example` 复制，但默认 mock 模式无需配置真实密钥：

```bash
LLM_MODE=mock
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=
```

不要提交真实 `.env`、token、SSH key 或 API key。

## 启动后端

```bash
.venv/bin/python -m uvicorn backend.python_service.main:app --host localhost --port 8000
```

主要接口：

- `POST /api/sessions`：创建会话。
- `POST /api/sessions/{session_id}/uploads`：上传文件，限制单文件 20MB、最多 10 个、总计 50MB。
- `POST /api/sessions/{session_id}/prepare`：根据自然语言需求生成追问或处理方案。
- `POST /api/sessions/{session_id}/execute`：确认后执行当前处理方案。
- `POST /api/sessions/{session_id}/feedback`：根据反馈创建新版本并等待确认。
- `POST /api/sessions/{session_id}/follow-up`：同一批文件继续提问或复用当前方案新跑一次。
- `GET /api/sessions/{session_id}/runs/{run_id}`：查询运行结果。

## 启动前端

另开一个终端：

```bash
npm run dev --workspace apps/web
```

默认访问：

```text
http://localhost:3000
```

前端只展示普通用户概念：上传文件、描述需求、系统追问、处理方案、确认执行、结果展示、反馈修改和执行详情。默认页面不暴露 Agent、Tool、Step、Registry、Executor 或 Workflow JSON 等内部概念。

## 运行测试

```bash
.venv/bin/python -m pytest
.venv/bin/python -m compileall backend core tools storage tests examples config.py
npm test --workspace apps/web
npm run build --workspace apps/web
```

## 运行三个 Python Demo

```bash
.venv/bin/python -m examples.run_demo_workflow
.venv/bin/python -m examples.run_document_qa_workflow
.venv/bin/python -m examples.run_data_analysis_workflow
```

## 当前支持能力

- 文档总结：读取 TXT、MD、PDF、DOCX 后生成稳定 mock 总结。
- 文档问答：文档切分、本地 TF-IDF 检索、基于来源片段回答并返回 citations。
- FAQ 客服问答：复用文档问答链路，不新增客服 Agent。
- 表格分析：CSV/XLSX 读取、画像、筛选、聚合、排序、chart_spec 输出、业务洞察文本。
- 反馈修改：创建新版本并完整重跑，不做增量执行。
- 本地持久化：SQLite 最小表结构记录 session、workflow version、run、step run。

## 五个验收场景

1. 上传文档并生成总结：可执行。
2. 只基于文件回答问题：可执行，无依据时拒答并返回空 citations。
3. 分析销售表格：可执行，输出聚合表格、chart_spec 和业务洞察。
4. 基于 FAQ 模拟客服问答：可执行，复用文档问答能力。
5. 用户要求每周生成报告：降级为一次性报告，不创建定时任务。

## 当前不支持能力

- 不支持真实联网搜索或浏览器检索。
- 不支持后台定时任务、cron、recurrence。
- 不支持 DAG，只支持线性 Workflow。
- 不支持多用户权限、云同步或团队协作权限模型。
- 不支持缓存复用或增量执行。
- 不执行模型生成的 Python、eval、exec、query、lambda 或 pandas expression。
- 默认不调用真实 LLM；OpenAI-compatible API 仅作为可选适配层。

## 安全与工程边界

- 上传文件只保存到 `data/uploads/`。
- 后端执行单文件 20MB、最多 10 个、总计 50MB 校验。
- 文件路径校验使用 `Path.resolve()` 和 `relative_to()`，避免路径穿越和软链接越界。
- 日志不记录用户文件全文、API Key、token 或 SSH key。
- `.env.example` 只保留空模板，不包含真实凭据。
- 本地 Git remote 应保持为空，确认交付目标前不要 push。

## 敏感信息检查

```bash
git status --short
git log --oneline -5
git remote -v
git ls-files
git grep -n -I -E 'BEGIN (OPENSSH|RSA|DSA|EC|PRIVATE) KEY|ghp_|github_pat_|sk-|AKIA|api[_-]?key|token|secret|password'
find . -maxdepth 4 -type f \( -name '.env' -o -name '*.key' -o -name '*.pem' -o -name 'id_rsa' -o -name 'id_ed25519' -o -name '*secret*' -o -name '*token*' \) -print
```

预期：没有 remote，没有真实 `.env`，没有 token、SSH key 或 API key。
