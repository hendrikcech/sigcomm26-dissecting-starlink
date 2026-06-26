#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "matplotlib",
#     "numpy",
#     "pandas",
#     "tqdm",
#     "scipy",
#     "matplotlib",
# ]
# ///
"""
TCP CCA Comparison — Mann-Whitney U test

For each phase and direction, compute the mean goodput per run for every CCA,
then report Mann-Whitney U p-values and Cliff's delta for all pairwise
CCA combinations.
"""

import argparse
import os
import sys
from itertools import combinations

import numpy as np
import pandas as pd
from pandas.api.types import CategoricalDtype
from scipy import stats
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.backends.backend_pdf import PdfPages

import utils


# ---------------------------------------------------------------------------
# Parsing (adapted from tcp_cmp.py / fig-12-tcpri.py)
# ---------------------------------------------------------------------------

def parse_filename(path):
    """Parse tcp_dl_bbr1_12000.csv → {direction, cca, duration_ms, path}."""
    filename = os.path.basename(path)
    parts = filename.split("_")
    try:
        assert len(parts) == 4
        protocol = parts[0]
        if protocol == "emu-tcp":
            protocol = "tcp"
        duration_parts = parts[3].split(".")
        return dict(
            protocol=protocol,
            direction=parts[1],
            cca=parts[2],
            duration_ms=int(duration_parts[0]),
            path=path,
        )
    except Exception:
        print(f"Skipping invalid filename: {filename}")
        return None


def parse_tcp_csv(args):
    f, idx = args

    df = utils.parse_tcp_csv((f["path"], idx))
    if df is None:
        return None

    df["direction"] = f["direction"]
    df["cca"] = f["cca"]
    df["duration_ms"] = f["duration_ms"]

    return df


# ---------------------------------------------------------------------------
# Phases 
# ---------------------------------------------------------------------------

PHASE_NAMES = ["ss", "pre", "reconf", "post"]
PHASE_LABELS = dict(ss="Slow Start",
                    pre="Pre-Reconf.",
                    reconf="Reconf.",
                    post="Post-Reconf.")

def label_phases(df):
    phases = CategoricalDtype(categories=PHASE_NAMES, ordered=True)

    midpoint = pd.to_timedelta(df["duration_ms"] / 2, unit="ms")
    ts_rel = df["ts"] - midpoint  # timedelta

    ts_rel_ms = ts_rel.dt.total_seconds() * 1000

    df = df.copy()
    df["phase"] = pd.NA
    df.loc[ts_rel_ms < -5000, "phase"] = "ss"
    df.loc[(ts_rel_ms >= -5000) & (ts_rel_ms < -500), "phase"] = "pre"
    df.loc[(ts_rel_ms >= -500) & (ts_rel_ms < 2000), "phase"] = "reconf"
    df.loc[ts_rel_ms >= 2000, "phase"] = "post"
    df["phase"] = df["phase"].astype(phases)
    return df


# ---------------------------------------------------------------------------
# Goodput
# ---------------------------------------------------------------------------

def compute_per_run_mean_gput(df, groupby_cols):
    # Rolling goodput per sample
    idx_cols = groupby_cols + ["idx"]
    dfi = df.set_index(idx_cols)
    dfg = (
        dfi.groupby(level=list(range(len(idx_cols))), observed=True)
        .rolling(window="100ms", on="ts")[["tsDiffSec", "ThruBytesAckedDiff"]]
        .sum()
    )
    gput = dfg["ThruBytesAckedDiff"] / dfg["tsDiffSec"] * 8 / 1e6  # Mbps

    # Mean per run
    return gput.groupby(level=list(range(len(idx_cols))), observed=True).mean()


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def cliffs_delta(x, y):
    """
    Cliff's delta effect size.
      0  → complete overlap
     ±1  → no overlap
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    m, n = len(x), len(y)
    if m == 0 or n == 0:
        return np.nan
    more = sum(np.sum(xi > y) for xi in x)
    less = sum(np.sum(xi < y) for xi in x)
    return (more - less) / (m * n)


def cliffs_delta_magnitude(d):
    """Romano et al. (2006) thresholds."""
    d = abs(d)
    if d < 0.147:
        return "negligible"
    elif d < 0.33:
        return "small"
    elif d < 0.474:
        return "medium"
    else:
        return "large"


def pairwise_mannwhitney(gput_per_run, direction, phase):
    try:
        data = gput_per_run.loc[direction, phase]
    except KeyError:
        return []

    ccas = sorted(data.index.get_level_values("cca").unique())
    results = []

    for cca_a, cca_b in combinations(ccas, 2):
        try:
            vals_a = data.loc[cca_a].dropna().values
            vals_b = data.loc[cca_b].dropna().values
        except KeyError:
            continue

        if len(vals_a) < 2 or len(vals_b) < 2:
            continue

        stat = stats.mannwhitneyu(vals_a, vals_b, alternative="two-sided")
        delta = cliffs_delta(vals_a, vals_b)

        results.append(dict(
            direction=direction,
            phase=phase,
            cca_a=utils.cca_label(cca_a),
            cca_b=utils.cca_label(cca_b),
            n_a=len(vals_a),
            n_b=len(vals_b),
            mean_a=np.mean(vals_a),
            mean_b=np.mean(vals_b),
            median_a=np.median(vals_a),
            median_b=np.median(vals_b),
            U=stat.statistic,
            p=stat.pvalue,
            significant=stat.pvalue < 0.05,
            cliffs_delta=delta,
            effect_magnitude=cliffs_delta_magnitude(delta),
        ))

    return results


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

# CCA display order: model-based first, then loss-based
CCA_ORDER = ["BBRv1", "LeoCC", "SatPipe", "BBRv3", "Illinois", "CUBIC", "HyStart", "HyStart++", "SEARCH", "SUSS"]

def plot_heatmap(result_df, phase):
    """
    Plot a pairwise Cliff's delta heatmap matrix for each direction.
    Full matrix: color encodes Cliff's delta, text shows value + significance.
    Returns the figure.
    """
    directions = sorted(result_df.direction.unique())
    subset = result_df[result_df.phase == phase]
    if subset.empty:
        print(f"No data for phase '{phase}', skipping heatmap.")
        return None

    # Determine CCA order from the data, respecting CCA_ORDER
    all_ccas = set(subset.cca_a) | set(subset.cca_b)
    ccas = [c for c in CCA_ORDER if c in all_ccas]
    # Append any CCAs not in the predefined order
    ccas += sorted(all_ccas - set(ccas))
    n = len(ccas)

    # Diverging colormap: blue (A < B) — white (equal) — red (A > B)
    cmap = plt.cm.RdBu_r
    norm = mcolors.TwoSlopeNorm(vmin=-1, vcenter=0, vmax=1)

    fig, axes = plt.subplots(1, len(directions),
                             figsize=(utils.COLUMN_WIDTH * len(directions) + 0.5,
                                      utils.COLUMN_WIDTH),
                             squeeze=False,
                             layout="constrained")

    for ax_idx, direction in enumerate(directions):
        ax = axes[0, ax_idx]
        dir_data = subset[subset.direction == direction]

        # Build matrices
        delta_matrix = np.full((n, n), np.nan)
        p_matrix = np.ones((n, n))

        for _, row in dir_data.iterrows():
            i = ccas.index(row["cca_a"]) if row["cca_a"] in ccas else None
            j = ccas.index(row["cca_b"]) if row["cca_b"] in ccas else None
            if i is None or j is None:
                continue
            delta_matrix[i, j] = row["cliffs_delta"]
            delta_matrix[j, i] = -row["cliffs_delta"]
            p_matrix[i, j] = row["p"]
            p_matrix[j, i] = row["p"]

        # Plot lower triangle as colored cells
        for i in range(n):
            for j in range(n):
                if i == j:
                    # Diagonal: CCA label
                    continue
                if np.isnan(delta_matrix[i, j]):
                    continue

                d = delta_matrix[i, j]
                p = p_matrix[i, j]
                color = cmap(norm(d))

                ax.add_patch(plt.Rectangle((j, n - 1 - i), 1, 1,
                                           facecolor=color, edgecolor="white", lw=0.5))

                # Text: show delta value; star if significant
                if p < 0.05:
                    sig_marker = "*" if p >= 0.01 else ("**" if p >= 0.001 else "***")
                    text = f"{d:+.2f}\n{sig_marker}"
                else:
                    text = f"{d:+.2f}\nn.s."

                # Pick text color for readability
                text_color = "white" if abs(d) > 0.6 else "black"
                ax.text(j + 0.5, n - 1 - i + 0.5, text,
                        ha="center", va="center",
                        fontsize=5.5, color=text_color)

        # Axis formatting
        ax.set_xlim(0, n)
        ax.set_ylim(0, n)
        ax.set_xticks(np.arange(n) + 0.5)
        ax.set_xticklabels(ccas, rotation=45, ha="right", fontsize=7)
        ax.set_yticks(np.arange(n) + 0.5)
        ax.set_yticklabels(ccas[::-1], fontsize=7)
        ax.set_aspect("equal")
        ax.set_title(f"{direction.upper()} — Phase: {PHASE_LABELS[phase]}", fontsize=9)
        ax.grid(False)

    # Colorbar
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=axes.ravel().tolist(), shrink=0.6, pad=0.02)
    cbar.set_label("Cliff's δ  (row > col)", fontsize=8)

    return fig


def make_table(result_df, directions, phases):
    # --- Format output ---
    output_lines = []
    output_lines.append("=" * 100)
    output_lines.append("TCP CCA Pairwise Comparison — Mann-Whitney U Test (§4.6)")
    output_lines.append("=" * 100)

    for direction in directions:
        for phase in phases:
            subset = result_df[(result_df.direction == direction) & (result_df.phase == phase)]
            if subset.empty:
                continue

            output_lines.append("")
            output_lines.append(f"--- {direction.upper()} / Phase: {phase} ---")
            output_lines.append("")

            fmt = subset[[
                "cca_a", "cca_b", "n_a", "n_b",
                "mean_a", "mean_b", "median_a", "median_b",
                "U", "p", "significant", "cliffs_delta", "effect_magnitude",
            ]].to_string(index=False)
            output_lines.append(fmt)

    # --- Summary table for the paper (Phase 2 = pre-reconf, steady state) ---
    output_lines.append("")
    output_lines.append("=" * 100)
    output_lines.append("Summary: Phase 2 (pre-reconf) — for the paper appendix")
    output_lines.append("=" * 100)
    pre = result_df[result_df.phase == "pre"]
    if not pre.empty:
        summary = pre[["direction", "cca_a", "cca_b", "n_a", "n_b",
                        "mean_a", "mean_b", "p", "cliffs_delta", "effect_magnitude"]]
        output_lines.append(summary.to_string(index=False))

    return "\n".join(output_lines)



# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Mann-Whitney U test for pairwise TCP CCA goodput comparison")
    parser.add_argument("csvs", nargs="+", help="TCP csv files")
    parser.add_argument("-o", help="Output text file for results")
    parser.add_argument("-p", "--pdf", help="Plot PDF with pairwise heatmap matrices")
    parser.add_argument("--phases", nargs="*", default=PHASE_NAMES, help="Phases to test (default: all)")
    args = parser.parse_args()

    utils.set_plt_style(10)

    pd.set_option("display.max_rows", 600)
    pd.set_option("display.max_columns", 20)
    pd.set_option("display.width", 200)
    pd.set_option("display.float_format", lambda x: "%.4f" % x)

    # --- Parse ---
    files = [parse_filename(csv) for csv in sorted(args.csvs)]
    tcp_files = [f for f in files if f is not None and f["protocol"] == "tcp"]
    if not tcp_files:
        print("No valid TCP files found.", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing {len(tcp_files)} TCP files …")
    tcp_args = list(zip(tcp_files, range(len(tcp_files))))
    df = utils.parse_csvs(tcp_args, parse_tcp_csv, cores=12)

    if df is None or len(df) == 0:
        print("No data after parsing.", file=sys.stderr)
        sys.exit(1)

    print("Labelling phases …")
    df = label_phases(df)
    df = df.dropna(subset=["phase"])

    print("Computing per-run mean goodput ...")
    groupby_cols = ["direction", "phase", "cca"]
    gput_per_run = compute_per_run_mean_gput(df, groupby_cols)

    directions = sorted(gput_per_run.index.get_level_values("direction").unique())
    phases = [p for p in PHASE_NAMES if p in args.phases]

    print("Computing pairwise Mann-Whitney U tests ...")
    all_results = []
    for direction in directions:
        for phase in phases:
            all_results.extend(pairwise_mannwhitney(gput_per_run, direction, phase))

    if not all_results:
        print("No pairwise comparisons could be computed.", file=sys.stderr)
        sys.exit(1)

    result_df = pd.DataFrame(all_results)

    result_str = make_table(result_df, directions, phases)
    if args.o:
        with open(args.o, "w") as f:
            f.write(result_str)
            f.write("\n")
        print(f"\nResults written to {args.o}")
    else:
        print(result_str)

    # --- Heatmap PDF ---
    if args.pdf:
        print("\nGenerating heatmap plots …")
        with PdfPages(args.pdf) as pdf:
            for phase in phases:
                phase_data = result_df[result_df.phase == phase]
                if phase_data.empty:
                    continue
                fig = plot_heatmap(result_df, phase)
                if fig is not None:
                    pdf.savefig(fig, bbox_inches="tight", pad_inches=0.05)
                    plt.close(fig)
        print(f"Heatmap PDF saved to {args.pdf}")


if __name__ == "__main__":
    main()
