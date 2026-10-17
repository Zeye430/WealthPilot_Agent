# WealthPilot AI — 开发日志

> 按时间顺序记录每一步做了什么、为什么、涉及哪些文件、如何验证。最新条目在最下方。
> 文件标记：🆕 新建 · ✏️ 修改 · 🗑️ 删除。提交哈希对应 GitHub 仓库 `Zeye430/WealthPilot_Agent`。

---

## 2026-10-16 · 第 1 步：需求评审

**目标**：阅读《WealthPilot AI 产品开发指引》，评估可行性并提出建议，暂不写代码。

**结论与建议**
- 原指引的方向与合规意识都很扎实，主要风险在范围过大、执行顺序不合理。
- 建议：先写清「未测评状态下能输出什么」；加入模拟风险测评；尽早打通一条端到端链路；精简 Phase 0 文档；语音移出 MVP。
- 指出原文档未覆盖的技术风险：中文分词检索、中文 Embedding 选型、说明书费率表解析、国内生成式 AI 备案要求。

**产品负责人决定**
- 项目定位：求职作品集；每周约 10 小时，2 周内完成。
- 模型：Kimi。
- 分工：工程实现主要由 Claude 完成，产品负责人重点学习设计与系统架构。
- 合规原则：国内理财销售须先完成风险测评，Agent 一开始就核对客户测评状态。

**文件**：无（仅讨论）。

---

## 2026-10-16 · 第 2 步：Phase 0 设计文档

**目标**：产出精简版设计文档，作为后续开发依据。

**做了什么**
- 在 `WealthPilot/` 内单独初始化 git 仓库（原先的 git 根目录是上一级的 `Will's Daily Work/`，混有其他项目）。
- 把原计划的 6 份文档合并为 4 份，并写下 11 条架构决策（ADR）及取舍。
- 核心设计：单主 Agent + 强类型工具 + 独立合规引擎；合规三道防线（流程门禁 / 工具自检 / 输出审查）；**按测评状态动态绑定工具**。
- 用 Python Decimal 核对评估方案中的全部计算基准数字。

**文件**
- 🆕 `.gitignore`
- 🆕 `CLAUDE.md`：开发约定（每次会话自动读取）
- 🆕 `docs/ARCHITECTURE.md`：架构、ADR、Agent 工作流、数据模型、API
- 🆕 `docs/COMPLIANCE_DESIGN.md`：测评门禁、规则清单、输出审查、交接触发条件
- 🆕 `docs/EVALUATION_PLAN.md`：计算 / 适当性 / RAG / 交接测试用例
- 🆕 `docs/ROADMAP.md`：两周 7 个阶段的计划

**提交**：`a897b8f`，推送到 GitHub（首次提交）。

---

## 2026-10-16 · 第 3 步：记录两条合规边界决策

**产品负责人确认**
1. 客户点名查询超出其评级的产品：可展示客观条款，同时给出风险提示，不做推荐；客户本身也无权限购买。
2. 测评前可以回答金融常识，但限于理财范围，不能成为通用问答机器（避免浪费 token），并提醒先做测评；推荐产品必须在测评之后。

**设计落地**
- 新增 D12「话题路由」：在主 Agent 前做轻量分类，无关问题用固定话术回复、不调用主模型。
- 明确分工：路由负责成本，可能分错；门禁负责安全，不依赖路由结果。
- 测评前允许通用复利 / 通胀计算（Claude 的判断，已请产品负责人确认，可通过配置收紧）。

**文件**
- ✏️ `docs/ARCHITECTURE.md`：新增 D12、§4.3 话题范围，更新流程图与权限表
- ✏️ `docs/COMPLIANCE_DESIGN.md`：§1 权限表、§3.2 已确认边界、新增 `OUT_OF_SCOPE` 规则
- ✏️ `docs/EVALUATION_PLAN.md`：新增 S02b–S02e、S04b 用例
- ✏️ `CLAUDE.md`

**提交**：`bebe40f`

---

## 2026-10-16 · 第 4 步：Phase 1 后端

**目标**：后端骨架，以及「提问 → Kimi 调用计算工具 → Decimal 精确计算」的链路。

**做了什么**
- **虚拟环境**：用 uv 管理（`backend/.venv` + `uv.lock` 锁定版本），后端不打包，直接用 `app/` 目录结构。
- **计算引擎**（`app/calculations/core.py`）：复利、现值、单利、定投、通胀折现、申购费（内扣 / 外扣）、赎回费分档、到手金额。纯函数、Decimal、不依赖 LLM；输入错误抛出中文提示，原样返回给 LLM 用于修正参数。
- **工具层**（`app/tools/calculation_tools.py`）：3 个 LLM 工具，分别为 `calculate_growth`、`generate_return_scenarios`、`calculate_fees`。每个工具返回两份内容：JSON 给 LLM 看，UI 块直接交给前端，因此**图表数字不经过 LLM**。
- **Agent**（`app/agent/graph.py`）：LangGraph 的 agent ↔ tools 循环，每轮工具调用上限 6 次；免责声明由代码追加。
- **LLM 适配层**（`app/llm/client.py`）：经 OpenAI 兼容接口接入 Kimi，换模型只改配置。
- **数据库**：Docker 中运行 PostgreSQL 16 + pgvector（宿主机端口 5433）；Alembic 迁移创建 `conversations`、`messages`、`tool_calls` 三张表。
- **API**：`POST /api/v1/chat`、`GET /api/v1/conversations/{id}`、`GET /health`。
- **测试**：用「脚本化假模型」代替 Kimi 测试 Agent 流程，不花 token、结果确定。

**文件**
- 🆕 `backend/pyproject.toml`、`backend/uv.lock`、`backend/.python-version`
- 🆕 `backend/app/main.py`
- 🆕 `backend/app/core/config.py`
- 🆕 `backend/app/calculations/core.py`
- 🆕 `backend/app/tools/calculation_tools.py`
- 🆕 `backend/app/agent/graph.py`、`backend/app/agent/prompts.py`
- 🆕 `backend/app/llm/client.py`
- 🆕 `backend/app/db/models.py`、`backend/app/db/session.py`
- 🆕 `backend/app/api/chat.py`、`backend/app/api/health.py`
- 🆕 各模块 `__init__.py`
- 🆕 `backend/alembic.ini`、`backend/migrations/`（含首个迁移 `97e688879f78`）
- 🆕 `backend/scripts/check_llm.py`：Kimi 连通性与工具调用冒烟测试
- 🆕 `backend/tests/test_calculations.py`（24 个）、`test_agent_graph.py`（7 个）、`test_api_chat.py`（5 个）、`fakes.py`
- 🆕 `backend/Dockerfile`、`backend/.dockerignore`
- 🆕 `docker-compose.yml`、`.env.example`

**验证**：36 个测试全部通过；ruff lint 与格式检查通过。

**遇到的问题**
- Docker Desktop 未运行，已启动。
- `docker compose` 因 `.env` 不存在而校验失败，已把 `env_file` 改为可选。
- ruff 的 `B008` 是 FastAPI `Depends()` 写法的误报，已在配置中忽略。

---

## 2026-10-16 · 第 5 步：Phase 1 前端

**目标**：对话界面，并能渲染结构化回答（测算凭证、折线图）。

**做了什么**
- 用 `create-next-app` 搭建 Next.js 16.4 + React 19 + Tailwind CSS 4；安装 Recharts 与 react-markdown。
- Next.js 16 比 Claude 的训练数据新，先阅读了 `node_modules/next/dist/docs/` 中的 rewrites、cacheComponents 等文档。
- 浏览器只访问 Next.js，`/api` 经 rewrites 代理到 FastAPI，无需处理跨域。
- **视觉设计**：冷调纸白配青黛主色，主色不用红（红色在中国市场代表上涨）；标题和数字用思源宋体，正文用思源黑体。唯一的视觉重点是「测算凭证」：齿孔分隔线、点线引导的金额行、「假设情景·非承诺」印章。
- **图表**：配色用 dataviz 校验脚本验证（色盲可分辨，浅色 / 深色模式都通过）；对比度偏低的颜色配了「查看数据表」。
- 中文输入法选词时按回车不会误发送（`isComposing` 判断）。
- 用 Playwright 截图检查桌面、深色、手机三种视图，修复 4 个问题：输入框双重描边、手机占位文字被截断、手机提示文字过长、图例文字误用系列颜色。

**文件**
- 🆕 `frontend/`（脚手架：`package.json`、`tsconfig.json`、`eslint.config.mjs`、`AGENTS.md`、`public/` 默认图标等）
- ✏️ `frontend/next.config.ts`：rewrites 代理、standalone 输出
- ✏️ `frontend/src/app/layout.tsx`、`globals.css`、`page.tsx`
- 🆕 `frontend/src/components/AppShell.tsx`：三栏布局（导航 / 对话 / 我的情况）
- 🆕 `frontend/src/components/Chat.tsx`
- 🆕 `frontend/src/components/blocks/CalculationSlip.tsx`
- 🆕 `frontend/src/components/blocks/LineChartBlock.tsx`
- 🆕 `frontend/src/lib/api.ts`、`frontend/src/lib/types.ts`
- 🆕 `frontend/Dockerfile`、`frontend/.dockerignore`
- 🗑️ `frontend/README.md`（脚手架默认文件，由根目录 README 代替）
- 🆕 `README.md`：项目门面（设计要点、架构、快速开始、进度）
- ✏️ `docs/ROADMAP.md`

**与原设计的偏差**：shadcn/ui 推迟到 Phase 2，等需要表单组件时再引入。

**验证**：TypeScript 检查、ESLint、生产构建均通过；手机宽度无横向滚动。

**提交**：`c298ebc`（第 4、5 步合并提交）

---

## 2026-10-16 · 第 6 步：接入真实 Kimi 验证

**做了什么**
- **安全处理**：发现 API Key 被写进了会提交的 `.env.example`。确认 GitHub 上的版本为空、未泄露后，把 `.env.example` 还原为空模板，Key 只留在 `.env`。
- **排查 401**：Key 属于国际站，只能用 `api.moonshot.ai`，不能用 `api.moonshot.cn`。
- **排查 400**：`kimi-k2.6` 和 `kimi-k3` 只接受 `temperature=1`。
- **模型对比**：两个模型各测 3 次，6 次都正确调用了工具、数字一致。k2.6 约 9 秒、k3 约 18 秒，默认选 **kimi-k2.6**。
- **Prompt 调整**：模型会自己写大段风险提示，与代码追加的声明重复；改为只在正文用一句话点明关键假设。
- **检查脚本**：同时接受完整金额和「万元」近似写法（温度为 1 时措辞会变化）。
- **浏览器端到端测试**：定投 + 通胀、多档收益追问，金额都已人工核算，正确；多轮上下文正常。

**文件**
- ✏️ `.env.example`：国际站地址、kimi-k2.6、temperature=1
- ✏️ `backend/app/core/config.py`：默认值同上
- ✏️ `backend/app/agent/prompts.py`
- ✏️ `backend/scripts/check_llm.py`
- ✏️ `README.md`、`docs/ROADMAP.md`：标记 Phase 1 完成

**验证**：36 个测试通过；真实 Kimi 冒烟测试 6/6 通过。

**提交**：`74e3766`、`75305ce`

---

## 2026-10-17 · 第 7 步：建立开发日志与提交流程

**产品负责人要求**
1. 建立开发日志，从头记录每一步做了什么、开发了哪些文件。
2. 以后的代码提交由 Claude 给出命令，产品负责人自己执行，Claude 不再直接提交或推送。

**文件**
- 🆕 `docs/DEVLOG.md`：本文件，补记第 1–6 步
- ✏️ `CLAUDE.md`：新增「开发日志」与「Git 提交」约定

**提交**：待产品负责人执行（命令见对话）。

---

## 2026-10-17 · 第 8 步：风险测评问卷调研与起草

**目标**：为 Phase 2 起草模拟风险测评问卷，交产品负责人审核。

**调研结论**
- 国内**没有全国统一的固定问卷**：监管规定评估维度和结果用途，题目、分值、分档由各机构自行设计。
- 公开资料：华夏银行（百分制、C1-0 否决子类）、中国银行 2022 年版权益须知（五级评级、有效期 12 个月、客户确认评估结果、评级不一致取较高者）、基金业协会适当性指引（最低类别投资者）。
- 决定：**不照搬任何机构的问卷**（避免冒用之嫌），只参考维度与结构，自行编写并标注「模拟问卷」。

**做了什么**
- 起草 10 道题，覆盖 9 个评估维度，外加 1 道一票否决题；满分 100 分，分档 C1–C5。
- 用 9 个典型客户画像实际计算并校准分档线：主场景客户得 51 分，评为 C2，符合预期。
- 补充两条此前设计里没有的规则：客户确认评级后才生效；产品评级不一致时取较高者。

**文件**
- 🆕 `docs/RISK_QUESTIONNAIRE.md`：问卷草案（题目、分值、分档、特殊规则、校准验证、审核清单）
- ✏️ `docs/COMPLIANCE_DESIGN.md`：有效期补充依据；新增客户确认、评级取高规则；链接到问卷文档
- ✏️ `docs/DEVLOG.md`

**状态**：等待产品负责人审核问卷。

**提交**：待产品负责人执行。
