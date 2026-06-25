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
#
import argparse
import multiprocessing
import os
import itertools

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
from tqdm import tqdm
from matplotlib.backends.backend_pdf import PdfPages

import utils

def parse_filename(path):
    # expects csvs file names of this pattern:
    # path/ul_0_elph_070.csv
    # path/ul_0_mouse_010.csv
    filename = os.path.basename(path)
    dirname = os.path.dirname(path)
    parts = filename.split("_")
    try:
        assert len(parts) == 4
        direction = parts[0]
        assert direction in ["ul", "dl"]
        idx = int(parts[1])
        animal = parts[2]
        assert animal in ["mouse", "eleph"]
        rate = int(parts[3].split(".")[0])
        key = dirname + "/" + "_".join(parts[:2])
        return dict(direction=direction, idx=idx, animal=animal, rate=rate, key=key, path=path)
    except:
        print(f"Invalid filename {filename}")
        return None

def parse_csvs(files):
    direction = None
    rate_eleph = None
    rate_mouse = None
    loss_eleph = None
    loss_mouse = None
    gput_eleph = None
    gput_mouse = None
    owd_eleph = None
    owd_mouse = None
    queue_eleph = None
    queue_mouse = None

    for f in files:
        df = utils.parse_udp_csv(f["path"])
        if df is None:
            return None

        if direction is None:
            direction = f["direction"]
        else:
            assert direction == f["direction"]

        margin = pd.Timedelta("1s")
        low, high = (df.ts_sent.min() + margin), (df.ts_sent.max() - margin)

        queue = utils.simulate_queue(df)
        queue = queue[(queue.index > low) & (queue.index < high)].queue.mean()

        df = df[(df.ts_sent > low) & (df.ts_sent < high)]

        loss = sum(df.lost) / len(df) * 100
        gput = df[~df.lost].set_index("ts_rcvd")["size"].resample("100ms").sum()\
                    .apply(lambda d: d * 1000/100 * 8 / 1e6)\
                    .mean()
        owd = df.owd_ms.mean()

        if f["animal"] == "eleph":
            assert rate_eleph is None
            rate_eleph = f["rate"]
            loss_eleph = loss
            gput_eleph = gput
            owd_eleph = owd
            queue_eleph = queue
        elif f["animal"] == "mouse":
            assert rate_mouse is None
            rate_mouse = f["rate"]
            loss_mouse = loss
            gput_mouse = gput
            owd_mouse = owd
            queue_mouse = queue
        else:
            raise Exception("Invalid animal")

    assert loss_eleph is not None and loss_mouse is not None

    loss_diff = loss_eleph - loss_mouse
    return [direction, rate_eleph, rate_mouse, loss_eleph, loss_mouse, loss_diff, gput_eleph, gput_mouse, owd_eleph, owd_mouse, queue_eleph, queue_mouse]

def plot_bars(grp, direction, metric, ylabel):
    assert direction in ["ul", "dl"]

    fig, ax = plt.subplots(figsize=(5.5 * 0.3, 1.2))
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Mouse Flow Rate [Mbps]")
    ax.grid(visible=True)

    mbps = None
    if direction == "dl":
        mbps = 700
    else:
        mbps = 70

    plot_bars_direction(ax, grp, direction, metric)

    # ax.legend(handles=[mpatches.Patch(color=mpl_colors()[0], label=f"Elephant Flow ({mbps} Mbps)"),
    #                    mpatches.patch(color=mpl_colors()[1], label="mouse flow")], loc="lower right")

    return fig

def plot_bars_direction(ax, grp, direction, metric, scatter=None):
    data = grp.loc[direction]
    _plot_bars(ax, data[f"{metric}_eleph"], ELEPH_COLORS[direction], 0.4, style_empty=scatter is not None)
    _plot_bars(ax, data[f"{metric}_mouse"], MOUSE_COLOR, 0.8, style_empty=scatter is not None)

    if scatter is not None:
        scatter = scatter.reset_index().set_index(["direction", "rate_mouse"]).sort_index()
        _plot_scatter(ax, scatter.loc[direction], f"{metric}_eleph", ELEPH_COLORS[direction], 0.4)
        _plot_scatter(ax, scatter.loc[direction], f"{metric}_mouse", MOUSE_COLOR, 0.8)

    # labels = [f"Eleph {rate_eleph:.0f}\nMouse {rate_mouse:.0f}" for (rate_eleph, rate_mouse) in data.index]
    labels = [f"{rate_mouse:.0f}" for (rate_eleph, rate_mouse) in data.index]
    ax.set_xticks([0.6 + i for i in range(len(data))], labels)

def plot_bars_fair(grp, grp_fair, direction, metric, ylabel, split_eleph=False):
    assert direction in ["ul", "dl"]
    fig, ax = plt.subplots(figsize=(5.5 * 0.3, 1.2))
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Mouse Flow Rate [Mbps]")
    ax.grid(visible=False, axis="x")
    plot_bars_split_fair(ax, grp, grp_fair, direction, metric, split_eleph=split_eleph)
    return fig

def plot_subplots(grp, grp_fair, directions, metrics, ylabels, split_eleph=False, sharey=True):
    fig, axes = plt.subplots(figsize=(utils.COLUMN_WIDTH, 1.1 * len(metrics)),
                             ncols=len(directions), nrows=len(metrics),
                             squeeze=False, sharey=sharey)
    # axes: columns, rows
    for i, axes_row in enumerate(axes):
        metric = metrics[i]
        for j, ax in enumerate(axes_row):
            if j == 0:
                ax.set_ylabel(ylabels[i])
            if i == len(axes) - 1:
                axes[i][j].set_xlabel("Mouse Flow Rate [Mbps]")
            ax.yaxis.set_minor_locator(mticker.MultipleLocator(10))
            ax.grid(visible=False, axis="x")
            plot_bars_split_fair(ax, grp, grp_fair, directions[j], metric, split_eleph=split_eleph)
            ax.annotate(text=directions[j].upper(), **utils.SUBPLOT_TOP_STYLE)
    return fig

def plot_bars_split_fair(ax, grp, grp_fair, direction, metric, split_eleph=False):
    if split_eleph:
        _plot_bars(ax, grp_fair.loc[direction, :,:,True][f"{metric}_eleph"],  ELEPH_COLORS[direction], 0.3, width=0.2)
        _plot_bars(ax, grp_fair.loc[direction, :,:,True][f"{metric}_mouse"],  MOUSE_COLOR, 0.5, width=0.2)
        _plot_bars(ax, grp_fair.loc[direction, :,:,False][f"{metric}_eleph"], ELEPH_COLORS[direction], 0.7, width=0.2, hatch=NOFAIR_HATCH)
        _plot_bars(ax, grp_fair.loc[direction, :,:,False][f"{metric}_mouse"], MOUSE_COLOR, 0.9, width=0.2, hatch=NOFAIR_HATCH)
    else:
        _plot_bars(ax, grp.loc[direction, f"{metric}_eleph"], ELEPH_COLORS[direction], 0.4)
        _plot_bars(ax, grp_fair.loc[direction, :,:,True][f"{metric}_mouse"],  MOUSE_COLOR, 0.7, width=0.2)
        _plot_bars(ax, grp_fair.loc[direction, :,:,False][f"{metric}_mouse"], MOUSE_COLOR, 0.9, width=0.2, hatch=NOFAIR_HATCH)

    # labels = [f"Eleph {rate_eleph:.0f}\nMouse {rate_mouse:.0f}" for (rate_eleph, rate_mouse) in data.index]
    labels = [f"{rate_mouse:.0f}" for rate_mouse in grp.loc[direction].index.get_level_values(1).unique()]
    ax.set_xticks([0.6 + i for i in range(len(labels))], labels)

def _plot_bars(ax, data, color, offset, style_empty=False, width=0.4, hatch=None):
    style = dict(edgecolor="black", linewidth=0.4, facecolor='none' if style_empty else color)
    xs = [offset + i for i in range(len(data))]
    ax.bar(xs, data["mean"], width=width, hatch=hatch, **style)
    # if hatch is not None:
    #     ax.bar(xs, data["mean"], width=width, facecolor="none", hatch=hatch)
    if not style_empty:
        ax.errorbar(xs, data["mean"],
                    yerr=data["std"] / 2,
                    marker="none", linestyle="none", color="black",
                    elinewidth=0.6)

def _plot_scatter(ax, df, metric, color, offset):
    for i, rate_mouse in enumerate(df.index.unique()):
        data = df.loc[rate_mouse]
        ax.scatter([offset + i] * len(data), data[metric], c=data["fair"], s=2)
        # fair = data[data["fair"]][metric]
        # nofair = data[~data["fair"]][metric]
        # ax.scatter([offset + i] * len(fair), fair, color=color, marker="1", s=2, alpha=0.5)
        # ax.scatter([offset + i] * len(nofair), nofair, color=color, marker=".", s=2, alpha=0.5)

ELEPH_COLORS = dict(dl=utils.mpl_colors()[0], ul=utils.mpl_colors()[1])
MOUSE_COLOR = utils.mpl_colors()[2]
# NOFAIR_HATCH = "oooo"
NOFAIR_HATCH = "////"

def plot_legend():
    parts = [mpatches.Patch(color=ELEPH_COLORS["dl"], label="DL Elephant Flow (250 Mbps)"),
             mpatches.Patch(color=ELEPH_COLORS["ul"], label="UL Elephant Flow (140 Mbps)"),
             mpatches.Patch(color=MOUSE_COLOR, label="Mouse Flow")]
    return utils.plot_external_legend(parts, ncols=3)

def plot_legend_fair():
    parts = [mpatches.Patch(color=ELEPH_COLORS["dl"], label="Elephant DL 250 Mbps"),
             mpatches.Patch(color=ELEPH_COLORS["ul"], label="Elephant UL 140 Mbps"),
             mpatches.Patch(facecolor=MOUSE_COLOR, edgecolor="black", linewidth=0.4,
                            label="Mouse"),
             mpatches.Patch(facecolor="white", edgecolor="white", label=""), # space
             mpatches.Patch(facecolor="white", edgecolor="black", linewidth=0.4,
                            label="Within Fair Share"), # label="Rate ≤ Fair Share"),
             mpatches.Patch(facecolor="white", edgecolor="black", linewidth=0.4, hatch=NOFAIR_HATCH,
                            label="Above Fair Share"), #label="Rate > Fair Share"),
             ]
    return utils.plot_external_legend(parts, ncols=3)


def plot_scatter(grp, df, direction, metric, ylabel):
    assert direction in ["ul", "dl"]

    # df = df.set_index(["direction", "rate_mouse"]).loc[direction].sort_index()

    fig, ax = plt.subplots(figsize=(5.5 * 0.3, 1.2))
    ax.set_ylabel(ylabel)
    ax.set_xlabel("Mouse Flow Rate [Mbps]")
    ax.grid(visible=True)

    plot_bars_direction(ax, grp, direction, metric, scatter=df)

    # ax.legend(handles=[mpatches.Patch(color=mpl_colors()[0], label=f"Elephant Flow ({mbps} Mbps)"),
    #                    mpatches.patch(color=mpl_colors()[1], label="mouse flow")], loc="lower right")

    return fig

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csvs", nargs="+", help="csvs")
    parser.add_argument("-b", action="store_true")
    parser.add_argument("-n", type=int)
    parser.add_argument("-o")
    args = parser.parse_args()

    utils.set_plt_style(2)

    files = [f for f in [parse_filename(csv) for csv in sorted(args.csvs)] if f is not None]
    grps_all = [[e for e in g] for (k, g) in itertools.groupby(files, key=lambda f: f["key"])]
    paths = [g for g in grps_all if len(g) == 2]
    if len(grps_all) != len(paths):
        print(f"Invalid groups present: {len(grps_all)=} != {len(paths)=}")

    columns = ["direction", "rate_eleph", "rate_mouse", "loss_eleph", "loss_mouse", "loss_diff", "gput_eleph", "gput_mouse", "owd_eleph", "owd_mouse", "queue_eleph", "queue_mouse"]

    rows = utils.parse_csvs(paths, parse_csvs, parallel=True, concat=False, sample=args.n)
    df = pd.DataFrame(rows, columns=columns)
    # with multiprocessing.Pool(multiprocessing.cpu_count()) as pool:
    #     rows = list(tqdm(pool.imap_unordered(parse_csvs, paths), total=len(paths), desc="Parsing csvs"))
    #     df = pd.DataFrame(rows, columns=columns)


    grp = df.groupby(["direction", "rate_eleph", "rate_mouse"]).agg(["mean", "std", "median", "count"])
    df["fair"] = ((df.gput_eleph + df.gput_mouse) / 2 >= df.rate_mouse).astype("category") # is the mouse rate within its fair share?
    df["queue_total"] = df.queue_eleph + df.queue_mouse
    grp_fair_ul = df[df.direction == "ul"].groupby(["direction", "rate_eleph", "rate_mouse", "fair"], observed=False).agg(["mean", "std", "median", "count"])
    grp_fair_dl = df[df.direction == "dl"].groupby(["direction", "rate_eleph", "rate_mouse", "fair"], observed=False).agg(["mean", "std", "median", "count"])
    grp_fair = pd.concat([grp_fair_ul, grp_fair_dl])

    print(grp_fair.loc[:, (slice(None), ["mean"])])
    print(grp_fair.loc[:, ("loss_eleph", "count")])

    if args.b:
        # df[["gput_total", "gput_eleph", "gput_mouse", "loss_mouse", "rate_mouse", "direction", "fair"]].sort_values(["direction", "rate_mouse"])
        # df.groupby(["direction", "rate_eleph", "rate_mouse", "fair"])[["loss_eleph", "loss_mouse", "owd_eleph", "owd_mouse"]].agg(["mean", "count"])
        # df.groupby(["direction", "rate_eleph", "rate_mouse", "fair"])["loss_eleph"].count()
        breakpoint()

    try:
        mouse_rates = [1, 20,35,70,140, 50,150,250,375,500]
        print(f"Only plot the following rates: {mouse_rates}")
        grp = grp.loc[:, :, mouse_rates].sort_index()
        grp_fair = grp_fair.loc[:, :, mouse_rates, :].sort_index()
    except:
        print("Failed selecting subset of rates")

    figs = []

    plt.rcParams["figure.max_open_warning"] = 30

    figs.append(plot_legend_fair()) # 1

    for split_eleph in [False, True]:
        figs.append(plot_subplots(grp, grp_fair, ["dl", "ul"], ["owd", "loss"],  ["OWD [ms]", "Loss Rate [%]"], split_eleph=split_eleph)) # 2, 10
        figs.append(plot_subplots(grp, grp_fair, ["dl", "ul"], ["owd", "loss", "queue"],  ["OWD [ms]", "Loss Rate [%]", "Queue [Packets]"], split_eleph=split_eleph, sharey=False)) # 2, 10
        figs.append(plot_bars_fair(grp, grp_fair, "dl", "owd",  "OWD [ms]", split_eleph=split_eleph)) # 2, 10
        figs.append(plot_bars_fair(grp, grp_fair, "dl", "loss",  "Loss Rate [%]", split_eleph=split_eleph)) # 3, 11
        figs.append(plot_bars_fair(grp, grp_fair, "dl", "gput",  "Received [Mbps]", split_eleph=split_eleph)) # 4, 12
        figs.append(plot_bars_fair(grp, grp_fair, "dl", "queue",  "Queue [Packets]", split_eleph=split_eleph)) # 5, 13
        figs[-1].get_axes()[0].set_ylim(-50, 1550)
        figs[-1].get_axes()[0].set_yticks([0, 500, 1000, 1500])
        figs.append(plot_bars_fair(grp, grp_fair, "ul", "owd",  "OWD [ms]", split_eleph=split_eleph)) # 6, 14
        figs.append(plot_bars_fair(grp, grp_fair, "ul", "loss",  "Loss Rate [%]", split_eleph=split_eleph)) # 7, 15
        figs.append(plot_bars_fair(grp, grp_fair, "ul", "gput",  "Received [Mbps]", split_eleph=split_eleph)) # 8, 16
        figs.append(plot_bars_fair(grp, grp_fair, "ul", "queue",  "Queue [Packets]", split_eleph=split_eleph)) # 9, 17

    figs.append(plot_legend())
    figs.append(plot_bars(grp, "dl", "loss", "Loss Rate [%]")) # 18
    figs.append(plot_bars(grp, "dl", "gput", "Received [Mbps]")) # 19
    figs.append(plot_bars(grp, "dl", "owd", "OWD [ms]")) # 20
    figs.append(plot_bars(grp, "dl", "queue", "Queue [Packets]")) # 21
    figs.append(plot_bars(grp, "ul", "loss", "Loss Rate [%]")) # 22
    figs.append(plot_bars(grp, "ul", "gput", "Received [Mbps]")) # 23
    figs.append(plot_bars(grp, "ul", "owd", "OWD [ms]")) # 24
    figs.append(plot_bars(grp, "ul", "queue", "Queue [Packets]")) # 25

    # figs.append(plot_scatter(grp, df, "ul", "loss",  "Loss Rate [%]"))
    # figs.append(plot_scatter(grp, df, "dl", "loss",  "Loss Rate [%]"))
    # figs.append(plot_scatter(grp, df, "ul", "owd",  "OWD [ms]"))
    # figs.append(plot_scatter(grp, df, "dl", "owd",  "OWD [ms]"))

    if args.o:
        with PdfPages(args.o) as pdf:
            for fig in figs:
                pdf.savefig(fig, bbox_inches="tight", pad_inches=0)
    else:
        plt.show()

if __name__ == "__main__":
    main()
