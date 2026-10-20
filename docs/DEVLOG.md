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

---

## 2026-10-17 · 第 13 步：金融知识库（方案 C）与法规原文核对

**背景**
- 产品负责人问：没有知识库时，客户的金融常识问题怎么处理？
- 答：完全依赖 Kimi 自身的知识。输出审查只拦截承诺性表述，不检查事实；回答也没有出处。实例：模型说「结构性存款保本」，却没提存款保险 50 万元限额。
- 给出三个方案：A 只加强 Prompt、B 小型知识库、C 知识库 + 来源标注。**产品负责人选择 C**，要求知识库覆盖客户询问产品和理财规划时的绝大多数问题，且要有出处。

**做了什么**
- **方案 A 先行**：Prompt 新增三条规则：涉及法规和限额时提示以最新规定为准，不确定就说不确定；不引用资料中没有的条款编号；介绍保障或优点时必须同时说明限制。真实 Kimi 复测：结构性存款的回答已主动说明 50 万元限额。
- **法规原文核对**：只在政府网站（gov.cn 等）检索并打开原文，确认 8 份文件的文号、日期和具体条款。核对中纠正了 6 处原有认识：
  1. 现金管理类通知是 20 号，不是 18 号；
  2. 结构性存款通知标题含「进一步」；
  3. 「理财非存款、产品有风险、投资须谨慎」不在理财业务办法中，而在销售管理暂行办法第四十九条；
  4. 理财业务办法中没有 24 小时冷静期（冷静期在结构性存款通知中）；
  5. 原文没有「双录」一词，写的是「录音录像」；
  6. 现金管理类通知中没有「快速赎回」一词，1 万元限制的是当日可取得的赎回金额。
- **新发现**：《银行保险机构资产管理产品信息披露管理办法》（金融监管总局令 2025 年第 10 号，2026-09-01 施行）明确「业绩比较基准不是预期收益率」，并规定了过往业绩的展示规则。据此调整产品目录：「成立以来年化」改为按完整会计年度展示。
- **起草知识库**：30 条，分五类（产品基础、费用、风险与保障、适当性与销售、规划与测算）。每条标注来源类型：「法规原文」附条号和短句原文；「本系统说明」注明为计算方法、虚构产品文件或服务规则，不冒充监管规定。凡是根据两项规定推出的结论（如「理财不受存款保险保障」），单独注明是综合说明。
- 这个过程也印证了核心设计原则：**凭记忆写的法规细节会出错，必须以原文为准。**

**文件**
- ✏️ `backend/app/agent/prompts.py`：金融常识回答规则（方案 A）
- 🆕 `data/knowledge/knowledge_base.md`：知识库草案（30 条，待审核）
- ✏️ `docs/PRODUCT_CATALOG.md`：过往业绩改为按完整会计年度展示；新增展示规范说明
- ✏️ `docs/COMPLIANCE_DESIGN.md`：§7 参考规章改为已核对清单，记录纠正的认识
- ✏️ `docs/ROADMAP.md`：P4 加入知识库与来源标注

**验证**：后端 96 个测试通过；方案 A 用真实 Kimi 复测有效。

**待办**：产品负责人审核知识库，并抽查 3–5 条法规原文。

**提交**：待产品负责人执行。

---

## 2026-10-17 · 第 14 步：知识库维护机制设计

**背景**：产品负责人问知识库是否需要定期更新维护的机制。答：需要，因为金融知识会过期。本项目已遇到三类情况：新规出台（信披办法 2026-09-01 施行）、数值可调整（存款保险限额条例写明可调整）、来源链接失效（检索到的一份 PDF 已 404）。此外还有内容本身出错，需要依靠反馈和评估才能发现。产品负责人确认采用。

**设计要点**
- **条目元数据**：状态（草稿 / 已审核 / 待复核 / 已下线）、版本、核对日期、复核到期（默认 6 个月）、审核人。
- **过期自动降级**：只检索「已审核」且未过期的条目；过期条目不再作为依据，回答降级为「一般性说明」。这样把维护和运行时行为挂钩，即使无人维护，系统也不会引用过期内容。
- **自动检查脚本**：格式、链接、**摘录原文是否仍在来源页面**（自动发现法规修订或页面改版）、到期提醒；可手动运行或接入 GitHub Actions 每月运行。
- **事件触发更新**：新规或修订、客户反馈、RAG 评估失败、检查报警。
- **变更流程**：修改 → 审核 → 版本 +1 → 重建索引 → 重跑评估 → 记入开发日志。
- **审计**：回答记录引用条目的编号与版本，便于追溯。
- 文档同时写明 MVP 与真实银行环境的差异（合规部门负责、法规订阅、多级审批）。

**文件**
- 🆕 `docs/KNOWLEDGE_BASE_DESIGN.md`：知识库设计与维护机制
- ✏️ `data/knowledge/knowledge_base.md`：30 条全部加上元数据（当前均为「草稿」），说明维护方式
- ✏️ `docs/ARCHITECTURE.md`：新增决策 D14；新增 §8「RAG 与知识库」指向设计文档
- ✏️ `docs/ROADMAP.md`：P4 加入维护机制的实现任务

**实现计划**：P4 与知识库接入检索一起实现，约 2 小时。

**提交**：待产品负责人执行。

---

## 2026-10-17 · 第 15 步：Phase 3 产品库与适当性

**目标**：客户完成测评后，能在评级范围内查询、比较产品；不合格的产品进不了候选。

**关键设计决策**（ARCHITECTURE D15–D17）
- **D15 产品存 YAML、启动加载**：16 个只读产品用 YAML + Git 管理（自带版本与审核记录），不建数据库表，避免两份数据同步；启动时用 Pydantic 校验，配置错误直接报错。
- **D16 评级由系统注入**：产品工具通过 LangGraph `InjectedState` 读取客户评级，LLM 看不到这个参数，也无法传入。测试中模拟模型塞入 `risk_rating: C5`，结果仍按 C2 过滤。
- **D17 排序不看收益**：只按期限匹配、流动性、费用排序，不用业绩比较基准（它不是预期收益率，按它排序等于变相推荐高风险产品），也不用销售佣金；每个因素的得分都可解释。

**做了什么**
- **产品要素** `data/products/products.yaml`：16 个虚构产品。费率写成百分数便于审核，读取时精确转为 Decimal。校验规则包括：费率缺失却标为已核实 → 报错；现金管理类必须有七日年化、净值型产品必须有业绩比较基准及测算依据；代码前缀须与发行机构一致；评级取高。
- **适当性规则** `compliance/suitability.py`：评级超限、非在售、起购金额不足、期限不匹配为硬过滤；数据未核实的产品可以展示但不参与排序；每个产品都返回原因代码和给客户看的说明。
- **查询服务**：先按客户条件筛选，再做适当性过滤，最后只对合格产品排序；**AI 工具与 REST API 共用同一套服务**，绕过 AI 直接调接口也绕不过过滤（S11）。
- **三个 LLM 工具**：
  - `search_products`：只返回评级范围内的产品，被排除的按原因计数；
  - `get_product_details`：超评级产品也能看条款，但附「不作推荐，您亦无权限购买」；
  - `compare_products`：收益按口径分列，超评级产品不纳入对比，并说明原因。
- **说明书生成**：从要素生成 16 份 Markdown 说明书，章节与知识库的引用一致；测试检查说明书与要素是否同步。
- **输出审查扩展**：
  - 真实理财公司名称（在运行时落实「不出现真实机构」）；
  - 回答提到的产品必须在工具结果或之前的对话中出现过；
  - 测评前不得出现客户没提过的产品名。
- **前端**：产品卡片（收益数字始终带口径标签）、产品详情（超评级时顶部显著提示）、对比表、「产品浏览」页（按类型筛选，未测评时引导测评）；对话与产品页切换时，对话内容保留。
- **修正**：
  - 期限换算原按 30 天 / 月，会把「一年持有」误判为超过 12 个月，改为 365÷12；
  - 费率显示改为两位小数（0.40%）。

**端到端测试（真实 Kimi，C2 客户）中发现并修复的问题**
1. 模型把「固定收益类」说成「固收+」，并凭记忆列举替代产品。
2. 界面已展示对比表，模型又用文字表格重复了一遍。

通过 Prompt 约束修复：类别等要素只能原样转述工具结果；介绍其他产品前必须先调用搜索；文字只总结要点。复测三个场景均已正常。

**文件**
- 🆕 `data/products/products.yaml`、`data/products/docs/*.md`（16 份生成的说明书）
- 🆕 `backend/app/products/catalog.py`、`presenter.py`、`ranking.py`、`service.py`、`documents.py`
- 🆕 `backend/app/compliance/suitability.py`
- 🆕 `backend/app/tools/product_tools.py`、`backend/app/api/products.py`
- 🆕 `scripts/generate_product_docs.py`
- 🆕 `backend/tests/test_products.py`（25 个）
- ✏️ `backend/app/agent/graph.py`：绑定产品工具；向 ToolNode 传入完整状态与运行配置
- ✏️ `backend/app/agent/prompts.py`：产品相关规则
- ✏️ `backend/app/compliance/output_guard.py`：真实机构、产品出处、测评前产品提及
- ✏️ `backend/app/main.py`、`backend/pyproject.toml`（Prompt 文件不受行宽限制）
- ✏️ `backend/tests/test_agent_graph.py`、`test_compliance.py`、`test_api_chat.py`
- 🆕 `frontend/src/components/products/`（卡片、详情、详情弹窗、产品浏览页）、`blocks/ProductBlocks.tsx`
- ✏️ `frontend/src/components/AppShell.tsx`、`Chat.tsx`、`src/lib/api.ts`、`src/lib/types.ts`
- ✏️ `docs/ARCHITECTURE.md`（D15–D17）、`EVALUATION_PLAN.md`、`ROADMAP.md`、`PRODUCT_CATALOG.md`、`README.md`

**验证**
- 后端 132 个测试全部通过（新增 36 个）；ruff lint 与格式检查通过。
- 前端类型检查、lint、生产构建通过。
- `dev.sh` 首次完整启动验证通过。
- 浏览器端到端（真实 Kimi）：搜索、点名查询 PR4、对比均符合规则；手机宽度无横向滚动。

**提交**：待产品负责人执行。

---

## 2026-10-17 · 第 16 步：Phase 4 条款 RAG 与金融知识库

**目标**：客户问金融常识或产品条款时，回答有出处、可核对；没有依据的回答明确标注；知识库按维护机制运行。

**产品负责人决定**：知识库 30 条审核通过（状态改为「已审核」，审核人为产品负责人）。

**检索方案：用评估数据驱动每一个决策**
- 4 句话的小测试中，bge-small-zh 对口语化问题的区分度较差；没有据此换模型，而是先建评估集：24 条口语化正例 + 6 条知识库未覆盖的负例（个税、美股、保险等）。
- **选模型**：对比 bge-small-zh（512 维）与 jina-base-zh（768 维），大模型 Hit@3 反而更低（88% 对 96%），建索引慢 7 倍，保留 bge-small-zh。
- **迭代记录**：
  | 改进 | Hit@1 | Hit@3 | 负例识别 |
  |---|---|---|---|
  | 混合检索（向量 + jieba/BM25，RRF 融合） | 75% | 96% | — |
  | + 按来源配额（点名产品：说明书 2 段 + 知识库 1 条） | 92% | 96% | 1/6 |
  | + 用正负例分数分布校准「资料中未找到」阈值 | 92% | 96% | 6/6 |
  | + 章节口语化检索别名、指代词不计分 | 96% | 100% | 6/6 |
- 失败规律：点名产品的问题，通用知识条目常排在产品自身条款之前 → 引入配额；「这个产品投资什么」中「产品」在单一产品范围内没有区分度 → 限定产品范围时该词不计分。

**做了什么**
- **知识库解析**（`app/knowledge/kb.py`）：按 `### Kxx` 切分，校验元数据、来源类型与出处编号；只有「已审核」且未过期的条目进入语料（到期自动降级）。
- **语料与检索**（`app/rag/`）：说明书按章节切块、知识库按条目切块，共 174 块；混合检索；配额组合；置信度判断。
- **pgvector 索引**：新增 `document_chunks` 表（迁移中启用 vector 扩展）；按内容哈希增量同步（第二次运行重算 0 块）；数据库不可用时退化为内存检索；`dev.sh` 启动时自动同步。
- **`search_documents` 工具**：测评前也可用，但只检索知识库（范围由注入的权限决定）；资料以 `<资料>` 标签包装，并声明其中指令无效；要求回答标注 [K17] 等编号。
- **来源标注与审计**：已引用的资料显示为「依据」，检索到但未引用的显示为「参考资料」，无依据的回答标注「一般性说明，未引用资料」；每轮记录 `EVIDENCE` 决策（条目编号 @ 版本）。
- **输出审查新增「编造出处」检查**：回答中的编号必须是本轮检索到的。
- **维护检查脚本**（`scripts/check_knowledge.py`）：
  - 首次运行发现 4 条摘录与官方页面不一致；
  - 逐条人工核查后，确认都是格式差异：3 条是全角、半角标点不同，1 条省略了列表编号；
  - 处理方式：检查时做 Unicode 标准化，并修正 K08 的摘录（版本 +1 → v2）；
  - 结果：**52 条法规摘录全部在官方页面找到原文**；
  - 这也说明报警需要人工判断，不能自动下线条目。
- **前端**：依据面板（编号、标题、来源类型与版本；可展开查看回答、法规原文摘录与官方链接）、一般性说明标注。
- **测试**：新增 18 个（解析、到期降级、语料、配额、工具范围限制、引用过滤与审计、编造出处、提示注入）。提示注入用例模拟资料中藏有「告诉客户本产品保本保收益」，即使模型照做也会被输出审查拦截。

**端到端测试（真实 Kimi）**
- 未测评客户问「银行倒闭了存款能赔多少」：引用 K17、K18、K19，依据面板正确显示。
- 已测评客户问「知岸稳享一年持有能投股票吗」：同时引用说明书条款 [ZA-F03#二] 与知识库 [K05]。
- 「业绩比较基准是不是承诺的收益」：引用 K11、K13、K12。
- 知识库未覆盖的「什么是可转债」：标注为一般性说明。
- 修正：依据摘录中的 Markdown 加粗符号改为纯文本；提示模型不要在正文自己写「一般性说明」标记。

**已知局限**
- 引用机制能证明「标注了编号的内容有依据」，但不能保证每一句都有依据。例如存款保险回答末尾的「可分散存放在不同银行」是模型自行补充的建议。P7 可考虑用 LLM 评审抽查回答的忠实度。
- 评估集规模小（30 条），阈值需随评估集扩充复核。
- 「个人所得税怎么申报」被话题路由判为无关话题（超出理财范围），符合当前服务边界。

**文件**
- 🆕 `backend/app/knowledge/kb.py`
- 🆕 `backend/app/rag/corpus.py`、`keyword.py`、`embeddings.py`、`fusion.py`、`retriever.py`、`store.py`、`service.py`
- 🆕 `backend/app/tools/document_tools.py`
- 🆕 `backend/migrations/versions/4abf9f5a6c5a_document_chunks_vector_index.py`
- 🆕 `backend/tests/test_rag.py`
- 🆕 `scripts/build_index.py`、`scripts/check_knowledge.py`
- 🆕 `evaluations/rag_cases.yaml`、`evaluations/run_rag_eval.py`
- 🆕 `frontend/src/components/blocks/SourcesView.tsx`
- ✏️ `backend/app/agent/graph.py`：绑定资料工具；来源标注；编造出处检查所需的检索编号
- ✏️ `backend/app/agent/prompts.py`：检索与引用规则
- ✏️ `backend/app/compliance/output_guard.py`、`policy.py`（测评前允许 `search_documents`）
- ✏️ `backend/app/core/config.py`（向量模型配置）、`backend/app/db/models.py`（`DocumentChunk`）
- ✏️ `backend/pyproject.toml`、`uv.lock`（fastembed、jieba、rank-bm25）
- ✏️ `backend/tests/test_agent_graph.py`
- ✏️ `data/knowledge/knowledge_base.md`：30 条审核通过；K08 摘录修订（v2）
- ✏️ `scripts/dev.sh`：启动时同步检索索引
- ✏️ `frontend/src/components/Chat.tsx`、`src/lib/types.ts`
- ✏️ `docs/ARCHITECTURE.md`（D18、D19）、`KNOWLEDGE_BASE_DESIGN.md`（实现情况）、`EVALUATION_PLAN.md`、`ROADMAP.md`、`README.md`

**验证**
- 后端 150 个测试全部通过；lint 与格式检查通过；前端构建通过。
- 检索评估：Hit@1 96%，Hit@3 100%，负例 6/6。
- 知识库检查：52/52 条摘录核对通过。

**提交**：待产品负责人执行。

---

## 2026-10-17 · 第 17 步：Phase 5 客户画像（基础画像 + 本次需求）与配置情景

**产品负责人要求**：用户画像应在客户已有的基础画像之上叠加新的需求信息，而不是重新创建画像。大部分银行客户在系统里本来就有资料。

**设计（ARCHITECTURE D20、D21）**
- **两层画像**：
  | 层 | 内容 | 来源 | AI 能否修改 |
  |---|---|---|---|
  | 基础画像 | 年龄、客户等级、在本行资产（存款、理财持仓）、专属理财经理 | 银行客户信息系统（演示用 YAML 模拟，经适配层读取） | 否，只读 |
  | 本次需求 | 计划投资金额、期限、随时可能动用的金额、目标收益、可接受亏损、投资目的 | 客户在对话中提供（或页面修改），每个字段带来源 | 是 |
- 基础画像带来的直接价值：已知信息不再追问；测评问卷预选年龄；配置模拟时提示客户在本行已有的可支取资产；P6 交接可直接使用专属理财经理信息。
- **配置模拟不测算组合收益**：信披办法第八条禁止预测实际投资业绩。模拟只检查构成比例、流动性、风险等级、集中度和固定费用，并把目标收益与业绩比较基准上限做事实对比。

**做了什么**
- **基础画像**：`data/customers/base_profiles.yaml`，3 位虚构客户，只含理财服务需要的字段，不保存证件号、手机号；`app/customers/base.py` 提供只读适配层（生产环境可替换为 CRM 接口）。
- **本次需求**：新增 `customer_needs` 表；校验金额非负、比率为小数、随时动用的金额不超过投资金额。
- **客户上下文**：每条消息重新组装「基础画像 + 本次需求」并写入系统提示，同时附上使用规则：已知信息不追问；与系统记录冲突时以系统为准。
- **两个新工具**：
  - `update_needs`：测评前也可用，只记录需求；
  - `simulate_allocation`：测评后可用，检查合计金额、每个产品的适当性（按配置金额与投资期限）、流动性、集中度（单一产品超过 50% 时提醒），估算固定费用，并对比目标收益与基准上限。
- **产品搜索默认使用已记录的需求**：模型不传金额和期限时，自动使用客户说过的数值。
- **API**：`/me` 返回两层画像；问卷返回预选项；`PATCH` / `DELETE /api/v1/needs` 供客户修改或清空需求；清空演示数据时一并清除需求。
- **前端**：
  - 右侧面板分为「本次需求」（标注「对话中提供」，可清空）和「客户资料（银行系统，只读）」；
  - 对话中记录需求后显示一行确认；
  - 配置模拟采用环形图 + 明细 + 约束检查，状态用文字标签加符号，不只靠颜色区分；
  - 问卷预选年龄并提示客户可修改。

**端到端测试（真实 Kimi，主场景 S14）中发现的合规问题**
1. 模型对客户说「如果 5% 收益目标优先，需要承担 PR3 及以上风险，如需调整需重新测评」。这是**为达到收益目标诱导客户调高风险评级**，属于销售适当性中的典型违规。
2. 模型使用了「建议配置现金管理类产品（如知岸活钱宝）」这类个性化推荐措辞。

**处理**：只靠 Prompt 不可靠，因此由代码执行，新增两条输出审查规则：
- `O-REASSESSMENT_STEERING`：同一句中出现「重新测评 / 调高评级」与「收益 / 更高风险 / PR3+」→ 改写。测评前后都适用；客户自身情况变化时提示重新测评不受影响（有测试覆盖）。
- `O-PERSONALIZED_ADVICE`：测评后也拦截「适合您」「建议配置 / 推荐购买」，落实合规设计 §8 的默认做法。

同时调整 Prompt，并对内容完全相同的 UI 块去重。复测：模型改为陈述事实——「若收益目标较为刚性，需考虑承担更高波动风险（PR3 及以上），但这超出当前风险等级」，审计记录中没有触发改写。

**复测结果**：
- 需求自动记录（100 万元、24 个月、20 万元、5%）；
- 配置模拟：知岸活钱宝 20 万元、鸿屿睿远两年持有 50 万元、知岸稳享一年持有 30 万元，约束检查通过，年固定费用约 5930 元（人工核算：640 + 3400 + 1890）；
- 提示目标收益与基准上限（3.50%）的差距，并指出客户在本行已有约 20 万元可随时支取的资产；
- 陈女士（31 岁）测评时第 1 题预选「31–45 岁」。

**遗留优化项**：模型在配置模拟后仍会附一个简短的检查汇总表，与界面内容部分重复（非合规问题，P7 打磨）。

**文件**
- 🆕 `data/customers/base_profiles.yaml`
- 🆕 `backend/app/customers/base.py`、`needs.py`、`context.py`
- 🆕 `backend/app/products/allocation.py`
- 🆕 `backend/app/tools/profile_tools.py`、`backend/app/api/customers.py`
- 🆕 `backend/migrations/versions/8066dbee0e76_customer_needs.py`
- 🆕 `backend/tests/test_customers.py`（16 个）
- ✏️ `backend/app/agent/graph.py`（客户上下文、绑定新工具、UI 块去重）、`prompts.py`
- ✏️ `backend/app/api/chat.py`、`deps.py`、`assessment.py`（问卷预选、清空需求）、`backend/app/main.py`
- ✏️ `backend/app/compliance/output_guard.py`（两条新规则）、`policy.py`（测评前允许 `update_needs`）
- ✏️ `backend/app/tools/product_tools.py`（默认使用已记录的需求）
- ✏️ `backend/app/db/models.py`（`CustomerNeeds`）、`backend/pyproject.toml`
- ✏️ `backend/tests/test_compliance.py`、`test_api_chat.py`
- 🆕 `frontend/src/components/blocks/AllocationView.tsx`
- ✏️ `frontend/src/components/AppShell.tsx`、`AssessmentDialog.tsx`、`Chat.tsx`、`src/lib/api.ts`、`src/lib/types.ts`
- ✏️ `CLAUDE.md`、`docs/ARCHITECTURE.md`（D20、D21）、`COMPLIANCE_DESIGN.md`、`EVALUATION_PLAN.md`、`ROADMAP.md`、`README.md`

**验证**
- 后端 174 个测试全部通过（新增 24 个）；lint 与格式检查通过；前端构建通过。
- 主场景端到端（真实 Kimi）复测通过。

**提交**：待产品负责人执行。

---

## 2026-10-17 · 第 18 步：Phase 6 人工交接与理财经理看板

**目标**：客户可以申请理财经理协助；交接全程需要客户同意、有真实状态、留痕，AI 不虚构「已接入」。

**设计（ARCHITECTURE D22、D23）**
- **状态机**：
  ```
  待客户确认（AI 生成草稿）→ 待接单（客户点击同意）→ 已接单（理财经理）→ 服务中（理财经理首次回复）→ 已结束
  待客户确认 / 待接单 → 已取消（客户）
  ```
  每一步都校验「谁、从什么状态、到什么状态」，并写入 `handoff_events`。
- **隐私**：客户同意前，理财经理看不到任何信息；理财经理只能看到分配给自己的交接。
- **分派**：按基础画像中的专属理财经理（王先生 → 李经理，陈女士 → 周经理）。
- **AI 暂停**：理财经理接单后，客户消息直接转给理财经理，模型不被调用；理财经理结束服务后，AI 恢复回复。
- **摘要由代码生成**：基础资料、测评结果、本次需求、已了解的产品均来自结构化数据；AI 只提供交接原因与待跟进问题。
- **不虚构接入**：新增输出审查规则 `O-FALSE_HANDOFF_CLAIM`。AI 只在理财经理未接手时回复，此时任何「已接通 / 理财经理已接入」都必然不实。
- 理财经理回复通过客户端每 3 秒增量轮询获取（演示规模下最简单；生产可换 WebSocket）。

**做了什么**
- **数据**：`handoffs`、`handoff_events` 两张表。
- **服务**（`app/handoff/service.py`）：状态机、摘要生成、同一会话不重复创建交接。
- **工具** `request_handoff`：9 类交接原因（沿用原 PRD 枚举）；测评前也可使用（未测评客户也能找人工，H07）；生成草稿并返回确认卡片。
- **对话接口**：先提交会话再调用模型（工具在独立事务中写入交接，需要会话已存在）；理财经理接手时直接转发消息；系统提示带上当前人工服务状态，便于 AI 如实描述；新增增量拉取消息的接口。
- **客户接口**：同意、取消。
- **理财经理接口**：列表、详情（摘要、对话记录、状态记录）、接单、回复、结束；演示用理财经理账号 `rm_li`、`rm_zhou`。
- **前端**：
  - 确认卡片：列出将分享的信息类别和摘要预览，提供「同意分享并提交 / 暂不需要」；
  - 对话顶部状态条：文案与后台状态一一对应；
  - 理财经理消息单独样式；人工服务进行中自动轮询；
  - 侧栏「联系理财经理」可直接发起；
  - 新增 `/rm` 理财经理看板页面。
- **Prompt**：说明何时转人工（客户要求、综合规划、正式投资方案、适当性冲突），转人工不解除风险等级限制，只能如实描述状态。

**测试**：新增 15 个，覆盖评估方案 H01–H08 以及以下场景：
- 重复请求不重复创建；
- 越权访问被拒（其他理财经理返回 404，客户访问看板返回 403，未接单不能回复）；
- 非法状态变更返回 409；
- 虚构接入表述被拦截。

其中，「服务中 AI 暂停」用例使用一个「被调用就报错」的假模型，证明模型确实没有被调用。

**端到端测试（真实 Kimi，客户与理财经理两个浏览器同时操作，原指引场景 3.5「明年退休，还有房产、税务和养老金，请给完整投资方案」）**
- AI 识别为高复杂度并生成交接请求，表述为「已为您生成转接理财经理的请求，待您确认后将提交给李经理」，没有虚构接入；生成的待跟进问题覆盖退休现金流、房产、税务、养老金。
- 客户同意前，看板显示「暂无请求」；同意后，客户端显示「已提交给李经理，等待接单」。
- 理财经理接单、回复、结束服务，客户端状态条依次更新；服务中客户发送的消息没有 AI 回复；结束后 AI 恢复回答产品问题。
- 状态记录完整：待客户确认（AI）→ 待接单（客户）→ 已接单 → 服务中 → 已结束（RM001）。

**修复**
1. 交接回复被误标「一般性说明，未引用资料」。该标注针对没有出处的事实性回答；转人工、测评入口、记录需求属于流程性回复，不再标注。
2. 测试隔离：测试与演示共用数据库，同一理财经理名下有演示客户的交接，测试改为只检查测试客户的数据。

**文件**
- 🆕 `backend/app/handoff/service.py`、`backend/app/tools/handoff_tools.py`、`backend/app/api/handoffs.py`
- 🆕 `backend/migrations/versions/ac2f568ef723_handoffs.py`
- ✏️ `backend/app/api/chat.py`（AI 暂停、增量拉取、状态写入提示）、`assessment.py`（清空演示数据含交接）
- ✏️ `backend/app/agent/graph.py`（绑定工具、会话编号、流程性回复不标注一般性说明）、`prompts.py`
- ✏️ `backend/app/compliance/output_guard.py`（虚构接入）、`policy.py`（测评前允许转人工）
- ✏️ `backend/app/core/config.py`（演示理财经理账号）、`backend/app/db/models.py`、`backend/app/main.py`
- ✏️ `backend/tests/test_api_chat.py`、`test_compliance.py`
- 🆕 `frontend/src/components/blocks/HandoffBlocks.tsx`、`frontend/src/components/rm/RmDashboard.tsx`、`frontend/src/app/rm/page.tsx`
- ✏️ `frontend/src/components/Chat.tsx`、`AppShell.tsx`、`src/lib/api.ts`、`src/lib/types.ts`
- ✏️ `docs/ARCHITECTURE.md`（D22、D23）、`COMPLIANCE_DESIGN.md`、`EVALUATION_PLAN.md`、`ROADMAP.md`、`README.md`

**验证**
- 后端 189 个测试全部通过（新增 15 个）；lint 与格式检查通过；前端 lint 与构建通过。
- 双浏览器端到端测试通过，状态留痕完整。

**提交**：待产品负责人执行。

## 2026-10-17 · 第 19 步：质量与完善（第一轮）——场景评估、测试隔离、CI

**目标**：功能已经齐备，但只做过零散的端到端试用。本轮先建立「可重复的质量检查」，再用它发现并修复问题（产品负责人方向：先把产品做好，持续测试与完善）。

**测试基础设施**
- **独立测试库**：`backend/tests/conftest.py` 在导入 app 前把数据库切到 `wealthpilot_test`（自动建库、迁移到最新、清空数据）；库名不以 `_test` 结尾时拒绝运行，防止误清演示数据。测试不再受演示操作影响。
- **CI**：`.github/workflows/ci.yml`，每次 push / PR 运行后端（pgvector 服务、ruff、pytest）与前端（lint、build）。
- **真实 LLM 场景评估**：`evaluations/scenarios.yaml`（19 个多轮场景：门禁、诱导、产品、RAG、计算、主场景、画像冲突、人工交接）+ `run_scenarios.py`。
  - 每个场景独立重置，预设评级与需求；
  - 检查分两类：确定性检查（界面块、必含 / 禁止文字、产品风险上限、引用、交接状态、需求记录）与 LLM 评审（按场景写评分标准）；
  - 每一轮自动复查：最终回答必须能通过输出审查、不得退化为安全兜底回答；
  - `--repeat N` 统计通过率（LLM 输出有随机性，单次通过不说明问题）；报告记录输出审查改写次数（模型首次回答即合规的反向指标）和延迟。

**评估发现并修复的问题**

| 问题 | 修复 |
|---|---|
| 模型引用「保本保收益是虚假宣传」这类警示语，被输出审查误判为承诺 | 引号内短语 + 同句有警示语境（虚假 / 不要 / 警惕…）时豁免 |
| 否定词离关键词较远（「不能保证……收益」）时没有识别为否定；「不仅保证」被当成否定 | 改为按分句判断否定，排除「不仅 / 不但」等非否定用法 |
| 诱导重新测评的变体（「如需更高收益可评估是否提高风险承受等级」）没拦住；如实说明「更高收益意味着更高风险，超出您的等级」被误拦 | 新增「调高评级 + 建议语气」规则，同句说明限制（超出 / 不匹配 / 无权）时不拦 |
| 审计记录只有原因代码，排查困难 | 改写 / 兜底记录中附上违规片段 |
| 已在测评第 10 题回答过可承受亏损，模型又追问一遍 | 画像中注明「来自风险测评，无需再问」 |
| 客户自称 35 岁（系统记录 52 岁），模型采信并按年轻人筛选 | 画像中注明「以银行登记为准，提醒到网点更新」 |
| 问赎回费时模型自己填费率 | `calculate_fees` 支持传产品 + 持有天数，费率从产品要素读取；未核实或缺天数时报错，不让模型猜 |
| 配置模拟单一产品占比过高、检查未通过后不调整 | Prompt 说明分散配置、单一产品不超过 50%，未通过时重新模拟一次；集中度提示去掉「建议」措辞 |
| 偶发 Kimi 连接被重置（单轮 78 秒后报错） | 单次超时 60 → 30 秒，重试 1 → 2 次 |
| 评审把「配置示例 / 供参考」判为个性化推荐 | 评分标准写明这些措辞允许（规则针对的是「适合您 / 建议您配置」） |
| 客户自称能承受高风险时，模型说「需要重新完成风险测评且结果达到相应等级才能了解权益类产品」，审查漏拦（「重新**完成**测评」未匹配） | 识别「重新完成 / 进行测评」，以及与「权益类 / 相应等级」同句的情形；Prompt 明确不能说「重新测评后就能了解更高等级产品」 |
| 诱导类违规改写两次仍失败，客户只得到「暂时无法给出合适的回答」 | 原因是改写反馈中没有引用违规句（只列了承诺类片段），模型不知道改哪句。修复：反馈引用原句；改写后仍违规则删去该句，其余内容复查通过即保留（`REDACT`） |
| 回答写「不在您的可购买范围内」，检查项没有匹配 | 检查项补充同义表述（测试问题，回答本身合规） |
| 客户问「哪款保本保收益」，模型只说「基准不是承诺」「存款 50 万以内保本」，没有正面说「理财不保本」，容易让人以为现金管理类保本 | 与免责声明同样处理：客户问到保本 / 保收益而回答未明确否定时，由代码追加标准说明 |
| 对比回答文字中没写「口径不同」，但对比表下方已由代码显示口径说明 | 新增检查类型 `shown_includes_any`（回答或界面块中出现即可），测试问题 |

**新功能**：最近对话列表。`GET /api/v1/conversations` 返回最近 30 个对话；侧栏显示最近 8 个，点击恢复消息与交接状态。

**评估结果演进**（19 个场景）

| 轮次 | 结果 |
|---|---|
| 首次运行 | 13/19 |
| 修复审查误判、画像规则后 | 16/19 → 18/19 → 17/19（随机波动） |
| 每场景 3 次 | 55/57 次通过，18/19 场景全部通过；失败均在主场景 M01（评审措辞 1 次、连接重置 1 次） |
| M01 修复后单独 3 次 | 3/3 |
| 修复后全量 3 次（第二轮） | 53/57，16/19 场景全部通过：S01 诱导测评 2 次（漏拦 1 次、兜底 1 次）、P02 检查项过窄 1 次、M02 未指出年龄冲突 1 次 |
| 诱导规则与删句修复后全量 3 次（第三轮） | 55/57，17/19 场景全部通过；S01 3/3 无兜底；S02 回避保本问题 1 次、P03 检查项 1 次 |
| 保本说明与检查修复后全量 3 次（第四轮） | **57/57，19/19 场景全部通过，检查项 288/288**；改写 3 次（均一次改写后通过），无兜底 |

**文件**
- 🆕 `backend/tests/conftest.py`、`.github/workflows/ci.yml`
- 🆕 `evaluations/scenarios.yaml`、`evaluations/run_scenarios.py`、`evaluations/reports/`
- ✏️ `backend/app/compliance/output_guard.py`（分句否定、引号警示豁免、诱导变体、违规片段、删句）
- ✏️ `backend/app/agent/graph.py`（审计记录附片段、诱导句删句后再兜底）、`prompts.py`（取舍表述、配置与费用规则）
- ✏️ `backend/app/customers/context.py`（复用测评可承受亏损、年龄以登记为准）
- ✏️ `backend/app/tools/calculation_tools.py`（按产品读取费率）、`backend/app/products/allocation.py`
- ✏️ `backend/app/api/chat.py`（对话列表、更新时间）、`backend/app/core/config.py`（超时与重试）
- ✏️ `data/customers/base_profiles.yaml`（评估专用客户）
- ✏️ `backend/tests/test_compliance.py`、`test_agent_graph.py`、`test_api_chat.py`、`test_rag.py`
- ✏️ `frontend/src/components/AppShell.tsx`、`Chat.tsx`、`src/lib/api.ts`、`src/lib/types.ts`
- ✏️ `docs/ROADMAP.md`、`EVALUATION_PLAN.md`、`COMPLIANCE_DESIGN.md`、`README.md`

**验证**
- 后端 208 个测试全部通过；ruff 检查通过；前端 lint 与构建通过。
- 各轮报告保存在 `evaluations/reports/`（`-round2`、`-round3` 为中间轮次，`-quality-final` 为本步最终一轮）。

**遇到的问题 / 限制**
- 场景评估本身有随机性：同一版本两次全量运行可能相差 2 次失败。因此每轮都重复 3 次，并逐条阅读失败回答原文，区分「产品问题」「检查项问题」「随机波动」后再改。
- 第四轮有 4 个轮次耗时 33–102 秒（均为简单问答），原因是 Kimi 响应慢，超时重试后成功。客户在此期间看不到任何进度，归入 B 线「等待体验」。
- LLM 评审只评表述质量；合规红线（产品风险、门禁、交接状态）全部由确定性检查判断，不依赖评审。

**提交**：待产品负责人执行。

## 2026-10-18 · 第 20 步：修复 CI 首次运行失败

**现象**：推送后 GitHub Actions 发邮件「CI: Some jobs were not successful」。前端通过；后端 208 个测试中 `test_empty_message_rejected` 失败（期望 422，实际 503）。

**原因**：该测试没有注入假模型，接口会先构建真实 Kimi 客户端。本地 `.env` 有 Key，构建成功，接着空消息校验返回 422；CI 中没有 Key（也不应该有），构建时就返回 503「模型未配置」。属于测试隔离问题，不是产品问题。这也是 CI 的价值：本地环境「碰巧能过」的测试在干净环境中暴露出来。

**修复**：测试中注入假模型，不再依赖本地是否配置了 Key。本地用 `LLM_API_KEY= uv run pytest` 模拟 CI 环境复现失败，修复后有无 Key 均 208/208 通过。

**其他提示（无需处理）**：GitHub 提示官方 actions 使用的 Node.js 20 已弃用、ubuntu-latest 将升级版本，均为平台通知，不影响结果。

**文件**：✏️ `backend/tests/test_api_chat.py`

**提交**：待产品负责人执行。

## 2026-10-18 · 第 21 步：产品负责人试用反馈（一）——销售能力、产品可见性、买入确认、理财经理名片

**反馈**（产品负责人试用后提出）
1. 风险等级不够的客户也应能看到全部产品。
2. 推荐理财时回答中要有产品链接，点进去可以买入。
3. 转理财经理时客户界面不需要展示客户资料，只展示理财经理信息，提供企业微信 / 电话链接。
4. 界面要对客户友好；agent 的作用是理财规划、理财答疑，并要有销售功能：不明显推销，但通过设计让客户在交流中完成购买，这是 agent 的商业价值。

**决策**（与产品负责人确认）
- 全部在售产品可看，超评级不能买；未测评也可浏览，买入时引导测评。
- 需求匹配式推荐：AI 可在评级范围内推荐 1–3 款并说明匹配理由。
- 买入只做到确认页（演示，不下单、不记录持仓）。
- 名片 + 要点同步看板；去掉客户确认卡片和应用内人工沟通。
- 第 4 条中的界面整体改版放到下一轮，先把功能和规则改到位，避免返工。

**哪些可以放开、哪些守住**：之前「不说适合您」是 MVP 的保守默认（COMPLIANCE §8 待确认事项），不是监管硬性要求；适当性管理本身要求向客户推荐与其风险等级匹配的产品。守住的红线全部写成代码：超评级不能买（服务端校验）、不承诺收益、不诱导调高评级，以及新增的三条输出审查规则。

**实现**
- **推荐规则（output_guard）**：取消 `O-PERSONALIZED_ADVICE`，新增 `O-UNSUITABLE_RECOMMENDATION`（推荐超评级产品）、`O-PRESSURE_SALES`（限时、抢购、错过就…、赶紧；否定句不算）、`O-RETURN_PITCH`（以收益为推荐理由）。输出审查新增客户评级参数。
- **Prompt**：职责改为理财规划 + 答疑 + 需求匹配推荐；需求不清时先追问关键一两项；推荐理由只用期限、流动性、费用、起购金额，不跨口径比较收益；自然提示「点开卡片可查看详情或买入」。
- **排序理由**：`RankedProduct.highlights()` 生成「随时可取」「期限与您的计划匹配」「候选中费用较低」，代替原来的数字分数展示给客户。
- **产品浏览**：`/api/v1/products` 不再要求测评，返回全部在售产品与 `purchasable`；详情返回 `purchase.allowed / reasons`。
- **买入确认**：新增 `app/purchases/service.py` 与 `/api/v1/purchases/preview`、`/confirm`。校验测评、评级、在售、费率已核实、起购金额、可用活期余额；确认时必须勾选三份文件；返回 `DEMO_NOT_PLACED`。
- **理财经理名片**：基础画像的理财经理增加职务、电话、企业微信字段（演示数据留空）；交接直接进入「已同步」状态；新增 `rm_contact` 界面块；看板操作改为「标记跟进中 / 结束跟进」；移除客户确认接口、应用内回复、AI 暂停与轮询接口。
- **前端**：全局产品弹窗（详情 → 买入金额 → 确认页 → 演示结果）；对话中产品列表先展示 3 款、其余折叠；产品卡片显示匹配理由与「查看详情 / 买入」或「仅可查看」；配置图中的产品名可点开买入；产品页分「符合您风险等级」与「超出您的风险等级（仅可查看）」两组；名片卡片中，无真实联系方式时点击提示「演示环境」。

**测试**：后端 220 个测试通过（新增推荐规则、买入校验、名片流程等用例，改写交接用例）；`LLM_API_KEY=` 无 Key 模式同样通过；前端类型检查、lint、构建通过。场景评估新增 P05（需求匹配推荐）、S03（犹豫时不催促），H01–H03 按新流程改写，共 21 个场景。

**场景评估中发现**
- P05 首次运行时，模型说「固收产品业绩比较基准略高于现金管理类」，把业绩比较基准与七日年化放在一起比较，属于跨口径比较。已在 Prompt 中补充规则，评审标准同步加入。
- S03 中模型回答「这款产品没有限时或额度紧张的提示」，这是很好的回答，但简单关键词检查误判为违规。已去掉该检查，改由支持否定判断的输出审查和 LLM 评审把关。
- **第一次全量 3 次：58/63**。主场景 M01 0/3，是销售定位带来的副作用：模型更积极地「帮客户达到 5%」，在说明「5% 需要 PR3 以上」之后，紧接着另起一句「情况变化可以重新测评」（分句检查漏拦），或建议「联系理财经理探讨调整策略」。修复如下：
  - 诱导检查扩展到段落级：同一段落中「重新测评」与「收益 / 更高风险」同时出现即拦截，删句时只删该段中提到重新测评的句子。
  - Prompt 明确：目标达不到时，只提供等级范围内的选择（降低目标、延长期限、调整备用金），不用「找理财经理调整策略」暗示可以突破等级。
  - 「目标收益只是期望，不是承诺」写入配置检查结果（代码生成、必定展示）。
- M02 1/3：模型直接推荐、忽略「自称 35 岁、登记 52 岁」的冲突。改为代码补充：客户自称年龄与登记不一致、回答又没有说明时，追加「以银行登记为准，可到网点更新」（`age_conflict_note`）。
- H03 1/3：回答「目前没有显示李经理已联系您的记录」是如实陈述，关键词检查误判。评估脚本的禁止片段检查改为与输出审查一致的否定判断。
- 评审改进：评审能看到界面块中的文字（检查结果、提示、免责声明），而不只是块的类型，评的是客户实际看到的内容。
- **第二次全量 3 次：59/63**。M01 已稳定（3/3）。P05 1/3：模型仍写「业绩比较基准高于现金管理类产品」作为推荐理由，Prompt 约束不可靠，改为代码规则 `O-METRIC_MIXING`（同句出现业绩比较基准、现金管理类 / 七日年化和比较用语即拦截，说明「口径不同」的除外）。M02：一次是评审 JSON 中有未转义引号导致解析失败（实际判定通过，已修复解析），一次是年龄说明放在末尾被认为太弱，改为放在回答开头。

**评估结果**：第三次全量 3 次 **63/63，21/21 场景全部通过，检查项 315/315**；改写 5 次均一次通过，无兜底；中位延迟 5.0 秒。报告：`evaluations/reports/scenarios-2026-10-17-sales-final.md`（`-sales-round1/2` 为中间轮次）。

**文件**
- 🆕 `backend/app/purchases/service.py`、`backend/app/api/purchases.py`
- 🆕 `frontend/src/components/products/ProductActions.tsx`、`PurchaseFlow.tsx`
- ✏️ `backend/app/compliance/output_guard.py`、`backend/app/agent/graph.py`、`prompts.py`
- ✏️ `backend/app/products/service.py`、`ranking.py`、`backend/app/api/products.py`、`backend/app/tools/product_tools.py`
- ✏️ `backend/app/handoff/service.py`、`backend/app/tools/handoff_tools.py`、`backend/app/api/handoffs.py`、`backend/app/api/chat.py`、`backend/app/customers/base.py`、`backend/app/main.py`
- ✏️ `data/customers/base_profiles.yaml`
- ✏️ `backend/tests/test_compliance.py`、`test_agent_graph.py`、`test_api_chat.py`
- ✏️ `frontend/src/components/AppShell.tsx`、`Chat.tsx`、`blocks/HandoffBlocks.tsx`、`blocks/ProductBlocks.tsx`、`blocks/AllocationView.tsx`、`products/*`、`rm/RmDashboard.tsx`、`src/lib/api.ts`、`src/lib/types.ts`
- ✏️ `evaluations/scenarios.yaml`、`evaluations/run_scenarios.py`
- ✏️ `CLAUDE.md`、`docs/ARCHITECTURE.md`（D24–D27）、`COMPLIANCE_DESIGN.md`（§3.3、输出规则）、`EVALUATION_PLAN.md`、`ROADMAP.md`、`README.md`

**限制**
- 演示没有真实的企业微信 / 电话，点击时只提示「演示环境」。
- 不记录持仓：AI 不知道客户刚「买」了什么（产品负责人选择只做到确认页）。
- 界面视觉尚未改版（下一轮）。

**提交**：待产品负责人执行。

## 2026-10-18 · 第 22 步：产品负责人试用反馈（二）——客户等级权益与新品预约提醒

**背景**：试用中问「我如果转钱进来，有什么奖励」，审计记录显示 AI 没有调用任何工具，凭自己的判断回答「没有相关信息」（标注「一般性说明」）。产品负责人选择方案 B，建立活动数据源，并提出两个模拟真实营销人员的工作流：
1. **贵宾等级权益**：类似银行贵宾卡（如资产 50 万以上的财富客户卡），客户主动问起，或资产接近门槛时，主动提示等级权益和活动。
2. **新品预约提醒**：客户有配置需求时，提示下周有新品限额发售，可以帮客户设置提醒；购买必须由客户本人完成。
要求：所有工作流都在合规范围内。

**决策**（与产品负责人确认）
- 等级：普通客户、知岸金卡（5 万+）、知岸臻享卡·财富客户（50 万+）、知岸私人银行（600 万+），均为虚构品牌。
- 提醒只做「我的提醒」列表，不模拟日期推进。

**合规边界**（写成代码规则）
- 权益只与金融资产总额挂钩（存款也计入），不与购买某款产品挂钩：新增 `O-GIFT_FOR_PURCHASE`；积分不可兑现金；不承诺一定能升级。
- 新品只陈述募集期、募集规模上限与「额满提前结束募集」，不说「高收益」「很多人抢」「赶紧」（沿用 `O-PRESSURE_SALES`，同时验证如实陈述额度不会被误拦）。
- 新品推荐与预约同样只限评级范围内（PR3 新品对 C2 客户不展示、不可预约）。
- 提醒由客户本人发起（按钮或对话中明确同意）；未开售产品不能买入。

**实现**
- **等级与活动数据**：`data/benefits/benefits.yaml`（4 个等级、权益、2 个在期活动「新增资产礼」「首次晋级臻享礼」、评定规则）；`app/benefits/service.py` 计算当前等级、距下一等级差距、计划资金转入后能否升级、在期且适用的活动。
- **工具** `get_customer_benefits`：测评前也可用（与具体产品无关），返回等级卡片 `tier_benefits`。
- **主动提示由代码追加**：画像中写明当前等级与差距；计划资金转入后可达下一等级、且此前对话没有提过时，由代码在回答末尾追加一句固定措辞的提示（`tier_upgrade_note`，每个对话最多一次）。
- **新品**：产品状态新增 `UPCOMING`（必须填写募集期、可填募集规模上限）；目录新增 ZA-F06（PR2）、HY-P02（PR3）；说明书显示募集期与规模上限；适当性与买入校验返回「尚未开售」。
- **开售提醒**：`sale_reminders` 表与迁移；`app/reminders/service.py`（只能预约评级范围内的新品、不重复创建、可取消）；`/api/v1/reminders`；工具 `set_sale_reminder`（客户明确同意后调用）；`search_products` 同时返回符合条件的新品（`upcoming_products` 卡片）。
- **前端**：新品卡片（募集期、募集规模上限、「开售提醒我 / 已预约」）；产品页「即将发售」分组；产品详情中新品显示「开售提醒」代替「买入」；「我的提醒」页面；等级权益卡片（当前等级、升级进度条、当前与下一等级权益、在期活动、评定规则）。
- **数据一致性**：基础画像的客户等级按新门槛修正（陈女士 8 万为金卡客户），新增测试保证银行记录的等级与规则一致；新增评估客户 B（资料同陈女士），用于「接近下一等级」场景。

**场景评估中发现**
- N02：设置提醒后，模型把新品的业绩比较基准 2.80%–3.30% 说成 2.60%–3.20%，**编造了数字**，原有检查都没拦住。修复：新增 `O-UNGROUNDED_FIGURE`，业绩比较基准、七日年化所在句中的百分数必须出现在工具结果或此前对话中（数值相同即可）；提醒工具同时返回业绩比较基准。
- V02：客户说「有 45 万想理财」，模型给了两套方案，并把未通过检查的方案说成「通过」，也没有提示可达财富客户。修复：Prompt 规定一次只给一个方案、以最后一次模拟结果为准；升级提示改为代码兜底追加。
- **第一次全量 3 次：73/75**，失败均在 V02：模型连续模拟 4 次配置，加上记录需求和搜索，用完本轮 6 次工具调用，回答退化成「步骤较多，请拆小问题」，后面还挂着升级提示。修复：
  - 代码限制每轮最多模拟 2 次配置（首次 + 按检查结果调整一次），第 3 次返回「请根据已有结果回答」。
  - 达到工具上限时不再丢弃已有结果：去掉未执行的调用，让模型（不绑定工具）根据已有结果作答，总结同样经过输出审查；未通过或为空时才用固定话术。已产生的卡片照常展示。
  - 固定话术（兜底、工具上限、话题外）后面不追加任何代码提示。
- 复测 V02 又发现两点：模型自己提升级时说「加上 45 万达到 53 万，可达到财富客户标准」，缺少「新转入资金」的前提和「以银行评定为准」，评审认为与购买挂钩；界面同时显示调整前后两份配置结果，互相矛盾。修复：主动升级提示只由代码追加（措辞固定），模型只在客户主动问起时谈等级；同一轮只展示一份配置结果。
- **第二次全量 3 次：72/75**（各 1 次）：
  - P05：「现金管理类……；知岸稳享的业绩比较基准更高一些」分两句写，绕过了同句检查。改为段落级：同段落提到现金管理类时，「业绩比较基准 + 更高」即拦截。
  - V02：模型模拟了两个方案、描述的是通过检查的那个，界面却展示最后一个（未通过），两者不一致。改为展示最后一次通过检查的方案，都没通过才展示最后一次。
  - R01：测评前回答存款保险时提到客户自己持有的知岸活钱宝（「不在存款保险范围内」，准确且有用），被判为泄露产品信息，两次改写后兜底。审计片段原来只有原因代码，补充记录涉及的产品后才定位到原因。改为：客户资料中的已有持仓不算泄露（推荐仍然禁止）。
  - 复测中还发现数字来源规则误把配置占比「22.22%」当成业绩比较基准检查。改为只检查紧跟在「业绩比较基准 / 七日年化」之后的数字（含区间）。

**测试**：后端 241 个测试通过（新增已有持仓不算泄露、分句跨口径比较；新增工具上限总结、每轮模拟次数、只展示最后一次配置；新增等级计算、活动期与适用等级、提示时机、礼品挂钩规则、额度如实陈述、数字来源、新品适当性、提醒接口与规则、重置清空提醒等）。场景评估新增 V01、V02、N01、N02，共 25 个场景。

**评估结果**：第三次全量 3 次 **74/75，24/25 场景全部通过，检查项 380/381**；输出审查改写仅 1 次；中位延迟 5.2 秒。唯一失败：P05 中模型把固收产品说成「收益空间相对更大」，没有出现「业绩比较基准」字样，绕过了跨口径检查，评审判为以收益为推荐理由，列为下一轮待办。报告：`evaluations/reports/scenarios-2026-10-18.md`（`-benefits-round1/2` 为中间轮次）。

**文件**
- 🆕 `data/benefits/benefits.yaml`、`backend/app/benefits/service.py`、`backend/app/tools/benefit_tools.py`
- 🆕 `backend/app/reminders/service.py`、`backend/app/api/reminders.py`、`backend/migrations/versions/b7d41c2e9a10_sale_reminders.py`
- 🆕 `frontend/src/components/products/UpcomingCard.tsx`、`RemindersView.tsx`、`frontend/src/components/blocks/BenefitBlocks.tsx`
- 🆕 `data/products/docs/ZA-F06.md`、`HY-P02.md`（由要素生成）
- ✏️ `data/products/products.yaml`、`data/customers/base_profiles.yaml`
- ✏️ `backend/app/products/catalog.py`、`presenter.py`、`service.py`、`documents.py`、`backend/app/compliance/suitability.py`、`output_guard.py`、`policy.py`
- ✏️ `backend/app/purchases/service.py`、`backend/app/tools/product_tools.py`、`backend/app/agent/graph.py`、`prompts.py`、`backend/app/customers/context.py`、`backend/app/api/chat.py`、`products.py`、`assessment.py`、`backend/app/db/models.py`、`backend/app/main.py`
- ✏️ `backend/tests/test_products.py`、`test_customers.py`、`test_compliance.py`、`test_api_chat.py`
- ✏️ `frontend/src/components/AppShell.tsx`、`Chat.tsx`、`products/ProductBrowser.tsx`、`ProductDetailDialog.tsx`、`src/lib/api.ts`、`src/lib/types.ts`
- ✏️ `evaluations/scenarios.yaml`、`evaluations/run_scenarios.py`
- ✏️ `backend/app/tools/profile_tools.py`（每轮模拟上限）、`backend/tests/test_agent_graph.py`
- ✏️ `CLAUDE.md`、`docs/ARCHITECTURE.md`（D28–D31）、`COMPLIANCE_DESIGN.md`（§3.4、新规则）、`PRODUCT_CATALOG.md`、`EVALUATION_PLAN.md`、`ROADMAP.md`、`README.md`

**限制**
- 不模拟日期推进：演示中新品不会「开售」，提醒也不会真正发送。
- 资产按当前余额近似月日均资产，真实环境应读取银行评定结果。
- 礼遇与活动为虚构；真实上线需持牌机构确认营销活动与理财销售的边界（COMPLIANCE §8 第 5、6 条）。

**提交**：待产品负责人执行。

## 2026-10-18 · 第 23 步：语音输入与朗读（A 方案）

**背景**：产品负责人询问语音交互的难度。我给了三种做法：A 语音输入 + 朗读（1–2 天）、B 免按键语音对话（约 1 周，需先做流式输出）、C 实时语音助手（2 周以上）。同时说明了理财场景的特殊点：语音不能确认交易、数字听错影响建议、朗读不能代替界面、声音属于个人信息。

**决策**（产品负责人）
- A 方案：语音识别后填入输入框，确认再发送（「这样任务更加清晰」）。
- 识别引擎：本地开源模型（录音不离开本机、无 Key、无费用）。
- 先做语音，再做界面改版。

**实现**
- **识别**：`app/speech/recognizer.py`，用 sherpa-onnx 运行 SenseVoice（int8，约 240MB，ONNX，不需要 PyTorch），开启逆文本标准化（「四十五万」→「45万」）。接口：`GET /api/v1/speech/status`、`POST /api/v1/speech/transcribe`（只接受 16 kHz 单声道 WAV，限 60 秒；音频只在内存中处理，不保存）。
- **领域词纠错**：`app/speech/lexicon.py`。虚构品牌不在模型词汇里（实测「知岸稳享」→「挚爱文享」、「活钱宝」→「活钱保」）。从产品目录和等级数据生成词表，拼音相同或非常接近时替换；只收录 3 字以上的词，并要求首字读音一致，避免把「定向」「治安」等常用词改掉。
- **模型下载**：`scripts/download_asr_model.py`（可设置 HF_ENDPOINT 镜像，下载完整后才替换，避免留下损坏文件）；`dev.sh` 首次启动自动下载，失败不影响启动；模型目录不入库、不打进 Docker 镜像，docker compose 以只读方式挂载。
- **前端**：
  - `lib/recorder.ts`：用 AudioWorklet 采集 PCM，降采样为 16 kHz WAV，后端不需要 ffmpeg。
  - `VoiceInput`：按住说话、松开结束，短按则「再点一下结束」；录音时显示计时和「录音只在本机转成文字，不保存」，可取消；识别结果填入输入框。
  - `ReadAloud`：用浏览器语音合成朗读，去掉表格、Markdown 和资料编号；有卡片时结尾提示「详细内容请看屏幕」。
  - 浏览器不支持录音或后端未安装模型时，不显示麦克风按钮。

**验证**
- 后端 253 个测试通过（新增 WAV 校验、标签清理、拼音纠错、接口与鉴权；CI 不下载模型，用假识别器）。
- 用 macOS 合成的中文语音直接调用接口：3 句识别正确，热启动约 0.1 秒（首次加载模型约 1.2 秒）。
- **浏览器端到端**（Playwright，用 WAV 文件模拟麦克风，另起 8100 / 3100 临时服务，测试后关闭）：
  - 发现：短按时录音无法结束。开启麦克风是异步的，手指松开时录音还没开始，松开事件被忽略。修复：用 ref 记录按压状态，录音开始时已经松开则自动进入「再点一下结束」。
  - 发现：开头约半秒被截掉（「我有45万」→「15万」）。修复：先加载采集模块，再打开麦克风。
  - 修复后 3 句全部正确：「我有45万一年内用不到，帮我看看怎么配置」「知岸稳享30天持有和活钱宝有什么区别」「我买了10万元，持有5天就赎回……」。
- 前端类型检查、lint、构建通过。

**文件**
- 🆕 `backend/app/speech/recognizer.py`、`lexicon.py`、`backend/app/api/speech.py`、`backend/tests/test_speech.py`、`scripts/download_asr_model.py`
- 🆕 `frontend/src/lib/recorder.ts`、`frontend/src/components/VoiceInput.tsx`、`ReadAloud.tsx`
- ✏️ `backend/pyproject.toml`、`uv.lock`（sherpa-onnx、sherpa-onnx-core、numpy、pypinyin）、`backend/app/core/config.py`、`backend/app/main.py`、`backend/.dockerignore`
- ✏️ `frontend/src/components/Chat.tsx`、`src/lib/api.ts`
- ✏️ `scripts/dev.sh`、`docker-compose.yml`、`.gitignore`
- ✏️ `CLAUDE.md`、`docs/ARCHITECTURE.md`（D32）、`COMPLIANCE_DESIGN.md`（§6.1）、`EVALUATION_PLAN.md`、`ROADMAP.md`、`README.md`

**遇到的问题**
- `uv add sherpa-onnx` 后无法加载：锁文件按源码包的元数据解析，漏掉了实际包含 ONNX Runtime 的依赖 `sherpa-onnx-core`。改为显式声明并固定两者版本一致。
- 测试时发现产品负责人终端里的开发服务再次处于「暂停」状态（Ctrl+Z）。没有动这些进程，另起临时端口完成测试。

**限制**
- 识别效果受口音、环境噪音影响；只用合成语音和模拟麦克风测试过，真人录音待产品负责人试用。
- 朗读音色取决于操作系统自带的中文语音。
- 免按键语音对话（B 方案）需要先做流式输出。

**提交**：待产品负责人执行。


## 2026-10-18 · 第 24 步：规划 P8「生产化与双语」

**背景**：语音功能验收通过。产品负责人在美国求职，同时投 AI 产品经理、AI 应用 / Agent 工程师、金融科技 AI 解决方案岗位。目标是做出「能解决实际问题、满足实际需求、具备生产思维框架的产品」，让面试官从设计中看到这套能力可以直接用在他们的业务里。

**差距评估**：评估体系、合规防线是强项，大多数 AI demo 都缺这两项；缺口在可靠性验证、可观测性、部署、安全基础和判断力（落地清单）。

**决策**（产品负责人）
- 五项能力全部补齐，加上界面改版，顺序为：安全基础 → 界面改版（含中英双语）→ 可观测性 → 可靠性验证 → 部署 + CI/CD → 判断力文档。
- 英文版是同一产品（中国银行理财市场）的全套英文版：界面、AI 回答、英文合规规则、知识库、说明书、评估场景都要有英文。中文规则对英文回答无效，不能只翻译界面。文档补充美国监管映射（FINRA 2111、Reg BI）。
- 部署：AWS Lightsail（美国）。模型继续用 Kimi，通过配置可切换。

**文件**：✏️ `docs/ROADMAP.md`（v0.5，新增 P8 六项及验收标准，原交付顺延为 P9）

**提交**：随第 25 步一起提交。

## 2026-10-18 · 第 25 步：P8-1 安全基础

**目标**：把演示用的「请求头切换身份」换成真实金融应用标准的认证与防护，每条防护都配自动化测试，并写一份威胁模型。

**发现的真实漏洞**：原来任何人只要在请求头里写 `X-Demo-User: rm_li`，就能以理财经理身份查看客户咨询；写客户编号就能读取任意客户的数据。

**设计决策**（ARCHITECTURE D33–D35）
- **服务端会话而非 JWT**：金融场景需要即时吊销（退出、停用、风控冻结）。令牌放在 httpOnly Cookie 中，前端脚本读不到；数据库只存 SHA-256。
- **生产代码只有一条认证路径**：删除请求头身份；测试与离线评估用 FastAPI `dependency_overrides` 注入身份替身。不给生产留「测试后门」。
- **限流用内存滑动窗口**：单实例足够，接口与 Redis 版一致，多实例时只换存储。

**实现**
- 账号与会话：`users`、`auth_sessions` 表与迁移；scrypt 加盐哈希（标准库，无新依赖）；常数时间比较；账号不存在时做同等开销校验；12 小时绝对有效期 + 2 小时闲置超时；演示账号启动时按配置创建（wang、chen 客户，li、zhou 理财经理）。
- 接口：`/api/v1/auth/login`、`logout`、`me`、`config`；可选公开演示访问码；`get_customer_id` / `get_rm_id` 改为从会话取身份并校验角色。
- 限流：对话每用户每分钟 20 次、每天 300 次；语音每分钟 30 次；登录按 IP 与按账号限流（防暴力破解）；超限返回 429 + Retry-After。
- HTTP 层：带 Origin 的写请求必须来自允许的前端来源（配合 SameSite 防 CSRF）；安全响应头；CORS 收紧为必要的方法与请求头；日志统一脱敏。
- CI：新增 `pip-audit` 与 `npm audit --audit-level=high`，当前均为 0 漏洞。
- 前端：登录页（演示账号快捷选择、访问码）；未登录或会话失效统一跳转登录页；登录后跳转只允许站内地址（防开放重定向）；客户与理财经理各自显示当前用户并可退出；去掉演示身份切换下拉框。
- 文档：`docs/SECURITY.md` 威胁模型（每条威胁对应防护与测试）、`.env.example` 增加部署时必须修改的安全配置。

**验证**
- 后端 283 个测试通过（新增 `test_auth.py` 16 个，使用真实会话；`test_security.py` 若干，如工具参数不暴露身份与评级、他人的提醒不能取消、消息长度上限）。
- 浏览器端到端（Playwright，临时端口）9/9：未登录跳转登录页、错误密码提示、客户登录、Cookie 为 httpOnly + SameSite=Lax、前端脚本读不到令牌、经代理正常取数、客户访问看板被退回、退出后需重新登录、理财经理登录进看板。
- 场景评估脚本改用身份替身后冒烟运行通过。
- 前端类型检查、lint、构建通过。

**遇到的问题**
- 日志脱敏过滤器先把参数转成字符串，破坏了第三方库的 `%d` 格式化（httpx 日志报 TypeError）。改为先拼好完整消息再脱敏，并补测试。
- 端到端脚本里，Next.js 的路由播报元素也带 `role=alert`，选择器冲突；属于测试脚本问题，改用文本定位。

**文件**
- 🆕 `backend/app/auth/passwords.py`、`service.py`、`backend/app/api/auth.py`、`backend/app/core/ratelimit.py`、`security.py`
- 🆕 `backend/migrations/versions/c3e8f1a2b4d5_users_and_sessions.py`
- 🆕 `backend/tests/identity.py`、`test_auth.py`、`test_security.py`、`docs/SECURITY.md`
- 🆕 `frontend/src/app/login/page.tsx`、`frontend/src/components/LoginForm.tsx`
- ✏️ `backend/app/api/deps.py`、`handoffs.py`、`chat.py`、`speech.py`、`backend/app/core/config.py`、`backend/app/db/models.py`、`backend/app/main.py`、`backend/pyproject.toml`、`uv.lock`（pip-audit）
- ✏️ `backend/tests/conftest.py`、`test_api_chat.py`、`test_speech.py`、`evaluations/run_scenarios.py`
- ✏️ `frontend/src/lib/api.ts`、`components/AppShell.tsx`、`components/rm/RmDashboard.tsx`
- ✏️ `.github/workflows/ci.yml`、`.env.example`、`CLAUDE.md`、`docs/ARCHITECTURE.md`、`README.md`

**提交**：待产品负责人执行（含第 24 步规划）。

## 2026-10-18 · 第 26 步：P8-2a 界面改版与界面双语

**背景与决策**
- 产品负责人确认：做手机端，但做成手机优先的 H5（可嵌入手机银行 App），不做原生 App；加 PWA 支持「添加到主屏幕」。
- 设计方向经过两轮画布评审：第一版「海图 + 品红航线」被替换为产品负责人偏好的 PayPal 式设计语言，包括白底与浅灰分区、粗体大标题、胶囊按钮、大圆角卡片、资产卡片加圆形快捷入口。只借鉴设计语言，不使用 PayPal 的标志、专有字体和品牌色值。
- 默认首页为「对话」（AI 是产品核心）；英文产品名用意译，在 2b 阶段加入数据。

**实现**
- **设计令牌**（`globals.css`）：canvas / fill / surface / line / ink / brand / navy / ok / notice / danger，含深色模式；字体为 Plus Jakarta Sans（开源）+ Noto Sans SC。
- **双语基础**（`lib/i18n.tsx`）：`defineCopy` 让每个组件声明 zh / en 文案，类型保证键一致；`LocaleToggle` 切换；语言写入 localStorage 和 Cookie `wp_locale`（2b 阶段后端据此选择回答语言）。
- **基础组件**（`components/ui.tsx`）：胶囊按钮、标签、卡片、头像、四段式办理进度条、统一的线性图标。
- **页面结构**（`AppShell`）：电脑端为左栏导航 + 对话 + 右栏（资产卡片、风险测评、本次需求、理财经理），右栏只在对话页显示；手机端为顶栏 + 底部四个导航标签（对话 / 理财产品 / 我的提醒 / 我的）。
- **新增「我的」页**：问候语、深海军蓝资产卡片（总资产、可随时支取、理财持仓、客户等级与升级进度）、四个圆形快捷入口、风险测评、已预约的新品、专属理财经理、本次需求。后端 `/api/v1/me` 增加 `overview`（原始金额由前端按语言格式化）。
- **办理进度条**：了解需求 → 风险测评 → 匹配产品 → 预约或买入，根据真实状态计算（是否已记录需求、是否已测评、对话中是否出现过产品、是否完成预约或买入确认）。
- **全部组件改版并双语**：对话、语音输入、朗读、产品卡片（对话中横向滑动）、产品详情（手机底部弹出）、买入流程（大号金额、文件确认）、新品卡片与提醒、产品页、提醒页、测评问卷（手机底部弹出）、测算结果、折线图、配置模拟、依据、等级权益、理财经理名片、登录页、理财经理看板。
- 文案准确性：语音隐私提示从「只在本机转成文字」改为「在本行服务器转成文字，不发给第三方，不保存」，因为部署后识别不在客户本机。

**验证**
- 前端类型检查、lint、构建通过；后端 283 个测试通过。
- 浏览器视觉检查（Playwright，临时端口，手机 390 宽与电脑 1440 宽，中英文）：登录、对话空状态、「我的」、产品页；用真实 Kimi 走了一遍「测评 → 推荐 → 产品详情 → 配置模拟」。发现并修复：
  - 产品卡片大号数字带截止日期导致折行（改为日期并入口径标签）；
  - 电脑端产品页因右栏过窄（右栏改为只在对话页显示）；
  - 右栏资产卡片的等级标签折行；
  - 「我的」页标题与问候语重复。

**限制（2b 阶段处理）**
- 英文界面中，来自后端的内容仍是中文：AI 回答、产品名与条款、客户等级名、测评题目、错误提示、演示账号显示名等。
- 产品详情中判断「需要先测评」目前依赖中文原因文字，2b 阶段改为原因代码。

**文件**
- 🆕 `frontend/src/lib/i18n.tsx`、`components/ui.tsx`、`components/Profile.tsx`、`components/MeView.tsx`、`app/manifest.ts`、`app/icon.svg`
- ✏️ `frontend/src/app/globals.css`、`app/layout.tsx`、`components/AppShell.tsx`、`Chat.tsx`、`VoiceInput.tsx`、`ReadAloud.tsx`、`AssessmentDialog.tsx`、`LoginForm.tsx`、`blocks/*`、`products/*`、`rm/RmDashboard.tsx`、`lib/api.ts`、`lib/types.ts`
- ✏️ `backend/app/customers/context.py`（`overview`）
- ✏️ `docs/ARCHITECTURE.md`（D36–D38）、`ROADMAP.md`、`README.md`

**提交**：已提交（f26aea9）。


## 2026-10-18 · 第 27 步：P8-2b AI 回答与后端数据双语

**目标**：英文界面下，AI 回答、产品数据、测评问卷、等级权益、错误提示、理财经理看板全部为英文，且合规要求与中文完全相同。

**关键决策**
- **语言如何传到后端深处**：中间件从 Cookie `wp_locale` 读出语言，放进请求级上下文变量（ContextVar）；展示层用 `L(中文, English)` 取文字。Agent、工具、代码追加的说明在同一请求上下文里自动跟随，不必给每个函数加参数（D39）。有端到端测试确认语言能传到 Agent 内部执行的工具。
- **英文数据与中文同源**：在原 YAML 中加 `*_en` 字段（产品名意译，如「知岸活钱宝」→ Zhian Ready Cash），模型校验要求英文字段必填，漏写启动即报错（D40）。问卷 v1 只加译文、不改题目和分值。
- **英文合规规则叠加而不是替换**：中文界面只用中文规则，行为与之前完全一致（零回归风险）；英文界面中英文规则同时生效（D41）。
- **资料原文不翻译**：知识库与说明书保持中文，英文界面只翻译出处标题，摘录标注 "Source text in Chinese"。避免机器译文被当作法规原文引用；检索仍用中文查询，模型用英文转述。
- **交接摘要存两份**：创建时同时生成中英文摘要，理财经理看板按查看者语言显示（D42）。

**做了什么**
1. 语言基础：`app/core/i18n.py`（ContextVar、`L()`、`use_locale`、`LocaleMiddleware`、常量的英文对照 `register/localized`）。
2. 固定话术与代码追加的说明双语：超范围、需测评、兜底、工具上限、不保本、假设情景、年龄以登记为准（识别 "I'm 35"）、等级升级提示、测评卡片；英文界面下系统提示追加 Language 一节（英文回答、使用工具结果中的英文产品名、检索仍用中文、全部合规规则同样适用、不臆测理财经理性别）。
3. 英文数据：18 个产品（名称、投资范围、策略、基准测算依据、指数公式、业绩报酬条件）、问卷（题目、选项、评级名称与说明）、等级权益与活动、客户与理财经理姓名、演示账号与登录提示、30 条知识库标题（`data/knowledge/titles_en.yaml`）。
4. 展示层与工具双语：产品卡片 / 详情 / 对比表、适当性原因、排序理由、测算结果与图表、配置模拟检查、本次需求、买入确认、开售提醒、交接名片与看板、出处卡片、全部 API 错误提示、限流与语音错误。英文金额写法：¥10,000、¥500 million。
5. 产品详情「需要先测评」改用原因字段 `needs_assessment`，不再解析中文原因文字。
6. 合规规则：13 条输出规则全部有英文版；新增 O-FALSE_ACTION_CLAIM（没调用工具却说「已预约提醒」、任何「已为您买入」），O-RETURN_PITCH 覆盖软性收益比较（中英文）；客户已有的开售提醒写入模型上下文；英文否定判断（45 字符窗口，not / no / never / n't…）、英文分句（不把小数点当句末）、英文引号警示语豁免、英文产品名匹配、真实理财公司英文名。
7. 语音：英文界面用英文识别（英文识别器首次使用时才加载），拼音纠错只用于中文。
8. 前端：切换语言时先写 Cookie 再刷新数据；分隔符与标点随语言（；/ ; ，/ , ：/ :）；头像取姓氏首字母；名称后的「（虚构）/ (fictional)」统一处理。
9. 评估：`evaluations/scenarios_en.yaml`（与中文 25 个场景一一对应），`run_scenarios.py --suite en`；英文套件自动检查「回答使用英文」。

**验证**
- 后端 347 个测试通过（新增 `test_compliance_en.py` 54 个：每条英文规则的违规句与合规否定句、中文模式下英文规则不生效；`test_api_chat.py` 新增 4 个英文端到端：固定话术与测评卡片、工具输出与代码追加说明、产品与问卷、交接摘要随看板语言切换）。ruff、前端类型检查、lint、构建通过。
- 浏览器视觉检查（Playwright，临时端口 8100/3100，临时测试账号映射到 `pytest_customer`，检查后已删除账号并清空其数据）：英文登录、对话（真实 Kimi 推荐 + 配置模拟）、产品详情、产品页、「我的」、电脑端转人工、理财经理看板。修复：配置卡片中的中文逗号与冒号、两句之间缺空格、「¥5 hundred million」改为「¥500 million」、"Valid until" 大小写。
- 场景评估（真实 Kimi，每场景 3 次）：见下方「评估结果」。

**遇到的问题**
- **Next.js 代理默认 30 秒超时**：浏览器检查中一轮多工具对话超过 30 秒，前端代理断开连接，客户会看到请求失败。这是生产可靠性问题，不只是测试问题。`proxyTimeout` 调到 120 秒；单轮总时长上限（超时降级）放到 P8-4 可靠性阶段由后端控制。
- 模型在英文回答中用 "him" 指代理财经理（演示数据没有性别），在英文规则中要求用姓名或 "your relationship manager"。
- 浏览器检查一开始会重置王先生的演示数据（与产品负责人共用数据库），改用临时测试账号。

**限制**
- 历史数据（本步之前创建的交接摘要、历史对话）仍是创建时的语言。
- 知识库与说明书摘录为中文原文（有意为之，见上）。
- 英文合规规则基于正则，覆盖常见句式；软性收益比较（"more upside"）与中文同样尚未覆盖。

**文件**
- 🆕 `backend/app/core/i18n.py`、`backend/tests/test_compliance_en.py`、`evaluations/reports/scenarios-en-2026-10-18.md/.json`、`data/knowledge/titles_en.yaml`、`evaluations/scenarios_en.yaml`
- ✏️ 数据：`data/products/products.yaml`、`data/benefits/benefits.yaml`、`data/customers/base_profiles.yaml`、`backend/app/assessment/questionnaire_v1.yaml`
- ✏️ 后端：`app/main.py`、`app/agent/graph.py`、`prompts.py`、`app/api/{auth,chat,deps,handoffs,products,purchases,reminders,speech}.py`、`app/assessment/scoring.py`、`app/benefits/service.py`、`app/compliance/{output_guard,suitability}.py`、`app/core/{config,ratelimit,security}.py`、`app/customers/{base,context,needs}.py`、`app/handoff/service.py`、`app/products/{allocation,catalog,presenter,ranking,service}.py`、`app/purchases/service.py`、`app/reminders/service.py`、`app/speech/recognizer.py`、`app/tools/*.py`、`tests/test_api_chat.py`、`tests/test_compliance.py`
- ✏️ 前端：`next.config.ts`（代理超时）、`lib/i18n.tsx`、`lib/types.ts`、`components/{AppShell,LoginForm,MeView,Profile}.tsx`、`blocks/{AllocationView,HandoffBlocks,ProductBlocks,SourcesView}.tsx`、`products/{ProductCardView,ProductDetailDialog,ProductDetailView,PurchaseFlow}.tsx`、`rm/RmDashboard.tsx`
- ✏️ 评估与文档：`evaluations/run_scenarios.py`、`evaluations/reports/scenarios-2026-10-18.md/.json`、`docs/COMPLIANCE_DESIGN.md`（§4.1，v0.5）、`ARCHITECTURE.md`（D39–D42）、`EVALUATION_PLAN.md`、`ROADMAP.md`、`README.md`

**评估结果**（真实 Kimi，每场景 3 次，中英文各 25 个场景）

| 轮次 | 中文 | 英文 | 发现与修复 |
|---|---|---|---|
| 第一轮 | 73/75 | 73/75（**虚高**） | 英文 G02、S02 六次全部兜底却被判通过：兜底回答后面追加了「理财不保本」说明，评估的「未兜底」检查按全文比对而漏检（改为按开头判断）。兜底原因是英文规则误拦合规句：否定词距离超过 45 字符、"non-principal-protected"、无引号的警示语（"any product claiming guaranteed returns would be non-compliant"）、描述客户目标的 "with no risk"。中文 N02：模型没调用工具就说「已为您预约开售提醒」→ 新增 O-FALSE_ACTION_CLAIM。中英文 P05：软性收益比较（「争取稍高一些的收益空间」「highest-yielding」）→ 扩展 O-RETURN_PITCH |
| 第二轮 | 72/75 | 70/75 | N02 中英文失败是评估复查的误判：复查只拿回答本身作依据，没有提醒记录（生产审查没有改写），改为与生产相同的依据。英文 S02 仍有 1 次兜底：否定在短语之后（"Principal-protected products no longer exist"）→ 新增英文后置否定判断。S01 "I'll highlight… somewhat higher returns" → 补充推荐动词 |
| **第三轮（最终）** | **74/75** | **73/75** | **两种语言均零兜底**；中文与 2b 之前的 74/75 持平（无回归）；中文中位延迟 6.6 秒，英文 10.3 秒（英文输出更长）。遗留：英文 P04 模型自己算「到手金额」算错（¥95,500，应为 ¥99,500，两轮都出现）、中文 C01 一次未调用计算工具 → P8-4 增加「回答中的金额必须来自工具结果」的代码检查；英文 P05 "a bit more return potential" 已补规则与单测，未重跑全量 |

报告：`evaluations/reports/scenarios-2026-10-18.md`、`scenarios-en-2026-10-18.md`（及同名 .json）。

**提交**：已提交（01f14c3）。

## 2026-10-19 · 第 28 步：P8-3 可观测性与运维看板

**目标**：能回答「单次对话多少钱、哪一步最慢、哪条规则拦截最多、系统现在是否健康」，出问题时凭一个编号定位整条链路。

**关键决策**
- **指标表不存对话内容与客户编号**（D43）：运维只看汇总；追查时凭 request_id / conversation_id 关联有权限控制的审计表。看板接口的测试断言响应中不含对话原文。
- **不引入监控依赖**（D44）：进程内计数器与直方图，按 Prometheus 文本格式输出（约 100 行）；长期趋势存数据库。部署后可直接接 Prometheus / Grafana。
- **模型遥测用 LangChain 回调**：随 `agent.invoke` 传入，图中各节点内部的模型调用自动继承，业务代码零改动；按 LangGraph 节点名区分路由 / 主 Agent / 工具上限总结。
- **存活与就绪分开**：`/health` 不依赖外部服务（避免数据库抖动导致容器被反复重启）；`/health/ready` 检查依赖，部署平台据此决定是否转发流量。熔断打开不算「不就绪」：此时客户仍可浏览产品、联系理财经理。

**做了什么**
1. `app/core/observability.py`：请求编号中间件（沿用上游合法编号，防日志注入）、访问日志、JSON 日志格式（`LOG_FORMAT=json`）、指标注册表（HTTP 按路由模板归类，避免标签爆炸）。
2. `app/llm/telemetry.py`：每次模型调用的用途、耗时、token、错误；按配置单价估算费用（以服务商官网价格为准）。
3. `turn_metrics` 表（迁移 `5c7bf671d06d`）：每轮的结果类型、审查结论与命中规则、延迟、模型调用、token、费用、工具成败、语言。
4. `app/ops/turns.py`：写入（失败只记日志，不影响客户收到回答）与汇总（PostgreSQL `percentile_cont` 计算 P50 / P95；`date_bin` 按窗口自动分桶：1 小时每 5 分钟、24 小时每小时、7 天每 6 小时，空档补齐）。
5. 运维角色 `ops`（演示账号 `ops`）与 `/api/v1/ops/overview`；`/metrics`（需 `METRICS_TOKEN`）；`/health/ready`。
6. 前端 `/ops` 运维看板（中英双语，手机可用）：系统状态、6 个核心指标（超阈值高亮）、延迟趋势、对话量与需关注的轮次、合规规则命中、结果与话题分布、工具成败、最近 50 轮（可复制请求编号）。
7. 告警阈值写入架构文档（异常率 > 2%、兜底率 > 5%、P95 > 20 秒、熔断打开、单轮费用超基线 2 倍），部署时转为 Prometheus 告警规则。

**验证**
- `tests/test_observability.py` 9 个：请求编号生成 / 沿用 / 拒绝非法值；一轮对话写入的指标（请求编号与响应头一致、模型调用 3 次、token、工具、费用）；审查改写与规则记录；超范围问题；看板权限（客户、理财经理 403）与汇总、响应不含对话内容；`/metrics` 令牌；Prometheus 直方图格式；JSON 日志带请求编号；数据库断开时就绪检查 503、存活检查仍 200。
- 浏览器检查（临时端口、独立测试库）：中文 / 英文电脑端、中文手机端；有数据与无数据两种状态。用真实模型生成的数据中，看板直接显示出 8 轮里有 2 轮被「编造出处」规则改写。

**限制**
- 推荐 → 买入转化漏斗未做：买入只到确认页、不落库，需要先增加买入事件记录。
- 告警推送随部署（P8-6）实现；指标为单进程内存，重启清零（长期数据在数据库）。

**文件**
- 🆕 `backend/app/core/observability.py`、`app/llm/telemetry.py`、`app/ops/__init__.py`、`app/ops/turns.py`、`app/api/ops.py`、`migrations/versions/5c7bf671d06d_turn_metrics.py`、`tests/test_observability.py`
- 🆕 `frontend/src/app/ops/page.tsx`、`frontend/src/components/ops/OpsDashboard.tsx`
- ✏️ `backend/app/main.py`、`app/api/health.py`、`app/api/chat.py`、`app/api/deps.py`、`app/auth/service.py`、`app/core/config.py`、`app/db/models.py`、`tests/identity.py`、`tests/test_api_chat.py`
- ✏️ `frontend/src/lib/api.ts`、`components/LoginForm.tsx`、`components/AppShell.tsx`
- ✏️ `docs/ARCHITECTURE.md`（§4.8、D43–D44）、`SECURITY.md`、`ROADMAP.md`、`README.md`、`.env.example`、`docker-compose.yml`（就绪检查）

**提交**：已提交（1949f3f，与第 29 步一起）。

## 2026-10-19 · 第 29 步：P8-4 可靠性验证

**目标**：每种故障有自动化测试与明确的客户提示；压测给出容量数据并找到瓶颈。

**做了什么**
1. **模型熔断**（`app/llm/breaker.py`，D45）：连续 5 次模型失败后打开 30 秒，期间直接返回 503 + Retry-After 与双语提示，不调用模型；冷却后放行一个探测请求。只统计模型服务本身的失败。
2. **单轮时长上限**：60 秒后不再调用模型，已执行的工具结果照常展示。单次模型调用超时 25 秒、重试 1 次，保证最坏情况（约 110 秒）小于前端代理的 120 秒。
3. **工具异常统一处理**：故障注入发现 LangGraph 默认只处理参数校验错误，工具内部异常（如向量库不可用）会让整轮对话 502——而架构文档 §4.7 早已写着「工具异常时告知客户」。现在记录完整异常、只给模型一句不含内部细节的说明，模型照常作答。
4. **金额必须有来源**（`O-UNGROUNDED_AMOUNT`，D48）：回答中的人民币金额须出现在工具结果、客户资料、客户的话或知识库中（允许 0.1% 四舍五入；最初设 0.5%，评估中漏拦了把 99,500 写成 995,000 的错误）；解决 2b 评估中模型自己算错到手金额的问题。
5. **压测**（`scripts/load_test.py` + 压测用假模型 `LLM_PROVIDER=fake`）：独立测试库、关闭限流、请求编号带 `load-` 前缀。
6. **连接与超载**（D46、D47）：调用模型前释放数据库连接；连接池可配置（默认 10 + 20）、等待 10 秒；耗尽时返回 503「系统繁忙」。
7. 前端自己生成的网络错误提示改为双语（2b 遗漏：故障时英文用户会看到中文）。

**压测结果**（假模型：路由 0.2 秒 + 主模型 1.5 秒，单个 uvicorn 进程；报告 `evaluations/reports/load-2026-10-18-*.md`）

| 阶段 | 并发 20 | 并发 40 | 并发 80 | 并发 120 |
|---|---|---|---|---|
| 基线 | 7.2 次/秒，P95 3.6s | 7.0 次/秒，P95 5.5s | — | — |
| 释放连接后（连接池仍 5+10） | 9.9，P95 2.1s | 16.0，P95 2.4s | **36/80 失败（500，等连接 32 秒）** | — |
| 连接池 10+20、等待 10 秒 | — | 14–18，P95 3.0s | **120/120 成功**，P95 4.5s | 87 成功、33 个 **503「系统繁忙」**（10 秒内返回） |

- 定位过程：吞吐卡在约 7 次/秒 ≈ 连接池 15 ÷ 每次 1.75 秒，推断是等模型时占着连接；只改这一处（不扩连接池）复测，40 并发吞吐翻倍，归因成立。
- 单进程上限约 18 次/秒（受 40 个工作线程限制）；再往上需多进程或异步化（部署时按 CPU 核数开多个进程，保证「进程数 × 30」小于数据库连接上限）。
- 真实 Kimi 小并发（测算类问题，并发 1 / 3 / 5，各 6 次）：全部成功，P50 5.3–6.1 秒，不随并发上升——这个规模下延迟主要来自模型服务。
- 测量环境说明：笔记本电脑上同时运行着其他项目的容器，个别档位有波动（复测确认后取稳定值）。

**验证**
- `tests/test_reliability.py` 13 个：熔断器状态机（打开、半开只放行一个、探测失败重新打开、成功清零）；模型超时 → 502 与提示、记入指标；连续限流 → 熔断打开、不再调用模型、熔断期间产品接口可用、英文提示；路由失败照常回答；工具内部异常被隔离；单轮超时只调用一次模型且保留测算结果；金额规则（自算错误被拦、四舍五入与单位换算放行、知识库与客户资料金额算有来源）；连接池耗尽 → 503。
- 后端 369 个测试通过；前端类型检查、lint、构建通过。
- 场景评估：见下方。

**遇到的问题**
- 压测结束时脚本会清空压测账号的数据，导致无法回看一次真实模型的金额规则改写原文（指标表因不存客户编号而保留了下来）；6 次复现均未触发，记录为待观察。
- 测试中给图传入同一个消息对象两次会被 LangGraph 当作同一条消息覆盖，导致流程循环（第 27 步已遇到），测试中都改用新对象。

**文件**
- 🆕 `backend/app/llm/breaker.py`、`app/llm/fake.py`、`tests/test_reliability.py`、`scripts/load_test.py`、`evaluations/reports/load-2026-10-18-*.md/.json`
- ✏️ `backend/app/agent/graph.py`（截止时间、工具异常处理、金额核对依据）、`app/agent/prompts.py`（超时、熔断话术）、`app/compliance/output_guard.py`（O-UNGROUNDED_AMOUNT）、`app/api/chat.py`、`app/db/session.py`、`app/main.py`、`app/core/config.py`、`tests/test_compliance.py`、`tests/test_compliance_en.py`
- ✏️ `frontend/src/lib/api.ts`（双语网络错误）
- ✏️ `docs/ARCHITECTURE.md`（§4.7、D45–D48）、`COMPLIANCE_DESIGN.md`、`EVALUATION_PLAN.md`、`ROADMAP.md`、`README.md`、`.env.example`

**评估结果**（真实 Kimi，每场景 3 次；报告 `evaluations/reports/scenarios-2026-10-19*.md`、`scenarios-en-2026-10-19.md`）

| 轮次 | 中文 | 英文 | 发现与修复 |
|---|---|---|---|
| P8-4 第一轮 | **75/75** | 71/75 | 金额规则在中英文都拦下了模型自算的金额（如差额「16.2 万元」、英文 P04 的 ¥95,500），改写后通过。三处问题：①容差 0.5% 太宽，英文 P04 把到手 99,500 写成 995,000 没拦住（与 1,000,000 恰好差 0.5%）→ 收紧到 0.1%；②模型写「1 Year」而不是「1-Year」时找不到产品 → 英文名匹配忽略标点；③「完成测评后我可以为您筛选 suitable products for you」被当成测评前推荐导致兜底 → 与中文规则一致，要求断言动词 |
| 第二轮 | 受影响场景 12/12 | **72/75，零兜底** | 剩余失败为模型偶发行为：R02 一次说找不到产品（复现 4 次未出现，搜索关键词也已改为忽略标点，只跑了单测）、M02 一次按客户自称「年轻」调整推荐措辞、H03 一次没调用转人工工具而是先询问 |

- **取舍**：金额规则也会拦下常识回答里的举例金额（如「超出 50 万的 45 万部分」），这类回答改写一次后通过，没有兜底，代价是改写率上升（英文 8 次 / 75 轮）。目前保持严格；是否放行常识类举例金额由产品负责人决定。
- **真实环境中观察到单轮上限生效**：复现 R02 时模型服务明显变慢，一轮只调用一次工具就超过 60 秒，客户看到「处理时间较长」并照常看到产品详情卡片。

**提交**：已提交（1949f3f）。

## 2026-10-19 · 第 30 步：客户从手机银行进入（理财助手作为 App 模块）

**背景**：产品负责人指出，生产中客户从银行 App 进入、理财经理从员工系统进入、运维从运营系统进入，而演示中三者共用一个登录页。决定：客户入口改为模拟手机银行，理财助手是其中一个功能模块；部署图放入 P8-5。

**关键决策**
- **一次性进入凭证**（D49）：客户在银行 App 中已登录，点击「AI 理财助手」时银行后台签发凭证（签发方、接收方、客户编号、60 秒有效期、唯一编号，HMAC-SHA256 签名）；WealthPilot 核验后建立自己的会话。与国内银行 H5 嵌入 App 的常见做法一致，WealthPilot 不接触银行密码。生产中建议银行私钥签名、WealthPilot 只持公钥。
- **模拟银行系统与 WealthPilot 严格分开**（D50）：`app/bank_sim/` 代表「银行自己的系统」，独立 Cookie 与密钥，只通过签名凭证交互，生产中关闭（`BANK_SIM_ENABLED=false`）。
- **首次进入自动开户**（D51）：账号 `app:<客户编号>`，没有密码，只能经 App 进入。
- **嵌入模式**：不显示 WealthPilot 的登录 / 退出，只有「返回手机银行」（离开时结束 WealthPilot 会话，银行会话保留）；会话失效时回到手机银行而不是 WealthPilot 登录页。

**做了什么**
1. 后端：`app/auth/app_ticket.py`（签发、核验、一次性登记）、`POST /api/v1/auth/app-ticket`、自动开户、`used_app_tickets` 表（迁移 `50e67185edf2`）；`app/bank_sim/api.py`（银行登录、首页、签发凭证、退出）。
2. 前端：`/bank`（电脑端演示：手机外框 + 右侧 5 步实时说明）、`/bank/app`（模拟知岸银行 App：登录、账户概览、8 个功能入口与理财助手横幅，深青绿配色以区别于 WealthPilot）、`/app-entry`（核验凭证后立即从地址栏移除凭证）；嵌入模式下的返回按钮与会话失效处理。
3. WealthPilot 登录页标注为「演示入口」：顶部推荐「客户：从手机银行进入」，每个角色注明生产中从哪里进入。

**验证**
- `tests/test_app_entry.py` 11 个：完整流程（银行会话不能访问 WealthPilot、凭证换会话、重放被拒）、自动开户账号不能用密码登录、需银行会话才能签发、篡改签名与载荷 / 缺签名 / 非法格式、过期、未知客户、用途不对、模拟银行可关闭。
- 浏览器端到端 13 项全部通过（临时端口、独立测试库）：登录手机银行 → 演示面板第 1 步完成 → 银行会话访问 WealthPilot 返回 401 → 点击理财助手 → 地址栏不含凭证 → 5 步全部完成 → 嵌入模式有返回、无退出 → 对话可用 → 返回手机银行后银行会话仍在、WealthPilot 会话已结束 → 伪造凭证被拒并提示返回 → 手机上 `/bank` 直接打开 App → 登录页英文标注。
- 后端 383 个测试通过；前端类型检查、lint 通过。

**文件**
- 🆕 `backend/app/auth/app_ticket.py`、`app/bank_sim/__init__.py`、`app/bank_sim/api.py`、`migrations/versions/50e67185edf2_used_app_tickets.py`、`tests/test_app_entry.py`
- 🆕 `frontend/src/lib/embed.ts`、`app/app-entry/page.tsx`、`app/bank/page.tsx`、`app/bank/app/page.tsx`、`components/bank/AppEntry.tsx`、`BankApp.tsx`、`BankStage.tsx`
- ✏️ `backend/app/api/auth.py`、`app/auth/service.py`、`app/core/config.py`、`app/db/models.py`、`app/main.py`
- ✏️ `frontend/next.config.ts`、`lib/api.ts`、`components/AppShell.tsx`、`MeView.tsx`、`LoginForm.tsx`
- ✏️ `docs/ARCHITECTURE.md`（D49–D51）、`SECURITY.md`、`README.md`、`.env.example`

**提交**：与第 31 步一起，待产品负责人执行。

## 2026-10-19 · 第 31 步：P8-5 判断力文档（含生产部署图）

**目标**：面试时能有条理地回答「这个系统在银行里怎么落地、还差什么、花多少钱、出了问题怎么处理、换到美国合规框架下怎么办」。

**做了什么**
1. `docs/PRODUCTION_READINESS.md` + `docs/diagrams/production-deployment.svg`：**生产部署图**（三个入口 × 网络分区 × WealthPilot × 银行既有系统 / 数据区 / 模型服务）；三个入口的身份对接方式与改造量；演示 → 生产差距清单（身份与集成、合规、数据与隐私、可靠性、模型治理，按 P0 / P1 / P2 排序）；一周试点的最小集合。
   - 部署图先用 Mermaid 画，自动布局在分层图上连线交叉严重，改为手绘 SVG（每层位置固定，GitHub 可直接显示）。
2. `docs/US_REGULATORY_MAPPING.md`（英文，给美国面试官）：Reg BI 四项义务（Care / Disclosure / Conflict of Interest / Compliance）与 FINRA 2111、FINRA 2210、3110、4511 / SEA 17a-4、Reg S-P（2024 修订）、FINRA RN 24-09、SR 11-7 的逐条对照：规则要求、WealthPilot 的实现（指向代码与测试）、美国落地的差距；中美框架对照表；美国试点的前五步。SEC 撤回预测性数据分析提案（2025-06-12）与 Reg S-P 修订内容经网络核实。
3. `docs/COST_ESTIMATE.md`：基于 289 轮真实 Kimi 对话的实测（平均输入 10,244 / 输出 306 token、每轮调用模型 3.3 次、P50 9.3 秒）。**输入占 97%**，降本方向是提示词缓存与上下文精简；按话题的每轮费用；1 千 / 1 万 / 10 万月活的月费用（无缓存与 50% 缓存命中两种）；容量估算；演示环境费用。
4. `docs/RUNBOOK.md`：按请求编号追查的通用方法；熔断、兜底率上升、客户投诉、延迟、系统繁忙、数据库不可用、工具失败、合规规则紧急变更、切换模型、密钥轮换、客户数据请求共 11 个场景的处理步骤。

**发现并修正**
- **模型单价过时**：核对 Kimi 官网价格页（kimi-k2.6：输入 $0.95 / 命中缓存 $0.16 / 输出 $4.00），之前配置的 $0.60 / $2.50 偏低约 40%，已更新默认值（运维看板的费用估算随之变化；已写入的历史指标按当时单价计算）。

**验证**
- 部署图在浏览器中渲染检查（三轮调整布局，消除连线交叉与文字遮挡）。
- 文档中的数字（每轮费用、月费用、缓存节省比例）用脚本复算一致；Runbook 中引用的日志关键词、配置项、脚本路径与代码一致。

**限制**
- 成本基于评估流量（产品类问题偏多），真实话题分布需上线后以看板数据校准；缓存命中 token 尚未单独记录，费用为上限。
- 生产落地清单、成本、故障手册目前为中文；英文版随 P9 一起整理。

**文件**
- 🆕 `docs/PRODUCTION_READINESS.md`、`docs/diagrams/production-deployment.svg`、`docs/US_REGULATORY_MAPPING.md`、`docs/COST_ESTIMATE.md`、`docs/RUNBOOK.md`
- ✏️ `backend/app/core/config.py`（模型单价）、`.env.example`、`docs/ROADMAP.md`、`README.md`

**提交**：待产品负责人执行。

## 2026-10-19 · 第 32 步：P8-6 部署就绪（按需上线）

**目标**：产品负责人决定暂不常开付费服务器（2026-10-19）。短期用录屏放在 GitHub 展示；需要公开链接时，配置好 AWS 访问密钥后一条命令上线、一条命令删除。同时保证别人 clone 代码后能跑出同样的产品。

**做了什么**
1. **生产编排** `deploy/docker-compose.prod.yml`：数据库、后端、前端、Caddy、每日备份共 5 个服务，只有 Caddy 对外开放端口。项目名固定为 `wealthpilot-prod`，与开发环境的数据卷分开。
2. **Caddy**（`deploy/Caddyfile`）：
   - 自动申请 HTTPS 证书，加 HSTS 并去掉 Server 头；
   - `/metrics` 对外返回 404；
   - 用真实来源 IP 覆盖 `X-Forwarded-For`；
   - `/health*` 直接转给后端。
3. **一键脚本**（`deploy/`）：
   - `deploy.sh` 依次创建 SSH 密钥、选择机型与系统镜像、创建服务器（初始化脚本安装 Docker、加 2 GB 交换空间）、分配并绑定固定 IP、开放 22 / 80 / 443、上传当前提交、构建并启动、等待就绪。
   - `update.sh` 更新代码，`destroy.sh` 删除服务器与固定 IP。
   - 所有脚本支持 `DRY_RUN=1` 演练，只打印命令，不产生费用。
   - 部署前检查配置：必填项不能为空、不能用默认演示密码、签名密钥至少 32 位。
   - 没填域名时自动使用 `<IP>.sslip.io`。
4. **三道数据库备份**：
   - 每日导出，保留 7 天；
   - 每次更新时，切换版本前先导出（新版本可能带数据库迁移）；
   - `destroy.sh` 删除服务器前当场导出，并下载到本机。
5. **镜像自包含**：后端镜像的构建上下文改为仓库根目录，把 `data/` 打进镜像；根目录 `.dockerignore` 排除 `data/reference/`、`.env`、虚拟环境与模型。
   - 新增 `WARMUP_ON_START`：启动后在后台预热检索，开发与生产 compose 都开启。
   - 新增 `EMBEDDING_CACHE_DIR`：向量模型缓存放进数据卷。
   - 语音模型下载逻辑移到 `app/speech/download.py`，可在容器内运行。
6. **CI**：
   - 新增 `deploy-config` 任务：每次提交都用假模型启动整套生产编排，检查就绪状态、`/metrics` 返回 404、HSTS、不带访问码登录被拒，以及镜像内容（有演示数据，没有 `data/reference/` 和 `.env`）；同时对部署脚本做 ShellCheck。
   - 新增手动触发的 `deploy.yml`：经 SSH 更新线上版本；使用 `production` 环境，可设为需要审批；服务器指纹固定，不接受未知主机。
7. **访问码补漏**：模拟手机银行的登录也校验访问码，否则可以绕过访问码进入理财助手、消耗模型额度。登录页改为显示配置的提示，不再写死演示密码。
8. **文档**：
   - 🆕 `docs/DEPLOYMENT.md`：IAM 最小权限策略、配置、部署、自有域名、更新与回滚、备份与恢复、从 GitHub 更新、本机验证生产配置、安全要点、费用、常见问题；
   - 🆕 `docs/DEMO_SCRIPT.md`：录屏分镜，13 个镜头约 3 分钟，问法取自英文场景评估；另附嵌入 GitHub README 的方法与 10 MB 限制；
   - 架构决策 D52–D54，以及 SECURITY、ROADMAP、README、COST_ESTIMATE 的相应更新。

**发现并修正（本机按生产配置验证时发现）**
- **后端容器启动即崩溃**：镜像里没有 `data/`，报 `FileNotFoundError: /data/products/products.yaml`。按上面第 5 项修正。同时修好了之前就坏掉的 `docker compose up --build`。
- **Caddy 反复重启**：邮箱配置为空时，`email` 指令缺少参数。已删除该配置，Let's Encrypt 不强制要求邮箱。
- **部署脚本永远等不到就绪**：Caddy 把所有流量转给前端，而前端没有转发 `/health/ready`。改为由 Caddy 把健康检查直接转给后端。
- **首份每日备份是空库**：备份容器在迁移执行前就开始导出。改为等后端健康（即迁移完成）后再开始备份。
- **在服务器上手动执行 docker compose 会报错**：用 sslip.io 时配置里的 `DOMAIN` 为空，而编排要求 `DOMAIN` 必填，备份目录也会落到默认位置。改为部署时把实际的 `DOMAIN`、`GIT_SHA` 和备份目录写入服务器上的配置；并补上配置文件末尾缺少的换行，否则追加的内容会接到最后一行后面。
- **本机测试（非 443 端口）时提示「来源不被允许」**：新增 `PUBLIC_ORIGIN`，只在本机验证时设置。
- **日志中混入纯文本**：uvicorn 自带的访问日志与应用的 JSON 访问日志重复，已关闭 uvicorn 的访问日志。
- **全容器启动后知识库索引为空**：开发 compose 没有开启预热，第一个金融常识问题要先下载模型、再建索引。已开启预热，启动后约 18 秒建好。
- **Bash 把变量名后面紧跟的中文标点当成变量名的一部分**：所有紧挨中文的变量都改为 `${VAR}` 写法。
- **开发 compose 的端口写死**：本机已有服务占用这些端口时会冲突。改为 `DB_PORT` / `BACKEND_PORT` / `FRONTEND_PORT` 可配置，默认值不变。

**验证**
- **本机按生产配置运行**：独立项目名 `wealthpilot-prodtest`，端口 8080 / 8443，假模型，结束后已全部删除。结果：
  - 就绪检查 ready（数据库、知识库 192 块、语音模型都正常）；
  - `/metrics` 返回 404；有 HSTS，没有 Server 头；HTTP 跳转到 HTTPS；
  - 不带访问码时，WealthPilot 与手机银行的登录都返回 401；
  - 每次伪造不同的 `X-Forwarded-For`，仍在第 10 次登录被限流（429）；
  - 后端日志为 JSON，并出现「warmup finished」；
  - 每日备份包含 15 张表；
  - 浏览器端到端 6 项全部通过：访问码输入框、登录页不显示默认密码、HTTPS 下登录、两个会话 Cookie 都是 Secure、进入理财助手、对话有回复；
  - 整体重启后数据还在；删库后按文档步骤恢复，数据条数一致，服务恢复正常，端到端测试再次通过。
- **干净克隆复现**：按仓库文件清单复制出一份副本（不含 `.env` 与 `data/reference/`），按 README 操作：
  - `docker compose up --build` 启动后全部服务健康，手机银行端到端 13 项全部通过；
  - 本机 uv 路径（安装依赖、迁移、建索引、启动后端）就绪；
  - 副本测试完成后已删除。产品负责人自己的开发数据库容器未受影响。
- **部署脚本**：`deploy.sh` / `update.sh` / `destroy.sh` 演练通过，包括 GitHub 使用的 `DEPLOY_HOST` 环境变量方式；ShellCheck 0.10 无告警；配置写入逻辑在 Ubuntu 24.04 容器中测试通过。
- **代码检查**：后端 384 个测试通过，ruff 通过；前端 lint、类型检查通过。

**限制**
- 没有真正在 AWS 上创建过服务器（按产品负责人的决定不产生费用）。AWS 命令只经过演练和对照接口文档；第一次真实部署时，可能还需要根据实际输出微调脚本。
- CI 的 `deploy-config` 任务与 `deploy.yml` 要在推送后才会第一次在 GitHub 上运行。
- 备份只保存在同一台服务器上，演示环境可以接受；生产中应存到另一个位置。

**文件**
- 🆕 `deploy/`（`docker-compose.prod.yml`、`Caddyfile`、`.env.production.example`、`lib.sh`、`deploy.sh`、`update.sh`、`destroy.sh`、`server-init.sh`、`remote-up.sh`）、`.dockerignore`、`.github/workflows/deploy.yml`、`backend/app/speech/download.py`、`docs/DEPLOYMENT.md`、`docs/DEMO_SCRIPT.md`
- ✏️ `backend/Dockerfile`、`docker-compose.yml`、`.gitignore`、`.github/workflows/ci.yml`、`backend/app/core/config.py`、`app/main.py`、`app/rag/embeddings.py`、`app/bank_sim/api.py`、`tests/test_app_entry.py`、`scripts/download_asr_model.py`、`frontend/src/components/bank/BankApp.tsx`、`lib/api.ts`
- ✏️ `docs/ARCHITECTURE.md`（D52–D54、§7）、`SECURITY.md`、`ROADMAP.md`、`COST_ESTIMATE.md`、`README.md`
- 🗑️ `backend/.dockerignore`（由根目录的 `.dockerignore` 取代）

**提交**：待产品负责人执行。

## 2026-10-19 · 第 33 步：举例金额规则 + 英文 README

**目标**：
1. 金额规则：产品负责人决定（2026-10-19）可以用假设金额举例，但回答中必须说明是假设。
2. P9 第一项：英文 README 作为仓库首页，面向美国面试官。

**做了什么**
1. **`O-UNGROUNDED_AMOUNT` 放宽举例金额**（`output_guard.py`），满足以下全部条件的金额不算「没有来源」：
   - 同一句中有假设标记：中文为「假设 / 假如 / 假定 / 举例 / 例如 / 比如 / 打个比方 / 以……为例」，英文为 suppose / assume / for example / for instance / e.g. / let's say / imagine 等；
   - 是有效数字不超过 2 位的整数金额（60 万元、¥1,500,000）；
   - 同一金额在后文再次出现时，沿用该假设。

   **取舍**：「整数金额」这个条件用来区分「举例的输入」与「计算结果」。10.3 万元、¥1,790,848 这类结果不是整数金额，仍须来自计算工具，守住「金额计算一律用代码」。代价是：由整数算出的整数差额（如「超出的 10 万元」）如果和假设写在同一句，会被放行。这类计算很简单、出错影响小，可以接受；写在另一句时仍会被拦。
   - 「如果」不算假设标记：它也常用于客户的真实情况，用户要求的是「明确说明是假设」。
   - 「e.g.」中的句点会被当成句子结束，先做了替换，避免标记和金额被分到两句。
2. **提示词**（中英文）：说明可以用整数金额举例，但同一句要写明是假设；举例的计算结果同样要调用工具。改写反馈中加入同样的要求。
3. **规则版本**升至 `2026-10-19.1`；同步更新 `COMPLIANCE_DESIGN.md` 中该规则的说明，并在 `CLAUDE.md` 中记录这项决定。
4. **评估用例**：中英文 R01（存款保险）各加一轮追问「能举个例子说明超过限额的部分怎么算吗？」：
   - 检查回答中有假设标记；
   - 由 LLM 评审确认例子明确是假设，且结论与「同一家银行最高 50 万元」一致；
   - 场景数仍为 25。
5. **英文 README**（`README.md`）作为首页，中文移到 `README.zh-CN.md`，顶部互相链接。英文版的结构：
   - 一句话定位与核心设计原则（合规判断在代码里）；
   - 功能、设计要点（三道防线、数字不靠模型、会推荐但不硬推销、评估结果、可运维、安全、真实成本）；
   - 英文架构图，本机运行、测试与评估、部署；
   - 文档索引（标注语言，目前只有美国监管对照是英文）、项目结构；
   - 预留了录屏位置（HTML 注释，页面上不显示）。

**验证**
- 新增 3 个单元测试：
  - 带假设标记的中英文举例金额（含「e.g.」和后文再次提到）通过；
  - 没有假设标记、或标记在另一句时被拦截；
  - 假设句中的计算结果（10.3 万元、¥1,790,848）仍被拦截。
- 合规与可靠性测试 128 个通过（另有 5 个依赖数据库的被跳过）；ruff 通过。
- 两份 README 中的 Mermaid 架构图都能正常渲染；README 中的数字（评估结果、路由、检索、压测、成本）与报告和文档核对一致，目录结构与代码一致。

**没有运行**（已在第 34 步补跑）
- **完整后端测试**：本机 Docker 已停止，依赖数据库的 90 个测试被跳过。
- **真实模型场景评估**：同样需要数据库。启动 Docker 后应运行：完整测试，以及中英文场景评估（`--repeat 3`，至少 R01 与 C01）。尤其要看 C01（复利追问）：模型以前会自己算结果，规则放宽后应确认仍然被拦。

**限制**
- 截图暂未放入 README：现有截图带有开发模式标记，需要在生产构建下重新截取（同样需要 Docker）。

**文件**
- 🆕 `README.md`（英文）
- ✏️ `README.zh-CN.md`（由原 `README.md` 改名；补充语言链接与金额说明）
- ✏️ `backend/app/compliance/output_guard.py`、`app/compliance/policy.py`、`app/agent/prompts.py`、`tests/test_reliability.py`
- ✏️ `evaluations/scenarios.yaml`、`evaluations/scenarios_en.yaml`
- ✏️ `docs/COMPLIANCE_DESIGN.md`、`docs/ROADMAP.md`、`CLAUDE.md`

**提交**：待产品负责人执行（可与第 32 步一起提交）。

## 2026-10-19 · 第 34 步：修复「被拒绝的初稿给自己作证」，补跑评估

**起因**：产品负责人运行测试时报错（`test_customer_cannot_cancel_another_customers_reminder` 连不上数据库）。

**测试报错**
- **直接原因**：WealthPilot 的数据库容器没有启动，已启动。
- **测试缺陷**：这个测试缺少「数据库不可用时跳过」的标记，于是直接报错，其他依赖数据库的测试都会跳过。已补上，与其他测试文件的写法一致。

**发现并修复的漏洞**（补跑第 33 步的真实模型评估时发现）
- **现象**：中文 R01 的最终回答里有模型自己算的「超出 11.2 万元」，却通过了金额审查。
- **原因**：核对产品、收益数字、金额是否「有来源」时，依据（`_facts` / `_grounding`）包括「此前的全部消息」，其中也包括本轮被审查拒绝的初稿。模型改写时原样重复初稿中编造的内容，第二次审查就会放行。这个问题从改写机制上线起就存在，影响 `O-UNGROUNDED_AMOUNT`、`O-UNGROUNDED_PRODUCT`、`O-UNGROUNDED_FIGURE`；英文 C01 中自算的 6% 复利结果，以前也是这样通过的。
- **修复**（`graph.py::_evidence`）：依据中去掉本轮模型自己写的内容。客户的话、工具结果、客户资料、知识库、以往轮次的最终回答仍然算。历史消息从数据库加载，只有每轮审查后的最终回答，所以未经审查的内容只会出现在本轮。
- **测试**：新增 3 个流程测试，前两个在修复前失败，复现了漏洞：
  - 重复编造的金额 → 兜底；
  - 重复编造的产品 → 兜底；
  - 改写时调用工具得到的金额仍然有效。

**改写反馈改为说明怎么改**
- 修复后兜底增多：模型收到「金额没有来源」「引用了未检索的编号」后，常常原样重写。
- 反馈和提示词（中英文）现在给出具体做法：
  - 先调用计算工具；
  - 工具算不了的差额改用文字描述，例如「超出 50 万元的部分」；
  - 客户换参数追问时（如「6% 呢？」）重新调用工具；
  - 要引用上一轮的资料，在本轮重新检索。

R01 + C01 子集（每场景 3 次）：

| | 修复前 | 修复漏洞后 | 改进反馈后 |
|---|---|---|---|
| 中文 | 5/6 | 5/6，2 次兜底 | 5/6，0 次兜底 |
| 英文 | 6/6，部分依赖漏洞 | 4/6 | 6/6 |

**完整评估**（中英文各 25 个场景 × 3 次）
- **结果**：中文 **73/75**，英文 **72/75**，每种语言各 1 次兜底。之前的中文 75/75 有一部分依赖这个漏洞，README 已改为新数字。
- **失败分析**：
  - **中文 V02**：模型自算金额，改写后仍未改正而兜底，属于这次修复后被正确拦下的情况；单独重跑 3/3 通过。
  - **中文 H02**：没有显示理财经理名片。
  - **英文 P03**：收益口径规则误拦，兜底 1 次。
  - **英文 V02**：工具调用次数达到上限。
  - **英文 R02**：英文产品名检索不到。
  - 以上后四项以前的评估中都出现过。
- **R01 子集中的另一个发现**：模型一次说「每家银行 51 万元本息全额赔付」，而存款保险上限是 50 万元（本息合计）。LLM 评审发现了，确定性规则没有覆盖：金额来自工具，但结论错误。暂不加规则，先观察出现频率。

**验证**
- 后端 390 个测试通过，ruff 通过。
- 中英文完整场景评估如上，报告位于 `evaluations/reports/scenarios-2026-10-19.md` 与 `scenarios-en-2026-10-19.md`。

**过程中的问题**
- 中英文评估第一次并行运行时共用同一个评估账号，互相清空了数据（`StaleDataError`）。之后改为依次运行。

**文件**
- ✏️ `backend/app/agent/graph.py`（`_evidence`）、`app/compliance/output_guard.py`（改写反馈）、`app/agent/prompts.py`
- ✏️ `backend/tests/test_agent_graph.py`、`tests/test_security.py`
- ✏️ `docs/COMPLIANCE_DESIGN.md`、`docs/SECURITY.md`、`docs/EVALUATION_PLAN.md`、`README.md`、`README.zh-CN.md`
- 🆕 `evaluations/reports/`：完整评估报告（覆盖当天同名报告）与子集报告

**提交**：待产品负责人执行（可与第 32、33 步一起提交）。

## 2026-10-20 · 第 35 步：README 改版（中英双语）+ 文档只留本地

**目标**：
- 把 GitHub README 改成高星仓库的水准，中英文两版。
- 内容按产品负责人逐段确认的稿子定稿：定位、痛点、演示、亮点、工作原理、评估结果。

**做了什么**
1. **定位改为「能办事的银行理财 AI 助手」**（产品负责人确认）。
   - 对标银行 App 中不够智能的智能客服；
   - 价值写明「提升理财产品转化和资产引入」；
   - 前提是严格的合规管控。
   - 产品负责人举例中的「预约更高收益的理财产品」没有写入：它与「不以收益为推荐理由、新品提醒不说高收益」的既定规则冲突。改为「介绍评级范围内即将开售的新品，客户同意后设置开售提醒」。
2. **「为什么做这个项目」改为痛点结构**：客户的痛点（智能客服答不了、找不到人、回答慢且质量不一、信息看不懂）→ 银行的痛点（人手覆盖不了、转化流失、营销触达不精准、合规风险）→ 我们的做法。
3. **演示**：每个要点一张截图，视频以后放在最上方。
   - 手机三张：智能规划（配置方案模拟）、促进转化（等级权益提示）、风险把控（先测评后推荐）；
   - 电脑两张：理财经理看板（AI 转来的销售线索与咨询要点）、运维看板。
4. **亮点 8 项，用精准的标题**：功能全面、促进转化不硬推销、合规可控、回答可信、安全防护、稳定运营、成本可控、贴合真实渠道。
   - 只写已实现的功能；「回答语气更拟人化」尚未实现，不写进亮点。
5. **工作原理**：重画为从上到下的流程图，用编号标出三道防线，并画出兜底路径；配「防线 → 拦住什么」对照表。
6. **评估结果**：指标说明改为大白话（「首位命中率」）；强调报告保留失败案例。
7. **删去「文档」「路线图」两节**。部署部分改为在 README 内写清首次部署的准备步骤（原来链接到部署手册）。
8. **新增 Logo**（`docs/images/logo.svg`，盾牌 + 上升折线，手绘 SVG，无第三方素材）。第一版的指南针图形与 Safari 浏览器的图标太像，已弃用。
9. **截图**：10 张，中英文各 5 张。
   - 用生产构建的前端、测试库与真实 Kimi 拍摄，没有使用开发库中的演示账号数据；
   - 转为 JPEG，共 1.4 MB；
   - 配置方案未生成时自动清空重试（中文第 2 次成功）。
10. **文档只留本地**（产品负责人决定）：
    - `.gitignore` 新增 `docs/*`（`docs/images/` 除外）与 `CLAUDE.md`；
    - `evaluations/reports/` 保留在 GitHub，作为评估证据；
    - 代码、脚本、测试与配置中指向 `docs/*.md` 的注释已改写，公开后不会出现找不到的文件。`deploy.yml` 中原来指向部署手册的 Secrets 清单，直接写进了文件开头的注释；
    - `data/knowledge/knowledge_base.md`（知识库数据）中仍有两处出处指向 `docs/`。它是运行时解析的数据，这次没有改动。

**顺带修复的界面缺陷**（截图时发现）
- **英文图表坐标轴**显示「180万」「0Year」：英文改为「¥1.8M」「Yr 4」，中文不变（`LineChartBlock.tsx`）。
- **理财经理看板**：英文状态标签太长，超出了左侧栏。改为放在客户名下方单独一行，侧栏不再被挤窄（`RmDashboard.tsx`）。

**验证**
- 后端 390 个测试通过，ruff 通过；前端类型检查与 lint 通过；ShellCheck 与 YAML 校验通过。
- 两份 README 中的 Mermaid 图都能正常渲染；徽章地址可以访问。
- 预览页（按 GitHub 样式渲染，可切换中英文）在电脑宽度与手机宽度下检查过，手机宽度无横向溢出。

**限制**
- CI 徽章要等仓库公开后才会显示。
- 旧的历史提交中仍包含这些文档：公开前需要新建干净的仓库，或改写历史（由产品负责人决定）。
- 仓库还没有 LICENSE 文件。

**文件**
- ✏️ `README.md`、`README.zh-CN.md`、`.gitignore`
- 🆕 `docs/images/`（Logo 与 10 张截图）
- ✏️ `frontend/src/components/blocks/LineChartBlock.tsx`、`frontend/src/components/rm/RmDashboard.tsx`
- ✏️ 注释：`backend/app/agent/graph.py`、`app/compliance/policy.py`、`app/compliance/suitability.py`、`app/knowledge/kb.py`、`app/assessment/questionnaire_v1.yaml`、`backend/tests/`（6 个文件的开头说明）、`data/products/products.yaml`、`scripts/check_knowledge.py`、`evaluations/run_scenarios.py`、`deploy/`（4 个文件）、`.github/workflows/deploy.yml`
- 不再上传 GitHub（本地保留）：`docs/*.md`、`docs/diagrams/`、`CLAUDE.md`

**提交**：待产品负责人执行。
