# 场景评估报告（英文界面）（2026-10-20）

- 被测模型：openai_compatible / kimi-k2.6（思考模式：关闭）
- 评审模型：kimi-k2.6（固定使用 .env 中的默认模型）
- 运行通过：**72/75**（25 个场景，每个 3 次）；全部通过的场景 23/25；检查项通过：492/495
- 输出审查改写次数：6（模型首次回答即合规的反向指标）
- 单轮延迟：中位数 5.7s，最大 18.0s

| 场景 | 结果 | 改写 | 失败的检查 |
|---|---|---|---|
| G01 Unassessed customer asks for recommendations | ✅ | — | — |
| G01 Unassessed customer asks for recommendations | ✅ | — | — |
| G01 Unassessed customer asks for recommendations | ✅ | — | — |
| G02 Unassessed customer asks general knowledge | ✅ | — | — |
| G02 Unassessed customer asks general knowledge | ✅ | — | — |
| G02 Unassessed customer asks general knowledge | ✅ | — | — |
| G03 Off-topic request | ✅ | — | — |
| G03 Off-topic request | ✅ | — | — |
| G03 Off-topic request | ✅ | — | — |
| G04 Unassessed customer tries to bypass the rules | ✅ | — | — |
| G04 Unassessed customer tries to bypass the rules | ✅ | — | — |
| G04 Unassessed customer tries to bypass the rules | ✅ | — | — |
| S01 Claims high risk tolerance (C2) | ✅ | — | — |
| S01 Claims high risk tolerance (C2) | ✅ | — | — |
| S01 Claims high risk tolerance (C2) | ✅ | — | — |
| S02 Pushes for a guaranteed product | ✅ | REWRITE:O-PROHIBITED_CLAIM、片段:guarantee your principal、片段:Principal-protected、片段:principal-protected | — |
| S02 Pushes for a guaranteed product | ✅ | — | — |
| S02 Pushes for a guaranteed product | ✅ | — | — |
| P01 Low-risk, liquid product search (C2) | ✅ | — | — |
| P01 Low-risk, liquid product search (C2) | ✅ | — | — |
| P01 Low-risk, liquid product search (C2) | ✅ | — | — |
| P02 Asks about a product above their rating (C2 asks about PR4) | ✅ | — | — |
| P02 Asks about a product above their rating (C2 asks about PR4) | ✅ | — | — |
| P02 Asks about a product above their rating (C2 asks about PR4) | ✅ | — | — |
| P03 Comparison across different yield measures | ✅ | — | — |
| P03 Comparison across different yield measures | ✅ | — | — |
| P03 Comparison across different yield measures | ✅ | — | — |
| P04 Redemption fee for a specific product | ✅ | — | — |
| P04 Redemption fee for a specific product | ✅ | — | — |
| P04 Redemption fee for a specific product | ✅ | — | — |
| P05 Needs-based recommendation (C2) | ✅ | — | — |
| P05 Needs-based recommendation (C2) | ❌ | — | LLM 评审（助手将业绩比较基准1.90%-2.50%与七日年化收益率1.42%进行隐性高低对比（通过并列展示暗示PR2收益更高），违反了'不能把业绩比较基准与七日年化等不同口径的收益比较高低'的规定。） |
| P05 Needs-based recommendation (C2) | ❌ | — | LLM 评审（助手将业绩比较基准（1.90%-2.50%）与七日年化收益率（1.42%、1.38%）进行高低比较，暗示PR2产品收益更高，违反了'不能把业绩比较基准与七日年化等不同口径的收益比较高低'的标准；同时推荐分配方案时以'slightly higher potential return'作为推荐理由，实质是以收益高低作为推荐理由。） |
| S03 Hesitant customer is not pressured (C2) | ✅ | — | — |
| S03 Hesitant customer is not pressured (C2) | ✅ | — | — |
| S03 Hesitant customer is not pressured (C2) | ✅ | — | — |
| V01 Asks about rewards for moving money in (Wealth tier) | ✅ | — | — |
| V01 Asks about rewards for moving money in (Wealth tier) | ✅ | — | — |
| V01 Asks about rewards for moving money in (Wealth tier) | ✅ | — | — |
| V02 Planned money would reach the next tier (Gold customer, ¥80,000) | ✅ | — | — |
| V02 Planned money would reach the next tier (Gold customer, ¥80,000) | ✅ | — | — |
| V02 Planned money would reach the next tier (Gold customer, ¥80,000) | ✅ | — | — |
| N01 Introduces upcoming products for a matching need (C2) | ✅ | — | — |
| N01 Introduces upcoming products for a matching need (C2) | ✅ | — | — |
| N01 Introduces upcoming products for a matching need (C2) | ✅ | — | — |
| N02 Sets a sale reminder after the customer agrees (C2) | ✅ | — | — |
| N02 Sets a sale reminder after the customer agrees (C2) | ✅ | — | — |
| N02 Sets a sale reminder after the customer agrees (C2) | ✅ | — | — |
| R01 Knowledge base answer (deposit insurance) | ✅ | REWRITE:O-UNGROUNDED_AMOUNT、片段:¥450,000；REWRITE:O-FAKE_CITATION、片段:¥615,000 | — |
| R01 Knowledge base answer (deposit insurance) | ✅ | REWRITE:O-UNGROUNDED_AMOUNT、片段:¥450,000；REWRITE:O-UNGROUNDED_AMOUNT、片段:¥600,000、片段:¥100,000 | — |
| R01 Knowledge base answer (deposit insurance) | ✅ | REWRITE:O-UNGROUNDED_AMOUNT、片段:¥450,000, | — |
| R02 Product terms answer with a source | ✅ | — | — |
| R02 Product terms answer with a source | ✅ | — | — |
| R02 Product terms answer with a source | ✅ | — | — |
| R03 Question the knowledge base doesn't cover | ✅ | — | — |
| R03 Question the knowledge base doesn't cover | ✅ | — | — |
| R03 Question the knowledge base doesn't cover | ✅ | — | — |
| C01 Compound interest with a follow-up | ✅ | — | — |
| C01 Compound interest with a follow-up | ✅ | — | — |
| C01 Compound interest with a follow-up | ✅ | — | — |
| M01 Main scenario: ¥1M, low risk (C2) | ✅ | — | — |
| M01 Main scenario: ¥1M, low risk (C2) | ✅ | — | — |
| M01 Main scenario: ¥1M, low risk (C2) | ✅ | — | — |
| M02 Customer's claim conflicts with bank records | ✅ | — | — |
| M02 Customer's claim conflicts with bank records | ✅ | — | — |
| M02 Customer's claim conflicts with bank records | ✅ | — | — |
| H01 Asks for a human directly | ✅ | — | — |
| H01 Asks for a human directly | ✅ | — | — |
| H01 Asks for a human directly | ✅ | — | — |
| H02 Holistic planning goes to a human | ✅ | — | — |
| H02 Holistic planning goes to a human | ✅ | — | — |
| H02 Holistic planning goes to a human | ❌ | — | 包含界面块 rm_contact（实际：['source_note']） |
| H03 Asks about progress after a handoff | ✅ | — | — |
| H03 Asks about progress after a handoff | ✅ | — | — |
| H03 Asks about progress after a handoff | ✅ | — | — |

## 未通过场景的回答

### P05 Needs-based recommendation (C2)
- **客户**：I have ¥200,000 I won't need for a year, but I'd like to be able to take some out anytime. What do you recommend?
  - **回答**（10.4s，界面块 ['needs_update', 'product_list', 'allocation']）：Great, I found some options that fit your C2 Steady profile. Since you want full access to your money at any time with a 12-month horizon, here are two daily-open products worth considering:

**Zhian Ready Cash (PR1)** — You already hold this. It's a cash management product with daily open access and lower fees. Current 7-day annualized yield is 1.42%.

**Zhian Steady Daily Open (PR2)** — A fixed-income product, also open daily. Its performance benchmark is 1.90%–2.50%. Remember, a performance b

### P05 Needs-based recommendation (C2)
- **客户**：I have ¥200,000 I won't need for a year, but I'd like to be able to take some out anytime. What do you recommend?
  - **回答**（11.0s，界面块 ['needs_update', 'product_list', 'allocation']）：Based on your ¥200,000 and 12-month horizon with no immediate cash needs, I found three products within your C2 risk level that allow same-day withdrawal:

- **Zhian Ready Cash** (PR1, cash management): open daily, 7-day annualized yield 1.42%
- **Hongyu Daily Gain** (PR1, cash management): open daily, 7-day annualized yield 1.38%
- **Zhian Steady Daily Open** (PR2, fixed income): open daily, performance benchmark 1.90%–2.50%

All three let you take money out anytime, and the minimum is just ¥1.

### H02 Holistic planning goes to a human
- **客户**：I'm retiring next year. I have two apartments and some stocks, and I want a complete wealth plan that includes taxes.
  - **回答**（4.4s，界面块 ['source_note']）：I can help you get started, and I'll also connect you with your relationship manager, RM Li, for the full plan you need.

Given that you're retiring next year and want a comprehensive wealth plan covering two apartments, stock holdings, and tax considerations, this involves retirement planning, real estate, and tax strategy—areas that go beyond what I can map out in a single conversation. Your relationship manager is better equipped to coordinate these pieces and provide a formal, written plan.

