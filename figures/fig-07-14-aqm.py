#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "matplotlib",
#     "numpy",
#     "pandas",
#     "pyarrow",
#     "tqdm",
# ]
# ///

import argparse

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.backends.backend_pdf import PdfPages

import utils

def plot_hist(items, key="queue", bin_size=10.0):
    """
    items e.g. [("ul", df.loc["ul", "70"]), ("dl", df.loc["dl", "300"])]
    """
    fig, axes = plt.subplots(nrows=1, sharex=True, figsize=FIGSIZE, dpi=300)
    ax = axes
    ax.set_ylabel("Frames with loss [%]")
    if key == "queue":
        ax.xaxis.set_minor_locator(mticker.MultipleLocator(100))
        ax.set_xlabel("Queue Size [Packets]")
    elif key == "sojourn_ms":
        ax.xaxis.set_minor_locator(mticker.MultipleLocator(25))
        ax.set_xlabel("Sojourn Time [ms]")
    elif key == "hour":
        ax.xaxis.set_minor_locator(mticker.MultipleLocator(1))
        ax.set_xlabel("Hour")
    ax.yaxis.set_minor_locator(mticker.MultipleLocator(10))

    # Increase height pad to prevent ylabel from being cut off
    fig.get_layout_engine().set(h_pad=0.5)

    parts = []
    for direction, lens, style in items:
        kwargs = { "label": direction.upper(),
                   "width": bin_size,
                   # "color": utils.direction_color(direction),
                   **style }

        bins = pd.cut(lens[key], np.arange(0, lens[key].max() + bin_size, bin_size))
        
        # Filter out data points that occur less than 0.001% of the time
        freq_full = lens.groupby(bins, observed=False).drops.count()
        threshold = freq_full.sum() * 0.005
        below_threshold = freq_full[freq_full.index[freq_full < threshold]]
        print(f"{kwargs['label']}: {below_threshold.count()} below threshold of {threshold:.0f} frames ({threshold * 1.33:.0f} ms)")
        freq = freq_full[freq_full > threshold]

        loss = lens[lens.drops > 0].groupby(bins, observed=False).drops.agg(["count", "median", "mean", "sum"])
        data = loss["count"] / freq * 100 # How many frames relative to all frames at each metric contain losses

        parts.append(ax.bar(data.index.categories.left, data.values, **kwargs))

        # threshold = freq.sum() * 0.001
        # below = freq[freq.index[freq < threshold]]
        # print(f"{kwargs['label']}: {below.count()} below threshold of {threshold:.0f} frames")
        # freq_norm = freq[freq >= threshold] / freq.sum() * 100

        if direction == "dl" and key == "queue" and style["label"] == "UDP 400 Mbps":
            print(freq_full)
        # if key == "queue" and style["label"] == "DL UDP 400 Mbps":
        #     breakpoint()

    # ax.legend()
    fig_legend = plot_legend(parts)

    return [fig_legend, fig]

def plot_freq(items, key="sojourn_ms", bin_size=10.0):
    fig, axes = plt.subplots(nrows=1, sharex=True, figsize=FIGSIZE, dpi=300)
    ax = axes
    ax.set_ylabel("Frequency [%]")
    if key == "queue":
        ax.xaxis.set_minor_locator(mticker.MultipleLocator(100))
        ax.yaxis.set_major_locator(mticker.MultipleLocator(5))
        ax.yaxis.set_minor_locator(mticker.MultipleLocator(1))
        ax.set_xlabel("Queue Size [Packets]")
    elif key == "sojourn_ms":
        ax.xaxis.set_minor_locator(mticker.MultipleLocator(5))
        ax.set_xlabel("Sojourn Time [ms]")
        ax.yaxis.set_minor_locator(mticker.MultipleLocator(5))
    elif key == "hour":
        ax.xaxis.set_minor_locator(mticker.MultipleLocator(1))
        ax.set_xlabel("Hour")

    parts = []
    for direction, lens, style in items:
        kwargs = { "label": direction.upper(),
                   "lw": 1,
                   # "color": utils.direction_color(direction),
                   **style }

        bins = pd.cut(lens[key], np.arange(0, lens[key].max() + bin_size, bin_size))
        
        # Filter out data points that occur less than 0.001% of the time
        freq_full = lens.groupby(bins, observed=False).drops.count()
        threshold = freq_full.sum() * 0.001
        below_threshold = freq_full[freq_full.index[freq_full < threshold]]
        # print(f"{kwargs['label']}: {below_threshold.count()} below threshold of {threshold:.0f} frames ({threshold * 1.33:.0f} ms)")
        freq = freq_full[freq_full > threshold]

        # threshold = freq.sum() * 0.001
        # below = freq[freq.index[freq < threshold]]
        # print(f"{kwargs['label']}: {below.count()} below threshold of {threshold:.0f} frames")
        # freq_norm = freq[freq >= threshold] / freq.sum() * 100
        freq_norm = freq / freq.sum() * 100 # or freq_full?
        parts.append(ax.plot(freq_norm.index.remove_unused_categories().categories.left, freq_norm,
                             drawstyle="steps-post",
                             **kwargs)[0])

    fig_legend = plot_legend(parts)

    return [fig_legend, fig]

def plot_legend(parts):
    parts = sorted(parts, key=lambda part: part.get_label()) # Alphabetical order
    ncols = 4 if len(parts) <= 4 else int(np.ceil(len(parts)/2))
    return utils.plot_external_legend(parts,
                                      figsize=(FIGSIZE[0], 0.5),
                                      ncols=ncols)

# def plot_capacity_drop_behavior(ax):
#     xs, ys = zip(*[(0, 10), (1500, 10), (1500, 100)])
#     line = ax.plot(xs, ys, lw=0.5, color="black", ls="dashed", zorder=0)[0]
#     # line.set_sketch_params(1.0, 100.0, 2.0)
# def plot_capacity_drop_behavior(ax):
#     xs, ys = zip(*[(x,5) for x in range(0, 1500, 10)], (1500, 100))
#     ax.bar(xs, ys, color="black", zorder=0,
#            label="Capacity Drop Behavior", width=10)
def plot_capacity_drop_behavior(ax):
    # xs, ys = zip(*[(x,5) for x in range(0, 1500, 10)], (1500, 100))
    xs = list(range(0, 1501, 10))
    ax.fill_betweenx([0, 100], 1490, 1510, hatch="XXXX", facecolor="white", edgecolor="black", zorder=0)
    return ax.fill_between(xs, 0, 5, hatch="XXXX", facecolor="white", edgecolor="black", zorder=0)
    # ax.plot([1500, 1500], [0, 100], color="black", lw=2, zorder=0)

FIGSIZE = (utils.COLUMN_WIDTH/2, 1.2)
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("parquet", help="Parquet from loss_input.py")
    parser.add_argument("-b", action="store_true")
    parser.add_argument("-o", required=True)
    args = parser.parse_args()

    utils.set_plt_style()

    print(f"Parsing {args.parquet}")
    df = pd.read_parquet(args.parquet)
    # df = df.reset_index().set_index(["direction", "duration", "test", "hour", "idx", "ts_s"])
    df = df.reset_index().set_index(["direction", "test", "idx", "ts_s"]).sort_index()

    # group_levels = [0, 1, 2]
    # df["queue_change_raw"] = df.groupby(level=group_levels, group_keys=False).apply(lambda df: (df.arrivals - df.departures).shift().fillna(0))
    # df["queue_change"] = df.groupby(level=group_levels).queue_change_raw.rolling(window=15, min_periods=1).mean().droplevel(group_levels)

    if args.b:
        breakpoint()

    print(f"Plotting")
    x_queue = "Queue Size [Packets]"
    x_sojourn = "Sojourn Time [ms]"
    figs = []

    ## --- Histograms ---
    # items = [("ul", df.loc["ul", "70"]), ("dl", df.loc["dl", "300"])]
    items_ul = [
        ("ul", df.loc["ul", "070"], dict(alpha=0.8, label="70 Mbps", color=utils.mpl_colors()[3])),
        ("ul", df.loc["ul", "050"], dict(alpha=0.8, label="50 Mbps", color=utils.mpl_colors()[2])),
        ("ul", df.loc["ul", "030"], dict(alpha=0.8, label="30 Mbps", color=utils.mpl_colors()[1])),
        ("ul", df.loc["ul", "015"], dict(alpha=0.8, label="15 Mbps", color=utils.mpl_colors()[0])),
        ("ul", df.loc["ul", "bbr1"], dict(alpha=0.8, label="TCP", color=utils.mpl_colors()[4])),
    ]
    figs.extend(plot_hist(items_ul, key="queue")) # 1,2
    figs[-1].get_axes()[0].annotate(text=f"UL", **utils.SUBPLOT_TOP_STYLE)

    figs.append(plot_hist(items_ul, key="sojourn_ms", bin_size=4)[1]) # 3

    items_dl = [
        ("dl", df.loc["dl", "300"], dict(alpha=0.8, label="300 Mbps", color=utils.mpl_colors()[3])),
        ("dl", df.loc["dl", "200"], dict(alpha=0.8, label="200 Mbps", color=utils.mpl_colors()[2])),
        ("dl", df.loc["dl", "bbr1"], dict(alpha=0.8, label="TCP", color=utils.mpl_colors()[4])),
        ("dl", df.loc["dl", "150"], dict(alpha=0.8, label="150 Mbps", color=utils.mpl_colors()[1])),
        ("dl", df.loc["dl", "100"], dict(alpha=0.8, label="100 Mbps", color=utils.mpl_colors()[0])),
    ]
    figs.extend(plot_hist(items_dl, key="queue", bin_size=10)) # 4,5
    figs[-1].get_axes()[0].annotate(text=f"DL",  **utils.SUBPLOT_TOP_STYLE)
    figs[-1].get_axes()[0].set_xticks([0,500,1000,1500])
    figs[-1].get_axes()[0].set_ylim(0, 70)
    # plot_capacity_drop_behavior(figs[-1].get_axes()[0])
    figs.append(plot_hist(items_dl, key="sojourn_ms", bin_size=4)[1]) # 6

    for dire in (["ul", "dl"]):
        items_tcp = [
            (dire, df.loc[dire, "bbr1"], dict(alpha=0.8, label="BBRv1", color=utils.mpl_colors()[0])),
            (dire, df.loc[dire, "bbr3"], dict(alpha=0.8, label="BBRv3", color=utils.mpl_colors()[1])),
            (dire, df.loc[dire, "illinois"], dict(alpha=0.8, label="Illinois", color=utils.mpl_colors()[2])),
            (dire, df.loc[dire, "cubic"], dict(alpha=0.8, label="CUBIC", color=utils.mpl_colors()[3])),
        ]
        figs.extend(plot_hist(items_tcp, key="queue")) # 7,8 | 11,12
        if dire == "dl":
            figs.append(plot_hist(items_tcp, key="queue")[1]) # 9
            figs[-1].get_axes()[0].set_ylim(0, 12.5)
            figs[-1].get_axes()[0].yaxis.set_minor_locator(mticker.MultipleLocator(1))
        figs.append(plot_hist(items_tcp, key="sojourn_ms", bin_size=4)[1]) # 10 | 13

    ## --- Frequency Plots ---

    freq_style = dict(alpha=0.8)

    # items_ul = [
    #     ("ul", df.loc["ul", "015"], dict(label="UDP 10 Mbps", color=utils.mpl_colors()[0], **freq_style)),
    #     ("ul", df.loc["ul", "030"], dict(label="UDP 30 Mbps", color=utils.mpl_colors()[1], **freq_style)),
    #     ("ul", df.loc["ul", "070"], dict(label="UDP 70 Mbps", color=utils.mpl_colors()[2], **freq_style)),
    #     ("ul", df.loc["ul", "bbr1"], dict(label="BBRv1", color=utils.mpl_colors()[3], **freq_style)),
    #     ("ul", df.loc["ul", "cubic-nohy"], dict(label="CUBIC", color=utils.mpl_colors()[4], **freq_style)),
    # ]
    figs.extend(plot_freq(items_ul, key="queue", bin_size=1)) # 17,18
    figs[-1].get_axes()[0].set_xlim(0, 100)
    figs.append(plot_freq(items_ul, key="sojourn_ms", bin_size=1)[1]) # 19

    # items_dl = [
    #     ("dl", df.loc["dl", "050"], dict(label="UDP 50 Mbps", color=utils.mpl_colors()[0], **freq_style)),
    #     ("dl", df.loc["dl", "400"], dict(label="UDP 150 Mbps", color=utils.mpl_colors()[1], **freq_style)),
    #     ("dl", df.loc["dl", "300"], dict(label="UDP 300 Mbps", color=utils.mpl_colors()[2], **freq_style)),
    #     ("dl", df.loc["dl", "300"], dict(label="UDP 400 Mbps", color=utils.mpl_colors()[3], **freq_style)),
    #     ("dl", df.loc["dl", "bbr1"], dict(label="BBRv1", color=utils.mpl_colors()[4], **freq_style)),
    #     ("dl", df.loc["dl", "cubic-nohy"], dict(label="CUBIC", color=utils.mpl_colors()[5], **freq_style)),
    # ]
    figs.extend(plot_freq(items_dl, key="queue", bin_size=1)) # 14,15
    # figs[-1].get_axes()[0].set_xlim(0, 200)
    figs.append(plot_freq(items_dl, key="sojourn_ms", bin_size=1)[1]) # 16
    figs[-1].get_axes()[0].set_xlim(0, 65)

    #### --- Hour ---
    # dfo = df[df.queue > 1600]
    # items_dl = [
    #     ("dl", dfo.loc["dl", "400"], dict(alpha=0.8, label="UDP 400 Mbps", color=utils.mpl_colors()[0])),
    #     ("dl", dfo.loc["dl", "300"], dict(alpha=0.8, label="UDP 300 Mbps", color=utils.mpl_colors()[1])),
    #     ("dl", dfo.loc["dl", "150"], dict(alpha=0.8, label="UDP 150 Mbps", color=utils.mpl_colors()[3])),
    # ]
    # figs.extend(plot_hist(items_dl, key="hour", bin_size=1)) # 4,5
    # figs.extend(plot_freq(items_dl, key="hour", bin_size=1)) # 14,15

    if args.o:
        with PdfPages(args.o) as pdf:
            for fig in figs:
                pdf.savefig(fig, pad_inches=0)
    else:
        plt.show()

if __name__ == "__main__":
    main()
