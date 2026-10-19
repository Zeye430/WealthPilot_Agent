# WealthPilot AI: US Regulatory Mapping

> **Purpose.** WealthPilot is built for the Chinese bank wealth-management market. This document maps its controls to the US obligations a broker-dealer would face if it put a similar AI assistant in front of retail customers. For each obligation it shows what the rule asks, how the current design addresses it (with the code and tests that prove it), and what would still be needed.
>
> **Not legal advice.** This is an engineering view, written to show how the architecture would carry over. A US deployment would need review by the firm's compliance and legal teams. Rule summaries are simplified.
>
> Chinese-market context and the production gap list: [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md). Control details: [COMPLIANCE_DESIGN.md](COMPLIANCE_DESIGN.md).

## 1. The design principle that carries over

US rules are technology-neutral: FINRA Regulatory Notice 24-09 (June 2024) reminds firms that existing obligations apply when they use generative AI. WealthPilot's core design choice fits that framing:

**Compliance decisions live in deterministic code, not in the prompt.** The language model never decides a customer's risk rating, which products are eligible, whether a purchase is allowed, or whether a handoff happened. It only reads those facts. Every reply passes an output review of 15 deterministic rules before the customer sees it, and every decision is logged with a rule version.

That separation is what makes the system supervisable: a reviewer can audit rules and logs, rather than trying to audit a model's judgment.

## 2. Obligation-by-obligation mapping

### Regulation Best Interest (Exchange Act Rule 15l-1) and FINRA Rule 2111

Since June 30, 2020, recommendations to retail customers are governed by Reg BI. FINRA amended Rule 2111 (suitability) so it no longer applies to recommendations covered by Reg BI, but its three-part framework (reasonable-basis, customer-specific, quantitative) still describes most of what Reg BI's Care Obligation expects.

| Obligation | What it asks (simplified) | How WealthPilot addresses it | Gap for a US deployment |
|---|---|---|---|
| **Care: reasonable basis** | Understand the product's risks, rewards and costs before recommending it | Product facts come only from a validated catalog (`data/products/products.yaml`, schema-checked at startup); the model can't invent terms (`O-UNGROUNDED_PRODUCT`, `O-UNGROUNDED_FIGURE`) | Product due-diligence records per product; catalog fed from the firm's product system |
| **Care: customer-specific** | Base recommendations on the customer's investment profile (age, financial situation, objectives, experience, time horizon, liquidity needs, risk tolerance, and so on) | Risk profile questionnaire scored in code; profile from the bank's system (read-only) plus goals captured in chat (amount, horizon, liquidity, return target, loss tolerance); products above the customer's rating are **hard-filtered** before ranking; ranking uses horizon fit, liquidity and fees only (`app/compliance/suitability.py`, `app/products/ranking.py`) | Profile lacks tax status and outside holdings; questionnaire is self-designed and not validated |
| **Care: quantitative** | A series of recommendations is not excessive when taken together | Not applicable today: no trading; purchases stop at a confirmation page | Needed if the assistant ever suggests repeated transactions |
| **Care: costs and alternatives** | Consider costs and reasonably available alternatives | Fees are a ranking factor; the response shows the ranked list and why other products were excluded; returns are never a ranking factor (`O-RETURN_PITCH`) | A stored rationale per recommendation documenting the alternatives considered |
| **Disclosure** | Disclose material facts: capacity, fees, conflicts, before or at the time of the recommendation | Fees, risk level and liquidity terms on every product card; risk disclaimers added by code, not by the model; benchmarks labeled "not an expected return" | Form CRS delivery; disclosing capacity and compensation; disclosing that the customer is talking to AI |
| **Conflict of interest** | Identify and mitigate conflicts; eliminate sales contests, quotas, bonuses and non-cash compensation tied to specific securities within a limited period | Commission is never a ranking input; rewards are tied to total assets, never to a specific product (`O-GIFT_FOR_PURCHASE`); no urgency language (`O-PRESSURE_SALES`); no steering customers to retake the risk profile to reach a return target (`O-REASSESSMENT_STEERING`) | Firm-level review of the time-limited "new assets" campaign; conflict inventory for the AI channel |
| **Compliance** | Written policies and procedures reasonably designed to achieve compliance | Rules are versioned code with unit tests; 25 multi-turn scenarios per language run 3 times each after every rule change; results recorded in [EVALUATION_PLAN.md](EVALUATION_PLAN.md) | Written supervisory procedures for the AI channel; annual review; change approval by compliance |

### FINRA Rule 2210: Communications with the public

The rule requires communications to be fair and balanced. Among other things, they must not be promissory, exaggerated or misleading, and generally must not predict or project performance. There are exceptions, for example hypothetical illustrations of mathematical principles that don't predict a particular investment's performance. A chatbot's replies are communications, and RN 24-09 reminds firms of this.

| Requirement | How WealthPilot addresses it | Gap |
|---|---|---|
| No promissory or guarantee language | `O-PROHIBITED_CLAIM` in Chinese and English (guaranteed returns, principal-protected, risk-free, can't lose), with negation handling so accurate statements like "returns are not guaranteed" pass | Rule list reviewed and signed off by compliance |
| No performance projections | The calculator only runs hypothetical math with a fixed rate the customer gives; code appends "hypothetical, not a projection of any product". The allocation simulator **does not estimate portfolio returns** by design | Confirm the calculator qualifies as a hypothetical illustration of mathematical principles |
| Fair and balanced; no misleading comparisons | `O-METRIC_MIXING` blocks comparing a performance benchmark with a 7-day annualized yield; figures must match the source (`O-UNGROUNDED_FIGURE`); amounts must come from tools, never model arithmetic (`O-UNGROUNDED_AMOUNT`) | |
| Principal approval / supervision | Dynamic replies can't be pre-approved one by one, so control works through fixed rules, fixed templates for sensitive replies, and post-review using the audit log | A principal sampling and review workflow; classify AI replies under 2210 categories |

### Supervision and recordkeeping

| Rule | What it asks | How WealthPilot addresses it | Gap |
|---|---|---|---|
| **FINRA Rule 3110** (supervision) | A supervisory system reasonably designed for compliance, including review of communications | Every turn records the guard decision, the rule codes that fired, tool calls and the handoff state machine. The ops dashboard shows rule hit counts, fallback and rewrite rates; any turn can be traced by request ID | Named supervising principals; documented review cadence; escalation workflow |
| **SEA Rule 17a-4 / FINRA Rule 4511** (books and records) | Preserve business communications for required periods, in a compliant form (WORM, or an audit-trail alternative) | Full conversation, decisions and tool-call logs are persisted; metrics are stored separately without content | WORM or audit-trail storage, retention schedule, legal hold, e-discovery export |

### Privacy and security

| Rule | What it asks | How WealthPilot addresses it | Gap |
|---|---|---|---|
| **Regulation S-P** (amended 2024) | Safeguard customer information; written incident response program; notify affected customers as soon as practicable and no later than 30 days after becoming aware of unauthorized access to sensitive customer information; oversee service providers, who must notify the firm within 72 hours | Threat model with a test per control ([SECURITY.md](SECURITY.md)); server-side sessions; role isolation; log redaction; customer ID and rating injected into tools, never into the prompt; metrics store no content or customer IDs; voice is transcribed on our server and never stored | Privacy notice; incident response program and notification process; vendor due diligence and contracts for the LLM provider; data processing terms |

### Model risk and AI governance

| Reference | What it asks | How WealthPilot addresses it | Gap |
|---|---|---|---|
| **FINRA RN 24-09** | Apply existing rules to GenAI; consider supervision, communications, recordkeeping, cybersecurity, third-party risk | See the sections above | AI use-case inventory and approval process |
| **Model risk management** (Fed / OCC SR 11-7, for bank-affiliated firms) | Sound development, independent validation, ongoing monitoring, governance | Regression evaluation in both languages; fault-injection tests; per-turn monitoring; model switchable through config (OpenAI-compatible adapter) and re-evaluated before switching | Independent validation; model inventory; formal change management for prompt and model updates |
| **SEC predictive data analytics proposal** | Proposed in July 2023 to address conflicts from analytics that steer investors; withdrawn in June 2025 | The underlying concern, technology steering customers toward the firm's interest, is handled by excluding commission from ranking and blocking return-based pitches | Conflicts from technology are still covered by Reg BI's conflict obligation |

## 3. Where the Chinese and US frameworks line up

| Concept | China (bank wealth management) | US (broker-dealer) | WealthPilot control |
|---|---|---|---|
| Know your customer's risk tolerance before recommending | Investor suitability: risk assessment, product risk level ≤ customer rating | Reg BI Care, customer investment profile | Gate: no product tools before a valid risk profile; hard filter on rating |
| No guaranteed returns | Wealth products are not principal-protected; benchmarks aren't promises | 2210: no promissory claims or projections | `O-PROHIBITED_CLAIM`, hypothetical notes, benchmark labels |
| No pressure or inducement | Sales conduct rules | Reg BI conflict obligation (no sales contests tied to specific products) | `O-PRESSURE_SALES`, `O-GIFT_FOR_PURCHASE` |
| Human in the loop | Relationship manager follow-up | Supervision; registered representative | Handoff state machine with audit trail; the AI can't claim a human has joined |
| Records | Sales process recording and retention | 17a-4 / 4511 | Persisted conversations and decision logs |

## 4. What I would do first for a US pilot

1. Map the risk questionnaire to the Reg BI investment profile fields and add tax status and outside assets.
2. Store a recommendation rationale record (alternatives considered, cost comparison) for every product suggestion.
3. Add Form CRS and an "AI assistant" disclosure to the first message.
4. Move conversation storage to a 17a-4 compliant archive.
5. Write supervisory procedures for the AI channel: rule changes approved by compliance, weekly principal sampling of conversations by rule hit, and a re-evaluation gate before any model or prompt change.

## Sources checked (October 2026)

- SEC withdrawal of 14 proposed rules, including the predictive data analytics proposal (June 12, 2025): [National Law Review](https://natlawreview.com/article/sec-formally-withdraws-fourteen-rule-proposals), [Ropes & Gray](https://www.ropesgray.com/en/insights/alerts/2025/06/sec-clears-unfinished-rulemakings-from-regulatory-agenda)
- Regulation S-P amendments (adopted May 2024): [KPMG regulatory alert](https://kpmg.com/us/en/articles/2024/regulation-sp-sec-final-amendments-reg-alert.html)
- FINRA Regulatory Notice 24-09, Reg BI, FINRA Rules 2111 / 2210 / 3110 / 4511 and SEA Rule 17a-4 are summarized from their published text; confirm current versions before relying on them.
