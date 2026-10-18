# WealthPilot AI — 安全设计与威胁模型（v0.1）

> 范围：作品集演示系统（虚构机构与客户、不接触真实资金）。按真实金融应用的思路设计，并标出与生产环境的差距。
> 每条防护都对应自动化测试，测试文件见「验证」列。

## 1. 资产与信任边界

| 需要保护的 | 说明 |
|---|---|
| 客户资料与对话 | 基础画像、资产、风险测评、本次需求、对话记录 |
| 合规结论 | 风险评级、能否买入、交接状态：只能由代码写入，模型只读 |
| 模型额度 | 每次对话都消耗 Kimi API 费用 |
| 理财经理看板 | 只能看到分配给自己的客户咨询 |

信任边界：浏览器 → Next.js（同源代理）→ FastAPI → PostgreSQL / Kimi / 本地语音模型。**浏览器发来的一切（含请求头、模型输出）都不可信**。

## 2. 威胁与防护

| 威胁 | 防护 | 验证 |
|---|---|---|
| **冒充身份**：改请求头冒充他人或理财经理 | 唯一身份来源是服务端会话（httpOnly Cookie）；旧的 `X-Demo-User` 请求头已从生产代码中删除 | `test_auth.py::test_header_identity_is_not_trusted` |
| **会话被盗用** | 令牌 32 字节随机数；数据库只存 SHA-256；httpOnly（脚本读不到）、SameSite=Lax、HTTPS 下 Secure；12 小时绝对有效期 + 2 小时闲置超时；退出与账号停用即时失效 | `test_logout_revokes_session_immediately`、`test_idle_and_absolute_expiry`、`test_disabled_account_loses_access`；浏览器端到端检查 Cookie 属性 |
| **密码泄露 / 暴力破解** | scrypt 加盐哈希；常数时间比较；账号不存在时做同等开销校验（防探测）；错误提示不区分账号与密码；按 IP 与按账号限流 | `test_passwords_are_hashed`、`test_wrong_password_and_unknown_user_look_the_same`、`test_login_brute_force_is_rate_limited` |
| **越权访问**：客户看他人数据、客户进看板、理财经理调客户接口 | 客户编号来自会话而非请求参数；客户与理财经理角色分离；理财经理只能看分配给自己的交接；提醒、会话按归属校验 | `test_customer_cannot_use_rm_dashboard`、`test_rm_cannot_use_customer_endpoints`、`test_api_chat.py`（跨客户会话、理财经理越权）、`test_security.py`（他人的提醒） |
| **跨站请求伪造（CSRF）** | SameSite=Lax；写请求带 Origin 时必须是允许的前端来源 | `test_cross_origin_writes_are_rejected` |
| **刷接口 / 刷模型额度** | 对话按用户每分钟 20 次、每天 300 次；语音每分钟 30 次；超限返回 429 + Retry-After；公开演示可设访问码 | `test_chat_is_rate_limited_per_user`、`test_access_code_required_when_configured` |
| **提示注入：让模型改评级、绕过规则** | 评级、客户身份通过 InjectedState 注入工具，模型看不到、也无法传入；未测评时产品工具不绑定，执行前再校验；输出审查拦截违规回答 | `test_security.py::test_llm_cannot_supply_identity_or_rating`、`test_agent_graph.py`（BLOCK_TOOL）、场景评估 G04、S01 |
| **间接提示注入：文档中夹带指令** | 检索资料作为数据传给模型，Prompt 声明文档内容不可信；输出审查兜底 | `test_rag.py::test_prompt_injection_in_document_is_caught` |
| **模型编造产品、收益数字、出处** | 产品必须出现在工具结果中；收益数字须有来源；引用编号须在检索结果中 | `test_compliance.py`（UNGROUNDED_PRODUCT、UNGROUNDED_FIGURE、FAKE_CITATION） |
| **敏感信息进日志** | 不记录对话内容与录音；日志统一脱敏（手机号、身份证号、卡号） | `test_log_redaction` |
| **语音录音泄露** | 本地模型识别，不发给第三方；只在内存中处理，不落盘 | `test_speech.py`；COMPLIANCE §6.1 |
| **超大请求 / 异常输入** | 消息 2000 字上限；录音 60 秒上限、格式校验 | `test_message_length_is_bounded`、`test_speech.py` |
| **点击劫持、内容嗅探、缓存客户数据** | X-Frame-Options: DENY、X-Content-Type-Options: nosniff、Cache-Control: no-store、Permissions-Policy 只允许本站用麦克风 | `test_security_headers_present` |
| **依赖漏洞** | CI 中 `pip-audit`（已知漏洞即失败）、`npm audit --audit-level=high` | `.github/workflows/ci.yml` |
| **密钥泄露** | `.env` 不入库；`.env.example` 只有空占位；提交前检查 | `.gitignore` |

## 3. 与生产环境的差距（真实银行上线前需要）

- **身份认证**：对接银行统一身份认证（SSO / OAuth2），手机银行内嵌时复用 App 登录态；增加多因素认证与设备绑定。
- **限流与会话存储**：多实例部署时迁移到 Redis；网关层（WAF / API Gateway）做 IP 信誉与 DDoS 防护。
- **数据安全**：数据库静态加密、字段级加密（资产、证件）；按《个人信息保护法》做最小化采集、留存期限与删除机制；金融数据不出境，模型私有化部署。
- **审计**：登录、权限变更、理财经理查看客户资料均写入不可篡改的审计日志；接入 SIEM 告警。
- **安全测试**：上线前渗透测试；定期红队测试提示注入；第三方组件 SBOM。
