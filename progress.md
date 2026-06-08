# Progress

本文记录 `/Users/regen-bio/project-nlp-hybrid` 的 MVP 进度。

## 阶段状态

| 阶段 | 状态 | 说明 |
| --- | --- | --- |
| 工作区脚手架 | 完成 | 已建立 hybrid workspace。 |
| Python workflow core 迁移 | 完成 | 保留 Orchestrator、Planner、Executor、Schema、Registry 和工具边界。 |
| FastAPI 服务 | 完成 | 已提供 session、upload、prepare、execute、feedback、follow-up、run 查询接口。 |
| Next.js Web App | 完成 | 已提供普通用户 Web 交互入口。 |
| 运行指南 | 完成 | README 已包含安装、启动、测试、demo 和边界说明。 |
| 交接收敛 | 进行中 | 补齐 AGENTS、handoff、progress 和 Codex notes。 |

## 已验证结果

上一阶段已完成以下验证：

- Python 测试：129 passed。
- Python compileall：通过。
- 前端测试：5 passed。
- Next.js build：通过。
- FastAPI `/api/health`：返回 `{"status":"ok"}`。
- Next.js 首页：HTTP 200。

本次文档收敛阶段不重新运行测试、构建或安装依赖。

## 已支持能力

- 文档总结。
- 文档问答和 citations。
- FAQ 客服问答复用文档问答链路。
- CSV/XLSX 表格画像、筛选、聚合、排序、chart_spec 和业务洞察。
- 反馈修改生成新版本并完整重跑。
- SQLite 最小持久化记录 session、workflow version、run 和 step run。

## MVP 边界

- 默认 `LLM_MODE=mock`。
- 只支持线性 Workflow。
- 不做真实联网搜索。
- 不做后台定时任务。
- 不做多用户权限。
- 不做缓存复用或增量执行。
- 不执行模型生成代码。

## 下一步最小任务

1. 完成交接文档收敛。
2. 只读检查改动范围，确认只新增文档。
3. 如进入提交前验证阶段，再按 README 跑测试、构建和敏感信息检查。
4. 面试演示时优先展示五个固定 demo 场景和 harness-first 设计取舍。

