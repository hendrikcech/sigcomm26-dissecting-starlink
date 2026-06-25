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
import pickle

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.patches as mpatches
import matplotlib.patheffects as mpeffects
from matplotlib.lines import Line2D
from matplotlib.backends.backend_pdf import PdfPages

import utils

def parse_csv(path):
    df = utils.parse_udp_csv(path)
    if df is None:
        return None
    df["ts_sent_rel"] = df["ts_sent"] - df["ts_sent"].min()
    df["ts_rcvd_rel"] = df.ts_rcvd.dropna() - df["ts_sent"].min()
    return df

COLOR_SL=utils.mpl_colors()[2]

def plot_legend(fig, axes):
    axes[0][0].set_title(" ") # Make space for legend
    # axes[0][0].set_title("UL", loc="left", pad=0)
    # axes[0][1].set_title("DL", loc="right", pad=0)

    parts = [
        Line2D([0], [0], color=utils.direction_color("ul"), lw=2, label="Starlink UL"),
        Line2D([0], [0], color=utils.direction_color("dl"), lw=2, label="Starlink DL"),
        # Line2D([0], [0], color=utils.direction_color("dl"), lw=2, label="DL"),
        # Line2D([0], [0], color=COLOR_SL, lw=2, label="Starlink"),
        Line2D([0], [0], color="black", lw=2, label="Head Drop"),
        Line2D([0], [0], color="black", lw=2, ls=(0, (2, 1)), label="Tail Drop"),
        # Line2D([0], [0], color="gray", lw=2, label="Head Drop", path_effects=[mpeffects.withStroke(linewidth=1.5, foreground="black", alpha=1)]),
    ]
        
    fig.legend(handles=parts,
               ncol=len(parts),
               handlelength=1.0,
               loc="lower center",
               bbox_to_anchor=(0.55, 0.90),
               frameon=False)

def replot_sl(axes, data):
    for direction, xy in data.items():
        assert direction in ["UL", "DL"]
        ax = axes[0] if direction == "UL" else axes[1]
        # color = COLOR_SL
        color = utils.direction_color(direction)
        ax.plot(xy[:,0], xy[:,1], lw=1, label=direction, color=color, zorder=1)
                # zorder=4, ls="solid", lw=0.3, alpha=.8,
                # path_effects=[mpeffects.withStroke(linewidth=1, foreground="black", alpha=.8)])
                # zorder=4, ls="solid", lw=0.3, alpha=.8,
                # path_effects=[mpeffects.withStroke(linewidth=1, foreground="black", alpha=.8)])

def plot_data(ax, data, key, resample=False):
    lss = dict(head="solid", tail="--")
    for (direction, strat, df) in data:
        df = df.dropna()
        d = df[key] if key is not None else df
        # index = df.ts_sent_rel.dt.total_seconds() * 1000
        if resample:
            d = d.resample("5ms").mean()
        ax.plot(d.index.total_seconds() * 1000, d,
                label=f"{direction.upper()}: {strat}",
                # color=utils.direction_color(direction),
                color="black",
                path_effects=[mpeffects.withStroke(linewidth=1.5, foreground=utils.direction_color(direction), alpha=1)], lw=0.8,
                ls=lss[strat])

def get_alpha_emu(owd):
    return owd[owd.index > pd.Timedelta("500ms")].iloc[0]

def get_alpha_meas(owd):
    # stable value in the second half
    return owd[:,1][int(len(owd)*0.9):].min()

def get_color(emu):
    return utils.mpl_colors()[2] if emu else utils.mpl_colors()[3]

def get_arrowprops(emu, one_sided=False):
    color = get_color(emu)
    widthA = 0 if one_sided else 0.1
    return dict(arrowstyle=f"|-|, widthA={widthA}, widthB=0.1", shrinkA=0, shrinkB=0, alpha=1, color=color)

def annotate_alpha_owd(ax, alpha, emu=True):
    # color = "gray" if emu else "lightgray"
    arrowprops = get_arrowprops(emu, one_sided=True)
    ax.annotate("", xy=(1000-alpha, 0), xytext=(1000-alpha, alpha), arrowprops=arrowprops) # vertical
    ax.annotate("", xy=(1000, alpha), xytext=(1000-alpha, alpha), arrowprops=arrowprops) # horizontal

def show_beta(ax, alpha): # emu marker
    color = get_color(True)
    ax.annotate("β", xy=(1000-alpha, alpha), xytext=(1,-1), va="top", ha="left", textcoords="offset points", color=color)

def show_alpha(ax, alpha): # meas marker
    color = get_color(False)
    ax.annotate("α", xy=(1000-alpha, alpha), xytext=(0,0), va="bottom", ha="right", textcoords="offset points", color=color)

def annotate_alpha_loss(ax, alpha, y, emu=True):
    arrowprops = get_arrowprops(emu)
    ax.annotate("", xy=(1000-alpha, y), xytext=(1000, y), arrowprops=arrowprops)

def loss_rate(df):
    # grp = df.set_index("ts_sent_rel")["lost"].resample(f"{10*1.33}ms").agg(["sum", "count"])
    grp = df["lost"].resample(f"{10*1.33}ms").agg(["sum", "count"])
    return grp["sum"] / grp["count"]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ul_head", help="netmeas csv from UL head drop emulation")
    parser.add_argument("ul_tail", help="netmeas csv from UL tail drop emulation")
    parser.add_argument("dl_head", help="netmeas csv from DL head drop emulation")
    parser.add_argument("dl_tail", help="netmeas csv from DL tail drop emulation")
    parser.add_argument("pickle", help="Lines from headdrop.py")
    # parser.add_argument("--direction", choices=["ul", "dl"], required=True)
    parser.add_argument("-b", action="store_true")
    parser.add_argument("-o")
    args = parser.parse_args()

    utils.set_plt_style(2)

    figs = []

    with open(args.pickle, "rb") as f:
        lines = pickle.load(f)

    ul = [("ul", "head", parse_csv(args.ul_head).set_index("ts_sent_rel")),
          ("ul", "tail", parse_csv(args.ul_tail).set_index("ts_sent_rel"))]
    dl = [("dl", "head", parse_csv(args.dl_head).set_index("ts_sent_rel")),
          ("dl", "tail", parse_csv(args.dl_tail).set_index("ts_sent_rel"))]
    
    if args.b:
        breakpoint()

    fig, axes = plt.subplots(figsize=(utils.COLUMN_WIDTH, 2.5), nrows=3, ncols=2, sharex=False)

    plot_legend(fig, axes)

    for ax in fig.axes:
        ax.grid(axis="x", visible=False)
        ax.xaxis.set_major_locator(mticker.MultipleLocator(500))
        ax.xaxis.set_minor_locator(mticker.MultipleLocator(100))

    alpha = dict(emu=dict(ul=get_alpha_emu(ul[0][2]["owd_ms"]),
                          dl=get_alpha_emu(dl[0][2]["owd_ms"])),
                 meas=dict(ul=get_alpha_meas(lines["owd"]["UL"]),
                           dl=get_alpha_meas(lines["owd"]["DL"])))
    print(f"{alpha=}")

    ax = axes[0]
    ax[0].set_ylabel("OWD [ms]")
    ax[0].yaxis.set_major_locator(mticker.MultipleLocator(500))
    ax[0].yaxis.set_minor_locator(mticker.MultipleLocator(250))
    ax[1].yaxis.set_major_locator(mticker.MultipleLocator(50))
    ax[1].yaxis.set_minor_locator(mticker.MultipleLocator(25))
    for a in ax:
        a.set_xticks([])
    plot_data(ax[0], ul, "owd_ms", resample=True)
    plot_data(ax[1], dl, "owd_ms", resample=True)
    replot_sl(ax, lines["owd"])
    annotate_alpha_owd(ax[0], alpha["emu"]["ul"])
    show_beta(ax[0], alpha["emu"]["ul"])
    annotate_alpha_owd(ax[1], alpha["emu"]["dl"])
    annotate_alpha_owd(ax[0], alpha["meas"]["ul"], emu=False)
    show_alpha(ax[0], alpha["meas"]["ul"])
    annotate_alpha_owd(ax[1], alpha["meas"]["dl"], emu=False)
    # annotate_beta(ax[0], ul[0][2]["owd_ms"])
    # annotate_beta(ax[1], dl[0][2]["owd_ms"], offset_y=-17)
    ax[1].set_ylim(bottom=-3)

    ax = axes[1]
    ax[0].set_ylabel("Loss [%]")
    for a in ax:
        a.yaxis.set_major_locator(mticker.MultipleLocator(50))
        a.yaxis.set_minor_locator(mticker.MultipleLocator(25))
        a.set_xlabel("Packet Send Time [ms]")
    loss_ul = [(direction, strat, loss_rate(df) * 100) for (direction, strat, df) in ul]
    loss_dl = [(direction, strat, loss_rate(df) * 100) for (direction, strat, df) in dl]
    plot_data(ax[0], loss_ul, None)
    plot_data(ax[1], loss_dl, None)
    replot_sl(ax, lines["loss"])
    annotate_alpha_loss(ax[0], get_alpha_emu(ul[0][2]["owd_ms"]), y=75)
    annotate_alpha_loss(ax[0], get_alpha_meas(lines["owd"]["UL"]), y=60, emu=False)
    annotate_alpha_loss(ax[1], get_alpha_emu(dl[0][2]["owd_ms"]), y=50)
    annotate_alpha_loss(ax[1], get_alpha_meas(lines["owd"]["DL"]), y=25, emu=False)

    ax = axes[2]
    ax[0].set_ylabel("Queue [Packets]")
    ax[0].set_yticks([0, 2000, 4000])
    ax[1].yaxis.set_major_locator(mticker.MultipleLocator(750))
    for a in ax:
        a.set_xlabel("Time [ms]")
    queue_ul = [(direction, strat, utils.simulate_queue(df.reset_index(), ts_sent="ts_sent_rel", ts_rcvd="ts_rcvd_rel", tail_drop=strat == "tail"))
                for (direction, strat, df) in ul]
    queue_dl = [(direction, strat, utils.simulate_queue(df.reset_index(), ts_sent="ts_sent_rel", ts_rcvd="ts_rcvd_rel", tail_drop=strat == "tail"))
                for (direction, strat, df) in dl]
    plot_data(ax[0], queue_ul, None, resample=True)
    plot_data(ax[1], queue_dl, None, resample=True)
    replot_sl(ax, lines["queue"])

    figs.append(fig)

    if args.o:
        with PdfPages(args.o) as pdf:
            for fig in figs:
                pdf.savefig(fig, pad_inches=0)
    else:
        plt.show()

if __name__ == "__main__":
    main()
