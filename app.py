"""StatusForge — Streamlit app.

Paste each team's raw status; a DETERMINISTIC rule engine computes Red/Amber/Green
(the LLM has no numeric path to the color), and the LLM only writes the narrative.

Works with ZERO setup: the engine + an offline narrator run everything by default.
A visitor can optionally paste their OWN API key (session-only, never stored) to
upgrade the prose to a real LLM. The health color is identical either way.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from statusforge.extract import extract_signals, LLMConfig
from statusforge.engine import evaluate_program, RuleConfig
from statusforge.narrate import narrate_rollup
from statusforge.calibration import narrative_contradicts
from statusforge.providers import PROVIDER_CATALOG, default_model

st.set_page_config(page_title="StatusForge", page_icon="🚦", layout="wide")

st.markdown("""
<style>
  .pill { padding:3px 12px; border-radius:20px; font-weight:700; font-size:.8rem; }
  .Red   { background:#7f1d1d; color:#fecaca; }
  .Amber { background:#78440a; color:#fde3c0; }
  .Green { background:#0f5132; color:#b7f0cf; }
  .note  { color:#8b97ad; font-size:.85rem; }
</style>
""", unsafe_allow_html=True)

SAMPLE = """Checkout: 2 open P1s on the payment retry path. Critical path slipped 6 days. 3 of 5 milestones hit.
Identity: On track. All 4 milestones hit this sprint, no blockers, scope stable.
Data Platform: 1 blocked dependency on the schema migration, owner assigned. Slipped 2 days. Scope +8%.
Billing: 1 blocked dependency with no owner on the tax service. Otherwise fine."""


def current_cfg() -> LLMConfig:
    """Build the LLM config from session state. No key -> offline (empty api_key)."""
    key = st.session_state.get("byok", "")
    model = st.session_state.get("model", default_model("Groq (free)"))
    return LLMConfig(model=model, api_key=key)


def run_rollup(raw: str, cfg: LLMConfig, rule_cfg: RuleConfig):
    lines = [l.strip() for l in raw.splitlines() if l.strip() and ":" in l]
    teams = [extract_signals(n.strip(), t.strip(), cfg)
             for n, t in (l.split(":", 1) for l in lines)]
    roll = evaluate_program(teams, rule_cfg)
    return narrate_rollup(roll, cfg)


# =============================== HEADER ===============================
st.title("🚦 StatusForge")
st.subheader("Auditable Red / Amber / Green for cross-team programs")
st.markdown(
    "Paste each team's weekly status. A **fixed rulebook — not an AI guess —** grades every "
    "team Red / Amber / Green and rolls it up to a program color. The model only writes the "
    "summary, and **it can never change the color.**")

tab_demo, tab_key, tab_how, tab_eval = st.tabs(
    ["▶ Demo", "🔑 Use your own key (optional)", "📐 How it works", "📊 Eval"])

# =============================== DEMO ===============================
with tab_demo:
    cfg = current_cfg()
    chip = (f"🟢 Live narrator — {st.session_state.get('provider_label','your key')} "
            "(key in session memory only)") if cfg.live else \
           "⚪ Offline narrator — no key needed. Add one under *Use your own key* for LLM prose."
    st.caption(chip)

    st.markdown("**Team statuses** — one team per line, `Team: status text`.")
    raw = st.text_area("statuses", value=SAMPLE, height=160, label_visibility="collapsed")

    with st.expander("Advanced: engine thresholds (change the rules, watch the color move)"):
        st.caption("The color is computed from these rules — the LLM never gets a vote. "
                   "Tighten a threshold and re-run to see teams shift.")
        rule_cfg = RuleConfig(
            red_slip_days=st.slider("Red if critical-path slip ≥ (days)", 1, 15, 5),
            red_open_p1s=st.slider("Red if open P1s ≥", 1, 5, 1),
        )

    clicked = st.button("Build roll-up", type="primary")
    # Auto-run on first visit so a stranger lands on a colored result, not a blank box.
    first_load = "seen" not in st.session_state
    st.session_state["seen"] = True

    if clicked or first_load:
        if not [l for l in raw.splitlines() if l.strip() and ":" in l]:
            st.warning("Add at least one `Team: status` line.")
            st.stop()
        try:
            roll = run_rollup(raw, cfg, rule_cfg)
        except Exception as e:
            st.error(f"LLM call failed: {e}\n\nRemove your key to use the offline narrator, "
                     "or check the key/model under *Use your own key*.")
            st.stop()

        color = roll.program_color
        st.markdown(f"### Program status &nbsp; <span class='pill {color}'>{color}</span>",
                    unsafe_allow_html=True)
        st.write(roll.summary)

        rows = [{
            "Team": v.team, "Color 🔒": v.color,
            "Slip (days)": v.signals.critical_path_slip_days,
            "Open P1s": v.signals.open_p1s,
            "Blocked deps": v.signals.blocked_dependencies,
            "Ownerless blocked": v.signals.ownerless_blocked_deps,
            "Scope Δ %": v.signals.scope_delta_pct,
            "Why (rules that fired)": "; ".join(v.reasons),
        } for v in roll.teams]
        df = pd.DataFrame(rows)

        def _paint(r):
            bg = {"Red": "#7f1d1d", "Amber": "#78440a", "Green": "#0f5132"}[r["Color 🔒"]]
            return [f"background-color: {bg}" if c == "Color 🔒" else "" for c in r.index]

        st.dataframe(df.style.apply(_paint, axis=1), width="stretch", hide_index=True)
        st.caption("🔒 Color is computed by the deterministic engine. The prose below is LLM-authored "
                   "(or the offline narrator) and is checked to never contradict the color.")

        st.markdown("**Narrative** _(LLM-authored — cannot change a color)_")
        for v in roll.teams:
            faithful = not narrative_contradicts(v.color, v.narrative)
            badge = "✓ consistent with engine color" if faithful else "⚠ contradicts engine — flagged"
            st.markdown(
                f"<span class='pill {v.color}'>{v.color}</span> **{v.team}** — {v.narrative}  \n"
                f"<span class='note'>{badge}</span>", unsafe_allow_html=True)

# =============================== BYO KEY ===============================
with tab_key:
    st.markdown("The demo already works with **zero setup**. Add your own key only if you want "
                "live LLM-written prose — **the Red/Amber/Green never changes.**")

    label = st.selectbox("Provider", list(PROVIDER_CATALOG.keys()), index=0)
    st.session_state["provider_label"] = label
    st.session_state["model"] = st.text_input("Model", value=default_model(label))
    st.text_input("Your API key", type="password", key="byok",
                  placeholder="pasted key stays in this browser session only")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Test key"):
            k = st.session_state.get("byok", "")
            if not k.strip():
                st.warning("Paste a key first.")
            else:
                try:
                    import litellm
                    litellm.suppress_debug_info = True
                    litellm.completion(model=st.session_state["model"], api_key=k,
                                       messages=[{"role": "user", "content": "ping"}], max_tokens=1)
                    st.success(f"Key works — connected to {label}.")
                except Exception as e:
                    st.error(f"Key rejected. Check it's a {label} key for `{st.session_state['model']}`.")
    with c2:
        if st.button("Clear key"):
            st.session_state.pop("byok", None)
            st.success("Key cleared from this session.")

    st.divider()
    st.markdown(
        "<span class='note'>"
        "• Held in memory for <b>this browser session only</b>. Never stored, never logged, never "
        "committed — it disappears when you close the tab.<br>"
        "• Your key is passed straight from this app to your chosen provider; it never touches a "
        "StatusForge server or the environment.<br>"
        "• Cost is a few hundred tokens per team — cents at most. <b>Groq</b> and <b>OpenRouter</b> "
        "have free keys (no card).<br>"
        "• Read the exact code that handles your key: "
        "<a href='https://github.com/singhalpooja9/StatusForge/blob/main/statusforge/narrate.py'>narrate.py</a>."
        "</span>", unsafe_allow_html=True)

# =============================== HOW IT WORKS ===============================
with tab_how:
    st.markdown("""
### The design in one idea
On a weekly program review, the number that matters is the **color** — is this workstream **Red**?
Letting an LLM *decide* that is a governance mistake: it can't be audited and it drifts.

So StatusForge splits the job:
- **A deterministic rule engine owns the color.** `Red/Amber/Green` is a pure function of numeric
  signals — critical-path slip, open P1s, ownerless blocked dependencies, scope delta, milestone miss.
  It lives in one inspectable place and is fully unit-tested.
- **The LLM only narrates.** It's handed the color + the reasons the engine already fired, and may only
  phrase them. A faithfulness check verifies the prose never claims a different health level.

The model *proposes* the numbers during extraction (a human can override them). **It never sets the verdict** —
so the health call is auditable, reproducible, and the same with a key or without one.

*Part of [The Lab](https://singhalpooja.com). Source: [github.com/singhalpooja9/StatusForge](https://github.com/singhalpooja9/StatusForge).*
""")

# =============================== EVAL ===============================
with tab_eval:
    st.markdown("""
### Does the engine agree with a human?
Measured on a synthetic gold set of team statuses. Because the classes are **ordinal**
(Green < Amber < Red) and the errors are **cost-asymmetric** (calling a truly-Red program Green is
the catastrophic error), aggregate accuracy is the wrong headline. The two that matter:
- **Danger rate = 0** — no truly-Red team was under-called; the only misses are Green→Amber (over-caution).
- **Narrative faithfulness = 1.0** — no generated line ever contradicts the engine's color, by construction.
""")
    try:
        st.image("docs/calibration.png", caption="Engine vs human (n=20) + metrics", width="stretch")
    except Exception:
        st.caption("Run `python scripts/run_calibration.py` to generate the chart.")
    st.code("n=20  exact-agreement=0.90  quadratic-weighted kappa=0.92\n"
            "DANGER RATE (truly-Red under-called)=0.00  (95% CI 0.00-0.35, n_red=7)\n"
            "narrative faithfulness = 1.00")
    st.caption("Honest note: n=20 → wide CIs. The gold set is synthetic and written to be unambiguous "
               "for the documented thresholds; it demonstrates the method, not a production benchmark.")

st.divider()
st.caption("Engine is deterministic and unit-tested; the LLM cannot change a color. "
           "Part of *The Lab* → singhalpooja.com")
