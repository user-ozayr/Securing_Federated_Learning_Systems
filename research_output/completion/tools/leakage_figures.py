"""Figures and a Markdown table for the E6 update-leakage study.

    python research_output/completion/tools/leakage_figures.py \
        research_output/completion/experiments/leakage/evaluation
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import ticker

VIEWS = {  # fixed colour per view, independent of plotting order
    "individual": ("FedAvg: individual update", "#2a78d6"),
    "secure_aggregate": ("SPDZ2k: aggregate of 4 clients", "#eb6834"),
}
STATES = {"initial": "untrained model", "trained": "after one epoch"}
ATTACKS = {  # attack: (panel title, metric, axis label)
    "optimisation": ("Optimisation inversion, CompactCNN", "ssim", "SSIM"),
    "fc_features": ("Analytic feature read-out, CompactCNN", "feature_cosine", "cosine similarity"),
    "fc_input": ("Analytic input read-out, probe MLP", "ssim", "SSIM"),
}
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def leakage_figure(summary: pd.DataFrame, out: Path) -> None:
    states = [s for s in STATES if s in set(summary.model_state)]
    attacks = [a for a in ATTACKS if a in set(summary.attack)]
    fig, axes = plt.subplots(len(states), len(attacks), figsize=(3.6 * len(attacks), 2.9 * len(states)),
                             sharex=True, sharey=True, squeeze=False)
    for r, state in enumerate(states):
        for c, attack in enumerate(attacks):
            title, metric, ylabel = ATTACKS[attack]
            ax = axes[r][c]
            data = summary[(summary.attack == attack) & (summary.model_state == state)
                           & (summary.metric == metric)]
            ends = {}
            for view, (label, colour) in VIEWS.items():
                rows = data[data.view == view].sort_values("batch_size")
                if rows.empty:
                    continue
                x, y = rows.batch_size.to_numpy(), rows["mean"].to_numpy()
                err = np.vstack([y - rows.ci95_lower.to_numpy(), rows.ci95_upper.to_numpy() - y])
                ax.errorbar(x, y, yerr=np.nan_to_num(np.clip(err, 0, None)), color=colour,
                            linewidth=2, marker="o", markersize=5, capsize=3, label=label)
                ends[view] = (x[-1], y[-1])
            # end labels; pushed apart vertically when the two lines finish close together
            close = len(ends) == 2 and abs(ends["individual"][1] - ends["secure_aggregate"][1]) < 0.06
            top = max(ends, key=lambda v: ends[v][1]) if ends else None
            for view, (x_end, y_end) in ends.items():
                dy = (5 if view == top else -5) if close else 0
                ax.annotate(f"{y_end:.2f}", (x_end, y_end), xytext=(6, dy),
                            textcoords="offset points", va="center", fontsize=7, color=MUTED)
            ax.set_xscale("log", base=2)
            ax.set_xticks([1, 2, 4, 8])
            ax.xaxis.set_major_formatter(ticker.ScalarFormatter())
            ax.set_xlim(0.8, 11)
            ax.set_ylim(0, 1.05)
            ax.grid(axis="y", color=GRID, linewidth=0.8)
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            ax.tick_params(colors=MUTED, labelsize=8)
            if r == 0:
                ax.set_title(title, fontsize=9, color=INK)
            if r == len(states) - 1:
                ax.set_xlabel("images per client batch (B)", fontsize=8, color=MUTED)
            if c == 0:
                ax.set_ylabel(f"{STATES[state]}\n{ylabel}", fontsize=8, color=MUTED)
            elif attack == "fc_features":
                ax.set_ylabel(ylabel, fontsize=8, color=MUTED)
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=2, frameon=False, fontsize=8)
    fig.suptitle("E6: reconstruction quality of the target client's images (mean, 95 % CI, 8 trials)",
                 fontsize=10, color=INK)
    fig.tight_layout(rect=(0, 0.06, 1, 0.97))
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    plt.close(fig)


def examples_figure(npz: Path, out: Path, state: str, batch: int) -> None:
    examples = np.load(npz)
    prefix = f"{state}__b{batch}__"
    rows = [("truth", "original")] + [
        (f"{attack}__{view}", f"{ATTACKS[attack][0].split(',')[0]}\n{VIEWS[view][0].split(':')[0]}")
        for attack in ("optimisation", "fc_input") for view in VIEWS]
    rows = [(key, label) for key, label in rows if prefix + key in examples]
    columns = examples[prefix + "truth"].shape[0]
    fig, axes = plt.subplots(len(rows), columns,
                             figsize=(max(1.25 * columns + 1.6, 4.2), 1.25 * len(rows) + 0.4),
                             squeeze=False)
    for r, (key, label) in enumerate(rows):
        images = examples[prefix + key]
        for c in range(columns):
            ax = axes[r][c]
            ax.imshow(images[c, 0], cmap="gray", vmin=0, vmax=1)
            ax.set_xticks([])
            ax.set_yticks([])
            if c == 0:
                ax.set_ylabel(label, fontsize=7, color=MUTED, rotation=0, ha="right", va="center")
    fig.suptitle(f"Target client's images and best matches\n{STATES[state]}, B = {batch}",
                 fontsize=9, color=INK)
    fig.tight_layout()
    fig.savefig(out, dpi=200, facecolor=SURFACE)
    plt.close(fig)


def markdown_table(summary: pd.DataFrame) -> str:
    lines = ["| Attack | Model | B | View | Metric | Mean | 95 % CI |",
             "|---|---|---:|---|---|---:|---|"]
    for attack, (_, metric, _) in ATTACKS.items():
        rows = summary[(summary.attack == attack) & (summary.metric == metric)]
        for _, r in rows.sort_values(["model_state", "batch_size", "view"]).iterrows():
            ci = (f"{r.ci95_lower:.3f}–{r.ci95_upper:.3f}" if np.isfinite(r.ci95_lower) else "–")
            lines.append(f"| {attack} | {r.model_state} | {int(r.batch_size)} | {r.view} | {metric} "
                         f"| {r['mean']:.3f} | {ci} |")
    labels = summary[(summary.attack == "optimisation") & (summary.metric.isin(
        ["label_precision", "label_recall"]))]
    lines += ["", "Label read-out from the output-bias update (target client's labels):", "",
              "| Model | B | View | Precision | Recall |", "|---|---:|---|---:|---:|"]
    wide = labels.pivot_table(index=["model_state", "batch_size", "view"], columns="metric",
                              values="mean").reset_index()
    for _, r in wide.iterrows():
        lines.append(f"| {r.model_state} | {int(r.batch_size)} | {r.view} | "
                     f"{r.label_precision:.2f} | {r.label_recall:.2f} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    folder = Path(sys.argv[1])
    summary = pd.read_csv(folder / "leakage_summary.csv")
    leakage_figure(summary, folder / "leakage_quality.png")
    for state in STATES:
        for batch in (1, 4):
            if (folder / "leakage_examples.npz").exists():
                examples_figure(folder / "leakage_examples.npz",
                                folder / f"leakage_examples_{state}_b{batch}.png", state, batch)
    table = markdown_table(summary)
    (folder / "leakage_table.md").write_text(table, encoding="utf-8")
    print(table)


if __name__ == "__main__":
    main()
