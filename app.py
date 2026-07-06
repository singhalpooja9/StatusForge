"""StatusForge — turn team updates into a status report you can paste anywhere.

Type your teams in a grid; a FIXED RULE computes each team's Red/Amber/Green from the
numbers (never guessed by AI), and the AI only writes the prose. Outputs come in four
copy-ready formats. Runs with zero setup; works for any program via editable rulebooks.
"""

from __future__ import annotations

import datetime
import html
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from statusforge.rulebook import load_rulebook
from statusforge.models import validate_signals
from statusforge.engine import evaluate_program
from statusforge.narrate import generate_formats
from statusforge.calibration import narrative_contradicts
from statusforge.extract import LLMConfig
from statusforge.providers import PROVIDER_CATALOG, default_model, owner_groq_key

_OFFLINE_CFG = LLMConfig(api_key="")   # deterministic offline writer (no LLM call)

st.set_page_config(page_title="StatusForge", page_icon="🚦", layout="wide")
st.markdown("""
<style>
  .block-container{max-width:1050px;}
  .pill{padding:3px 12px;border-radius:20px;font-weight:700;font-size:.8rem;}
  .Red{background:#7f1d1d;color:#fecaca;} .Amber{background:#78440a;color:#fde3c0;}
  .Green{background:#0f5132;color:#b7f0cf;} .note{color:#8b97ad;font-size:.85rem;}
  .banner{padding:16px 22px;border-radius:14px;font-family:'Sora',sans-serif;
          font-size:1.35rem;font-weight:800;margin:.3rem 0 1rem;border:1px solid #243049;}
  .b-Red{background:linear-gradient(120deg,#3b0d0d,#7f1d1d);color:#fecaca;}
  .b-Amber{background:linear-gradient(120deg,#3a2408,#78440a);color:#fde3c0;}
  .b-Green{background:linear-gradient(120deg,#082c1c,#0f5132);color:#b7f0cf;}
  .card{border:1px solid #243049;border-radius:12px;padding:14px 18px;margin:.4rem 0;
        background:linear-gradient(160deg,#141b2b,#0e1320);}
  .delta{font-size:.8rem;font-weight:600;}
  .up{color:#fca5a5;} .down{color:#86efac;} .same{color:#8b97ad;}
</style>""", unsafe_allow_html=True)

RB = load_rulebook("program")
SIGNAL_LABELS = [s.label for s in RB.signals]
LABEL_TO_NAME = {s.label: s.name for s in RB.signals}
EMOJI = {"Red": "🔴", "Amber": "🟡", "Green": "🟢", "": "⚪"}

STARTER = pd.DataFrame([
    {"Team": "Checkout", "Notes": "payment retry service; two P1s block the release candidate",
     "Blockers": 1, "% Complete": 60, "Days Behind": 6, "Critical Issues": 2},
    {"Team": "Identity", "Notes": "auth revamp shipped; all sprint milestones hit",
     "Blockers": 0, "% Complete": 90, "Days Behind": 0, "Critical Issues": 0},
    {"Team": "Billing",  "Notes": "tax-service integration; blockers stacking on vendor API",
     "Blockers": 3, "% Complete": 50, "Days Behind": 1, "Critical Issues": 0},
])

DAILY_CAP, SESSION_CAP = 200, 8


@st.cache_resource
def _live_counter():
    return {"date": None, "count": 0}


def _can_use_owner_key() -> bool:
    if st.session_state.get("live_runs", 0) >= SESSION_CAP:
        return False
    c = _live_counter(); today = datetime.date.today().isoformat()
    if c["date"] != today:
        c["date"], c["count"] = today, 0
    return c["count"] < DAILY_CAP


def _narrator_cfg():
    from statusforge.extract import LLMConfig
    byok = st.session_state.get("byok", "").strip()
    if byok:
        model = st.session_state.get("model", default_model(st.session_state.get("provider_label", "Groq (free)")))
        return LLMConfig(model=model, api_key=byok), f"your {st.session_state.get('provider_label','')} key"
    owner = owner_groq_key()
    if owner and _can_use_owner_key():
        return LLMConfig(model="groq/llama-3.3-70b-versatile", api_key=owner), "shared Groq key"
    return LLMConfig(api_key=""), "offline writer"


def _copy_button(text: str, key: str):
    """A small clipboard button (components HTML). Reports success ONLY on a real
    clipboard write; falls back to selecting a hidden textarea if the API is blocked
    (common in sandboxed iframes / Safari)."""
    safe = (text.replace("\\", "\\\\").replace("`", "\\`")
                .replace("${", "\\${").replace("</", "<\\/"))
    components.html(f"""
      <button id="b{key}" style="background:#182135;color:#5eead4;border:1px solid #243049;
        border-radius:8px;padding:6px 14px;font-size:.8rem;cursor:pointer;font-family:sans-serif;">
        Copy</button>
      <textarea id="t{key}" style="position:absolute;left:-9999px;"></textarea>
      <script>
        const b=document.getElementById("b{key}"), t=document.getElementById("t{key}");
        const txt=`{safe}`; t.value=txt;
        function ok(){{b.innerText="Copied ✓";setTimeout(()=>b.innerText="Copy",1400);}}
        function fail(){{try{{t.select();document.execCommand("copy");ok();}}
          catch(e){{b.innerText="Copy failed";setTimeout(()=>b.innerText="Copy",1600);}}}}
        b.onclick=()=>{{
          if(navigator.clipboard&&navigator.clipboard.writeText){{
            navigator.clipboard.writeText(txt).then(ok).catch(fail);
          }} else {{ fail(); }}
        }};
      </script>""", height=42)


def _delta_badge(team: str, sig: dict) -> str:
    """Compare this run's signals to the previous run for the same team."""
    prev = st.session_state.get("prev_signals", {}).get(team)
    prevc = st.session_state.get("prev_colors", {}).get(team)
    if not prev:
        return "<span class='delta same'>new</span>"
    bits = []
    curc = st.session_state.get("_curcolor", {}).get(team)
    if prevc and curc and prevc != curc:
        bits.append(f"<span class='delta'>{EMOJI[prevc]}{prevc} → {EMOJI[curc]}{curc}</span>")
    for lbl, name in LABEL_TO_NAME.items():
        a, b = prev.get(name), sig.get(name)
        if a is not None and b is not None and a != b:
            arrow = "up" if b > a else "down"
            # for %Complete, up is good -> flip color meaning
            if name == "percent_complete":
                arrow = "down" if b > a else "up"
            bits.append(f"<span class='delta {arrow}'>{lbl} {a:g}→{b:g}</span>")
    return " · ".join(bits) if bits else "<span class='delta same'>no change</span>"


# ---- sidebar: optional key ----
with st.sidebar:
    st.header("Optional: nicer wording")
    st.caption("StatusForge works with no setup. A key only upgrades the *prose* — "
               "the Red/Amber/Green never changes. Groq & OpenRouter are free.")
    label = st.selectbox("Provider", list(PROVIDER_CATALOG.keys()), index=0)
    st.session_state["provider_label"] = label
    st.session_state["model"] = st.text_input("Model", value=default_model(label))
    st.text_input("Your API key", type="password", key="byok",
                  placeholder="stays in this browser session only")
    st.caption("Session-only — never stored, logged, or committed; sent straight to your provider. "
               "[Code](https://github.com/singhalpooja9/StatusForge/blob/main/statusforge/narrate.py)")

# =============================== HEADER ===============================
st.title("🚦 StatusForge")
st.markdown("### Turn your team updates into a status report you can paste anywhere.")
st.markdown(
    "Fill the grid — one row per team. StatusForge grades each team **🔴 Red / 🟡 Amber / 🟢 Green** by a "
    "fixed rule (not an AI guess) and writes your update in four ready-to-copy formats. "
    "**Reuse it for any program** by editing the numbers; add your own columns for anything else.")

# =============================== GRID ===============================
st.markdown("#### 1. Your teams")

# column manager, tucked into a popover so it doesn't clutter first view
DEFAULT_COLS = ["Notes", *SIGNAL_LABELS]
if "cols" not in st.session_state:
    st.session_state["cols"] = list(DEFAULT_COLS)
with st.popover("⚙ Columns"):
    st.caption("The four signal columns drive the color. Add your own (Owner, ETA, Budget…) — "
               "they appear in the report but don't change the color.")
    nc = st.text_input("Add a column", placeholder="e.g. Owner")
    a, b, c = st.columns(3)
    if a.button("＋ Add") and nc.strip() and nc.strip() != "Team" and nc.strip() not in st.session_state["cols"]:
        st.session_state["cols"].append(nc.strip()); st.rerun()
    drop = b.selectbox("Remove", ["—", *st.session_state["cols"]], label_visibility="collapsed")
    if drop != "—":
        st.session_state["cols"].remove(drop); st.rerun()
    if c.button("↺ Reset"):
        st.session_state["cols"] = list(DEFAULT_COLS); st.rerun()

st.caption("Edit any cell. ＋ at the bottom of the grid adds a team. Everything updates live.")
grid_df = pd.DataFrame({"Team": STARTER["Team"]})
for col in st.session_state["cols"]:
    grid_df[col] = STARTER[col] if col in STARTER.columns else ""
grid = st.data_editor(grid_df, num_rows="dynamic", width="stretch", key="grid")

context = st.text_input(
    "Program context (optional) — what's launching, the deadline, what's at stake",
    placeholder="e.g. Launching Payments v2 on Aug 15; a slip risks the Prime Day window.",
    help="Grounds the executive summary's impact + the ask. Left blank, the summary sticks to the "
         "signals and your Notes — it never invents impact.")

cfg_preview, src = _narrator_cfg()
c_go, c_hint = st.columns([1, 3])
regen = c_go.button(
    "✨ Write with AI" if cfg_preview.live else "Regenerate",
    type="primary", disabled=not cfg_preview.live,
    help=("Re-run the AI writer on the current grid." if cfg_preview.live
          else "Add an API key (sidebar) to enable AI-written prose. The report already updates live."))
c_hint.caption(
    "Colors + table update **live** as you edit (deterministic, free). "
    + ("Prose is AI-written — click **Write with AI** to refresh it after edits."
       if cfg_preview.live else
       "Prose uses the built-in writer; add a key in the sidebar for AI-written prose."))

# =============================== COMPUTE ===============================
# The COLOR + table are deterministic and recompute every rerun (instant, free).
# The LLM prose only fires on the button (or first load) so live edits never burn quota.
extra_cols = [c for c in grid.columns if c not in LABEL_TO_NAME and c != "Team"]
teams, extras, cur_signals = [], {}, {}
for _, row in grid.iterrows():
    team_cell = row.get("Team")
    if pd.isna(team_cell) or not str(team_cell).strip():
        continue
    team = str(team_cell).strip()
    raw = {}
    for lbl in SIGNAL_LABELS:
        if lbl in grid.columns and pd.notna(row.get(lbl)):
            cell = row[lbl]
            # A blank cell is already excluded by pd.notna above. A present-but-non-
            # numeric cell ("TBD", "n/a") is treated as "not provided" — omit it, don't
            # coerce to 0 (a phantom 0 would wrongly fire "only 0% complete").
            if isinstance(cell, str) and not cell.strip():
                continue
            try:
                raw[LABEL_TO_NAME[lbl]] = float(cell)
            except (TypeError, ValueError):
                continue
    sig = validate_signals(raw, RB)
    teams.append((team, sig))
    cur_signals[team] = sig
    extras[team] = {c: ("" if pd.isna(row.get(c)) else str(row.get(c))) for c in extra_cols}

if not teams:
    st.warning("Add at least one team to the grid above.")
    st.stop()

roll = evaluate_program(teams, RB)
st.session_state["_curcolor"] = {v.team: v.color for v in roll.teams}

# Use the live LLM only when the button was clicked (or the very first load); otherwise
# the offline writer keeps the live-updating view instant and quota-safe.
first_load = "generated_once" not in st.session_state
use_live = cfg_preview.live and (regen or first_load)
cfg = cfg_preview if use_live else _OFFLINE_CFG
with st.spinner("Writing your report…" if use_live else ""):
    out = generate_formats(roll, cfg, extras=extras, extra_names=extra_cols, context=context)
st.session_state["generated_once"] = True
if use_live and out["used_live"]:
    st.session_state["live_runs"] = st.session_state.get("live_runs", 0) + 1
    _c = _live_counter(); _c["count"] += 1

# =============================== PROGRAM STATUS (banner) ===============================
st.markdown("#### 2. Program status")
driver = next((v.team for v in roll.teams if v.color == "Red"),
              next((v.team for v in roll.teams if v.color == "Amber"), None))
lead = f"{EMOJI[roll.program_color]} PROGRAM: {roll.program_color.upper()}"
if driver:
    lead += f" — driven by {driver}"
st.markdown(f"<div class='banner b-{roll.program_color}'>{lead}</div>", unsafe_allow_html=True)
st.caption("Program color = the worst team's color. Per-team badges below show what changed since your "
           "last edit this session.")
with st.container(border=True):
    st.markdown("**How the color is decided** — a fixed rule reads the numbers: "
                "🔴 **Red** if any critical issue, 5+ days behind, or 3+ blockers · "
                "🟡 **Amber** if 2+ days behind, any blocker, or 20% complete or less · "
                "🟢 **Green** otherwise. Calculated, not guessed by AI — the same every time. "
                "Extra columns you add show in the report but don't change the color.")

# =============================== OUTPUTS ===============================
st.markdown("#### 3. Copy your update")
st.caption(f"Prose by: {src}. Colors are deterministic — identical with a key or without one.")

# Executive summary
with st.container(border=True):
    st.markdown("**Executive summary**")
    st.markdown(out["exec_summary"])
    _copy_button(out["exec_summary"].replace("**", ""), "exec")   # plain text for paste

# Status table (rendered) + copy markdown
with st.container(border=True):
    st.markdown("**Status table**")
    st.markdown(out["table"])
    with st.expander("Copy as Markdown"):
        st.code(out["table"], language="markdown")

# Per-team paragraphs (with delta + faithfulness pass-state)
with st.container(border=True):
    st.markdown("**Per-team paragraphs**")
    para_lines = []
    for v in roll.teams:
        ok = not narrative_contradicts(v.color, v.narrative)
        badge = ("<span class='delta down'>✓ matches engine color</span>" if ok
                 else "<span class='delta up'>⚠ contradicts engine — flagged</span>")
        delta = _delta_badge(v.team, cur_signals[v.team])
        team_s, narr_s = html.escape(v.team), html.escape(v.narrative)   # user input -> escape
        st.markdown(
            f"<div class='card'><span class='pill {v.color}'>{EMOJI[v.color]} {v.color}</span> "
            f"<b>{team_s}</b> — {narr_s}<br>"
            f"<span class='note'>{delta} &nbsp;·&nbsp; {badge}</span></div>",
            unsafe_allow_html=True)
        para_lines.append(f"{EMOJI[v.color]} {v.team} — {v.narrative}")
    _copy_button("\n\n".join(para_lines), "paras")

# Slack post — show it as preformatted so Slack's *bold* / • markers stay literal for pasting
with st.container(border=True):
    st.markdown("**Slack post** — paste straight into Slack (uses Slack's own `*bold*` formatting)")
    st.code(out["bullets"], language=None)   # st.code has its own copy button; keeps * literal

# remember this run for next-run deltas
st.session_state["prev_signals"] = cur_signals
st.session_state["prev_colors"] = {v.team: v.color for v in roll.teams}

# =============================== HOW IT WORKS ===============================
st.divider()
with st.expander("How it works — why the color is trustworthy"):
    st.markdown("""
The number that matters on a status review is the **color**. Letting an AI *decide* it is risky — it can't
be audited and it drifts. So StatusForge splits the job:

- **A fixed rulebook owns the color.** Red/Amber/Green is computed from your numbers by a small rule set
  ([`rulebooks/program.yaml`](https://github.com/singhalpooja9/StatusForge/blob/main/rulebooks/program.yaml)) —
  data, not code, no AI in the loop. Same numbers → same color, every time.
- **The AI only writes the words.** It's handed the color + the reasons and may only phrase them; a check
  flags any sentence that contradicts the color (shown as ✓ / ⚠ above).

Point it at a different domain by editing the rulebook (a YAML file) — the repo ships a marketing-launch
rulebook as a second worked example.
""")

# =============================== IS IT ACCURATE (honest eval) ===============================
with st.expander("Is it accurate? — how the color rule was tested"):
    st.markdown("The interesting question isn't *is the rule accurate* — a rule is exact by definition. "
                "It's **does the rule agree with human judgment, and where doesn't it?** Two honest layers:")
    st.markdown("**1. The engine is deterministic — same numbers, same color, always.** Given signals, the "
                "color is a pure function of the rulebook. There is nothing to drift; you can re-derive any "
                "verdict by hand from `program.yaml`.")
    st.markdown("**2. Where it disagrees with a human, that's a threshold *choice*, not a bug.** On a "
                "marketing gold set the rule matched the human on ~11 of 16 teams (**danger rate 0.33** — "
                "some truly-Red teams the rule called Amber). Checking each miss: the *numbers were extracted "
                "correctly* — the gaps are places where the shipped thresholds (e.g. *2 channels blocked → "
                "Red*) don't match how this particular labeler weighed things. That's the point of a **rulebook "
                "you edit**: the disagreement is visible and tunable in YAML, not hidden inside a model. "
                "(In the software domain, by contrast, the misses are the free-text *reader* — which is why "
                "the grid lets you correct every number before the engine rules.)")
    try:
        st.image("docs/calibration_marketing.png", width="stretch",
                 caption="Marketing domain: rule-vs-human threshold disagreements, extraction correct.")
    except Exception:
        st.caption("run `python scripts/run_calibration.py --domain marketing`")
    st.caption("Small example sets → wide confidence intervals; this demonstrates the method, not a "
               "production benchmark.")

st.divider()
st.caption("The color is computed, never guessed. Part of *The Lab* → singhalpooja.com")
