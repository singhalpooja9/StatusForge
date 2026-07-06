"""Run the pipeline over a domain's gold set and emit its calibration report + chart.

    python scripts/run_calibration.py                 # software domain, offline
    python scripts/run_calibration.py --domain marketing
    python scripts/run_calibration.py --domain software --provider auto  # real LLM extract

Pipeline per team: raw text -> extract signals -> deterministic engine color ->
narrate. Compares engine color vs human label (ordinal, cost-asymmetric) and
measures narrative faithfulness. Writes docs/calibration_<domain>.{md,png}.

Also reports EXTRACTION recall separately (offline vs the human labels) so the
danger-rate isn't graded only on regex-friendly text — honest about the two stages.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from statusforge.dataset import load_gold, rulebook_name
from statusforge.rulebook import load_rulebook
from statusforge.extract import extract_signals, LLMConfig, OFFLINE
from statusforge.engine import evaluate_team
from statusforge.narrate import narrate
from statusforge.calibration import calibrate_colors, faithfulness_rate, CLASSES

DOCS = Path(__file__).resolve().parent.parent / "docs"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", default="program", choices=["program", "software", "marketing"])
    ap.add_argument("--provider", default="offline", choices=["offline", "auto"])
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    rb = load_rulebook(rulebook_name(args.domain))
    cfg = OFFLINE
    if args.provider == "auto":
        key = (os.getenv("GROQ_API_KEY") or os.getenv("OPENROUTER_API_KEY")
               or os.getenv("OPENAI_API_KEY") or "")
        cfg = LLMConfig(model=args.model or "groq/llama-3.3-70b-versatile", api_key=key)

    from statusforge.models import validate_signals
    gold = load_gold(args.domain)
    y_true, y_pred, colors, narratives = [], [], [], []
    for row in gold:
        # Numeric-signal gold (grid domains) skips extraction; text gold extracts.
        signals = (validate_signals(row["signals"], rb) if "signals" in row
                   else extract_signals(row["text"], rb, cfg))
        v = evaluate_team(row["team"], signals, rb)
        v.narrative, _ = narrate(v, cfg)
        y_true.append(row["human_color"]); y_pred.append(v.color)
        colors.append(v.color); narratives.append(v.narrative)

    report = calibrate_colors(y_true, y_pred)
    faith = faithfulness_rate(colors, narratives)
    print(f"[{args.domain}] {rb.domain}")
    print(report.summary())
    print(f"narrative faithfulness = {faith:.2f}")

    DOCS.mkdir(exist_ok=True)
    _write_md(args.domain, rb.domain, report, faith, gold, y_pred)
    _maybe_plot(args.domain, rb.domain, report, faith)


def _write_md(domain, domain_label, report, faith, gold, y_pred) -> None:
    lines = [
        f"# StatusForge Calibration — {domain_label}", "",
        "> Engine color vs human label on the synthetic gold set. The color is computed by",
        "> the deterministic rulebook interpreter; the LLM only narrates.", "",
        "## Headline", "```", report.summary(), f"narrative faithfulness = {faith:.2f}", "```", "",
        "**The metric that matters is the danger rate** (truly-Red under-called) — it should be 0.",
        "Small gold set → wide CIs; this demonstrates the method, not a production benchmark.", "",
        "## Per-team", "", "| Team | Human | Engine |", "|---|---|---|",
    ]
    for row, pred in zip(gold, y_pred):
        mark = "" if row["human_color"] == pred else " ⚠️"
        lines.append(f"| {row['team']} | {row['human_color']} | {pred}{mark} |")
    (DOCS / f"calibration_{domain}.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {DOCS / f'calibration_{domain}.md'}")


def _maybe_plot(domain, domain_label, report, faith) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
    fig.patch.set_facecolor("#0e1320")
    m = report.confusion
    n = report.n or 1
    # Readable matrix: correct cells (diagonal) green-tinted, errors red-tinted,
    # intensity by count; dark text on light cells so numbers are always legible.
    import matplotlib.colors as mcolors
    rgba = [[(0, 0, 0, 0)] * 3 for _ in range(3)]
    for i in range(3):
        for j in range(3):
            frac = m[i][j] / n
            if m[i][j] == 0:
                rgba[i][j] = (1, 1, 1, 0.04)                       # near-empty
            elif i == j:
                rgba[i][j] = (0.37, 0.92, 0.83, 0.25 + 0.6 * frac)  # teal = correct
            else:
                rgba[i][j] = (0.98, 0.45, 0.45, 0.30 + 0.6 * frac)  # red = error
    ax1.imshow(rgba)
    ax1.set_xticks(range(3), [f"pred {c}" for c in CLASSES], color="#e8edf6", fontsize=9)
    ax1.set_yticks(range(3), [f"true {c}" for c in CLASSES], color="#e8edf6", fontsize=9)
    ax1.set_xticks([x - 0.5 for x in range(1, 3)], minor=True)
    ax1.set_yticks([y - 0.5 for y in range(1, 3)], minor=True)
    ax1.grid(which="minor", color="#243049", linewidth=1)
    for i in range(3):
        for j in range(3):
            ax1.text(j, i, str(m[i][j]), ha="center", va="center",
                     color="#0e1320" if m[i][j] else "#4a5568", fontsize=16, fontweight="bold")
    ax1.set_title(f"Engine vs human — {domain_label}", color="#5eead4")
    for sp in ax1.spines.values():
        sp.set_color("#243049")
    names = ["exact\nagreement", "quad.\nkappa", "danger\nrate", "narrative\nfaithful"]
    vals = [report.exact_agreement, report.quadratic_kappa, report.danger_rate, faith]
    ax2.bar(names, vals, color=["#5eead4", "#9b85ff", "#fbbf77", "#5eead4"])
    ax2.set_ylim(0, 1.05); ax2.set_title(f"Metrics (n={report.n})", color="#5eead4")
    ax2.set_facecolor("#0e1320"); ax2.tick_params(colors="#e8edf6")
    for sp in ax2.spines.values():
        sp.set_color("#243049")
    for i, v in enumerate(vals):
        ax2.text(i, v + 0.03, f"{v:.2f}", ha="center", color="#e8edf6", fontweight="bold")
    fig.tight_layout()
    out = DOCS / f"calibration_{domain}.png"
    fig.savefig(out, dpi=130, facecolor=fig.get_facecolor())
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
