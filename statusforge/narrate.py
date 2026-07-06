"""Narrator: turn an engine Verdict into grounded prose.

The narrator is handed the color + the reasons the engine already computed; it may
only phrase them, never change them. A faithfulness check (calibration.py) verifies
the prose never claims a different health level.

Offline builds the narrative deterministically from the reasons (and is the silent
fallback when a live call fails). The real path asks an LLM to phrase those same
reasons, with the color pinned. On ANY real-call failure we fall back to offline —
so the demo never breaks on a rate-limit or outage.
"""

from __future__ import annotations

from .engine import Verdict, ProgramRollup
from .extract import LLMConfig, OFFLINE


def _english_join(items: list[str]) -> str:
    """Join reason fragments as a human would say them, not with semicolons.
    []->''  ['a']->'a'  ['a','b']->'a and b'  ['a','b','c']->'a, b, and c'."""
    items = [i.strip().rstrip(".") for i in items if i and i.strip()]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _note_of(extras: dict[str, dict] | None, team: str) -> str:
    return ((extras or {}).get(team, {}) or {}).get("Notes", "").strip().rstrip(".")


def _mock_narrate(v: Verdict, note: str = "") -> str:
    """Offline narrative for one team — one human status sentence, not a label dump.

    Does NOT lead with the team name: callers (cards, paragraphs) render the team
    label themselves, so leading with it here would double it ('Checkout — Checkout
    — At risk…'). The tier word ('At risk'/'Watch'/'On track') is deliberate — it's a
    level the faithfulness checker can verify against the engine color — but it's
    joined to the facts with a colon so the whole thing reads as ONE sentence, not
    two clipped fragments ('At risk. 2 critical issues open.').

    SHAPE (grammatical for any input):
      * Red / Amber:  '{tier}: {reasons in English}{ (human note) }.'
                      reasons read as one clause ('A and B'), never a ';' list; the
                      team's Note is folded in parenthetically as supporting color
                      (same convention as the exec brief), omitted when there is none.
      * Green:        '{tier}: {note}.'  — the Note carries the good news ('auth revamp
                      shipped'); with no note we fall back to the honest, if plainer,
                      'all signals within thresholds'."""
    lead = {"Red": "At risk", "Amber": "Watch", "Green": "On track"}[v.color]
    note = (note or "").strip().rstrip(".")
    if v.color == "Green":
        return f"{lead}: {note or 'all signals within thresholds'}."
    reasons = _english_join(v.reasons) or "all signals within thresholds"
    tail = f" ({note})" if note else ""
    return f"{lead}: {reasons}{tail}."


_NARRATE_INSTRUCTIONS = (
    "You write one crisp status sentence for a program review. You are GIVEN the "
    "health color, the exact reasons a deterministic engine assigned it, and an "
    "optional human NOTE. Explain those reasons plainly and, if a note is given, work "
    "it in as supporting context. RULES: (1) never state or imply a different health "
    "level than the given color; (2) never introduce a metric not in the given "
    "reasons; (3) use the note only for color/context, never to change the facts; "
    "(4) one or two sentences, factual, no hype.")


def _real_narrate(v: Verdict, cfg: LLMConfig, note: str = "") -> str:
    import litellm
    litellm.suppress_debug_info = True
    note_line = f"\nHUMAN NOTE (context only): {note.strip()}" if note and note.strip() else ""
    resp = litellm.completion(
        model=cfg.model, api_key=cfg.api_key,
        messages=[
            {"role": "system", "content": _NARRATE_INSTRUCTIONS},
            {"role": "user", "content": (
                f"TEAM: {v.team}\nCOLOR (fixed): {v.color}\n"
                f"REASONS (only use these): {v.reasons}{note_line}")},
        ],
        temperature=0.2, max_tokens=120,
    )
    return resp["choices"][0]["message"]["content"].strip()


def narrate(v: Verdict, cfg: LLMConfig | None = None, note: str = "") -> tuple[str, bool]:
    """Return (narrative, used_live). Falls back to offline prose on any live failure.
    `note` is the team's optional human Note, woven into either path as context."""
    cfg = cfg or OFFLINE
    if not cfg.live:
        return _mock_narrate(v, note), False
    try:
        return _real_narrate(v, cfg, note), True
    except Exception:
        return _mock_narrate(v, note), False   # silent fallback — demo never breaks


EMOJI = {"Red": "🔴", "Amber": "🟡", "Green": "🟢", "": "⚪"}


def _md_cell(text) -> str:
    """Make a value safe inside a Markdown table cell: escape pipes, flatten newlines,
    show an em-dash for blanks so the column never looks broken or empty."""
    s = "" if text is None else str(text).strip()
    if not s or s.lower() == "nan":
        return "—"
    return s.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _fmt_table(roll: ProgramRollup, extras: dict[str, dict] | None = None,
               extra_names: list[str] | None = None) -> str:
    """Markdown RAG table (deterministic — no LLM). `extras` maps team -> {col: value}
    for any non-signal columns (Notes + user-added), placed after Why. Notes is pulled
    to the front of the extras so it reads as the natural context column."""
    extras = extras or {}
    extra_names = list(extra_names or [])
    # Ensure Notes leads the extra columns if present.
    if "Notes" in extra_names:
        extra_names = ["Notes"] + [c for c in extra_names if c != "Notes"]

    header = ["Team", "Status", "Why", *extra_names]
    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join(["---"] * len(header)) + "|"]
    for v in roll.teams:
        # Green teams show a human "On track", not the engine's internal reason string.
        why = "On track" if v.color == "Green" else "; ".join(v.reasons)
        cells = [_md_cell(v.team), f"{EMOJI[v.color]} {v.color or 'n/a'}", _md_cell(why)]
        for name in extra_names:
            cells.append(_md_cell(extras.get(v.team, {}).get(name, "")))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _fmt_bullets(roll: ProgramRollup, context: str = "",
                 extras: dict[str, dict] | None = None) -> str:
    """A real Slack status post (deterministic — no LLM).

    Uses Slack-native formatting: *bold* (single asterisks, not Markdown **) and
    • bullets, with literal Unicode emoji throughout (no :shortcodes: — mixing the
    two forms is the classic auto-generated tell). Structure a human would post:
    header + TL;DR + teams grouped by severity + folded-in Notes + a concrete ask
    that names every red team.
    """
    reds = [v for v in roll.teams if v.color == "Red"]
    ambers = [v for v in roll.teams if v.color == "Amber"]
    greens = [v for v in roll.teams if v.color == "Green"]
    driver = reds[0].team if reds else (ambers[0].team if ambers else None)

    lines = [f"{EMOJI[roll.program_color]} *Weekly status — Program {roll.program_color.upper()}*"]
    if context.strip():
        lines.append(f"_{context.strip()}_")

    tldr = f"*TL;DR:* {len(reds)} at risk, {len(ambers)} watch, {len(greens)} on track."
    if driver:
        tldr += f" Biggest risk: *{driver}*."
    lines.append(tldr)

    def bullet(v):
        why = _english_join(v.reasons) if v.color else ""
        note = _note_of(extras, v.team)
        tail = f" — {why}" if why else ""
        if note:
            tail += f" ({note})" if why else f" — {note}"
        return f"{EMOJI[v.color]} *{v.team}*{tail}"

    if reds:
        lines.append("\n*At risk*")
        lines += [f"• {bullet(v)}" for v in reds]
    if ambers:
        lines.append("\n*Watch*")
        lines += [f"• {bullet(v)}" for v in ambers]
    if greens:
        lines.append("\n*On track:* " + ", ".join(v.team for v in greens))

    # Ask names every red team (a real TPM wouldn't leave one out), joined naturally.
    if reds:
        names = _english_join([f"*{v.team}*" for v in reds])
        lines.append(f"\n*Ask:* unblock {names} this week.")
    return "\n".join(lines)


def _team_facts(roll: ProgramRollup, extras: dict[str, dict] | None) -> str:
    """One line per non-green team: color, the rule reasons, and its Notes (if any)."""
    extras = extras or {}
    rows = []
    for v in roll.teams:
        if v.color == "Green":
            continue
        note = (extras.get(v.team, {}) or {}).get("Notes", "").strip()
        line = f"{v.team} ({v.color}): {', '.join(v.reasons)}"
        if note:
            line += f" — note: {note}"
        rows.append(line)
    return "; ".join(rows) or "all teams on track"


def _exec_summary(roll: ProgramRollup, cfg: LLMConfig, *, context: str = "",
                  extras: dict[str, dict] | None = None) -> tuple[str, bool]:
    """An executive brief in Amazon BLUF style. LLM if live, else a structured template.
    `context` (optional) is the program's real business context; `extras` carries Notes.

    OFFLINE TEMPLATE RULE (must read like a leader wrote it, never a label dump). The
    brief is a fixed skeleton of *sentences*, each grammatical for any input:
      1. Bold BOTTOM LINE — overall color + the single team driving it.
      2. The STAKES / 'so what' — the user's own context verbatim as its own sentence
         (never invented; omitted if none given).
      3. The DRIVER, spelled out — its reasons in plain English ('A and B'), with its
         Note woven in parenthetically.
      4. Any OTHER red teams, one short sentence each.
      5. A single 'Meanwhile…' sentence folding the ambers-to-watch and the on-track
         teams together (so greens get one clause, not their own label line).
      6. One crisp ASK, tied to the driver.
    Reasons are always joined as English ('A and B', 'A, B, and C') — never 'A; B; C'."""
    reds = [v for v in roll.teams if v.color == "Red"]
    ambers = [v for v in roll.teams if v.color == "Amber"]
    greens = [v for v in roll.teams if v.color == "Green"]
    n = len(roll.teams)
    facts = _team_facts(roll, extras)

    if not cfg.live:
        def clause(v: Verdict) -> str:
            """This team's reasons as one English phrase, with its Note woven in."""
            body = _english_join(v.reasons)
            note = _note_of(extras, v.team)
            return f"{body} ({note})" if note else body

        C = roll.program_color.upper()
        driver = reds[0] if reds else (ambers[0] if ambers else None)

        # (1) bottom line
        parts = [f"**The program is {C}, driven by {driver.team}.**" if driver
                 else f"**The program is {C} — all teams on track.**"]
        # (2) the stakes, straight from the user's context (never invented)
        if context.strip():
            c = context.strip().rstrip(".")
            parts.append(c[:1].upper() + c[1:] + ".")
        # (3) the driver, spelled out, + (4) any other reds
        if reds:
            parts.append(f"{reds[0].team} is the biggest risk: {clause(reds[0])}.")
            parts += [f"{v.team} is also red — {clause(v)}." for v in reds[1:]]
        elif ambers:
            parts.append(f"{ambers[0].team} is the one to watch: {clause(ambers[0])}.")
        # (5) one 'Meanwhile' sentence: leftover ambers to watch + greens on track.
        # Skipped entirely when everything is green — the bottom line already said it,
        # so we don't repeat "on track".
        watch_more = ambers if reds else ambers[1:]     # ambers not already named above
        if driver:
            tail = []
            if watch_more:
                tail.append("keep an eye on " +
                            _english_join([f"{v.team} ({_english_join(v.reasons)})" for v in watch_more]))
            if greens:
                verb = "is" if len(greens) == 1 else "are"
                tail.append(f"{_english_join([v.team for v in greens])} {verb} on track")
            if tail:
                parts.append("Meanwhile, " + _english_join(tail) + ".")
        # (6) the ask, tied to the driver
        if reds:
            parts.append(f"Ask: dedicated help to unblock {reds[0].team} this week.")
        elif ambers:
            parts.append(f"Ask: hold {ambers[0].team} on the weekly watch until the slip closes.")
        return " ".join(parts), False

    try:
        import litellm
        litellm.suppress_debug_info = True
        ctx = f"\nPROGRAM CONTEXT (use for impact + the ask): {context.strip()}" if context.strip() else ""
        resp = litellm.completion(
            model=cfg.model, api_key=cfg.api_key, temperature=0.3, max_tokens=340,
            messages=[
                {"role": "system", "content":
                 "You are a senior technical program manager writing a tight EXECUTIVE STATUS BRIEF for "
                 "leadership, in the Amazon style: BLUF, declarative, no hedging, no filler.\n"
                 "Structure (4-6 sentences, no bullet list):\n"
                 "1. First sentence = the overall status AND its single biggest driver.\n"
                 "2. The 'so what': tie the at-risk work to its business impact — but ONLY using the given "
                 "context/notes; if none is given, state the delivery risk plainly, do NOT invent impact.\n"
                 "3. Secondary risks / what to watch, briefly.\n"
                 "4. The ASK: the specific decision or help needed this week.\n"
                 "HARD RULES: never state a different overall status than the given color; use ONLY the given "
                 "facts, notes, and context; invent no metrics, dates, or impact; confident and concise."},
                {"role": "user", "content":
                 f"PROGRAM COLOR (fixed): {roll.program_color}\n"
                 f"TEAMS: {n} ({len(reds)} red, {len(ambers)} amber, {len(greens)} green)\n"
                 f"AT-RISK / WATCH (color, reasons, notes): {facts}\n"
                 f"ON TRACK: {', '.join(v.team for v in greens) or 'none'}{ctx}"},
            ])
        return resp["choices"][0]["message"]["content"].strip(), True
    except Exception:
        return _exec_summary(roll, OFFLINE, context=context, extras=extras)[0], False


def _fmt_paragraphs(roll: ProgramRollup) -> str:
    """Per-team paragraphs (uses each verdict's narrative, already set)."""
    return "\n\n".join(f"**{EMOJI[v.color]} {v.team}** — {v.narrative}" for v in roll.teams)


def generate_formats(roll: ProgramRollup, cfg: LLMConfig | None = None, *,
                     extras: dict[str, dict] | None = None,
                     extra_names: list[str] | None = None,
                     context: str = "") -> dict:
    """Produce all copy-paste status formats from one rollup.
    `extras`/`extra_names` carry non-signal columns (Notes + custom) into the table;
    `context` is the optional program business context that grounds the exec brief.
    Returns {exec_summary, table, paragraphs, bullets, used_live, rollup}."""
    cfg = cfg or OFFLINE
    roll = narrate_rollup(roll, cfg, extras=extras)   # sets per-team narratives + summary
    exec_text, live = _exec_summary(roll, cfg, context=context, extras=extras)
    return {
        "exec_summary": exec_text,
        "table": _fmt_table(roll, extras, extra_names),
        "paragraphs": _fmt_paragraphs(roll),
        "bullets": _fmt_bullets(roll, context, extras),
        "used_live": live,
        "rollup": roll,
    }


def narrate_rollup(roll: ProgramRollup, cfg: LLMConfig | None = None,
                   extras: dict[str, dict] | None = None) -> ProgramRollup:
    """Attach narratives + a program summary. Sets roll.summary; leaves a flag on
    each verdict-less; caller can inspect if any live call fell back. `extras` carries
    each team's Notes so the narrator can weave it in (same source as the table/brief)."""
    cfg = cfg or OFFLINE
    for v in roll.teams:
        v.narrative, _ = narrate(v, cfg, note=_note_of(extras, v.team))
    reds = [v.team for v in roll.teams if v.color == "Red"]
    ambers = [v.team for v in roll.teams if v.color == "Amber"]
    if reds:
        noun = "team" if len(reds) == 1 else "teams"
        roll.summary = f"Program {roll.program_color}: {len(reds)} {noun} at risk — {', '.join(reds)}."
    elif ambers:
        roll.summary = f"Program {roll.program_color}: watch {', '.join(ambers)}."
    else:
        roll.summary = f"Program {roll.program_color}: all teams on track."
    return roll
