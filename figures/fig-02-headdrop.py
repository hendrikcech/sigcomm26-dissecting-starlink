#!/usr/bin/env python3
import argparse
import os
import sys
import random
import pickle

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.patches import Ellipse
from matplotlib.backends.backend_pdf import PdfPages

import utils

def parse_csv(args):
    path, idx = args

    df = utils.parse_udp_csv(path)
    if df is None:
        return None
    df["ts_sent_rel"] = df.ts_sent - df.ts_sent.min()
    df["ts_rcvd_rel"] = df.ts_rcvd - df[~df.lost].ts_rcvd.min()
    df["ts_rcvd_rel_sent"] = df.ts_rcvd - df.ts_sent.min()
    # df["ts_rcvd_rel_ms"] = df["ts_rcvd_rel"].dt.total_seconds() * 1000
    # df["ts_rcvd_rel_ms"] = (df.ts_rcvd - df.ts_sent.get(0)).dt.total_seconds() * 1000

    queue = utils.simulate_queue(df, ts_sent="ts_sent_rel", ts_rcvd="ts_rcvd_rel_sent")

    #                                     rate_ul_070_1000.csv
    # 20250707T145926_20250604T140157_prograte_dl_3_0700.csv
    parts = os.path.splitext(os.path.basename(path))[0].split("_")
    for d in [df, queue]:
        d["idx"] = idx
        d["direction"] = parts[-3] # ul dl
        d["rate_mbps"] = int(parts[-2])  # not correct for mahimahi traces
        d["duration_ms"] = int(parts[-1])

    return df, queue

def group_df_gput(df, ts_key="ts_rcvd_rel", freq_ms=1.33*10):
    grp_base = df[~df.lost]\
        .set_index(ts_key)\
        .groupby(["direction", "rate_mbps", "idx", pd.Grouper(freq=f"{freq_ms}ms")])\
        .agg({ "size": "sum" })\
        .apply(lambda df: df * (1000/freq_ms) * 8 / 1e6)

    # Sum the bytes received during the first 100 ms
    sum_until = int(100//freq_ms)
    first_sum = grp_base.groupby(["direction", "rate_mbps", "idx"])["size"].apply(lambda df: df[:sum_until].sum() / freq_ms)

    grp = grp_base.reset_index().set_index(["direction", "rate_mbps", "idx"]).join(first_sum.rename("first"))
    gput_abs = grp.reset_index()\
                  .groupby(["direction", "rate_mbps", ts_key])["size"]\
                  .agg(["mean", "median", "std", "count"])
    grp = grp.reset_index().set_index(["direction", "rate_mbps", "idx", ts_key])
    gput_rel = (grp["size"] / grp["first"]).groupby(["direction", "rate_mbps", ts_key])\
                  .agg(["mean", "median", "std", "count"])
                  # .apply(lambda df: df["size"] / df["first"], include_groups=False, axis=0)\
    return gput_abs, gput_rel

def plot_gput(grp, relative):
    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.set_xlabel(f"Receive Time [ms]")
    ax.grid(visible=True, axis="both")

    parts = []

    for i, rate_mbps in enumerate(grp.index.levels[0]):
        try:
            data = grp.loc[rate_mbps]
        except:
            continue
        color = utils.mpl_colors()[i % len(utils.mpl_colors())]
        data = data[data["count"] > data["count"].max() * 0.1] # filter out few long tests
        index = data.index.total_seconds() * 1000
        parts.append(ax.plot(index, data["mean"], label=f"{rate_mbps} Mbps", color=color)[0])
        # ax.plot(index, data["median"], label=f"{direction.upper()} Mean", color=color, linestyle="dashed")

        cil, cih = utils.compute_ci(data)
        ax.fill_between(index, cil, cih,
                        color=color, alpha=0.2, edgecolor="white",
                        rasterized=True)

        # ax.legend(loc="lower right")
        if relative:
            ax.set_ylabel(f"Relative Goodput")
            # ax.set_ylim(-0.3, np.ceil(max_mean))
            ax.set_ylim(0, 3.5)
        else:
            ax.set_ylabel(f"Goodput [Mbps]")

    legend = utils.plot_external_legend(parts, ncols=len(parts) // 2)

    # fig.tight_layout()

    return [fig, legend]

# --- OWD ---
def filter_outliers(df):
    outliers = df[df.owd_ms > df.owd_ms.quantile(0.9999)].idx.unique()
    if len(outliers) > 0:
        print(f"Exclude {len(outliers)} outlier from df")
        df = df[~df.idx.isin(outliers)]
    return df

def plot_owd(df, duration_ms, freq_ms, plot_indiv=False):
    grp_idx = df.groupby(["direction", "idx", pd.Grouper(freq=f"{freq_ms}ms", key="ts_sent_rel")])["owd_ms"].mean()
    grp = df.groupby(["direction", pd.Grouper(freq=f"{freq_ms}ms", key="ts_sent_rel")])["owd_ms"]\
            .apply(utils.get_stats, statistic=np.median).unstack()

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.set_xlabel(f"Send Time [ms]")
    ax.set_ylabel(f"OWD [ms]")
    ax.yaxis.set_major_locator(mticker.MultipleLocator(50))
    ax.yaxis.set_minor_locator(mticker.MultipleLocator(25))

    for i, direction in enumerate(reversed(grp.index.levels[0])):
        color = utils.direction_color(direction)

        data = grp.loc[direction]
        data = data.set_index(data.index.total_seconds() * 1000)
        # Clip to measured time
        data = data[data.index < duration_ms]

        ax.plot(data.index, data["median"], label=f"{direction.upper()}", color=color)
        ax.fill_between(data.index, data["ci_low"], data["ci_high"],
                        color=color, alpha=0.2, edgecolor="white",
                        rasterized=True)

        # Plot individual runs
        if plot_indiv:
            df_idx = grp_idx.loc[direction]
            all_idxs = list(df_idx.index.get_level_values(0).unique())
            idxs = random.sample(all_idxs, k=min(10, len(all_idxs)))
            for idx in idxs:
                data = df_idx.loc[idx]
                data.index = data.index.total_seconds() * 1000
                data = data[data.index < duration_ms]
                ax.plot(data.index, data, lw=1, color=color, alpha=0.1, zorder=0)

    if len(grp.index.levels[0]) == 1:
        ax.legend(loc="lower center", ncols=2)

    return fig

# --- loss ---
def plot_loss(df, duration_ms, freq_ms, plot_indiv=False):
    grp_a = df.groupby(["direction", "idx", pd.Grouper(freq=f"{freq_ms}ms", key="ts_sent_rel")])["lost"]\
                .agg(["sum", "count"])
    grp_idx = grp_a.apply(lambda df: df["sum"] / df["count"] * 100, axis=1)
    grp = grp_idx.groupby(level=[0,2]).apply(utils.get_stats, statistic=np.median).unstack()

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.set_xlabel(f"Send Time [ms]")
    ax.set_ylabel(f"Loss %")
    ax.yaxis.set_major_locator(mticker.MultipleLocator(50))
    ax.yaxis.set_minor_locator(mticker.MultipleLocator(10))

    for i, direction in enumerate(reversed(grp.index.levels[0])):
        color = utils.direction_color(direction)
        data = grp.loc[direction]
        data = data.set_index(data.index.total_seconds() * 1000)
        # Clip to measured time
        if duration_ms:
            data = data[data.index < duration_ms]

        # Used mean before
        ax.plot(data.index, data["median"], label=f"{direction.upper()}", color=color)
        ax.fill_between(data.index, data["ci_low"], data["ci_high"],
                        color=color, alpha=0.2, edgecolor="white",
                        rasterized=True)

        # Plot individual runs
        if plot_indiv:
            df_idx = grp_idx.loc[direction]
            all_idxs = list(df_idx.index.get_level_values(0).unique())
            idxs = random.sample(all_idxs, k=min(10, len(all_idxs)))
            for idx in idxs:
                data = df_idx.loc[idx]
                data.index = data.index.total_seconds() * 1000
                data = data[data.index < duration_ms]
                ax.plot(data.index, data, lw=1, color=color, alpha=0.1, zorder=0)

    # ax.legend(loc="lower center", ncols=2)

    return fig

# --- receive rate ---
def plot_rate(df, duration_ms, freq_ms, plot_indiv=False):
    # sent_a = df.groupby(["direction", "idx", pd.Grouper(freq=f"{freq_ms}ms", key="ts_sent_rel")])["size"].sum() * (1000/freq_ms) * 8 / 1e6
    # sent = sent_a.groupby(level=[0,2]).agg(["mean", "median", "std", "count"])

    rcvd_idx = df[~df.lost]\
        .groupby(["direction", "rate_mbps", "idx", pd.Grouper(freq=f"{freq_ms}ms", key="ts_rcvd_rel_sent")])\
        ["size"].sum() * (1000/freq_ms) * 8 / 1e6
    rcvd = rcvd_idx.groupby(level=[0, 1, 3]).apply(utils.get_stats, statistic=np.median).unstack()

    fig, ax = plt.subplots(figsize=FIGSIZE)
    # ax.set_xlabel(f"Receive Time [ms]")
    ax.set_xlabel(f"Time [ms]")
    ax.set_ylabel(f"Rates [Mbps]\nReceived (solid)\nSent (dashed)")
    ax.yaxis.set_major_locator(mticker.MultipleLocator(200))
    ax.yaxis.set_minor_locator(mticker.MultipleLocator(50))

    for i, direction in enumerate(reversed(rcvd.index.levels[0])):
        color = utils.direction_color(direction)

        rate = rcvd.loc[direction].index.get_level_values(0)[0]
        data_rcvd = rcvd.loc[direction, rate]
        data_rcvd = data_rcvd.set_index(data_rcvd.index.total_seconds() * 1000)
        # Clip to measured time
        data_rcvd = data_rcvd[data_rcvd.index < duration_ms]
        ax.plot(data_rcvd.index, data_rcvd["median"], label=f"{direction.upper()}", color=color)
        ax.fill_between(data_rcvd.index, data_rcvd["ci_low"], data_rcvd["ci_high"],
                        color=color, alpha=0.2, edgecolor="white",
                        rasterized=True)

        ax.axhline(rate, color=color, linestyle="dashed")

        # Plot individual runs
        if plot_indiv:
            df_idx = rcvd_idx.loc[direction, rate]
            all_idxs = list(df_idx.index.get_level_values(0).unique())
            idxs = random.sample(all_idxs, k=min(10, len(all_idxs)))
            for idx in idxs:
                data = df_idx.loc[idx]
                data.index = data.index.total_seconds() * 1000
                data = data[data.index < duration_ms]
                ax.plot(data.index, data, lw=1, color=color, alpha=0.1, zorder=0)

    if len(rcvd.index.levels[0]) == 1:
        ax.legend(loc="lower center", ncols=2)

    return fig

# ----
def shade_tail(ax, df, duration_ms):
    # ul_from = {"1000": 240, "1500": 90, "2000": 95}
    ul_from = {"700": 85, "1000": 85, "1500": 90, "2000": 95}
    dl_from = {"700": 40, "1000": 40,  "1500": 40, "2000": 45}

    # 1000: UL OWD rises but loss only starts decreasing with ~100 ms before the end
    # 1500 and 2000: UL OWD and loss matches
    shade_from = dict(ul=(duration_ms-ul_from[str(duration_ms)], "//"),
                    dl=(duration_ms-dl_from[str(duration_ms)], "\\\\")) # for 1500 ms
    for key, (s, hatch) in shade_from.items():
        if key in df.direction.unique():
            ax.axvspan(s, duration_ms, facecolor="None", edgecolor=utils.direction_color(key), alpha=0.7, hatch=hatch)

# ---

def plot_queue(dfq, duration_ms, freq_ms):
    grp = dfq.groupby(["direction", pd.Grouper(freq=f"{freq_ms}ms")]).queue.agg(["mean", "std", "count", "median"])

    fig, ax = plt.subplots(figsize=FIGSIZE)
    ax.set_xlabel(f"Time [ms]")
    ax.set_ylabel(f"Estimated Queue [Packets]")

    for i, direction in enumerate(reversed(grp.index.levels[0])):
        color = utils.direction_color(direction)

        data = grp.loc[direction]
        data = data.set_index(data.index.total_seconds() * 1000)
        # Clip to measured time
        data = data[data.index < duration_ms]

        ax.plot(data.index, data["median"], label=f"{direction.upper()}", color=color)
        cil, cih = utils.compute_median_ci(data)
        # ax.plot(data.index, data["mean"], label=f"{direction.upper()}", color=color,
        #         linewidth=1, linestyle="dashed")
        # cil, cih = utils.compute_ci(data)
        ax.fill_between(data.index, cil, cih,
                        color=color, alpha=0.2, edgecolor="white",
                        rasterized=True)

    # ax.axvline(duration_ms, color="black", linewidth=2, zorder=0)

    # ax.set_ylim(bottom=-10)

    # ax.xaxis.set_major_locator(mticker.MultipleLocator(200))
    # ax.xaxis.set_minor_locator(mticker.MultipleLocator(100))

    if len(grp.index.levels[0]) == 1:
        ax.legend(loc="lower center", ncols=2)

    return fig

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csvs", nargs="+", help="Burst measure csvs")
    parser.add_argument("--pickle", help="Export plotted lines")
    parser.add_argument("-b", action="store_true")
    parser.add_argument("-o")
    args = parser.parse_args()

    utils.set_plt_style(10)

    random.seed(1)

    global FIGSIZE
    FIGSIZE = (utils.FULL_WIDTH/3, 1.25)

    map_args = list(zip(args.csvs, range(len(args.csvs))))
    results = utils.parse_csvs(map_args, parse_csv, concat=False)
    if results is None:
        return
    df = pd.concat(df for df, _ in results if df is not None)
    dfq = pd.concat(queue for _, queue in results if queue is not None)

    duration_ms = df.duration_ms.unique()
    if len(duration_ms) != 1:
        print(f"Expects all tests to have run for the same duration; got: {duration_ms}")
        sys.exit(1)
    duration_ms = duration_ms[0]

    comb = df[["direction", "duration_ms", "rate_mbps"]].nunique()
    if comb.duration_ms != 1 or comb.direction > 2 or comb.rate_mbps > 2:
        print(f"Unexpected number of combinations: {comb}")
        breakpoint()

    if args.b:
        breakpoint()

    print(f"Number of samples: ", end="")
    samples = df.groupby(["direction"]).idx.nunique()
    print(str(samples))

    freq_ms = 10*1.3

    print(f"Plotting with {freq_ms=}...")
    figs = []
    lines = dict()

    df_all = df
    df = filter_outliers(df)

    text_style = dict(color="black", weight="bold", horizontalalignment="center")
    # ellipse_style = dict(color=color_draw, fill=False, lw=2)
    # ellipse_style = dict(color="#D1D1D1", fill=True, zorder=0)
    ellipse_style = dict(color="#969696", fill=False, zorder=0, lw=1)

    print("Plot rate")
    figs.append(plot_rate(df, duration_ms=duration_ms, freq_ms=freq_ms))
    ax = figs[-1].get_axes()[0]
    ax.add_artist(Ellipse(xy=(200, 260), width=170, height=500, angle=300, **ellipse_style))
    ax.add_artist(Ellipse(xy=(200, 40), width=430, height=70, angle=5, **ellipse_style))
    ax.annotate(text=f"(A)", xy=(180, 84), **text_style)
    lines["rate"] = { l.get_label(): l.get_xydata() for l in ax.lines if l.get_label() in ["UL", "DL"] }

    print("Plot owd")
    figs.append(plot_owd(df, duration_ms=duration_ms, freq_ms=freq_ms))
    ax = figs[-1].get_axes()[0]
    ax.add_artist(Ellipse(xy=(80, 65), width=230, height=105,angle=3,  **ellipse_style))
    ax.add_artist(Ellipse(xy=(965, 75), width=130, height=100, **ellipse_style))
    ax.annotate(text=f"(B)", xy=(80, 65), **text_style)
    ax.annotate(text=f"(C)", xy=(850, 85), **text_style)
    # shade_tail(ax, df, duration_ms)
    lines["owd"] = { l.get_label(): l.get_xydata() for l in ax.lines if l.get_label() in ["UL", "DL"] }

    print("Plot loss")
    figs.append(plot_loss(df, duration_ms=duration_ms, freq_ms=freq_ms))
    ax = figs[-1].get_axes()[0]
    ax.add_artist(Ellipse(xy=(120, 40), width=300, height=85, angle=5, **ellipse_style))
    ax.add_artist(Ellipse(xy=(950, 35), width=180, height=70, angle=350, **ellipse_style))
    ax.annotate(text=f"(D)", xy=(120, 25), **text_style)
    lines["loss"] = { l.get_label(): l.get_xydata() for l in ax.lines if l.get_label() in ["UL", "DL"] }

    ax.annotate(text=f"(E)", xy=(850, 10), **text_style)
    # shade_tail(ax, df, duration_ms)

    print("Plot queue")
    figs.append(plot_queue(dfq, freq_ms=freq_ms, duration_ms=duration_ms))
    ax = figs[-1].get_axes()[0]
    lines["queue"] = { l.get_label(): l.get_xydata() for l in ax.lines if l.get_label() in ["UL", "DL"] }

    if args.pickle is not None:
        with open(args.pickle, "wb") as f:
            pickle.dump(lines, f)

    if args.o:
        with PdfPages(args.o) as pdf:
            for i, fig in enumerate(figs):
                ax = fig.get_axes()[0]
                ax.xaxis.set_major_locator(mticker.MultipleLocator(250))
                ax.xaxis.set_minor_locator(mticker.MultipleLocator(50))
                # pdf.savefig(fig, bbox_inches="tight", pad_inches=0)
                pdf.savefig(fig, pad_inches=0)
    else:
        plt.show()

if __name__ == "__main__":
    main()
