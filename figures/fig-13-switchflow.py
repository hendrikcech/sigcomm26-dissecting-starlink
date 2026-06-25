#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "matplotlib",
#     "numpy",
#     "pandas",
#     "tqdm",
# ]
# ///

import argparse
import os

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D
from matplotlib.backends.backend_pdf import PdfPages
import itertools

import utils

def parse_filename(path):
    # expects csvs file names of this pattern:
    # rate_{dl / ul}_{rate in bmps}_{a / b: the run}
    # rate_dl_0200_a.csv
    # rate_dl_0200_b.csv
    filename = os.path.basename(path)
    parts = filename.split("_")
    try:
        assert len(parts) == 4
        mbps = int(parts[2])
        run = parts[3].split(".")[0]
        key = "_".join(parts[:3])
        return dict(direction=parts[1], mbps=mbps, run=run, key=key, path=path)
    except:
        print(f"Invalid filename {filename}")
        return None

def parse_csv(args):
    files, idx = args

    dfs = []
    for f in files:
        path = f["path"]
        df = utils.parse_udp_csv(path)
        if df is None:
            return

        df["idx"] = idx

        df["direction"] = f["direction"]
        df["run"] = f["run"]
        df["mbps"] = f["mbps"]
        # df["ts_sent_rel"] = df.ts_sent - df.ts_sent.min()
        df["ts_rcvd_rel"] = df.ts_rcvd - df[~df.lost].ts_rcvd.min()

        dfs.append(df)
    df = pd.concat(dfs)
    # df["ts_rcvd_rel_a"] = df.ts_rcvd - df[~df.lost].ts_rcvd.min()
    df["ts_rcvd_rel_a"] = df.ts_rcvd - df.ts_sent.min()
    return df

grp_freq_ms = 10
def group_df(df):
    grp_idx = df[~df.lost]\
        .set_index("ts_rcvd_rel_a")\
        .groupby(["direction", "mbps", "run", "idx", pd.Grouper(freq=f"{grp_freq_ms}ms")], observed=True)\
        .agg(dict(size="sum", owd_ms="mean"))
    grp_idx["gput"] = grp_idx["size"].apply(lambda df: df * (1000/grp_freq_ms) * 8 / 1e6)
    gput_run = grp_idx.reset_index().drop(columns=["size", "idx"])\
                      .groupby(["direction", "mbps", "run", "ts_rcvd_rel_a"])\
                      .apply(utils.get_stats, use_bootstrap=False)
    gput_sum = grp_idx.groupby(level=[0,1,3,4], observed=True)["gput"].sum()\
        .groupby(level=[0,1,3])\
        .apply(utils.get_stats, use_bootstrap=False).unstack()
    return gput_run, gput_sum

def plot_gput(axes, gput_run, gput_sum, direction, ymajor, yminor):
    gput_run = gput_run.loc[direction]
    gput_sum = gput_sum.loc[direction]
    rates = gput_run.index.get_level_values(0).unique()
    for ax in axes:
        # ax.set_ylabel(f"Goodput [Mbps, resampled to {gput_run_freq_ms} ms]")
        # ax.set_ylabel(f"Goodput")
        ax.grid(visible=True)
        ax.xaxis.set_major_locator(mticker.MultipleLocator(800))
        ax.xaxis.set_minor_locator(mticker.MultipleLocator(200))
        ax.yaxis.set_major_locator(mticker.MultipleLocator(ymajor))
        ax.yaxis.set_minor_locator(mticker.MultipleLocator(yminor))
        ax.set_xlim(0, 1600)
    axes[-1].set_xlabel(f"Receive Time [ms]")
    axes[0].set_title(direction.upper())

    # Only annotate the central plot due to space limitations

    def plot_data(i, data, color, ls="solid", alpha=None):
        axes[i].plot(data.index, data["mean"], label=f"{mbps} Mbps", color=color, ls=ls, alpha=alpha)
        axes[i].fill_between(data.index,
                             data["mean"] - data["std"]/2,
                             data["mean"] + data["std"]/2,
                             alpha=0.2, edgecolor="white",
                             rasterized=True, color=color)

    for i, mbps in enumerate(rates):
        try:
            data_a = gput_run.loc[mbps, "a"]["gput"]
            data_b = gput_run.loc[mbps, "b"]["gput"]
            data_sum = gput_sum.loc[mbps]
        except:
            continue

        plot_data(i, data_a.set_index(data_a.index.total_seconds() * 1000, drop=True),
                  # color=utils.direction_color(direction))
                  color=mpl_colors()[0])
        plot_data(i, data_b.set_index(data_b.index.total_seconds() * 1000, drop=True),
                  # color=utils.direction_color(direction), ls="dashed")
                  color=mpl_colors()[1])

        plot_data(i, data_sum.set_index(data_sum.index.total_seconds() * 1000, drop=True), color="black", alpha=0.7)

        # axes[i].axvline(800, color="black", linewidth=2, zorder=0)
        # axes[i].axvline(1600, color="black", linewidth=2, zorder=0)
        # axes[i].legend(loc="lower right")

        # title = f"{direction.upper()} Send Rate: {mbps} Mbps"
        # axes[i].set_title(title)
        # title = f"{direction.upper()} {mbps} Mbps"
        title = f"{mbps} Mbps"
        # axes[i].legend(handles=[Line2D([0], [0], label=title)],
        #                frameon=True, loc="lower left", handlelength=0, framealpha=0.7)
        axes[i].annotate(text=title, xy=(0.04, 0.01), xycoords="axes fraction",
                         ha="left", va="bottom", size=8)

def plot_owd(grp, ylim=None):
    fig, axes = plt.subplots(nrows=len(grp.index.levels[0]), sharex=True, sharey=True, figsize=(6,8))
    for ax in axes:
        ax.set_ylabel(f"OWD [ms]")
        ax.grid(visible=True)
        ax.xaxis.set_major_locator(mticker.MultipleLocator(200))
        ax.xaxis.set_minor_locator(mticker.MultipleLocator(50))
    axes[-1].set_xlabel(f"Receive Time [ms]")

    if ylim is not None:
        axes[0].set_ylim(0, ylim)
        axes[0].yaxis.set_major_locator(mticker.MultipleLocator(100))
        axes[0].yaxis.set_minor_locator(mticker.MultipleLocator(25))

    def plot_data(i, data, color, label):
        axes[i].plot(data.index, data["mean"], label=f"{label} {mbps} Mbps", color=color, alpha=0.8)
        axes[i].fill_between(data.index,
                             data["mean"] - data["std"]/2,
                             data["mean"] + data["std"]/2,
                             color=color, alpha=0.2, edgecolor="white",
                             rasterized=True,)

    for i, mbps in enumerate(grp.index.levels[0]):
        # axes[i].set_title(f"gap {mbps} ms")

        try:
            data_a = grp.loc[mbps, "a"]["owd_ms"]
            data_b = grp.loc[mbps, "b"]["owd_ms"]
        except:
            continue

        plot_data(i, data_a.set_index(data_a.index.total_seconds() * 1000, drop=True), color=mpl_colors()[0], label="A")
        plot_data(i, data_b.set_index(data_b.index.total_seconds() * 1000, drop=True), color=mpl_colors()[1], label="B")

        axes[i].axvline(800, color="black", linewidth=2, zorder=0)
        axes[i].axvline(1600, color="black", linewidth=2, zorder=0)

        axes[i].legend(loc="upper right")


    return fig


def plot_legend():
    parts = [
        Line2D([0], [0], color=utils.mpl_colors()[0], lw=2, label="Flow A"),
        Line2D([0], [0], color=utils.mpl_colors()[1], lw=2, label="Flow B"),
        Line2D([0], [0], color="black", lw=2, label="Total"),
    ]
    return utils.plot_external_legend(parts, ncol=len(parts), figsize=(utils.COLUMN_WIDTH, 1))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csvs", nargs="+", help="Burst measure csvs")
    parser.add_argument("-b", action="store_true")
    parser.add_argument("-o")
    args = parser.parse_args()

    utils.set_plt_style(2)

    files = [parse_filename(csv) for csv in sorted(args.csvs)]
    files = [f for f in files if f is not None]
    grps_all = [[e for e in g] for (k, g) in itertools.groupby(files, key=lambda f: f["key"])]
    grps = [g for g in grps_all if len(g) == 2]
    if len(grps_all) != len(grps):
        print(f"Incomplete groups: {len(grps_all)=} != {len(grps)=}")

    map_args = list(zip(grps, range(len(grps))))
    df = utils.parse_csvs(map_args, parse_csv)

    print(f"Grouping df")
    gput_run, gput_sum = group_df(df)

    if args.b:
        breakpoint()

    figs = []
    figs.append(plot_legend())

    num_rates_max = max(gput_run.loc["dl"].index.get_level_values(0).nunique(),
                        gput_run.loc["ul"].index.get_level_values(0).nunique())
    fig, axes = plt.subplots(nrows=num_rates_max,
                             ncols=2,
                             sharex=True, sharey=False,
                             figsize=(utils.COLUMN_WIDTH, 1 + 0.5*num_rates_max))
    figs.append(fig)
    print(len(axes))

    axes[len(axes)//2][0].set_ylabel(f"Receive Rate [Mbps]", loc="bottom")

    plot_gput([ax[0] for ax in axes], gput_run, gput_sum, "dl", 150, 50)
    plot_gput([ax[1] for ax in axes], gput_run, gput_sum, "ul", 30, 10)
    # figs.append(plot_owd(gput_run, ylim=250))
    # figs.append(plot_owd(gput_run.loc["dl"]))
    # figs.append(plot_owd(gput_run, ylim=250))
    # figs.append(plot_owd(gput_run.loc["ul"]))

    if args.o:
        with PdfPages(args.o) as pdf:
            for fig in figs:
                pdf.savefig(fig, bbox_inches="tight", pad_inches=0)

def mpl_colors():
    return plt.rcParams['axes.prop_cycle'].by_key()['color']

if __name__ == "__main__":
    main()
