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
import sys
import traceback

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.backends.backend_pdf import PdfPages

import utils

# derived fromp prograte.py

def parse_csv(args):
    path, idx, xlim = args

    df = utils.parse_udp_csv(path)
    if df is None:
        return None

    df["ts_sent_rel"] = df.ts_sent - df.ts_sent.min()
    df["ts_rcvd_rel"] = df.ts_rcvd - df[~df.lost].ts_rcvd.min()
    df["ts_rcvd_rel_sent"] = df.ts_rcvd - df.ts_sent.min()
    # df["ts_rcvd_rel_ms"] = df["ts_rcvd_rel"].dt.total_seconds() * 1000
    # df["ts_ravd_rel_ms"] = (df.ts_rcvd - df.ts_sent.get(0)).dt.total_seconds() * 1000

    queue = utils.simulate_queue(df, ts_sent="ts_sent_rel", ts_rcvd="ts_rcvd_rel_sent")
    # index = pd.MultiIndex.from_tuples(zip([idx] * len(queue.index), queue.index), names=["idx", "ts"])
    # queue.set_index(index, inplace=True)

    # rate_ul_001_0300.csv
    parts = os.path.splitext(os.path.basename(path))[0].split("_")

    for d in [df, queue]:
        d["idx"] = idx
        d["direction"] = parts[1] # ul dl
        d["rate_mbps"] = int(parts[2])
        d["duration_ms"] = int(parts[3])

    xlim_ts = pd.to_timedelta(xlim + 100, unit="ms")
    df = df[df["ts_rcvd_rel"] <= xlim_ts]
    queue = queue[queue.index <= xlim_ts]

    return df, queue

def group_df_gput_abs_rel(df, ts_key="ts_rcvd_rel", freq_ms=1.3*10):
    grp_base = df[~df.lost]\
        .set_index(ts_key)\
        .groupby(["direction", "rate_mbps", "idx", pd.Grouper(freq=f"{freq_ms}ms")])\
        .agg({ "size": "sum" })\
        .apply(lambda df: df * (1000/freq_ms) * 8 / 1e6)

    # Sum the bytes received during the first 100 ms
    sum_until = int(100//freq_ms)
    first_sum = grp_base.groupby(["direction", "rate_mbps", "idx"])["size"].apply(lambda df: df[:sum_until].sum() / freq_ms)

    agg_fns = ["mean", "median", "std", "count", utils.groupby_q(0.9), utils.groupby_q(0.95), utils.groupby_q(0.99)]

    grp = grp_base.reset_index().set_index(["direction", "rate_mbps", "idx"]).join(first_sum.rename("first"))
    gput_abs = grp.reset_index().groupby(["direction", "rate_mbps", ts_key])["size"].agg(agg_fns)
    grp = grp.reset_index().set_index(["direction", "rate_mbps", "idx", ts_key])
    gput_rel = (grp["size"] / grp["first"]).groupby(["direction", "rate_mbps", ts_key]).agg(agg_fns)
                  # .apply(lambda df: df["size"] / df["first"], include_groups=False, axis=0)\
    return gput_abs, gput_rel

# grp_agg_fns = ["mean", "median", "std", "count", utils.groupby_q(0.9), utils.groupby_q(0.95), utils.groupby_q(0.99)]

def group_df(df, ts_key="ts_rcvd_rel", freq_ms=1.3*10):
    grp_base = df[~df.lost]\
        .set_index(ts_key)\
        .groupby(["direction", "rate_mbps", "idx", pd.Grouper(freq=f"{freq_ms}ms")])\
        .agg(dict(size="sum", owd_ms="mean"))
    grp_base["gput"] = grp_base["size"] * (1000/freq_ms) * 8 / 1e6
    # return grp_base.groupby(level=[0, 1, 3])[["gput", "owd_ms"]].agg(grp_agg_fns)
    return grp_base.groupby(level=[0, 1, 3])[["gput", "owd_ms"]]\
                   .apply(utils.get_stats, use_bootstrap=True, method="percentile")

def group_dfq(dfq, freq_ms=1.3*10):
    return dfq\
        .groupby(["direction", "rate_mbps", pd.Grouper(freq=f"{freq_ms}ms")])\
        .queue\
        .apply(utils.get_stats, use_bootstrap=False, method="percentile").unstack()
        # .agg(grp_agg_fns)

def plot(ax, grp, relative, metric, ylabel=None, major=None, minor=None):
    ax.set_ylabel(ylabel, loc="bottom")
    if major:
        ax.yaxis.set_major_locator(mticker.MultipleLocator(major))
    if minor:
        ax.yaxis.set_minor_locator(mticker.MultipleLocator(minor))

    parts = []

    for i, rate_mbps in enumerate(grp.index.get_level_values(0).unique()):
        try:
            data = grp.loc[rate_mbps]
        except:
            continue
        color = utils.mpl_colors()[i % len(utils.mpl_colors())]
        linestyle = "solid" if i < len(utils.mpl_colors()) else "dashed"
        data = data[data["count"] > data["count"].max() * 0.1] # filter out few long tests
        index = data.index.total_seconds() * 1000
        label = f"{rate_mbps}"
        parts.append(ax.plot(index, data[metric], label=label, color=color,
                             linewidth=1.0, linestyle=linestyle)[0])
        ax.fill_between(index, data["ci_low"],  data["ci_high"],
                        color=color, alpha=0.2, edgecolor="white",
                        rasterized=True)

    return parts

def plot_legend(fig, parts_dl, parts_ul):
    style = dict(
        fancybox=False,
        shadow=False,
        framealpha=1,
        edgecolor="black",
        facecolor="white",
        borderpad=0.2,
        handleheight=0.5,
        handlelength=0.6,
        frameon=False,
    )
    legends = []
    def ncols(parts):
        if len(parts) < 4:
            return 4
        return int(np.ceil(len(parts_dl)/2))
    if parts_dl is not None:
        legends.append(fig.legend(handles=parts_dl, ncols=ncols(parts_dl),
                                  bbox_to_anchor=(0.07, 0.95, 0.45, 0.2), **style))
    if parts_ul is not None:
        legends.append(fig.legend(handles=parts_ul, ncols=ncols(parts_ul),
                                  # bbox_to_anchor=(0.58, 0.95, 0.45, 0.2),
                                  bbox_to_anchor=(0.52, 0.95, 0.45, 0.2),
                                  **style))

    # Make the legend lines thicker
    for legend in legends:
        for line in legend.get_lines():
            line.set_linewidth(2.0)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csvs", nargs="+", help="Burst measure csvs")
    parser.add_argument("--xlim", type=int, default=800, help="Plot x 0-XLIM")
    parser.add_argument("-n", type=int, help="Sample N csvs")
    parser.add_argument("-b", action="store_true")
    parser.add_argument("-o")
    args = parser.parse_args()

    utils.set_plt_style(10)

    map_args = list(zip(args.csvs, range(len(args.csvs)), [args.xlim] * len(args.csvs)))
    results = utils.parse_csvs(map_args, parse_csv, parallel=True, concat=False, sample=args.n)
    if results is None:
        return
    df = pd.concat(df for df, _ in results if df is not None)
    dfq = pd.concat(queue for _, queue in results if queue is not None)

    # df_gput_abs, df_gput_rel = group_df_gput(df, ts_key="ts_sent_rel")
    # df_gput_abs, df_gput_rel = group_df_gput(df)

    print("Grouping receive rate and owd ...")
    grp = group_df(df, freq_ms=10*1.3)
    print("Grouping queue ...")
    grpq = group_dfq(dfq)

    duration_ms = df.duration_ms.unique()
    if len(duration_ms) != 1:
        print(f"Expects all tests to have run for the same duration; got: {duration_ms}")
        sys.exit(1)

    directions = df.direction.unique()

    if args.b:
        breakpoint()

    print(f"Number of samples:")
    print(str(df.groupby(["direction", "rate_mbps"]).idx.nunique()))

    print("Plotting ...")

    df_gput_abs = grp["gput"]
    ylabel_gput = "Received [Mbps]"
    # ylabel_owd = "OWD [ms]"
    ylabel_queue = "Queue [Packets]"

    parts_dl = None
    parts_ul = None

    if len(directions) == 1:
        # one direction only
        fig, axes = plt.subplots(figsize=(utils.COLUMN_WIDTH/1.1, 1.2), ncols=2)
        fig.get_layout_engine().set(w_pad=2/72, wspace=0.00)

        for ax in axes:
            ax.set_xlim(0, args.xlim)
            ax.set_xlabel(f"Receive Time [ms]")
            ax.xaxis.set_major_locator(mticker.MultipleLocator(400))
            ax.xaxis.set_minor_locator(mticker.MultipleLocator(100))

        direction = directions[0]
        parts_dl = plot(axes[0], df_gput_abs.loc[direction], relative=False, metric="mean",
                        ylabel=ylabel_gput, major=150, minor=50)
        axes[0].set_ylim(bottom=-20, top=350)# top=425)

        plot(axes[1], grpq.loc[direction], relative=False, metric="mean",
            ylabel=ylabel_queue, major=1000, minor=500)
    else: # one column per direction
        fig, axes = plt.subplots(figsize=(utils.COLUMN_WIDTH/1.1, 2.2),
                                nrows=2, ncols=2, sharex=True)
        axes[0][0].set_xlim(0, args.xlim)
        fig.get_layout_engine().set(w_pad=2/72, wspace=0.00)

        for ax in axes[1]:
            ax.set_xlabel(f"Receive Time [ms]")
            ax.xaxis.set_major_locator(mticker.MultipleLocator(200))
            ax.xaxis.set_minor_locator(mticker.MultipleLocator(50))

        parts_dl = plot(axes[0][0], df_gput_abs.loc["dl"], relative=False, metric="mean",
                        ylabel=ylabel_gput, major=200, minor=50)
        axes[0][0].set_ylim(bottom=-20, top=425)
        plot(axes[1][0], grpq.loc["dl"], relative=False, metric="mean", ylabel=ylabel_queue,
             major=500, minor=250)

        parts_ul = plot(axes[0][1], df_gput_abs.loc["ul"], relative=False, metric="mean",
                        major=20, minor=10)
        axes[0][1].set_ylim(bottom=10, top=75)
        plot(axes[1][1], grpq.loc["ul"], relative=False, metric="mean", major=500, minor=250)

    plot_legend(fig, parts_dl, parts_ul)

    if args.o:
        with PdfPages(args.o) as pdf:
            pdf.savefig(fig, pad_inches=0)
    else:
        plt.show()

if __name__ == "__main__":
    main()
