# StatusForge Calibration

> Engine color vs human label on the synthetic gold set. The engine's color is
> computed by deterministic rules; the LLM only narrates. Offline mock unless a
> provider key was set.

## Headline
```
n=20  exact-agreement=0.90  quadratic-weighted kappa=0.92
DANGER RATE (truly-Red under-called)=0.00 (95% CI 0.00-0.35, n_red=7)
confusion (rows=true, cols=pred Green/Amber/Red):
  true Green |   5   2   0
  true Amber |   0   6   0
  true Red   |   0   0   7
narrative faithfulness = 1.00
```

**Read honestly:** small gold set → wide CIs. The metric that matters most is the
**danger rate** (truly-Red teams under-called) — it should be 0, and the narrative
faithfulness should be 1.0 by construction (the LLM cannot change the color).

## Per-team

| Team | Human | Engine |
|---|---|---|
| Checkout | Red | Red |
| Identity | Green | Amber ⚠️ |
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
