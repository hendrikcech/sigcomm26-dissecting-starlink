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
import random

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.backends.backend_pdf import PdfPages

import utils

def parse_csv(args):
    path, idx = args

    df = utils.parse_udp_csv(path)
    if df is None:
        return None

    if len(df[~df.lost]) == 0:
        print(f"{path}: no packet received")
        return None

    dfq = utils.simulate_queue(df)

    df.set_index("ts_sent", inplace=True)
    df = add_metadata(df, path, idx)
    df = df.reset_index()
    # df["iat"] = df.ts_rcvd.diff().dt.total_seconds() * 1000

    dfq = add_metadata(dfq, path, idx)

    return df, dfq

def add_metadata(df, path, idx):
    rel_ts = (df.index - df.index.min().floor("min")).total_seconds()
    ri_ms = (rel_ts - 12) % 15 * 1000
    # df["ri_ms"] = (rel_ts - 12) % 15 * 1000
    df["ri_rel_ms"] = np.where(ri_ms > 7500, ri_ms - 15000, ri_ms)
    df["ri_rel_ts"] = pd.to_timedelta(df.ri_rel_ms, unit="ms")
    # Limit to relevant section of test
    df = df[(df.ri_rel_ms >= -LENS_DURATION_MS / 2) & (df.ri_rel_ms <= LENS_DURATION_MS / 2)]
    df = df.sort_index()
    df["idx_ho"] = idx * 100 + (df.ri_rel_ms < df.ri_rel_ms.shift()).cumsum()
    df = df.drop(columns="ri_rel_ms")
    # rate_ul.csv
    parts = os.path.splitext(os.path.basename(path))[0].split("_")
    df["idx"] = idx
    df["direction"] = parts[1]
    return df


def group_df(df, grp_freq_ms=1.33*10):
    groupby = ["ho", "direction", "idx_ho", pd.Grouper(key="ri_rel_ts", freq=f"{grp_freq_ms}ms")]
    grp_idx = df[~df.lost].groupby(groupby).agg(dict(size="sum", owd_ms="mean"))
    grp_idx["gput"] = grp_idx["size"].apply(lambda df: df * (1000/grp_freq_ms) * 8 / 1e6)
    grp_idx = grp_idx.drop(columns=["size"])
    lost = df.groupby(groupby).lost.agg(["sum", "count"])
    grp_idx["loss_rate"] = lost["sum"] / lost["count"] * 100
    grp = grp_idx.groupby(level=[0,1,3]).apply(utils.get_stats)
    return grp, grp_idx.reset_index(level=0)

def group_queue(df, grp_freq_ms=1.33*10):
    groupby = ["ho", "direction", "idx_ho", pd.Grouper(key="ri_rel_ts", freq=f"{grp_freq_ms}ms")]
    grp_idx = df.groupby(groupby).queue.last()
    grp = grp_idx.groupby(level=[0,1,3]).apply(utils.get_stats).unstack()
    return grp, grp_idx.reset_index(level=0)

HO_LINESTYLES = { True: "solid", False: (0, (1, 1)) }
HO_LINEWIDTH = { True: 2, False: 1 }

def plot(directions, column, ylabel, df, df_idx, xlabel="Receive Time [ms]", ymajor=None, yminor=None):
    fig, ax = plt.subplots(figsize=(utils.FULL_WIDTH/4, utils.FULL_WIDTH/4 / 1.5))
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.xaxis.set_major_locator(mticker.MultipleLocator(300))
    ax.xaxis.set_minor_locator(mticker.MultipleLocator(100))
    if ymajor:
        ax.yaxis.set_major_locator(mticker.MultipleLocator(ymajor))
    if yminor:
        ax.yaxis.set_minor_locator(mticker.MultipleLocator(yminor))

    # Aggregate: TODO plot median?
    for ho in [True, False]:
        for direction in directions:
            data = df.loc[ho, direction]
            if column is not None: # None if the columns are already "mmean", "ci_low", etc.
                data = data[column]
            if data.empty:
                continue
            index = data.index.total_seconds() * 1000
            color = utils.direction_color(direction)
            ax.plot(index, data["mean"], color=color, label=direction.upper(),
                    ls=HO_LINESTYLES[ho], lw=HO_LINEWIDTH[ho])
            ax.fill_between(index, data["ci_low"], data["ci_high"],
                            color=color, alpha=0.2, edgecolor="white") # color=color,

    # Plot individual runs
    direction = directions[0]
    df_idx = df_idx.loc[direction]
    if column is not None:
        df_idx = df_idx[column]
    all_idxs = list(df_idx.index.get_level_values(0).unique())
    idxs = random.sample(all_idxs, k=min(20, len(all_idxs)))
    for idx in idxs:
        data = df_idx.loc[idx]
        index = data.index.total_seconds() * 1000
        ax.plot(index, data, lw=1, color="black", alpha=0.1, zorder=0)

    return fig


def ri_break_duration(df):
    margin = pd.to_timedelta(300, unit="ms")
    dfs = df[~df.lost]
    lens = dfs[(dfs.ri_rel_ts > -margin) & (dfs.ri_rel_ts < margin)]
    lens2 = lens.sort_values("ts_rcvd").reset_index(drop=True)
    grp = lens2.groupby(["ho", "direction", "idx_ho"]).apply(lambda df: df.ts_rcvd.diff().dt.total_seconds() * 1000, include_groups=False)#.reset_index(level=[3,4,5], drop=True).reset_index(names=0)
    res = grp.dropna().groupby(["ho", "direction", "idx_ho"], group_keys=False).max()# .nlargest(5)
    return res

def plot_ri_break_cdf(df):
    grp = ri_break_duration(df)

    fig, ax = plt.subplots(figsize=(utils.FULL_WIDTH/4, utils.FULL_WIDTH/4 / 1.5))
    ax.set_ylabel("CDF")
    ax.set_xlabel("Connection Break [ms]")
    for ho in [True, False]:
        for direction in grp.index.get_level_values(1).unique():
            data = grp.loc[ho, direction]
            color = utils.direction_color(direction)
            # utils.plot_cdf_fixed(ax, data, color=color,
            #                      ls=HO_LINESTYLES[ho], lw=HO_LINEWIDTH[ho],
            #                      ci=ho)
            utils.plot_cdf(ax, data, color=color,
                           ls=HO_LINESTYLES[ho], lw=HO_LINEWIDTH[ho],
                           ci=ho)
    ax.set_xlim(left=-5)
    ax.yaxis.set_major_locator(mticker.MultipleLocator(0.5))
    ax.yaxis.set_minor_locator(mticker.MultipleLocator(0.25))
    ax.xaxis.set_major_locator(mticker.MultipleLocator(50))
    ax.xaxis.set_minor_locator(mticker.MultipleLocator(25))

    desc = f"RI Break\n{grp.groupby(level=[0,1]).describe()}"
    print(desc)
    fig.pdf_note = desc

    return fig

def merge_with_sats(df, sat_df):
    df = pd.merge_asof(df.sort_index(), sat_df, left_index=True, right_index=True)
    df_ho = df.groupby(["idx", "idx_ho"]).Connected_Satellite.nunique() == 1
    df_ho = df_ho.reset_index(level=0, drop=True).rename("ho")
    df = df.join(df_ho.rename("ho"), on="idx_ho")
    return df

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csvs", nargs="+", help="Long-running rate measurements that contain reconfigurations")
    parser.add_argument("--sats", nargs="+", help="Paths to csv file of connected satellites")
    parser.add_argument("-n", type=int, help="Sample N csvs")
    parser.add_argument("-b", action="store_true")
    parser.add_argument("-o")
    args = parser.parse_args()

    global LENS_DURATION_MS
    LENS_DURATION_MS = 1400

    random.seed(1)

    parse_args = list(zip(args.csvs, range(len(args.csvs))))
    results = utils.parse_csvs(parse_args, parse_csv, parallel=True, sample=args.n, concat=False)
    if results is None:
        return
    dfs, dfqs = zip(*[res for res in results if res is not None])
    df = pd.concat([df for df in dfs if df is not None])
    dfq = pd.concat([df for df in dfqs if df is not None])

    print(f"Merging dfs", end="")
    if args.sats is not None:
        sats = utils.Satellites()
        sats.parse(args.sats)
        sat_df = sats.df.Connected_Satellite
        sat_df.index = sat_df.index.tz_convert(None)

        df = merge_with_sats(df.set_index("ts_sent"), sat_df).reset_index()
        dfq = merge_with_sats(dfq, sat_df)
    else:
        df["ho"] = True

    if args.b:
        breakpoint()

    print(f", grouping df", end="")
    grp, grp_idx = group_df(df)
    print(f", grouping dfq")
    grpq, grpq_idx = group_queue(dfq)

    utils.set_plt_style()

    figs = []

    figs.append(plot(["dl", "ul"], "gput", "Received [Mbps]", grp, grp_idx)) # 1
    figs[-1].get_axes()[0].annotate(text=f"(a)", **utils.SUBPLOT_TOP_STYLE)

    # ax.yaxis.set_major_locator(mticker.MultipleLocator(250))
    figs[-1].get_axes()[0].yaxis.set_minor_locator(mticker.MultipleLocator(50))

    figs.append(plot(["dl", "ul"], "owd_ms", "OWD [ms]", grp, grp_idx)) # 2
    figs[-1].get_axes()[0].annotate(text=f"(c)", **utils.SUBPLOT_TOP_STYLE)

    figs.append(plot(["dl"], "gput", "Received [Mbps]", grp, grp_idx)) # 3
    # ax = figs[-1].get_axes()[0]
    # ax.yaxis.set_major_locator(mticker.MultipleLocator(100))
    figs[-1].get_axes()[0].yaxis.set_minor_locator(mticker.MultipleLocator(50))

    figs.append(plot(["ul"], "gput", "Received [Mbps]", grp, grp_idx)) # 4

    figs.append(plot(["dl"], "owd_ms", "OWD [ms]", grp, grp_idx)) # 5
    figs.append(plot(["ul"], "owd_ms", "OWD [ms]", grp, grp_idx)) # 6

    figs.append(plot(["dl", "ul"], "loss_rate", "Loss [%]", grp, grp_idx,
                     xlabel="Send Time [ms]", ymajor=50, yminor=10)) # 7
    figs[-1].get_axes()[0].set_ylim(top=105)

    figs.append(plot(["dl", "ul"], None, "Queue [Packets]", grpq, grpq_idx,
                     xlabel="Time [ms]", ymajor=1000, yminor=500)) # 8
    figs[-1].get_axes()[0].annotate(text=f"(b)", **utils.SUBPLOT_TOP_STYLE)
    figs.append(plot(["dl"], None, "Queue [Packets]", grpq, grpq_idx,
                     xlabel="Time [ms]", ymajor=1000, yminor=500)) # 9
    figs.append(plot(["ul"], None, "Queue [Packets]", grpq, grpq_idx,
                     xlabel="Time [ms]", ymajor=1000, yminor=500)) # 10

    # for fig in figs[-2:]: # OWD figures
    #     ax.set_ylim(0, 200)

    for fig in figs:
        ax = fig.get_axes()[0]
        # ax.axvline(0, color="black", linewidth=2, zorder=0)
        # ax.set_xlim(-LENS_DURATION_MS/2, LENS_DURATION_MS/2)
        ax.set_xlim(-LENS_DURATION_MS/4, LENS_DURATION_MS/2)

    figs.append(plot_ri_break_cdf(df)) # 11
    figs[-1].get_axes()[0].annotate(text=f"(d)", **utils.SUBPLOT_TOP_STYLE)

    if args.o:
        with PdfPages(args.o) as pdf:
            for fig in figs:
                try:
                    pdf.attach_note(fig.pdf_note)
                except:
                    pass
                pdf.savefig(fig, bbox_inches="tight", pad_inches=0)
def mpl_colors():
    return plt.rcParams['axes.prop_cycle'].by_key()['color']

if __name__ == "__main__":
    main()
