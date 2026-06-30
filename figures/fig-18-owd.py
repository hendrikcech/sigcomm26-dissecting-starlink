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

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.backends.backend_pdf import PdfPages
from tqdm import tqdm

import utils

def parse_csvs(csvs):
    with multiprocessing.Pool(multiprocessing.cpu_count()) as pool:
        map_args = zip(csvs, range(len(csvs)))
        dfs = list(tqdm(pool.imap_unordered(parse_csv, map_args), total=len(csvs),
                        desc="parsing csvs"))
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
    # Convert to UTC
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

def group_df(df):
    cuts = pd.cut(df.ri_sec, np.arange(0, 15.1, 0.25))
    return df.groupby(["direction", cuts], observed=False).owd_ms.apply(utils.get_stats).unstack()

def plot_in_ri(grp):
    fig, ax = plt.subplots(figsize=(utils.COLUMN_WIDTH/2, 1.4))
    ax.set_xlabel("Secs since prev. reconf.")
    ax.set_ylabel("OWD [ms]")
    ax.set_xticks(np.arange(0, 15.1, 5))
    ax.xaxis.set_minor_locator(mticker.MultipleLocator(1))
    # ax.set_xlim(-0.4, 14.9)

    for i, direction in enumerate(grp.index.levels[0]):
        color = utils.mpl_colors()[i]
        data = grp.loc[direction]
        index = data.index.categories.left # (1.0, 1.5] -> 1.0
        ax.plot(index, data["mean"], label=f"{direction.upper()}", color=color,
                marker=".")
        ax.fill_between(index, data["ci_low"], data["ci_high"],
                        color=color, alpha=0.2, edgecolor="white",
                        rasterized=True)

        mean = data.loc[1:14, "mean"].mean()
        ax.annotate(text=f"{round(mean)} ms" if not np.isnan(mean) else "",
                    xy=(7.5, mean), xycoords="data",
                    # xytext=(0, 4), textcoords="offset points",
                    xytext=(0, 5), textcoords="offset points",
                    horizontalalignment="center",
                    verticalalignment="center",
                    color=color)

        first = data.iloc[0]
        ax.annotate(text=f"{round(first['mean'])} ms" if not np.isnan(first["mean"]) else "",
                    xy=(first.name.left, first['mean']), xycoords="data",
                    # xytext=(3, -2), textcoords="offset points",
                    xytext=(2, 0), textcoords="offset points",
                    horizontalalignment="left",
                    verticalalignment="center",
                    color=color)

        last = data.iloc[-1]
        ax.annotate(text=f"{round(last['mean'])} ms" if not np.isnan(last["mean"]) else "",
                    xy=(last.name.left, last['mean']), xycoords="data",
                    # xytext=(-22,-2), textcoords="offset points")
                    xytext=(-2, 0), textcoords="offset points",
                    horizontalalignment="right",
                    verticalalignment="center",
                    color=color)

    # ax.legend(loc="upper center", ncol=len(grp.index.levels[0]))
    return fig

# ---

def group_owd_ri_change(df):
    dfs = df.sort_values("ts_sent")
    grp_ri = dfs.groupby(["direction", "idx", (dfs.ri_sec < dfs.ri_sec.shift()).cumsum()])\
                .agg(dict(ts_sent=["min", "max", "count"], owd_ms=["mean", "median"]))
    change = grp_ri.groupby(level=[0, 1], group_keys=False).apply(lambda df: df["owd_ms", "median"] - df["owd_ms", "median"].shift()).abs().dropna()
    frame = change.to_frame()
    frame.columns = [("owd_ms")]
    return frame

def group_owd_ri_change_with_sats(df):
    dfs = df.sort_values("ts_sent")
    grp_ri = dfs.groupby(["direction", "idx", (dfs.ri_sec < dfs.ri_sec.shift()).cumsum()])\
                .agg(dict(ts_sent=["min", "max", "count"], owd_ms=["mean", "median"], Connected_Satellite="last"))
    change_owd = grp_ri.groupby(level=[0, 1], group_keys=False).apply(lambda df: df["owd_ms", "median"] - df["owd_ms", "median"].shift()).abs().dropna()
    change_sat = grp_ri.groupby(level=[0, 1], group_keys=False).apply(lambda df: df.iloc[1:]["Connected_Satellite", "last"].values != df.iloc[1:]["Connected_Satellite", "last"].shift())
    change = pd.concat([change_owd.rename("owd_ms"), change_sat.rename("handover")], axis=1)
    return change

def main():
    parser = argparse.ArgumentParser()
    # Expects DL and UL csvs
    parser.add_argument("csvs", nargs="+")
    parser.add_argument("--sats", help="Path to csv file of connected satellites")
    parser.add_argument("-b", action="store_true")
    parser.add_argument("-o")
    args = parser.parse_args()

    utils.set_plt_style()

    df = parse_csvs(args.csvs)
    grp = group_df(df)

    if args.sats is not None:
        sats = utils.Satellites()
        sats.parse(args.sats)

        sat_df = sats.df.Connected_Satellite
        sat_df.index = sat_df.index.tz_convert(None)
        df = pd.merge_asof(df.sort_values("ts_sent"), sat_df, left_on="ts_sent", right_index=True)

        grp_change = group_owd_ri_change_with_sats(df)
    else:
        grp_change = group_owd_ri_change(df)
    print(grp_change.groupby(level=0).describe())

    if args.b:
        breakpoint()

    figs = []
    figs.append(plot_in_ri(grp))

    xlabel = "OWD Difference [ms]"
    if args.sats is not None:
        # figs.append(utils.plot_ri_change(grp_change[grp_change.handover].owd_ms, "OWD Change after Satellite Handover [ms]", 5, 1))
        # figs.append(utils.plot_ri_change(grp_change[~grp_change.handover].owd_ms, "OWD Change without Satellite Handover [ms]", 5, 1))
        figs.append(utils.plot_ri_change_with_handovers(grp_change, "owd_ms", xlabel, 5, 1))
    else:
        figs.append(utils.plot_ri_change(grp_change.owd_ms, xlabel, 5, 1))
    figs[-1].get_axes()[0].annotate(text=f"(f)", **utils.SUBPLOT_TOP_STYLE)

    figs[-1].get_axes()[0].set_xlim(0, 12)

    if args.o:
        with PdfPages(args.o) as pdf:
            for fig in figs:
                # fig.tight_layout()
                pdf.savefig(fig, bbox_inches="tight", pad_inches=0)
    else:
        plt.show()

if __name__ == "__main__":
    main()
