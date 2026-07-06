# StatusForge Calibration — Program status

> Engine color vs human label on the synthetic gold set. The color is computed by
> the deterministic rulebook interpreter; the LLM only narrates.

## Headline
```
n=20  exact-agreement=1.00  quadratic-weighted kappa=1.00
DANGER RATE (truly-Red under-called)=0.00 (95% CI 0.00-0.39, n_red=6)
confusion (rows=true, cols=pred Green/Amber/Red):
  true Green |   7   0   0
  true Amber |   0   7   0
  true Red   |   0   0   6
narrative faithfulness = 1.00
```

**The metric that matters is the danger rate** (truly-Red under-called) — it should be 0.
Small gold set → wide CIs; this demonstrates the method, not a production benchmark.

## Per-team

| Team | Human | Engine |
|---|---|---|
| Checkout | Red | Red |
| Identity | Green | Green |
| Data | Amber | Amber |
| Billing | Red | Red |
| Search | Green | Green |
| Fraud | Red | Red |
| Mobile | Amber | Amber |
| Infra | Green | Green |
| Analytics | Amber | Amber |
| Support | Red | Red |
| Growth | Green | Green |
| Payments | Amber | Amber |
| Compliance | Amber | Amber |
| Content | Green | Green |
| Partner | Red | Red |
| Ledger | Red | Red |
| Design | Green | Green |
| Localization | Amber | Amber |
| Platform | Amber | Amber |
| Reporting | Green | Green |
