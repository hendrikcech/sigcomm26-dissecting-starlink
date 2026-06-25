#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "matplotlib",
#     "numpy",
#     "pandas",
#     "tqdm",
#     "scipy",
# ]
# ///

import argparse
import os
import multiprocessing

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.backends.backend_pdf import PdfPages
from tqdm import tqdm

import utils

def parse_csvs(csvs):
    with multiprocessing.Pool(multiprocessing.cpu_count()) as pool:
        map_args = zip(csvs, range(len(csvs)))
        dfs = list(tqdm(pool.imap_unordered(parse_csv, map_args), total=len(csvs), desc="parsing csvs"))
        # dfs = list(tqdm(map(parse_csv, map_args), total=len(csvs)))
        return pd.concat([df for df in dfs if df is not None])

def parse_csv(args):
    path, idx = args

    try:
        df = pd.read_csv(path)
    except Exception as e:
        print(f"Failed to parse {path}: {e}")
        return None

    df["ts_sent"] = pd.to_datetime(df.ts_sent, format="ISO8601")
    df["ts_rcvd"] = pd.to_datetime(df.ts_rcvd, format="ISO8601")
    try:
        df["ts_sent"] = df["ts_sent"].dt.tz_convert(None)
    except Exception as e:
        pass
    try:
        df["ts_rcvd"] = df["ts_rcvd"].dt.tz_convert(None)
    except Exception as e:
        pass

    if len(df[~df.lost]) == 0:
        print(f"{path}: no packet received")
        return None

    if sum(df.lost) > 0.1 * len(df):
        print(f"{path}: high loss rate {sum(df.lost) / len(df) * 100:.2f}%")

    df["idx"] = idx

    parts = os.path.splitext(os.path.basename(path))[0].split("_")
    df["direction"] = parts[1] # ul dl

    rel_ts = (df.ts_sent - df.ts_sent.min().floor("min")).dt.total_seconds()
    df["ri_sec"] = (rel_ts - 12) % 15

    # Cut off first second to remove any artifacts from the start up phase
    margin = pd.to_timedelta(1, unit="s")
    lens_start = df.ts_sent > (df.ts_sent.min() + margin)
    lens_end = df.ts_sent < (df.ts_sent.max() - margin)
    dfl = df[lens_start & lens_end]

    return dfl

bin_width = 0.5
def loss_rate(df):
    cuts = pd.cut(df.ri_sec, np.arange(0, 15.1, bin_width))
    grp_a = df.groupby(["direction", cuts, "idx"], observed=True)["lost"].agg(["count", "sum"])
    grp_b = grp_a["sum"] / grp_a["count"] * 100
    return grp_b.groupby(level=[0, 1], observed=True).apply(utils.get_stats).unstack()

def consecutive_losses(df):
    dfi = df.reset_index(drop=True)
    dfl = dfi[dfi.lost].query("ri_sec > 1 & ri_sec <= 14")
    # cuts = pd.cut(dfl.ri_sec, np.arange(0, 15.1, 0.25))
    cumsum = dfl.index.to_series().diff().ne(1).cumsum()
    # grp = dfl.groupby(["direction", cuts, cumsum], observed=True)["lost"].sum()
    grp = dfl.groupby(["direction", cumsum], observed=True)["lost"].sum()
    # grp = dfl.groupby(["direction", "idx", cumsum], observed=True)["lost"].sum()
    freq = grp.groupby(level=0).value_counts(normalize=True, sort=False)
    return freq

def plot_loss_rate(grp):
    fig, ax = plt.subplots(figsize=(utils.COLUMN_WIDTH/2, 1.4))
    ax.set_xlabel("Secs since prev. reconf.")
    ax.set_ylabel("Packet Loss [%]")
    ax.set_xticks(np.arange(0, 15.1, 5))
    ax.xaxis.set_minor_locator(mticker.MultipleLocator(1))
    # ax.set_xlim(-0.4, 14.9)

    last = dict(mean=0) #hack, remove

    for i, direction in enumerate(grp.index.levels[0]):
        color = utils.mpl_colors()[i]
        data = grp.loc[direction]
        index = data.index.categories.left # (1.0, 1.5] -> 1.0
        ax.plot(index, data["mean"], label=f"{direction.upper()}", color=color, marker=".")
        ax.fill_between(index, data["ci_low"], data["ci_high"],
                        color=color, alpha=0.2, edgecolor="white",
                        rasterized=True)

        mean = data.loc[1:14, "mean"].mean()
        ax.annotate(text=f"{round(mean, 2)}%",
                    xy=(6.5 + i*4, mean), xycoords="data",
                    # xytext=(0, 4), textcoords="offset points",
                    xytext=(0, 6), textcoords="offset points",
                    horizontalalignment="center",
                    verticalalignment="center",
                    color=color)

        # first = data.iloc[0]
        # ax.annotate(text=f"{round(first['mean'], 2)}%",
        #             xy=(first.name.left, first['mean']), xycoords="data",
        #             # xytext=(3, -2), textcoords="offset points",
        #             xytext=(3, 0), textcoords="offset points",
        #             horizontalalignment="left",
        #             verticalalignment="center",
        #             color=color)

        last = data.iloc[-1]
        if direction == "dl" and last["mean"] < 50: # only for loss_idle
            ax.annotate(text=f"{round(last['mean'], 2)}%",
                        xy=(last.name.left, last['mean']), xycoords="data",
                        # xytext=(-22,-2), textcoords="offset points")
                        xytext=(-3, 0), textcoords="offset points",
                        horizontalalignment="right",
                        verticalalignment="center",
                        color=color)

    # if last["mean"] < 50: # quick hack: only plot non-newtonian fluidslegend for
    #     ax.legend(loc="upper center", ncol=len(grp.index.levels[0]))
    return fig

def plot_consecutive_losses(grp):
    fig, ax = plt.subplots(figsize=(utils.FIGSIZE[0], 1.5))
    ax.set_xlabel("Size of loss group")
    ax.set_ylabel("Percentage")
    ax.set_xticks(np.arange(0, 10.1, 2))
    ax.xaxis.set_minor_locator(mticker.MultipleLocator(1))
    ax.set_xlim(-0.4, 10)
    ax.grid(visible=True, axis="y")

    multiplier = -1
    width = 0.45
    for i, direction in enumerate(grp.index.levels[0]):
        color = utils.mpl_colors()[i]
        data = grp.loc[direction]
        offset = width * multiplier
        ax.bar(data.index + offset, data,
               label=f"{direction.upper()}", color=color,
               align="edge", width=width)
        multiplier += 1

    ax.legend(loc="upper center", ncol=len(grp.index.levels[0]))
    return fig

def main():
    parser = argparse.ArgumentParser()
    # Expects DL and UL csvs
    parser.add_argument("csvs", nargs="+")
    parser.add_argument("-b", action="store_true")
    parser.add_argument("-o")
    args = parser.parse_args()

    utils.set_plt_style()

    df = parse_csvs(args.csvs)

    if args.b:
        breakpoint()

    figs = []
    rate = loss_rate(df)
    figs.append(plot_loss_rate(rate))

    cons = consecutive_losses(df)
    figs.append(plot_consecutive_losses(cons))

    if args.o:
        with PdfPages(args.o) as pdf:
            for fig in figs:
                # tig.tight_layout()
                pdf.savefig(fig, bbox_inches="tight", pad_inches=0)
    else:
        plt.show()

if __name__ == "__main__":
    main()
