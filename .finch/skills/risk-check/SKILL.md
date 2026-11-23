---
name: risk-check
version: 1.0.0
description: Independent pre-trade risk checklist for MARKETMIND.
---
# Risk Check Skill

Before a proposed paper trade:
1. Confirm the decision is BUY and the proposal has a positive reference price.
2. Enforce the configured risk-profile position cap.
3. Check volatility and concentration; conservative profile vetoes a BUY when the observed absolute daily move exceeds 3%.
4. Treat synthetic/demo quotes as paper-only and disclose them.
5. Return PASS or VETO with explicit reasons.
6. Never let an LLM override a deterministic veto.
