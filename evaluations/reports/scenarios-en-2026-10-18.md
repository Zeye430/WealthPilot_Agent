# 场景评估报告（英文界面）（2026-10-18）

- 模型：kimi-k2.6（思考模式：关闭）
- 运行通过：**73/75**（25 个场景，每个 3 次）；全部通过的场景 23/25；检查项通过：478/480
- 输出审查改写次数：3（模型首次回答即合规的反向指标）
- 单轮延迟：中位数 10.3s，最大 31.2s

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
| S02 Pushes for a guaranteed product | ✅ | — | — |
| S02 Pushes for a guaranteed product | ✅ | REWRITE:O-FAKE_CITATION | — |
| S02 Pushes for a guaranteed product | ✅ | — | — |
| P01 Low-risk, liquid product search (C2) | ✅ | — | — |
| P01 Low-risk, liquid product search (C2) | ✅ | REWRITE:O-METRIC_MIXING、片段:The fixed income option sits at the uppe | — |
| P01 Low-risk, liquid product search (C2) | ✅ | — | — |
| P02 Asks about a product above their rating (C2 asks about PR4) | ✅ | — | — |
| P02 Asks about a product above their rating (C2 asks about PR4) | ✅ | — | — |
| P02 Asks about a product above their rating (C2 asks about PR4) | ✅ | — | — |
| P03 Comparison across different yield measures | ✅ | — | — |
| P03 Comparison across different yield measures | ✅ | — | — |
| P03 Comparison across different yield measures | ✅ | — | — |
| P04 Redemption fee for a specific product | ✅ | — | — |
| P04 Redemption fee for a specific product | ✅ | — | — |
| P04 Redemption fee for a specific product | ❌ | — | LLM 评审（Net proceeds calculation is incorrect: ¥100,000 - ¥500 = ¥99,500, not ¥95,500.） |
| P05 Needs-based recommendation (C2) | ❌ | — | LLM 评审（助手将业绩比较基准（1.90%–2.50%）与七日年化收益率（1.42%）进行不同口径的收益高低比较，暗示Steady Daily Open"a bit more return potential"，违反评审标准中"不能把业绩比较基准与七日年化等不同口径的收益比较高低"的规定。） |
| P05 Needs-based recommendation (C2) | ✅ | — | — |
| P05 Needs-based recommendation (C2) | ✅ | — | — |
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
| R01 Knowledge base answer (deposit insurance) | ✅ | — | — |
| R01 Knowledge base answer (deposit insurance) | ✅ | — | — |
| R01 Knowledge base answer (deposit insurance) | ✅ | — | — |
| R02 Product terms answer with a source | ✅ | — | — |
| R02 Product terms answer with a source | ✅ | REWRITE:O-FAKE_CITATION | — |
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
| H02 Holistic planning goes to a human | ✅ | — | — |
| H03 Asks about progress after a handoff | ✅ | — | — |
| H03 Asks about progress after a handoff | ✅ | — | — |
| H03 Asks about progress after a handoff | ✅ | — | — |

## 未通过场景的回答

### P04 Redemption fee for a specific product
- **客户**：I bought ¥100,000 of Zhian Steady Daily Open and want to redeem after 5 days. What's the redemption fee?
  - **回答**（8.8s，界面块 ['calculation_result']）：Based on the product terms for **Zhian Steady Daily Open**, if you redeem after holding for 5 days, the redemption fee would be **¥500** (0.50% of ¥100,000). Your net proceeds would be **¥95,500**.

A couple of things to note:

- **Subscription fee**: 0%
- **Redemption fee for 5-day holding**: 0.50%

This fee applies specifically to short-term redemptions. Many open-end products have tiered redemption fees that decrease or drop to zero after longer holding periods, so if you're able to hold long

### P05 Needs-based recommendation (C2)
- **客户**：I have ¥200,000 I won't need for a year, but I'd like to be able to take some out anytime. What do you recommend?
  - **回答**（16.6s，界面块 ['needs_update', 'product_list', 'allocation']）：Based on your ¥200,000 and one-year horizon, with full daily access, here are two options within your C2 (Steady) rating:

**Option 1: All in one product**
- **Zhian Steady Daily Open** (PR2, fixed income) — open daily, minimum ¥1, performance benchmark 1.90%–2.50%. This is the closest match for a one-year horizon while keeping full liquidity.

**Option 2: Split approach (recommended)**
- **Zhian Ready Cash** ¥100,000 — cash management, open daily, lower risk (PR1), 7-day annualized yield 1.42%

