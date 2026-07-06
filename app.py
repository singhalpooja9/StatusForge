"""StatusForge — Streamlit app.

Paste team statuses (or a CSV). A DETERMINISTIC rulebook interpreter grades each team
Red/Amber/Green (the LLM has no numeric path to the color); the LLM only writes the
narrative. Point it at a different rulebook and it grades any program.

Key model:
  * Colors are ALWAYS deterministic (offline) — a key never touches the numbers.
  * Narration uses, in order: the visitor's own key (BYOK) > the owner's shared Groq
    key (st.secrets) > offline prose. Any live failure falls back to offline silently.
  * Extraction stays deterministic even with the shared key, so colors are reproducible.
"""

from __future__ import annotations

import datetime
import pandas as pd
import streamlit as st

from statusforge.rulebook import load_rulebook
from statusforge.extract import extract_signals, LLMConfig
from statusforge.engine import evaluate_program
from statusforge.narrate import narrate_rollup
from statusforge.calibration import narrative_contradicts
from statusforge.providers import PROVIDER_CATALOG, default_model, owner_groq_key

st.set_page_config(page_title="StatusForge", page_icon="🚦", layout="wide")
st.markdown("""
<style>
  .pill { padding:3px 12px; border-radius:20px; font-weight:700; font-size:.8rem; }
  .Red{background:#7f1d1d;color:#fecaca;} .Amber{background:#78440a;color:#fde3c0;} .Green{background:#0f5132;color:#b7f0cf;}
  .note{ color:#8b97ad; font-size:.85rem; }
</style>""", unsafe_allow_html=True)

SAMPLES = {
    "software": """Checkout: 2 open P1s on the payment retry path. Critical path slipped 6 days. 3 of 5 milestones hit.
Identity: On track. All 4 milestones hit this sprint, no blockers, scope stable.
Data Platform: 1 blocked dependency on the schema migration, owner assigned. Slipped 2 days. Scope +8%.
Billing: 1 blocked dependency with no owner on the tax service. Otherwise fine.""",
    "marketing": """Brand Film: 2 legal approvals still pending on the hero video. 40 of 40 assets ready. 12 days to launch.
Paid Media: All channels go, budget 3% under plan, 20 of 20 assets ready.
Email: 1 launch channel blocked on the ESP migration. Assets 18 of 20 ready.
PR: Budget 25% over plan after the agency retainer. No approvals pending.""",
}

DAILY_LIVE_CAP = 200   # process-global/day soft cap for the shared owner key
SESSION_LIVE_CAP = 8   # per-visitor live runs


@st.cache_resource
def _live_counter():
    return {"date": None, "count": 0}


def can_use_owner_key() -> bool:
    """Rate-limit the shared owner key: per-session + a soft process-global daily cap."""
    if st.session_state.get("live_runs", 0) >= SESSION_LIVE_CAP:
        return False
    c = _live_counter()
    today = datetime.date.today().isoformat()
    if c["date"] != today:
        c["date"], c["count"] = today, 0
    return c["count"] < DAILY_LIVE_CAP


def note_live_run():
    st.session_state["live_runs"] = st.session_state.get("live_runs", 0) + 1
    c = _live_counter()
    c["count"] += 1


def narrator_cfg() -> tuple[LLMConfig, str]:
    """Resolve the NARRATION config + a human label. BYOK > owner Groq > offline."""
    byok = st.session_state.get("byok", "").strip()
    if byok:
        model = st.session_state.get("model", default_model(st.session_state.get("provider_label", "Groq (free)")))
        return LLMConfig(model=model, api_key=byok), f"your key ({st.session_state.get('provider_label','?')})"
    owner = owner_groq_key()
    if owner and can_use_owner_key():
        return LLMConfig(model="groq/llama-3.3-70b-versatile", api_key=owner), "shared Groq key"
    return LLMConfig(api_key=""), "offline narrator"


# =============================== HEADER ===============================
st.title("🚦 StatusForge")
st.subheader("Auditable Red / Amber / Green for cross-team programs")
st.markdown("A **fixed rulebook — not an AI guess —** grades every team Red / Amber / Green and rolls it "
            "up to a program color. The model only writes the summary, and **it can never change the color.** "
            "Swap the rulebook and it grades a marketing launch or any program.")

tab_demo, tab_key, tab_how, tab_eval = st.tabs(
    ["▶ Demo", "🔑 Use your own key", "📐 How it works", "📊 Eval"])

# =============================== DEMO ===============================
with tab_demo:
    domain = st.radio("Rulebook", ["software", "marketing"], horizontal=True,
                      format_func=lambda d: {"software": "Software delivery", "marketing": "Marketing launch"}[d])
    rb = load_rulebook(domain)

    st.markdown("**Team statuses** — one per line, `Team: status text`. "
                "Colors are computed by the deterministic engine (no key needed); a key only changes the prose.")
    raw = st.text_area("statuses", value=SAMPLES[domain], height=150, label_visibility="collapsed", key=f"raw_{domain}")

    build = st.button("Build roll-up", type="primary")
    if build or st.session_state.get(f"seen_{domain}") is None:
        st.session_state[f"seen_{domain}"] = True
        lines = [l.strip() for l in raw.splitlines() if l.strip() and ":" in l]
        if not lines:
            st.warning("Add at least one `Team: status` line.")
            st.stop()

        # Extraction is ALWAYS deterministic (offline) so colors stay reproducible.
        extracted = [(n.strip(), extract_signals(t.strip(), rb)) for n, t in (l.split(":", 1) for l in lines)]

        st.markdown("**Extracted signals — edit any number, then rebuild.** "
                    "_The engine decides the color from these; the LLM never touches them._")
        edit_df = pd.DataFrame([{"Team": n, **{s.label: sig[s.name] for s in rb.signals}} for n, sig in extracted])
        edited = st.data_editor(edit_df, hide_index=True, width="stretch", key=f"editor_{domain}")

        # rebuild signal dicts from the (possibly edited) table
        label_to_name = {s.label: s.name for s in rb.signals}
        teams = []
        for _, row in edited.iterrows():
            sig = {label_to_name[c]: float(row[c]) for c in edited.columns if c in label_to_name}
            teams.append((str(row["Team"]), sig))

        roll = evaluate_program(teams, rb)
        cfg, label = narrator_cfg()
        roll = narrate_rollup(roll, cfg)
        if cfg.live:
            note_live_run()

        st.markdown(f"### Program status &nbsp; <span class='pill {roll.program_color}'>{roll.program_color}</span>",
                    unsafe_allow_html=True)
        st.write(roll.summary)
        st.caption(f"Narrator: {label}. 🔒 Colors are deterministic — identical with a key or without one.")

        st.markdown("**Narrative** _(LLM-authored — cannot change a color)_")
        for v in roll.teams:
            ok = not narrative_contradicts(v.color, v.narrative)
            badge = "✓ consistent with engine color" if ok else "⚠ contradicts engine — flagged"
            st.markdown(f"<span class='pill {v.color}'>{v.color}</span> **{v.team}** — {v.narrative}  \n"
                        f"<span class='note'>{badge}</span>", unsafe_allow_html=True)

# =============================== BYO KEY ===============================
with tab_key:
    st.markdown("The demo already works with **zero setup** — a shared Groq key writes the prose (or the offline "
                "narrator if it's rate-limited). Add **your own** key to use it instead of the shared one. "
                "**The Red/Amber/Green never changes either way.**")
    label = st.selectbox("Provider", list(PROVIDER_CATALOG.keys()), index=0)
    st.session_state["provider_label"] = label
    st.session_state["model"] = st.text_input("Model", value=default_model(label))
    st.text_input("Your API key", type="password", key="byok",
                  placeholder="stays in this browser session only")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Test key"):
            k = st.session_state.get("byok", "").strip()
            if not k:
                st.warning("Paste a key first.")
            else:
                try:
                    import litellm
                    litellm.suppress_debug_info = True
                    litellm.completion(model=st.session_state["model"], api_key=k,
                                       messages=[{"role": "user", "content": "ping"}], max_tokens=1)
                    st.success(f"Key works — connected to {label}.")
                except Exception:
                    st.error(f"Key rejected for `{st.session_state['model']}`. Check it's a {label} key.")
    with c2:
        if st.button("Clear key"):
            st.session_state.pop("byok", None)
            st.success("Cleared from this session.")
    st.markdown("<span class='note'>Held in memory for this browser session only — never stored, logged, or "
                "committed. Passed straight from this app to your provider, never to a StatusForge server or the "
                "environment. Groq & OpenRouter have free keys. "
                "<a href='https://github.com/singhalpooja9/StatusForge/blob/main/statusforge/narrate.py'>See the code.</a>"
                "</span>", unsafe_allow_html=True)

# =============================== HOW IT WORKS ===============================
with tab_how:
    st.markdown("""
### The design in one idea
On a program review, the number that matters is the **color** — is this workstream **Red**? Letting an LLM
*decide* that is a governance mistake: it can't be audited and it drifts. So StatusForge splits the job:

- **A deterministic interpreter owns the color.** `Red/Amber/Green` is a pure function of numeric signals and a
  **rulebook** (`rulebooks/*.yaml`) — a whitelisted-operator spec with no code and no `eval`. Edit the rulebook to
  grade a different domain; the engine never changes. Malformed rulebooks **fail closed** (refuse to run).
- **The LLM only narrates.** It's handed the color + the reasons the engine fired, and may only phrase them. A
  faithfulness check verifies the prose never claims a different health level.

You can **edit the extracted numbers** before the engine decides — the model *proposes*, a human *confirms*, the
engine *rules*. Colors are identical with a key or without one.

*Honest scope: the offline free-text reader is best-effort; for non-software domains the LLM extractor is more
reliable (the engine generalizes; a regex reader doesn't). Source:
[github.com/singhalpooja9/StatusForge](https://github.com/singhalpooja9/StatusForge).*
""")

# =============================== EVAL ===============================
with tab_eval:
    st.markdown("Engine-vs-human agreement on synthetic gold sets, per rulebook. Classes are **ordinal** "
                "(Green<Amber<Red) and errors **cost-asymmetric** (a truly-Red program called Green is the "
                "catastrophic error) — so the headline is the **danger rate**, not accuracy.")
    ec1, ec2 = st.columns(2)
    with ec1:
        st.markdown("**Software delivery**")
        try:
            st.image("docs/calibration_software.png", width="stretch")
        except Exception:
            st.caption("run `python scripts/run_calibration.py --domain software`")
    with ec2:
        st.markdown("**Marketing launch** (proves generalization)")
        try:
            st.image("docs/calibration_marketing.png", width="stretch")
        except Exception:
            st.caption("run `python scripts/run_calibration.py --domain marketing`")
    st.caption("The engine (pure rulebook interpreter) is perfect on both; remaining marketing misses are "
               "offline-extraction limits, not engine errors — the honest engine-vs-extraction split. "
               "Small gold sets → wide CIs; this demonstrates the method, not a production benchmark.")

st.divider()
st.caption("Deterministic engine + honest eval. The LLM cannot change a color. Part of *The Lab* → singhalpooja.com")
