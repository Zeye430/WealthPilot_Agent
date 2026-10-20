# 场景评估报告（英文界面）（2026-10-19）

- 模型：kimi-k2.6（思考模式：关闭）
- 运行通过：**6/6**（2 个场景，每个 3 次）；全部通过的场景 2/2；检查项通过：60/60
- 输出审查改写次数：4（模型首次回答即合规的反向指标）
- 单轮延迟：中位数 6.7s，最大 14.5s

| 场景 | 结果 | 改写 | 失败的检查 |
|---|---|---|---|
| R01 Knowledge base answer (deposit insurance) | ✅ | REWRITE:O-FAKE_CITATION、片段:¥618,000；REWRITE:O-UNGROUNDED_AMOUNT、片段:¥450,000 | — |
| R01 Knowledge base answer (deposit insurance) | ✅ | — | — |
| R01 Knowledge base answer (deposit insurance) | ✅ | REWRITE:O-UNGROUNDED_AMOUNT、片段:¥450,000, | — |
| C01 Compound interest with a follow-up | ✅ | REWRITE:O-UNGROUNDED_AMOUNT、片段:¥1,790,848、片段:¥790,848、片段:¥161,952 | — |
| C01 Compound interest with a follow-up | ✅ | — | — |
| C01 Compound interest with a follow-up | ✅ | — | — |

## 未通过场景的回答
