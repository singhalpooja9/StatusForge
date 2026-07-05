"""Run the full pipeline over the gold set and emit the calibration report + chart.

    python scripts/run_calibration.py                 # offline mock (CI-safe)
    python scripts/run_calibration.py --provider auto # real model if a key is set

Pipeline per team: raw text -> extract signals -> deterministic engine color ->
narrate. Then compare engine color vs human label (ordinal, cost-asymmetric) and
measure narrative faithfulness. Writes docs/calibration.md + docs/calibration.png.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the package importable when run as `python scripts/run_calibration.py`
# from the repo root (no PYTHONPATH needed — works in CI and locally).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from statusforge.dataset import load_gold
from statusforge.extract import extract_signals, LLMConfig, OFFLINE
from statusforge.engine import evaluate_team
from statusforge.narrate import narrate
from statusforge.calibration import calibrate_colors, faithfulness_rate, CLASSES
from statusforge.providers import default_model

DOCS = Path(__file__).resolve().parent.parent / "docs"


def main() -> None:
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="mock",
                    help="'mock' (offline, default) or 'auto' (use an env key if present)")
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    # Offline by default. For a real run, --provider auto reads a key from the env
    # (this is the DEV/CI path; the app uses a per-session key, never the env).
    cfg = OFFLINE
    if args.provider == "auto":
        key = (os.getenv("GROQ_API_KEY") or os.getenv("OPENROUTER_API_KEY")
               or os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
               or os.getenv("GEMINI_API_KEY") or "")
        model = args.model or default_model("Groq (free)")
        cfg = LLMConfig(model=model, api_key=key)

    gold = load_gold()
    y_true, y_pred, colors, narratives = [], [], [], []
    for row in gold:
        signals = extract_signals(row["team"], row["text"], cfg)
        verdict = evaluate_team(signals)
        verdict.narrative = narrate(verdict, cfg)
        y_true.append(row["human_color"])
        y_pred.append(verdict.color)
        colors.append(verdict.color)
        narratives.append(verdict.narrative)

    report = calibrate_colors(y_true, y_pred)
    faith = faithfulness_rate(colors, narratives)
    print(report.summary())
    print(f"narrative faithfulness = {faith:.2f} (1.0 = no prose contradicts its engine color)")

    DOCS.mkdir(exist_ok=True)
    _write_md(report, faith, gold, y_pred)
    _maybe_plot(report, faith)


def _write_md(report, faith, gold, y_pred) -> None:
    lines = [
        "# StatusForge Calibration", "",
        "> Engine color vs human label on the synthetic gold set. The engine's color is",
        "> computed by deterministic rules; the LLM only narrates. Offline mock unless a",
        "> provider key was set.", "",
        "## Headline", "```", report.summary(),
        f"narrative faithfulness = {faith:.2f}", "```", "",
        "**Read honestly:** small gold set → wide CIs. The metric that matters most is the",
        "**danger rate** (truly-Red teams under-called) — it should be 0, and the narrative",
        "faithfulness should be 1.0 by construction (the LLM cannot change the color).", "",
        "## Per-team", "", "| Team | Human | Engine |", "|---|---|---|",
    ]
    for row, pred in zip(gold, y_pred):
        mark = "" if row["human_color"] == pred else " ⚠️"
        lines.append(f"| {row['team']} | {row['human_color']} | {pred}{mark} |")
    (DOCS / "calibration.md").write_text("\n".join(lines) + "\n")
    print(f"\nwrote {DOCS / 'calibration.md'}")


def _maybe_plot(report, faith) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("(matplotlib missing — skipping chart)")
        return
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    fig.patch.set_facecolor("#0e1320")
    m = report.confusion
    ax1.imshow(m, cmap="magma")
    ax1.set_xticks(range(3), [f"pred {c}" for c in CLASSES], color="#e8edf6", fontsize=8)
    ax1.set_yticks(range(3), [f"true {c}" for c in CLASSES], color="#e8edf6", fontsize=8)
    for i in range(3):
        for j in range(3):
            ax1.text(j, i, str(m[i][j]), ha="center", va="center",
                     color="white", fontsize=15, fontweight="bold")
    ax1.set_title("Engine vs human (3-class)", color="#5eead4")
    names = ["exact\nagreement", "quad.\nkappa", "danger\nrate", "narrative\nfaithful"]
    vals = [report.exact_agreement, report.quadratic_kappa, report.danger_rate, faith]
    cols = ["#5eead4", "#9b85ff", "#fbbf77", "#5eead4"]
    ax2.bar(names, vals, color=cols)
    ax2.set_ylim(0, 1.05)
    ax2.set_title(f"Metrics (n={report.n})", color="#5eead4")
    ax2.set_facecolor("#0e1320")
    ax2.tick_params(colors="#e8edf6")
    for sp in ax2.spines.values():
        sp.set_color("#243049")
    for i, v in enumerate(vals):
        ax2.text(i, v + 0.03, f"{v:.2f}", ha="center", color="#e8edf6", fontweight="bold")
    fig.tight_layout()
    out = DOCS / "calibration.png"
    fig.savefig(out, dpi=130, facecolor=fig.get_facecolor())
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
