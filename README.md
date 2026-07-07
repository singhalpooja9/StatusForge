# StatusForge

**Auditable Red/Amber/Green for any program — a deterministic rulebook owns the color, the LLM only narrates.**

[![CI](https://github.com/singhalpooja9/StatusForge/actions/workflows/ci.yml/badge.svg)](https://github.com/singhalpooja9/StatusForge/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![status](https://img.shields.io/badge/status-working%20app%20%2B%20eval-5eead4)

> A **deterministic rulebook interpreter** computes each team's Red/Amber/Green from numeric
> signals; the model *only* writes the narrative. The LLM has **no numeric path to the color**
> — so the health call is auditable, reproducible, unit-tested, and can never be argued up by
> generated prose. Point it at a different **rulebook** (a YAML spec) and it grades a marketing
> launch — or any program — with no code change.
>
> This is the weekly program-health dashboard rebuilt as public code, with the eval to back it.
> Synthetic data only; the color path runs fully offline with no keys.

**Live demo:** _(Streamlit Community Cloud — link after deploy)._ Zero setup: a shared Groq key
writes the prose (or an offline narrator if it's rate-limited); bring your own key to use instead.
**The Red/Amber/Green is identical either way.**

---

## The design in one idea

On a program review, the number that matters is the **color** — is this workstream **Red**?
Letting an LLM *decide* that is a governance mistake: it can't be audited and it drifts. So the
job is split:

- **A deterministic interpreter owns the color.** `Red/Amber/Green` is a pure function of numeric
  signals and a **rulebook** — a whitelisted-operator YAML spec (`>=`, `abs>=`, …) with **no code
  and no `eval`**. The engine loops the validated rules; malformed rulebooks **fail closed** (refuse
  to run). Edit the rulebook to grade a different domain — the engine never changes.
- **The LLM only narrates.** It's handed the color + the reasons the engine fired, and may only
  phrase them. A faithfulness check verifies the prose never claims a different health level.
- **A human confirms the numbers.** Extracted signals land in an **editable table** — the model
  *proposes*, a human *corrects*, the engine *rules*.

## Configurable — one engine, any program

The engine is domain-agnostic; the domain lives entirely in a rulebook:

- [`rulebooks/software.yaml`](rulebooks/software.yaml) — slip days, open P1s, ownerless blocked deps, scope delta, milestone miss
- [`rulebooks/marketing.yaml`](rulebooks/marketing.yaml) — legal approvals, channels blocked, budget overrun, creative-asset readiness

Same code, same governance property, a completely different domain. Writing a `construction.yaml`
or `research.yaml` is a data change, not a code change.

## Quickstart (no API key needed)

```bash
pip install -r requirements-dev.txt

streamlit run app.py                                  # the interactive app
pytest -q                                             # 36 offline tests
python scripts/run_calibration.py --domain software   # -> docs/calibration_software.{md,png}
python scripts/run_calibration.py --domain marketing  # -> docs/calibration_marketing.{md,png}
```

The **colors are always deterministic and offline** — no key ever touches them. A real LLM only
changes the *prose*, and resolves in this order: **your own key (BYOK) → shared Groq key → offline
narrator**, with any live failure falling back to offline silently so the demo never breaks.

## Results (engine vs. human, per rulebook)

Classes are **ordinal** (Green < Amber < Red) and errors are **cost-asymmetric** — calling a
truly-Red program Green is the catastrophic error — so the headline is the **danger rate**, not
accuracy.

| Rulebook | exact | quad-κ | danger rate | faithfulness |
|---|---|---|---|---|
| Software (n=20) | 0.95 | 0.96 | **0.00** | 1.00 |
| Marketing (n=16) | 0.69 | 0.79 | 0.33 | 1.00 |

**What the numbers actually say (two honest layers):**
- **The engine is deterministic — same numbers, same color, always.** Given signals, the color is a pure
  function of the rulebook; there is nothing to drift, and any verdict re-derives by hand from the YAML.
- **Where it disagrees with a human, that's a threshold *choice*, not a bug.** On the marketing gold set
  the rule matched the human on ~11/16 (danger rate 0.33). Checking each miss, the *numbers were extracted
  correctly* — the gaps are places where the shipped thresholds don't match how that labeler weighed
  things. That's the point of a **rulebook you edit**: the disagreement is visible and tunable in YAML, not
  hidden in a model. (In the software domain, the misses are the free-text *reader* instead — which is why
  the grid lets you correct every number before the engine rules.)

Small gold sets → wide CIs; this demonstrates the method, not a production benchmark.

## What this demonstrates (concepts + stack)

| Concept | Where |
|---|---|
| **Deterministic-engine + LLM-narrates** (LLM has no numeric path) | `engine.py`, `narrate.py` |
| **Configurable rulebook interpreter** (data, not code; whitelisted operators; **fail-closed**) | `rulebook.py`, `rulebooks/*.yaml` |
| **3-class ordinal, cost-asymmetric eval** | `calibration.py` — quadratic-weighted κ + danger-rate + Wilson CIs |
| **Narrative faithfulness** (prose can't contradict the color) | `calibration.py`, live badge in the app |
| **Human-in-the-loop override** (editable signal table) | `app.py` (`st.data_editor`) |
| **Safe BYO-key** (session-only, per-call `api_key`, never `os.environ`) | `providers.py`, `extract.py` |
| **Silent offline fallback + deterministic CI** | `narrate.py`, `requirements-ci.txt` (no litellm) |

**Stack:** Python · Pydantic · PyYAML · Streamlit · LiteLLM (Groq/OpenRouter/OpenAI/Anthropic/Gemini) ·
pandas · matplotlib · pytest + GitHub Actions.

## Deploy to Streamlit Community Cloud

1. Push to GitHub (public).
2. [share.streamlit.io](https://share.streamlit.io) → New app → point at `app.py`.
3. **Optional shared key:** add `GROQ_API_KEY` under App → Settings → Secrets to give every visitor
   live prose by default (free Groq key; rate-limited in-app). With no secret it runs offline; visitors
   can still bring their own key.

**Key safety:** a visitor's key lives only in `st.session_state` and is passed per request as
`api_key=…` straight to LiteLLM — **never** `os.environ` (Streamlit Cloud shares one process across
visitors, so a process-global key would leak). See [`statusforge/extract.py`](statusforge/extract.py).

## Layout

```
statusforge/
  rulebook.py      # load + validate a rulebook (whitelisted ops, fail-closed)
  engine.py        # pure interpreter: (signals, rulebook) -> color  (Verdict, ProgramRollup)
  models.py        # signal validation, spec-driven from the rulebook
  extract.py       # status text -> validated signals (offline reader or LLM); LLMConfig
  narrate.py       # verdict -> grounded prose; silent offline fallback on live failure
  calibration.py   # ordinal cost-asymmetric eval + narrative faithfulness
  dataset.py       # per-domain gold sets
  providers.py     # provider catalog + owner-key (st.secrets) resolver
app.py             # Streamlit: Demo / Use your own key / How it works / Eval
rulebooks/         # program.yaml (default), software.yaml, marketing.yaml  (write your own domain)
data/              # per-domain gold sets (program / software / marketing)
scripts/run_calibration.py   # per-domain calibration -> docs/
tests/             # 53 offline tests (engine, rulebook fail-closed, extraction, missing-signal, fallback)
```

## Honest scope

Working app + eval harness, not a product. Synthetic data only, no integrations. The offline free-text
reader is best-effort (a real deployment would use structured import or the LLM extractor + the editable
table). The point is the **architecture** — an auditable, configurable health call — and the **eval** that
proves it, honestly separating engine correctness from extraction.

## License

[MIT](LICENSE) — free to use, adapt, and build on.

---

*Part of [The Lab](https://singhalpooja.com) — Pooja Singhal, Senior Technical Program Manager.*
