# StatusForge Calibration — Marketing launch

> Engine color vs human label on the synthetic gold set. The color is computed by
> the deterministic rulebook interpreter; the LLM only narrates.

## Headline
```
n=16  exact-agreement=0.69  quadratic-weighted kappa=0.79
DANGER RATE (truly-Red under-called)=0.33 (95% CI 0.10-0.70, n_red=6)
confusion (rows=true, cols=pred Green/Amber/Red):
  true Green |   5   0   0
  true Amber |   3   2   0
  true Red   |   0   2   4
narrative faithfulness = 1.00
```

**The metric that matters is the danger rate** (truly-Red under-called) — it should be 0.
Small gold set → wide CIs; this demonstrates the method, not a production benchmark.

## Per-team

| Team | Human | Engine |
|---|---|---|
| Brand Film | Red | Red |
| Paid Media | Green | Green |
| Email | Amber | Amber |
| PR | Red | Red |
| Web | Green | Green |
| Social | Amber | Green ⚠️ |
| Partnerships | Red | Red |
| Events | Green | Green |
| Lifecycle | Red | Amber ⚠️ |
| Influencer | Amber | Green ⚠️ |
| Content | Red | Red |
| Analytics | Green | Green |
| Retail | Amber | Amber |
| SEO | Green | Green |
| Creative Ops | Red | Amber ⚠️ |
| Comms | Amber | Green ⚠️ |
