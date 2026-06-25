#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
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


def compute_ri_sec(ts):
    rel_ts = (ts - ts.min().floor("min")).dt.total_seconds()
    return (rel_ts - 12) % 15

def parse_csv(args, ts_key="ts_rcvd"):
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

    df["idx"] = idx

    parts = os.path.splitext(os.path.basename(path))[0].split("_")
    df["direction"] = parts[1] # ul dl

    # Cut off remove any artifacts from the start up phase
    try:
        ri_sec = compute_ri_sec(df[~df.lost][ts_key])
        margin = 2 # seconds
        start_from_ri_sec = (ri_sec.iloc[0] + margin) // 1 # e.g., 5.04 + 2 => 7
        start_idx = ri_sec[ri_sec >= start_from_ri_sec].index[0]
        end_at_ri_sec = (ri_sec.iloc[-1] - margin) // 1
        end_idx = ri_sec[ri_sec <= end_at_ri_sec].index[-1]
        dfl = df[(df.index >= start_idx) & (df.index <= end_idx)]
    except:
        print(f"Failed cut off for {path}: {len(df)=}, {df.ts_sent.min()=} {df.ts_sent.max()=}")
        return None

    return dfl

grp_freq_ms = 250
def group_df(df, ts_key="ts_rcvd"):
    grp_idx = df[~df.lost]\
        .set_index(ts_key)\
        .groupby(["direction", "idx", pd.Grouper(freq=f"{grp_freq_ms}ms")])[["owd_ms", "size"]]\
        .agg(dict(size="sum", owd_ms="mean"))
    grp_idx["gput"] = grp_idx["size"].apply(lambda df: df * (1000/grp_freq_ms) * 8 / 1e6)
    ri_sec = compute_ri_sec(grp_idx.reset_index()[ts_key])
    grp = grp_idx.reset_index().drop(columns=["idx", "size", ts_key])\
                                    .groupby(["direction", ri_sec])\
                                    .agg(["mean", "median", "std", "count"])
    return grp

def plot_in_ri(grp, col):
    fig, ax = plt.subplots(figsize=(utils.FULL_WIDTH * 0.32, 1.5))
    ax.set_xlabel("Seconds since last reconfiguration")
    if col == "gput":
        ax.set_ylabel("Goodput [Mbps]")
    elif col == "owd_ms":
        ax.set_ylabel("OWD [ms]")
    ax.set_xticks(np.arange(0, 15.1, 5))
    ax.xaxis.set_minor_locator(mticker.MultipleLocator(1))
    # ax.set_xlim(-0.4, 14.9)

    for i, direction in enumerate(grp.index.levels[0]):
        color = utils.mpl_colors()[i]
        data = grp.loc[direction][col]
        index = data.index
        cil, cih = utils.compute_ci(data)
        ax.plot(index, data["mean"], label=f"{direction.upper()}", color=color,
                marker=".")
        ax.fill_between(index, cil, cih,
                        color=color, alpha=0.2, edgecolor="white",
                        rasterized=True)

        unit = ""
        xytext = (0, 5)
        halign = "center"
        if col == "gput":
            unit = "Mbps"

        elif col == "owd_ms":
            unit = "ms"
            if direction == "dl":
                xytext = (-1, 10)
                halign = "right"

                first = data.iloc[0]
                ax.annotate(text=f"{round(first['mean'])} ms",
                            xy=(index[0], first['mean']), xycoords="data",
                            # xytext=(3, -2), textcoords="offset points",
                            xytext=(2, 0), textcoords="offset points",
                            horizontalalignment="left",
                            verticalalignment="center",
                            color=color)
            if direction == "ul":
                xytext = (1, 5)
                halign = "left"

        mean = data.loc[5:10, "mean"].mean()
        ax.annotate(text=f"{round(mean)} {unit}",
                    xy=(7.5, mean), xycoords="data",
                    xytext=xytext, textcoords="offset points",
                    horizontalalignment=halign,
                    verticalalignment="center",
                    color=color)

    ax.legend(ncol=len(grp.index.levels[0]))
    return fig

# ---
def owd_ri_change(df):
    dfs = df.sort_values("ts_sent")
    ri_sec = compute_ri_sec(dfs["ts_sent"])
    grp_ri = dfs.groupby(["direction", "idx", (ri_sec < ri_sec.shift()).cumsum()])\
                .agg(dict(ts_sent=["min", "max", "count"], owd_ms=["mean", "median"]))
    change = grp_ri.groupby(level=[0,1], group_keys=False).apply(lambda df: df["owd_ms", "median"] - df["owd_ms", "median"].shift()).abs()
    return change

def owd_ri_change_with_sats(df):
    dfs = df.sort_values("ts_sent")
    ri_sec = compute_ri_sec(dfs["ts_sent"])
    grp_ri = dfs.groupby(["direction", "idx", (ri_sec < ri_sec.shift()).cumsum()])\
                .agg(dict(ts_sent=["min", "max", "count"], owd_ms=["mean", "median"], Connected_Satellite="last"))
    change_owd = grp_ri.groupby(level=[0, 1], group_keys=False).apply(lambda df: df["owd_ms", "median"] - df["owd_ms", "median"].shift()).abs().dropna()
    change_sat = grp_ri.groupby(level=[0, 1], group_keys=False).apply(lambda df: df.iloc[1:]["Connected_Satellite", "last"].values != df.iloc[1:]["Connected_Satellite", "last"].shift())
    change = pd.concat([change_owd.rename("owd_ms"), change_sat.rename("handover")], axis=1)
    return change

def gput_ri_change(df):
    freq = 10
    grp_a = df[~df.lost]\
        .set_index("ts_rcvd")\
        .groupby(["direction", "idx", pd.Grouper(freq=f"{freq}ms")])\
        .agg(dict(size="sum"))
    grp_a["gput"] = grp_a["size"].apply(lambda df: df * (1000/freq) * 8 / 1e6)
    grp_b = grp_a.reset_index()
    grp_b["ri_sec"] = compute_ri_sec(grp_b["ts_rcvd"])
    grp_c = grp_b.groupby(["direction", "idx", (grp_b.ri_sec < grp_b.ri_sec.shift()).cumsum()]).agg(dict(gput=["mean", "median", "count"]))
    change = grp_c.groupby(level=[0,1]).apply(lambda df: df["gput", "median"] - df["gput", "median"].shift()).abs()
    return change

def gput_ri_change_with_sats(df):
    freq = 10
    grp_a = df[~df.lost]\
        .set_index("ts_rcvd")\
        .groupby(["direction", "idx", pd.Grouper(freq=f"{freq}ms")])\
        .agg(dict(size="sum", Connected_Satellite="last"))
    grp_a["gput"] = grp_a["size"].apply(lambda df: df * (1000/freq) * 8 / 1e6)
    grp_b = grp_a.reset_index()
    grp_b["ri_sec"] = compute_ri_sec(grp_b["ts_rcvd"])
    grp_c = grp_b.groupby(["direction", "idx", (grp_b.ri_sec < grp_b.ri_sec.shift()).cumsum()])\
                 .agg(dict(gput=["mean", "median", "count"], Connected_Satellite="last"))
    change_owd = grp_c.groupby(level=[0, 1], group_keys=False).apply(lambda df: df["gput", "median"] - df["gput", "median"].shift()).abs().dropna()
    change_sat = grp_c.groupby(level=[0, 1], group_keys=False).apply(lambda df: df.iloc[1:]["Connected_Satellite", "last"].values != df.iloc[1:]["Connected_Satellite", "last"].shift())
    change = pd.concat([change_owd.rename("gput"), change_sat.rename("handover")], axis=1)
    return change

# ---

def main():
    parser = argparse.ArgumentParser()
    # Expects DL and UL csvs
    parser.add_argument("csvs", nargs="+", help="Burst measure csvs")
    parser.add_argument("--sats", nargs="+", help="Paths to csv file of connected satellites")
    parser.add_argument("--ts-key", default="ts_rcvd")
    parser.add_argument("-n", type=int)
    parser.add_argument("-b", action="store_true")
    parser.add_argument("-o")
    args = parser.parse_args()

    utils.set_plt_style()

    map_args = list(zip(args.csvs, range(len(args.csvs))))
    df = utils.parse_csvs(map_args, parse_csv, sample=args.n)

    print(f"Grouping for RI change")
    if args.sats is not None:
        sats = utils.Satellites()
        sats.parse(args.sats)
        sat_df = sats.df.Connected_Satellite
        sat_df.index = sat_df.index.tz_convert(None)
        df = pd.merge_asof(df.sort_values("ts_sent"), sat_df, left_on="ts_sent", right_index=True)

        print(f"Grouping OWD RI change")
        grp_ri_owd = owd_ri_change_with_sats(df)
        print(f"Grouping gput RI change")
        grp_ri_gput = gput_ri_change_with_sats(df)
    else:
        grp_ri_owd = owd_ri_change(df)
        grp_ri_gput = gput_ri_change(df)
        print("RI change OWD under load")
        print(grp_ri_owd.groupby(level=0).describe())
        print("RI change bandwidth")
        print(grp_ri_gput.groupby(level=0).describe())

    if args.b:
        breakpoint()

    print(f"Grouping for OWD in RI")
    grp = group_df(df, ts_key=args.ts_key)

    print(f"Plotting")
    figs = []
    figs.append(plot_in_ri(grp, "gput")) # 1
    figs.append(plot_in_ri(grp, "owd_ms")) # 2

    if args.sats is not None:
        figs.append(utils.plot_ri_change_with_handovers(grp_ri_owd,  "owd_ms", "OWD Difference [ms]", 50, 10)) # 3
        figs.append(utils.plot_ri_change_with_handovers(grp_ri_gput, "gput",   "BW Difference [Mbps]", 100, 20)) # 4
        figs[-1].get_axes()[0].annotate(text=f"(d)", **utils.SUBPLOT_TOP_STYLE)
    else:
        figs.append(utils.plot_ri_change(grp_ri_owd,  "OWD Change [ms]", 50, 10))
        figs.append(utils.plot_ri_change(grp_ri_gput, "BW Change [Mbps]", 100, 20))

    if args.o:
        print(f"Writing to {args.o}")
        with PdfPages(args.o) as pdf:
            for fig in figs:
                pdf.savefig(fig, bbox_inches="tight", pad_inches=0)
    else:
        plt.show()

if __name__ == "__main__":
    main()
