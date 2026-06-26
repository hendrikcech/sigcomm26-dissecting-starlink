
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "matplotlib",
#     "numpy",
#     "pandas",
#     "tqdm",
#     "scipy"
# ]
# ///

import argparse
import os
import multiprocessing

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.backends.backend_pdf import PdfPages
from tqdm import tqdm

import utils

import importlib
tcpri = importlib.import_module("fig-12-tcpri")


grp_freq_ms = 100
metric = "SenderWindowSegs"
# metric = "UnackedSegs"

def group_tcp_cwnd(df):
    grp_idx = df\
        .set_index("ts_rel")\
        .groupby(["direction", "cca", "idx", pd.Grouper(freq=f"{grp_freq_ms}ms")])\
        .agg({ metric: "mean" })
    grp = grp_idx.reset_index().drop(columns=["idx"])\
                                    .groupby(["direction", "cca", "ts_rel"])\
                                    .agg(["mean", "median", "std", "count"])
    return grp

def group_tcp_losses(df):
    grp_idx = df.set_index("ts_rel")\
                .groupby(["direction", "cca", "idx", pd.Grouper(freq=f"100ms")])\
                .TotalRetransSegsDiff.sum()
    grp = grp_idx.reset_index().drop(columns=["idx"])\
                                    .groupby(["direction", "cca", "ts_rel"])\
                                    .agg(["mean", "median", "std", "count"])
    return grp


def plot_bak(grp_cwnd, grp_ssexit, grp_loss):
    fig, ax = plt.subplots(figsize=FIGSIZE, layout="constrained")
    ax.set_ylabel(f"cwnd [segments]")
    ax.set_xlabel(f"Time [ms]")
    ax.grid(visible=True, axis="y")
    ax.grid(visible=False, axis="x")

    ax2 = ax.twinx()
    ax2.set_ylabel(f"Losses [segments]")

    parts = []
    zorder_cwnd = 12
    zorder_axv = 11
    zorder_bar = 10
    bar_width = grp_freq_ms / len(grp_cwnd.index.levels[0])
    for i, cca in enumerate(list(grp_cwnd.index.levels[0])):
        color = utils.mpl_colors()[i]

        cwnd = grp_cwnd.loc[cca][metric]
        index = cwnd.index.total_seconds() * 1000
        cil, cih = utils.compute_ci(cwnd)
        parts.append(ax.plot(index, cwnd["mean"], color=color, zorder=zorder_cwnd,
                             label=utils.cca_label(cca), linewidth=0.8)[0])
        # ax.fill_between(index, cil, cih, color=color, alpha=0.2, edgecolor="white") # color=color,

        ssexit = grp_ssexit.loc[cca]
        ax.axvline(ssexit["ts"]["mean"], color=color, zorder=zorder_axv, alpha=1)
        cil, cih = utils.compute_ci(ssexit["ts"])
        ax.axvspan(cil, cih, facecolor=color, alpha=0.2, edgecolor=None) # color=color,

        # ax.axhline(ssexit[metric]["mean"], color=color, zorder=zorder)
        # cil, cih = utils.compute_ci(ssexit[metric])
        # ax.axhspan(cil, cih, facecolor=color, alpha=0.2, edgecolor=None) # color=color,

        # loss = grp_loss.loc[cca]
        # index = loss.index.total_seconds() * 1000
        # pos = index + bar_width * i
        # ax2.bar(pos, loss["TotalRetransSegsDiff"]["median"], color=color,
        #         zorder=zorder_bar, width=bar_width, alpha=.5)

    fig_legend = utils.plot_external_legend(parts, ncol=np.ceil(len(parts)/2),
                                            figsize=(utils.FIGSIZE[0]*2, 1.3))
    return fig_legend, fig

def plot(grp_cwnd, grp_ssexit, grp_loss):
    with_losses = False
    if with_losses:
        fig, axes = plt.subplots(figsize=FIGSIZE, layout="constrained",
                                nrows=2, gridspec_kw={'height_ratios': [3, 1]},
                                sharex=True)
        ax = axes[0]
        ax2 = axes[1]

        ax2.set_ylabel(f"Losses")
        ax2.set_xlabel(f"Time [ms]")
        ax2.set_ylim(0, 10)
        ax2.grid(visible=False, axis="both")
    
        fig.get_layout_engine().set(w_pad=4 / 72, h_pad=0, hspace=0, wspace=0)

        ax.xaxis.set_visible(False)
    else:
        fig, ax = plt.subplots(figsize=(FIGSIZE[0], 1.3))
        ax.set_xlabel(f"Time [ms]")

    ax.set_ylabel(f"cwnd [Packets]")
    ax.grid(visible=False, axis="x")

    parts = []
    zorder_prim = 12
    zorder_back = 11
    bar_width = grp_freq_ms / len(grp_cwnd.index.levels[0])
    # for i, cca in enumerate(list(grp_cwnd.index.levels[0])):
    for cca in grp_cwnd.index.levels[0]:
        if cca not in tcpri.CCA_LINESTYLES:
            print(f"WARNING: CCA {cca} in grp but not in CCA_LINESTYLES")
    for i, cca in enumerate(tcpri.CCA_LINESTYLES.keys()): # control the order of lines
        try:
            cwnd = grp_cwnd.loc[cca][metric]
        except KeyError:
            ax.plot([0], [0], color="white", alpha=0, label=" ") # add white field to legend
            continue # not present, e.g., udp

        # color = utils.mpl_colors()[i]
        color = tcpri.CCA_COLORS[cca]
        ls = tcpri.CCA_LINESTYLES[cca] 
        label = utils.cca_label(cca)

        index = cwnd.index.total_seconds() * 1000
        cil, cih = utils.compute_ci(cwnd)
        parts.append(ax.plot(index, cwnd["mean"], color=color, zorder=zorder_prim,
                             label=label, linewidth=0.8,
                             ls=ls)[0])
        # ax.fill_between(index, cil, cih, color=color, alpha=0.2, edgecolor="white") # color=color,

        ssexit = grp_ssexit.loc[cca]
        ax.axvline(ssexit["ts"]["mean"], color=color, zorder=zorder_back, alpha=1)
        cil, cih = utils.compute_ci(ssexit["ts"])
        ax.axvspan(cil, cih, facecolor=color, alpha=0.2, edgecolor=None) # color=color,

        # ax.axhline(ssexit[metric]["mean"], color=color, zorder=zorder)
        # cil, cih = utils.compute_ci(ssexit[metric])
        # ax.axhspan(cil, cih, facecolor=color, alpha=0.2, edgecolor=None) # color=color,

        if with_losses:
            loss = grp_loss.loc[cca]
            index = loss.index.total_seconds() * 1000
            pos = index + bar_width * i
            ax2.bar(pos, loss["TotalRetransSegsDiff"]["median"], color=color,
                    zorder=zorder_prim, width=bar_width, alpha=1,
                    align="edge")

    if with_losses:
        for i in range(0, 2000, grp_freq_ms):
            ax2.axvline(i, color="black", alpha=0.4, zorder=zorder_back, lw=0.8, linestyle="dotted")

    fig_legend = utils.plot_external_legend(parts, ncol=np.ceil(len(parts)/2),
                                            figsize=(FIGSIZE[0], 1.3))
    for line in fig_legend.legends[0].get_lines():
        line.set_linewidth(1.5)

    return fig_legend, fig

FIGSIZE=(utils.COLUMN_WIDTH/1.8, 1.5)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csvs", nargs="+", help="Burst measure csvs")
    parser.add_argument("-b", action="store_true")
    parser.add_argument("-o")
    args = parser.parse_args()

    utils.set_plt_style(10)

    files = [tcpri.parse_filename(csv) for csv in sorted(args.csvs)]
    tcp_files = [f for f in files if f is not None and f["protocol"] == "tcp"]

    with multiprocessing.Pool(multiprocessing.cpu_count()) as pool:
        tcp_args = list(zip(tcp_files, range(len(tcp_files))))
        tcp_dfs = list(tqdm(pool.imap_unordered(tcpri.parse_tcp_csv, tcp_args),
                            total=len(tcp_args),
                            desc="parsing tcp csvs"))
        df = pd.concat([df for df in tcp_dfs if df is not None])

    print(f"Grouping dfs")
    cwnd = group_tcp_cwnd(df)
    ssexit = utils.calc_ssexit(df, ["direction", "cca", "idx"])
    loss = group_tcp_losses(df)

    if args.b:
        breakpoint()

    print(f"Plotting")
    figs = []
    figs.extend(plot(cwnd.loc["dl"], ssexit.loc["dl"], loss.loc["dl"]))
    figs[-1].get_axes()[0].annotate(text=f"DL", **utils.SUBPLOT_TOP_STYLE)
    figs.append(plot(cwnd.loc["ul"], ssexit.loc["ul"], loss.loc["ul"])[1])
    figs[-1].get_axes()[0].annotate(text=f"UL", **utils.SUBPLOT_TOP_STYLE)

    for fig in figs:
        try:
            ax = fig.get_axes()[0]
        except:
            # legend figure
            continue
        ax.set_xlim(0, 1000)

    if args.o:
        with PdfPages(args.o) as pdf:
            for fig in figs:
                pdf.savefig(fig, bbox_inches="tight", pad_inches=0)
            for fig in figs:
                try:
                    ax = fig.get_axes()[0]
                    ax.set_xlim(0, 2000)
                    pdf.savefig(fig, bbox_inches="tight", pad_inches=0)
                except:
                    # legend figure
                    continue

if __name__ == "__main__":
    main()
