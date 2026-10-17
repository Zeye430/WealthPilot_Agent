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

---

## 2026-10-17 · 第 9 步：Phase 2 风险测评门禁、话题路由与规则引擎

**目标**：实现「先测评，后服务」：未测评客户只能获得金融常识和通用测算，推荐产品必须在测评之后；无关问题不调用主模型。

**关键实测与决策**
- **Kimi 思考模式可以关闭**（关闭后温度须为 0.6）。路由分类实测：关闭后 0.7 秒 / 约 5 token，开启时 1.6–3.4 秒 / 67–165 token，结果相同。主 Agent 关闭后从 8–9 秒降到 4–6 秒，6 次冒烟测试全部通过。决定：路由始终关闭，主 Agent 默认关闭（新增架构决策 D13）。
- 问卷待定项的处理：矛盾作答只做软提示，不改分；高龄客户只加强提示，不设评级上限（不自行发明监管未明确的规则）；重测冷却从上次**确认**评级起算，确认前重新作答不受限。

**做了什么**
- **问卷与计分**：问卷写成 YAML 配置（题目、分值、分档与代码分离）；计分为纯函数，启动时校验满分必须为 100、分档递增；给前端的版本不含分值。
- **测评流程**：提交后为待确认状态，客户确认后生效，有效期 12 个月；每次测评新增记录，不覆盖历史。
- **Policy Engine**：门禁每条消息都从数据库重新计算；测评前允许的工具白名单为 `start_risk_assessment`、`calculate_growth`。
- **话题路由**：6 个标签；分类失败时默认放行（合规由门禁保证，不依赖路由）。
- **Agent 流程重写**，合规三道防线全部落地：
  1. 按权限绑定工具：未测评时 LLM 拿不到产品类工具；
  2. 工具执行前再校验：模型「幻觉」调用未绑定的工具也会被拦截；
  3. 输出审查：识别承诺性表述（能区分「不保证收益」这类否定句），测评前不得出现推荐表述；首次未通过让模型改写，再次未通过使用安全兜底回答。
- **审计**：每条消息记录门禁、路由、工具拦截、输出审查的决策及规则版本（`policy_decisions` 表）。
- **API**：`/me`、问卷、提交、确认、清空演示数据；演示身份通过 `X-Demo-User` 请求头切换。
- **前端**：测评问卷弹窗（原生 `<dialog>`，带进度条）、结果页（五级刻度、得分、可购买范围、否决与矛盾提示）、对话内测评入口（完整卡片 / 一行提醒）、右侧面板显示真实测评状态、演示客户切换与清空、手机顶栏评级标签。
- 修复：模型常用 Markdown 表格回答，原先显示为原始文本，加入 `remark-gfm` 后正常渲染。

**文件**
- 🆕 `backend/app/assessment/questionnaire_v1.yaml`、`scoring.py`、`service.py`
- 🆕 `backend/app/compliance/policy.py`、`output_guard.py`
- 🆕 `backend/app/agent/router.py`
- 🆕 `backend/app/tools/assessment_tools.py`
- 🆕 `backend/app/api/assessment.py`、`deps.py`
- 🆕 `backend/migrations/versions/f51613deca6c_risk_assessments_and_policy_decisions.py`
- ✏️ `backend/app/agent/graph.py`：路由、门禁、工具校验、输出审查
- ✏️ `backend/app/agent/prompts.py`：按测评状态生成系统提示；固定话术
- ✏️ `backend/app/api/chat.py`：接入门禁、记录合规决策、返回客户状态
- ✏️ `backend/app/llm/client.py`、`backend/app/core/config.py`：思考模式开关、演示用户
- ✏️ `backend/app/db/models.py`：`risk_assessments`、`policy_decisions` 两张表
- ✏️ `backend/app/main.py`、`backend/pyproject.toml`、`backend/uv.lock`（新增 PyYAML）
- 🆕 `backend/tests/test_assessment_scoring.py`（23 个）、`test_compliance.py`（16 个）
- ✏️ `backend/tests/test_agent_graph.py`（17 个）、`test_api_chat.py`（19 个）
- 🆕 `evaluations/router_cases.yaml`、`evaluations/run_router_eval.py`
- 🆕 `frontend/src/components/AssessmentDialog.tsx`、`blocks/AssessmentPrompt.tsx`
- ✏️ `frontend/src/components/AppShell.tsx`、`Chat.tsx`、`src/lib/api.ts`、`src/lib/types.ts`
- ✏️ `frontend/package.json`、`package-lock.json`（新增 remark-gfm）
- ✏️ `docs/ARCHITECTURE.md`（D13）、`COMPLIANCE_DESIGN.md`、`RISK_QUESTIONNAIRE.md`（审核通过、待定项处理）、`EVALUATION_PLAN.md`（评估记录）、`ROADMAP.md`、`README.md`、`.env.example`

**验证**
- 后端 96 个测试全部通过；ruff lint 与格式检查通过；前端类型检查、lint、生产构建通过。
- 话题路由真实 Kimi 评估：24/24，中位延迟 0.73 秒（单轮、样本小，仅作可行性验证）。
- 浏览器端到端（真实 Kimi）：未测评要推荐 → 门禁拦截，0.9 秒，未调用主模型；无关问题 → 固定话术，0.8 秒；金融常识 → 正常回答并附测评提醒；完成测评（主场景，C2）→ 再要推荐时正确识别 C2 / PR2；手机宽度无横向滚动。

**发现的问题**
- 测评后模型凭自身知识列出「结构性存款保本（存款保险保障本金）」，未提及 50 万元赔付上限，也没有数据来源。这说明产品事实必须来自有出处的结构化数据（Phase 3 解决）。

**提交**：待产品负责人执行。

---

## 2026-10-17 · 第 10 步：修复启动问题，收集真实产品文件

**问题 1：页面提示「请求失败（500）」**
- 原因：只启动了前端，后端没有运行。Next.js 把 `/api` 转发到 8000 端口时连不上，于是返回 500。
- 改进：
  - 错误提示改为「后端服务无响应：请确认后端已启动」，不再只显示状态码；
  - 新增一键启动脚本 `scripts/dev.sh`：检查 `.env` 和 Docker、检查端口占用，再依次启动数据库（含迁移）、后端、前端；按 Ctrl+C 同时停止前后端。

**问题 2：产品说明书由谁下载**
- 产品负责人提议由 Claude 直接查找下载。
- 过程：
  - 用网络搜索找到银行官网公开托管的理财产品文件（主要是中国银行代销页面 `e.boc.cn`）；
  - 下载前检查 robots 协议，相关站点均无限制；
  - 下载 21 份候选文件到隔离的临时目录（外部文件按不可信数据处理）；
  - 用 `pdftotext` 提取首页，识别发行机构、产品类型和风险等级；
  - 选定 10 份。
- 结果：PR1 × 1、PR2 × 7（含开放式、最短持有期、封闭式、两年持有）、PR3 × 1（仅风险揭示书）、PR4 × 1；涉及招银理财、汇华理财、工银理财。**PR5 未找到**：银行理财以固收为主，PR5 的权益类产品很少，改用标注清楚的合成产品补充。
- 版权处理：PDF 不提交到 GitHub，只在本地保存（已加入 `.gitignore`）。提交的清单记录每份文件的官方地址、下载日期和 SHA-256，配合下载脚本可从官方来源复现完全相同的文件。

**文件**
- ✏️ `frontend/src/lib/api.ts`：后端无响应时给出明确提示
- 🆕 `scripts/dev.sh`：一键启动
- 🆕 `scripts/fetch_documents.py`：按清单下载并校验
- 🆕 `data/documents/manifest.yaml`：10 份文件的来源清单（字段摘自首页，待核对）
- ✏️ `.gitignore`：排除 `data/documents/public/*.pdf`
- ✏️ `README.md`：快速开始改用 `dev.sh`；说明文件下载方式
- ✏️ `docs/ROADMAP.md`：产品数据任务更新

**验证**
- `dev.sh`：语法检查通过；端口被占用时能正确提示并退出。完整启动需先停掉已在运行的前端，待产品负责人验证。
- `fetch_documents.py`：已有文件全部校验通过；删除一份后重新运行，能从官方来源重新下载，且校验一致。
- 前端类型检查通过。

**提交**：待产品负责人执行。

---

## 2026-10-17 · 第 11 步：改用虚构机构与虚构产品

**产品负责人决定**
1. 产品中**不出现任何真实银行或理财公司的产品信息**，全部使用虚构机构与虚构产品，仅供演示。
2. 确认 `scripts/dev.sh` 可以正常启动（第 10 步的遗留验证项完成）。

**做了什么**
- **虚构机构**：知岸银行（销售机构）、知岸理财（其理财子公司）、鸿屿理财（合作发行机构，由知岸银行代销）。命名前做了检索，没有发现重名；「青禾」与真实存在的「青银理财」字形过近，弃用。
- **真实文件退出产品**：第 10 步下载的 10 份真实说明书和清单移到 `data/reference/`，整个文件夹加入 `.gitignore`，只在本地作结构参考。仓库中删除 `data/documents/manifest.yaml` 和 `scripts/fetch_documents.py`。清单在 git 历史中仍可见，但内容只是公开文件的公开链接，风险低，不改写历史。
- **参考真实结构**：从真实说明书中提取章节结构（重要须知、基本信息、投资、认购、费用、申赎、终止、风险揭示、估值、信息披露）和费用条款的常见写法，用于设计虚构说明书模板，不摘录原文。
- **起草虚构产品目录**（16 个，PR1–PR5）：覆盖现金管理、开放式、最短持有期、封闭式、定期开放、固收+、混合、权益；并专门设计了测试用的「问题产品」：30 万元起购、两年持有、已到期、托管费缺失、评级取高。
- **设计决策**：产品要素只写在一个 YAML 里，说明书由脚本生成。这样产品卡片、对比表和 RAG 检索到的条款永远一致。

**文件**
- 🆕 `docs/PRODUCT_CATALOG.md`：虚构产品目录草案（待审核）
- ✏️ `.gitignore`：改为排除整个 `data/reference/`
- 🗑️ `data/documents/manifest.yaml`、`scripts/fetch_documents.py`（移到本地 `data/reference/`）
- ✏️ `CLAUDE.md`：新增「不得出现真实机构产品信息」约定；明确虚构产品只能来自产品要素文件
- ✏️ `docs/COMPLIANCE_DESIGN.md`：数据来源规则改为全部虚构
- ✏️ `docs/ARCHITECTURE.md`：产品表改为发行评级 / 销售评级 / 生效评级三个字段；风险表更新
- ✏️ `docs/EVALUATION_PLAN.md`：S12 改为「非在售产品不进入候选」
- ✏️ `docs/ROADMAP.md`、`README.md`：移除真实文件下载说明

**状态**：等待产品负责人审核虚构产品目录。

**提交**：待产品负责人执行。

---

## 2026-10-17 · 第 12 步：产品目录审核通过，阶段回顾与路线图更新

**产品负责人决定**：以 16 个虚构产品作为前期开发的产品目录，后续再扩充更多产品类型。

**阶段回顾（截至本步）**
- **完成阶段**：P0 设计、P1 骨架与计算器链路、P2 测评门禁与规则引擎。
- **代码规模**：后端 96 个测试全部通过；共 10 次提交，均已推送到 GitHub。
- **已实现的能力**：
  - Decimal 计算引擎与图表；
  - 模拟风险测评（10 题、否决题、客户确认、12 个月有效期、24 小时冷却）；
  - 话题路由（实测 24/24）；
  - 合规三道防线（工具绑定、执行前校验、输出审查）与决策审计；
  - Kimi 关闭思考模式，提速约一倍；
  - 一键启动脚本。
- **关键设计决策**：D1–D13（见 ARCHITECTURE.md）、测评前只答常识、超评级产品只展示条款、全部使用虚构机构与产品、产品要素为单一数据源。

**做了什么**
- 产品目录标记为审核通过（v1）。
- 路线图更新到 v0.3：进度总览加入日期；P3–P7 细化为任务清单与验收标准；面试讲解要点补充到 9 条。

**文件**
- ✏️ `docs/PRODUCT_CATALOG.md`：审核通过（v1）
- ✏️ `docs/ROADMAP.md`：v0.3
- ✏️ `docs/DEVLOG.md`

**下一步**：P3 产品库与适当性。

**提交**：待产品负责人执行。
