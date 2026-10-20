# WealthPilot AI — 安全设计与威胁模型（v0.2）

> 范围：作品集演示系统（虚构机构与客户、不接触真实资金）。按真实金融应用的思路设计，并标出与生产环境的差距。
> 每条防护都对应自动化测试，测试文件见「验证」列。

## 1. 资产与信任边界

| 需要保护的 | 说明 |
|---|---|
| 客户资料与对话 | 基础画像、资产、风险测评、本次需求、对话记录 |
| 合规结论 | 风险评级、能否买入、交接状态：只能由代码写入，模型只读 |
| 模型额度 | 每次对话都消耗 Kimi API 费用 |
| 理财经理看板 | 只能看到分配给自己的客户咨询 |
| 运维看板与指标（P8-3） | 运维角色只看汇总指标与审计编号，看不到对话内容与客户资料；Prometheus 接口需令牌 |

信任边界：浏览器 → Next.js（同源代理）→ FastAPI → PostgreSQL / Kimi / 本地语音模型。**浏览器发来的一切（含请求头、模型输出）都不可信**。

## 2. 威胁与防护

| 威胁 | 防护 | 验证 |
|---|---|---|
| **冒充身份**：改请求头冒充他人或理财经理 | 唯一身份来源是服务端会话（httpOnly Cookie）；旧的 `X-Demo-User` 请求头已从生产代码中删除 | `test_auth.py::test_header_identity_is_not_trusted` |
| **会话被盗用** | 令牌 32 字节随机数；数据库只存 SHA-256；httpOnly（脚本读不到）、SameSite=Lax、HTTPS 下 Secure；12 小时绝对有效期 + 2 小时闲置超时；退出与账号停用即时失效 | `test_logout_revokes_session_immediately`、`test_idle_and_absolute_expiry`、`test_disabled_account_loses_access`；浏览器端到端检查 Cookie 属性 |
| **密码泄露 / 暴力破解** | scrypt 加盐哈希；常数时间比较；账号不存在时做同等开销校验（防探测）；错误提示不区分账号与密码；按 IP 与按账号限流 | `test_passwords_are_hashed`、`test_wrong_password_and_unknown_user_look_the_same`、`test_login_brute_force_is_rate_limited` |
| **越权访问**：客户看他人数据、客户进看板、理财经理调客户接口 | 客户编号来自会话而非请求参数；客户与理财经理角色分离；理财经理只能看分配给自己的交接；提醒、会话按归属校验 | `test_customer_cannot_use_rm_dashboard`、`test_rm_cannot_use_customer_endpoints`、`test_api_chat.py`（跨客户会话、理财经理越权）、`test_security.py`（他人的提醒） |
| **跨站请求伪造（CSRF）** | SameSite=Lax；写请求带 Origin 时必须是允许的前端来源 | `test_cross_origin_writes_are_rejected` |
| **刷接口 / 刷模型额度** | 对话按用户每分钟 20 次、每天 300 次；语音每分钟 30 次；超限返回 429 + Retry-After；公开演示可设访问码（WealthPilot 与模拟手机银行的登录都校验）；公开部署时部署脚本拒绝默认演示密码 | `test_chat_is_rate_limited_per_user`、`test_access_code_required_when_configured`、`test_bank_login_requires_access_code_when_configured` |
| **提示注入：让模型改评级、绕过规则** | 评级、客户身份通过 InjectedState 注入工具，模型看不到、也无法传入；未测评时产品工具不绑定，执行前再校验；输出审查拦截违规回答 | `test_security.py::test_llm_cannot_supply_identity_or_rating`、`test_agent_graph.py`（BLOCK_TOOL）、场景评估 G04、S01 |
| **间接提示注入：文档中夹带指令** | 检索资料作为数据传给模型，Prompt 声明文档内容不可信；输出审查兜底 | `test_rag.py::test_prompt_injection_in_document_is_caught` |
| **模型编造产品、收益数字、金额、出处** | 产品必须出现在工具结果中；收益数字、金额须有来源；引用编号须在本轮检索结果中；被审查拒绝的初稿不算来源（否则改写时重复编造内容即可通过） | `test_compliance.py`（UNGROUNDED_PRODUCT、UNGROUNDED_FIGURE、FAKE_CITATION）、`test_agent_graph.py::test_rejected_draft_cannot_ground_*` |
| **敏感信息进日志** | 不记录对话内容与录音；日志统一脱敏（手机号、身份证号、卡号）；运行指标表不存对话内容与客户编号 | `test_log_redaction`、`test_observability.py::test_ops_overview_requires_ops_role_and_aggregates`（看板响应不含对话内容） |
| **运维接口越权** | 运维看板只允许运维角色（客户、理财经理均 403）；`/metrics` 未配置令牌时关闭，配置后需 Bearer 令牌（常数时间比较） | `test_ops_overview_requires_ops_role_and_aggregates`、`test_metrics_endpoint_requires_token` |
| **伪造或盗用手机银行进入凭证**（P8-5） | 凭证由银行签名（演示为 HMAC-SHA256，常数时间比较；生产建议银行私钥签名、WealthPilot 只持公钥）；校验签发方、接收方（用途）、60 秒有效期（允许 10 秒时钟偏差）；一次性：编号写入数据库，重复使用即拒绝（多实例有效）；拒绝原因只写日志，对外统一提示；进入页立即从地址栏移除凭证；按 IP 限流 | `test_app_entry.py`（篡改签名与载荷、过期、重放、用途不对、未知客户、需银行会话） |
| **手机银行与 WealthPilot 会话混用** | 两套独立 Cookie：银行会话不能访问 WealthPilot 接口；经 App 自动开户的账号没有密码，无法用账号密码登录；返回手机银行时结束 WealthPilot 会话 | `test_bank_app_entry_flow`、`test_app_only_account_cannot_password_login`；浏览器端到端 13 项 |
| **日志注入**：伪造请求编号写入换行等内容 | 上游传入的 `X-Request-ID` 只接受 8–64 位字母数字与连字符，否则重新生成 | `test_request_id_header_is_generated_or_propagated` |
| **超载 / 上游故障拖垮服务** | 模型熔断（连续失败后快速失败）；单轮时长上限；连接池耗尽时 10 秒内返回 503 | `test_reliability.py` |
| **语音录音泄露** | 本地模型识别，不发给第三方；只在内存中处理，不落盘 | `test_speech.py`；COMPLIANCE §6.1 |
| **超大请求 / 异常输入** | 消息 2000 字上限；录音 60 秒上限、格式校验 | `test_message_length_is_bounded`、`test_speech.py` |
| **点击劫持、内容嗅探、缓存客户数据** | X-Frame-Options: DENY、X-Content-Type-Options: nosniff、Cache-Control: no-store、Permissions-Policy 只允许本站用麦克风 | `test_security_headers_present` |
| **依赖漏洞** | CI 中 `pip-audit`（已知漏洞即失败）、`npm audit --audit-level=high` | `.github/workflows/ci.yml` |
| **伪造来源 IP 绕过登录限流**（P8-6） | 限流按来源 IP 计数；公开部署时 Caddy 用真实来源 IP 覆盖客户端自带的 `X-Forwarded-For` | 本机生产配置验证：每次伪造不同 IP，仍在第 10 次登录被限流（DEVLOG 步骤 32） |
| **部署链路暴露内部接口**（P8-6） | 只有 Caddy 对外开放端口，数据库、后端、前端只在容器网络内；`/metrics` 在入口返回 404；HTTPS + HSTS，Cookie 为 Secure | CI `deploy-config`：启动整套生产编排，检查 `/metrics` 404、HSTS、无访问码登录被拒 |
| **密钥泄露** | `.env` 与 `deploy/.env.production` 不入库；`.env.example` 只有空占位；镜像构建排除 `.env` 与 `data/reference/`；服务器上的配置权限 600；部署用只有 Lightsail 权限的 IAM 访问密钥，不用账号密码；提交前检查 | `.gitignore`、`.dockerignore`；CI `deploy-config` 检查镜像内容 |

## 3. 与生产环境的差距（真实银行上线前需要）

- **身份认证**：对接银行统一身份认证（SSO / OAuth2），手机银行内嵌时复用 App 登录态；增加多因素认证与设备绑定。
- **限流与会话存储**：多实例部署时迁移到 Redis；网关层（WAF / API Gateway）做 IP 信誉与 DDoS 防护。
- **数据安全**：数据库静态加密、字段级加密（资产、证件）；按《个人信息保护法》做最小化采集、留存期限与删除机制；金融数据不出境，模型私有化部署。
- **审计**：登录、权限变更、理财经理查看客户资料均写入不可篡改的审计日志；接入 SIEM 告警。
- **安全测试**：上线前渗透测试；定期红队测试提示注入；第三方组件 SBOM。
