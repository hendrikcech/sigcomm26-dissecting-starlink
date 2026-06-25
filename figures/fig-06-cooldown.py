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
import itertools

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from matplotlib.backends.backend_pdf import PdfPages

from scipy.optimize import curve_fit

import utils

def parse_filename(path):
    # expects csvs file names of this pattern:
    # rate_{dl / ul}_{ms of gap between start of _a and _b}_{a / b: the run}
    # rate_dl_0200_a.csv
    # rate_dl_0200_b.csv
    folder = os.path.basename(os.path.dirname(path))
    filename = os.path.basename(path)
    parts = filename.split("_")
    try:
        assert len(parts) == 3 or len(parts) == 4
        gap = int(parts[2])
        run = parts[3].split(".")[0] if len(parts) == 4 else ""
        key = folder + "_" "_".join(parts[:3])
        return dict(direction=parts[1], gap=gap, run=run, key=key, path=path)
    except:
        print(f"Invalid filename {filename}")
        return None

def _parse_csv(path, idx):
    df = utils.parse_udp_csv(path)
    if df is None:
        return

    df["idx"] = idx

    parts = os.path.splitext(os.path.basename(path))[0].split("_")
    break_ms = parts[2]
    if break_ms == "init":
        return None
    df["break_ms"] = int(break_ms)
    df["direction"] = parts[1]
    assert parts[1] in ["dl", "ul"]

    # df["folder"] = os.path.basename(os.path.dirname(path))

    return df

def _parse_csv_add_cols(df_a, df_b):
    df_a["ts_rcvd_rel"] = df_a.ts_rcvd - df_a.ts_rcvd.min()
    df_b["ts_rcvd_rel"] = df_b.ts_rcvd - df_b.ts_rcvd.min()
    df_a["ts_rcvd_idx"] = df_a.ts_rcvd - df_a.ts_rcvd.min()
    df_b["ts_rcvd_idx"] = df_b.ts_rcvd - df_a.ts_rcvd.min()
    df_a["phase"] = 0
    df_b["phase"] = 1

def parse_csv_sameflow(args):
    path, idx = args
    df = _parse_csv(path, idx)
    if df is None:
        return None

    parts = os.path.splitext(os.path.basename(path))[0].split("_")
    break_ms = parts[2]
    if break_ms == "init":
        return None
    break_ms = int(break_ms)
    direction = parts[1]
    assert direction in ["dl", "ul"]
    # df["break_ms"] = int(break_ms)
    # df["direction"] = parts[1]

    # CDSF: one flow with 800 ms, gap, 800 ms
    # TODO: use the seq num of the last packet sent in the first 800 ms to split df_a and df_b
    # Is there no ramp up for the small gaps because we count the still-queued pre-gap packets?
    warmup_until = df.ts_sent.min() + pd.Timedelta(800, unit="ms")
    followup_start = warmup_until + pd.Timedelta(break_ms, unit="ms")
    try:
        assert warmup_until <= followup_start
    except:
        print(f"{warmup_until=} {followup_start=}")
        breakpoint()

    df = df[~df.lost]
    if df.empty:
        return

    mask_a = df.ts_sent <= warmup_until
    mask_b = df.ts_sent >= followup_start
    if not mask_a.any():
        print(f"No phase 0 in {path}")
        return None
    if not mask_b.any():
        print(f"No phase 1 in {path}")
        return None

    # df["phase"] = np.
    phases = pd.Categorical([0, 1, -1])
    df["phase"] = phases[2]
    df.loc[mask_a, "phase"] = phases[0]
    df.loc[mask_b, "phase"] = phases[1]

    mask_break = df.phase == -1
    if mask_break.sum() > 0:
        error = df[mask_break].ts_sent.max() - warmup_until
        if error > pd.Timedelta(10, unit="ms"):
            print(f"Discarded: {mask_break.sum()} P in break, {error.total_seconds() * 1000:.0f} ms error: {direction.upper()} {break_ms} ms break, {path}")
            return

    df.loc[mask_a, "ts_rcvd_rel"] = df.loc[mask_a, "ts_rcvd"] - df.loc[mask_a, "ts_rcvd"].min()
    df.loc[mask_b, "ts_rcvd_rel"] = df.loc[mask_b, "ts_rcvd"] - df.loc[mask_b, "ts_rcvd"].min()

    rows = []
    if MULTI_PARAMS:
        params = [(400, 0, 50), (700, 0, 50), (750, 0, 50),
                  (400, 0, 100), (700, 0, 100),
                  (400, 50, 50), (700, 50, 50), (750, 50, 50),
                  (0, 0, 50), (0, 0, 100)]
    else:
        # params = [(750, 0, 50)]
        params = [(0, 0, 100)]
    for (phase0_ms, phase1_ms, bin_ms) in params:
        params = f"{phase0_ms:03d}-{phase1_ms:03d}-{bin_ms:03d}"
        try:
            change = calc_change(df, phase0_ms=phase0_ms, phase1_ms=phase1_ms, bin_ms=bin_ms, relative=RELATIVE)
        except KeyError as e:
            print(f"{e} in {path} ({params=})")
            continue
        rows.append([direction, break_ms, idx, params, change])

        # if direction == "ul" and break_ms == 75 and change > 1 and len(rows) == 1:
        #     grp = df.groupby(["phase", pd.Grouper(key="ts_rcvd_rel", freq=f"{BIN_MS}ms")], observed=False)["size"].sum()
        #     print(f"{change=:.2f} {path}\n{grp}")
        #     # breakpoint()

    return rows

def calc_change(df, phase0_ms=400, phase1_ms=0, bin_ms=50, relative=True):
    grp = df.groupby(["phase", pd.Grouper(key="ts_rcvd_rel", freq=f"{bin_ms}ms")], observed=False)["size"].sum()
    phase0 = grp.loc[0, pd.Timedelta(phase0_ms, unit="ms")]
    phase1 = grp.loc[1, pd.Timedelta(phase1_ms, unit="ms")]
    if relative:
        # > 1: phase 1 throughput is greater
        return phase1 / phase0
    else:
        # > 0: phase 1 throughput is greater
        return phase1 - phase0

def parse_csv_diffflow(args):
    files, idx = args
    df_a, df_b = None, None
    for f in files:
        df = _parse_csv(f["path"], idx)
        if df is None:
            print(f"Parsing {f['path']} failed")
            return None, None
        try:
            if f["run"] == "a":
                df_a = df[~df.lost].reset_index(drop=True)
            elif f["run"] == "b":
                df_b = df[~df.lost].reset_index(drop=True)
            else:
                print(f"Unknown run {f['run']}")
                return None, None
        except:
            breakpoint()

    if df_a["ts_sent"].min() > df_b["ts_sent"].min():
        # Happens if the same break_ms was tested twice within one round
        print(f"Negative ts_rcvd_idx")
        return None, None

    _parse_csv_add_cols(df_a, df_b)

    return df_a, df_b

def plot_change(ax, grp, direction):
    try:
        grp = grp.loc[direction]
    except:
        # Data for this direction is not available
        return
    if not grp.empty:
        color = utils.direction_color(direction)
        ax.plot(grp.index, grp["median"], zorder=10,
                label=direction.upper(),
                color=color)
        ax.fill_between(grp.index, grp["ci_low"], grp["ci_high"],
                        alpha=0.2, edgecolor="white", color=color,
                        rasterized=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["sf", "sf_params", "df"])
    parser.add_argument("csvs", nargs="+", help="Burst measure csvs")
    # parser.add_argument("--relative", action="store_true", help="Plot relative received bytes instead of absolute")
    parser.add_argument("-n", type=int, help="Sample N csvs")
    parser.add_argument("-b", action="store_true")
    parser.add_argument("-o")
    args = parser.parse_args()

    utils.set_plt_style()

    global RELATIVE
    RELATIVE = True

    paths = []
    fn = None
    if args.mode.startswith("sf"):
        fn = parse_csv_sameflow
        paths = args.csvs
        global MULTI_PARAMS
        MULTI_PARAMS = args.mode == "sf_params"
    else:
        raise Exception("broken")
        fn = parse_csv_diffflow
        files = [f for f in [parse_filename(csv) for csv in sorted(args.csvs)] if f is not None]
        grps_all = [[e for e in g] for (k, g) in itertools.groupby(files, key=lambda f: f["key"])]
        paths = [g for g in grps_all if len(g) == 2]
        if len(grps_all) != len(paths):
            print(f"Invalid groups present: {len(grps_all)=} != {len(paths)=}")

    map_args = list(zip(paths, range(len(paths))))
    results = utils.parse_csvs(map_args, fn, concat=False, sample=args.n, parallel=True)
    if results is None:
        return
    # [sum(for res in results if res is None) for result in results if result is not None]
    rows = itertools.chain.from_iterable(results)
    columns = ["direction", "break_ms", "idx", "params", "change"]
    df = pd.DataFrame(rows, columns=columns)

    if args.b:
        breakpoint()

    figs = []

    for params in df.params.unique():
        print(f"Plotting {params}")
        fig, ax = plt.subplots(figsize=(utils.COLUMN_WIDTH/2, 1.1))
        if len(df.params.unique()) > 1:
            fig.suptitle(params)
        figs.append(fig)
        # grp = df[df.params == params].groupby(["direction", "break_ms"]).change.agg(["mean", "std", "median", "count", utils.mcil, utils.mcih])
        df_params = df[df.params == params]
        grp = df_params.groupby(["direction", "break_ms"])\
                       .change\
                       .apply(utils.get_stats, use_bootstrap=True, statistic=np.median)\
                       .unstack()
        print(params)
        print(grp)

        ax.set_xlabel("Break Duration [ms]")
        ax.xaxis.set_major_locator(mticker.MultipleLocator(200))
        ax.xaxis.set_minor_locator(mticker.MultipleLocator(50))
        if RELATIVE:
            # ax.set_ylabel("Relative change: B / A")
            ax.set_ylabel("B ÷ A")
            ax.axhline(1, linestyle="dashed", color="black", zorder=0, lw=1)
            ax.yaxis.set_major_locator(mticker.MultipleLocator(0.25))
            # ax.yaxis.set_minor_locator(mticker.MultipleLocator(0.2))
        else:
            ax.set_ylabel("Change after 400 ms [rcvd bytes]")

        plot_change(ax, grp, "dl")
        plot_change(ax, grp, "ul")

        # ax.legend(loc="upper right")

    if args.o:
        print("Saving plots")
        with PdfPages(args.o) as pdf:
            for fig in figs:
                # fig.suptitle(os.path.basename(args.o))
                pdf.savefig(fig, bbox_inches="tight", pad_inches=0)
    else:
        plt.show()

if __name__ == "__main__":
    main()
