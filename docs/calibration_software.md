# StatusForge Calibration — Software delivery

> Engine color vs human label on the synthetic gold set. The color is computed by
> the deterministic rulebook interpreter; the LLM only narrates.

## Headline
```
n=20  exact-agreement=0.95  quadratic-weighted kappa=0.96
DANGER RATE (truly-Red under-called)=0.00 (95% CI 0.00-0.35, n_red=7)
confusion (rows=true, cols=pred Green/Amber/Red):
  true Green |   6   1   0
  true Amber |   0   6   0
  true Red   |   0   0   7
narrative faithfulness = 1.00
```

**The metric that matters is the danger rate** (truly-Red under-called) — it should be 0.
Small gold set → wide CIs; this demonstrates the method, not a production benchmark.

## Per-team

| Team | Human | Engine |
|---|---|---|
| Checkout | Red | Red |
| Identity | Green | Green |
| Data Platform | Amber | Amber |
| Notifications | Red | Red |
| Search | Green | Green |
| Billing | Red | Red |
| Onboarding | Amber | Amber |
| Fraud | Red | Red |
| Mobile | Amber | Amber |
| Infra | Green | Green |
| Analytics | Amber | Amber |
| Support Tools | Red | Red |
| Growth | Green | Green |
| Payments Infra | Amber | Amber |
| Compliance | Red | Red |
| Content | Green | Green |
| Partner API | Amber | Amber |
| Ledger | Red | Red |
| Design System | Green | Green |
| Localization | Green | Amber ⚠️ |
