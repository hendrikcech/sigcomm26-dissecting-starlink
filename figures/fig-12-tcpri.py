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
import multiprocessing
from itertools import pairwise

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.backends.backend_pdf import PdfPages
from tqdm import tqdm

import utils

def parse_filename(path):
    # tcp_dl_search_6000.csv
    # tcp_dl_cubic_12000.packets.csv
    # udp_dl_700_6000.csv
    filename = os.path.basename(path)
    parts = filename.split("_")
    try:
        assert len(parts) == 4
        protocol = parts[0]
        if protocol == "emu-tcp":
            protocol = "tcp"
        duration_parts = parts[3].split(".")
        if len(duration_parts) > 2 and duration_parts[1] == "packets":
            protocol += "-packets"
        return dict(protocol=protocol,
                    direction=parts[1],
                    cca=parts[2] if protocol != "udp" else "udp",
                    duration_ms=int(duration_parts[0]),
                    path=path)
    except:
        print(f"Invalid filename {filename}")
        return None

def parse_udp_csv(args):
    f, idx = args

    path = f["path"]
    df = utils.parse_udp_csv(path)
    if df is None:
        return

    ts_offset = pd.to_timedelta(f["duration_ms"] / 2, unit="ms")
    df["ts_rcvd_rel"] = df.ts_rcvd - df[~df.lost].ts_rcvd.min() - ts_offset

    if len(df[~df.lost]) == 0:
        print(f"{path}: no packet received")
        return None

    df["idx"] = idx
    df["direction"] = f["direction"]
    # df["cca"] = "udp"
    df["cca"] = f["cca"]
    df["duration_ms"] = f["duration_ms"]

    return df

def parse_tcp_csv(args):
    f, idx = args

    df = utils.parse_tcp_csv((f["path"], idx))
    if df is None:
        return None

    ts_offset = pd.to_timedelta(f["duration_ms"] / 2, unit="ms")
    df["ts_rel"] = df.ts - df.ts.min()
    df["ts_rel_ri"] = df.ts_rel - ts_offset

    df["direction"] = f["direction"]
    df["cca"] = f["cca"]
    df["duration_ms"] = f["duration_ms"]

    return df

def process_tcp_packets(args):
    f, idx = args

    path = f["path"]
    df_udp = utils.parse_udp_csv(path)
    if df_udp is None:
        return

    ts_offset = pd.to_timedelta(f["duration_ms"] / 2, unit="ms")
    df_udp["ts_sent_rel"] = df_udp.ts_sent - df_udp.ts_sent.min() - ts_offset
    df_udp["ts_rcvd_rel"] = df_udp.ts_rcvd - df_udp.ts_sent.min() - ts_offset

    df = utils.simulate_queue(df_udp, ts_sent="ts_sent_rel", ts_rcvd="ts_rcvd_rel")

    df["idx"] = idx
    df["direction"] = f["direction"]
    df["cca"] = f["cca"]
    df["duration_ms"] = f["duration_ms"]

    return df

grp_freq_ms = 50
def group_udp_df(df):
    grp_idx = df[~df.lost]\
        .set_index("ts_rcvd_rel")\
        .groupby(["direction", "cca", "idx", pd.Grouper(freq=f"{grp_freq_ms}ms")])\
        .agg(dict(size="sum", owd_ms="mean"))
    grp_idx["gput"] = grp_idx["size"].apply(lambda df: df * (1000/grp_freq_ms) * 8 / 1e6)
    # grp = grp_idx.reset_index().drop(columns=["idx", "size"])\
    #                                 .groupby(["direction", "cca", "ts_rcvd_rel"])\
    #                                 .agg(["mean", "median", "std", "count"])
    grp = grp_idx.groupby(level=[0,1,3]).apply(utils.get_stats)
    # grp = grp_idx.groupby(level=[0,1,3]).agg(["mean", "median", "std", "count"])
    return grp

def group_tcp_df(df):
    grp_idx = df\
        .set_index("ts_rel_ri")\
        .groupby(["direction", "cca", "idx", pd.Grouper(freq=f"{grp_freq_ms}ms")])\
        .agg(dict(gput="mean", RTT="mean"))
    # grp = grp_idx.groupby(level=[0,1,3]).agg(["mean", "median", "std", "count"])
    grp = grp_idx.groupby(level=[0,1,3]).apply(utils.get_stats)
    return grp

def group_queue_df(df):
    grp_idx = df\
        .groupby(["direction", "cca", "idx", pd.Grouper(freq=f"{grp_freq_ms}ms")])\
        .queue.mean()
    # grp = grp_idx.groupby(level=[0,1,3]).agg(["mean", "median", "std", "count"])
    grp = grp_idx.groupby(level=[0,1,3]).apply(utils.get_stats).unstack()
    return grp

# Order determines order of plotting and in legend
CCA_LINESTYLES = {
    "bbr1": "solid",
    "bbr3": "solid",
    "leocc": "solid",
    "satpipe": "solid",
    "illinois": "solid",
    "cubic-nohy": "solid",
    "cubic": "dashed", # hystart
    "hystartpp": "dashed",
    "search": "dashed",
    "suss": "dashed",
    "udp": "dotted",
}

CCA_COLORS = {
    "bbr1": utils.mpl_colors()[0],
    "bbr3": utils.mpl_colors()[1],
    "leocc": utils.mpl_colors()[2],
    "satpipe": utils.mpl_colors()[3],
    "illinois": utils.mpl_colors()[4],
    "cubic-nohy": utils.mpl_colors()[5],
    "cubic": utils.mpl_colors()[6], # hystart
    "hystartpp": utils.mpl_colors()[7],
    "search": utils.mpl_colors()[8],
    "suss": utils.mpl_colors()[9],
    "udp": "black",
}

def plot_on_ax(ax, grp):
    """Plot CCA lines with confidence bands onto an existing axes. Returns line artists."""
    parts = []
    for cca in grp.index.levels[0]:
        if cca not in CCA_LINESTYLES:
            print(f"WARNING: CCA {cca} in grp but not in CCA_LINESTYLES")
    for i, cca in enumerate(CCA_LINESTYLES.keys()): # control the order of lines
        color = CCA_COLORS[cca]
        try:
            data = grp.loc[cca]
        except:
            continue # not present
        # cil, cih = utils.compute_ci(data)
        try:
            cil, cih = data["ci_low"], data["ci_high"]
            index = data.index.total_seconds() * 1000
            parts.append(ax.plot(index, data["mean"],
                                 color=color,
                                 label=utils.cca_label(cca),
                                 linestyle=CCA_LINESTYLES[cca])[0])
            ax.fill_between(index, cil, cih, color=color, alpha=0.2, edgecolor="white") # color=color,
        except:
            breakpoint()
    return parts

def plot(grp, xlabel, ylabel):
    fig, ax = plt.subplots(figsize=FIGSIZE, layout="constrained")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)

    parts = plot_on_ax(ax, grp)

    fig_legend = utils.plot_external_legend(parts, ncol=np.ceil(len(parts)/2),
                                            figsize=(FIGSIZE[0], 1.3))
    return fig_legend, fig

def plot_rtt(grp):
    fig, ax = plt.subplots(figsize=FIGSIZE, layout="constrained")
    ax.set_ylabel(f"RTT [ms]")
    ax.set_xlabel(f"Receive Time [ms]")
    ax.grid(visible=True, axis="both")

    for cca in grp.index.levels[0]:
        if cca not in CCA_LINESTYLES:
            print(f"WARNING: CCA {cca} in grp but not in CCA_LINESTYLES")
    for i, cca in enumerate(CCA_LINESTYLES.keys()): # control the order of lines
        try:
            data = grp.loc[cca]
        except:
            continue
        # cil, cih = utils.compute_ci(data)
        cil, cih = data["ci_low"], data["ci_high"],
        index = data.index.total_seconds() * 1000
        color = CCA_COLORS[cca]
        ax.plot(index, data["mean"], color=color, label=utils.cca_label(cca))
        ax.fill_between(index, cil, cih, color=color, alpha=0.2, edgecolor="white")

    return fig

def plot_combined(gput, grp_queue):
    """2x2 figure: top=receive rate, bottom=queue size, left=DL, right=UL."""
    fig, axes = plt.subplots(2, 2, figsize=(utils.FULL_WIDTH, FIGSIZE[1] * 2 + 0.3),
                             layout="constrained")

    has_ul_gput = "ul" in gput.index.levels[0]
    has_ul_queue = grp_queue is not None and "ul" in grp_queue.index.levels[0]

    # Top-left: DL receive rate
    plot_on_ax(axes[0, 0], gput.loc["dl"])
    axes[0, 0].set_ylabel("Receive Rate [Mbps]")
    axes[0, 0].set_ylim(0, 400)
    # axes[0, 0].set_title("Downlink")

    # Top-right: UL receive rate
    if has_ul_gput:
        plot_on_ax(axes[0, 1], gput.loc["ul"])
        axes[0, 1].set_ylim(0, 80)
    else:
        axes[0, 1].set_visible(False)
    # axes[0, 1].set_title("Uplink")

    # Bottom-left: DL queue size
    if grp_queue is not None:
        plot_on_ax(axes[1, 0], grp_queue.loc["dl"])
    else:
        axes[1, 0].set_visible(False)
    axes[1, 0].set_ylabel("Queue Size [Packets]")
    axes[1, 0].set_xlabel("Time [ms]")

    # Bottom-right: UL queue size
    if has_ul_queue:
        plot_on_ax(axes[1, 1], grp_queue.loc["ul"])
    else:
        axes[1, 1].set_visible(False)
    axes[1, 1].set_xlabel("Time [ms]")

    # Add shared x-label to top row
    axes[0, 0].set_xlabel("Receive Time [ms]")
    axes[0, 1].set_xlabel("Receive Time [ms]")

    col_label = dict(xycoords="axes fraction", xy=(0.0, -0.26),
                     weight="bold", ha="right", va="top", size="large", zorder=20)
    axes[1][0].annotate(text="DL", **col_label)
    axes[1][1].annotate(text="UL", **col_label)

    return fig

def annotate_phases_on_top(ax):
    vline_style = dict(linestyle="dashed", color="black")
    trans = ax.get_xaxis_transform() # x in data untis, y in axes fraction
    annotate_style = dict(va="bottom", ha="center", xycoords=trans) # ma="center")
    y = 1.02

    ax.annotate("Phase 1\nSlow Start", xy=(-5500, y), **annotate_style)
    
    # Post-slwo start
    ax.axvline(-5000, **vline_style)
    ax.annotate("Phase 2\nPre-Reconf.", xy=(-2750, y), **annotate_style)

    # Reconf
    ax.axvline(-500, **vline_style)
    ax.annotate("Phase 3\nReconf.", xy=(750, y), **annotate_style)

    # Recovery
    ax.axvline(2000, **vline_style)
    ax.annotate("Phase 4\nPost-Reconf.", xy=(4000, y), **annotate_style)

def annotate_phases(ax):
    vline_style = dict(ls="dashed", color="black", zorder=2.8, lw=1) # zorder: above grid, below lines
    trans = ax.get_xaxis_transform() # x in data untis, y in axes fraction
    annotate_style = dict(va="top", ha="center", xycoords=trans,
                          weight="bold")
                          # bbox=dict(facecolor="white", alpha=0.5, edgecolor="white", boxstyle="round"))
    y = 0.98

    ax.annotate("SS", xy=(-5500, y), **annotate_style)
    
    # Post-slwo start
    ax.axvline(-5000, **vline_style)
    ax.annotate("Pre-Reconf.", xy=(-2750, y), **annotate_style)

    # Reconf
    ax.axvline(-500, **vline_style)
    ax.annotate("Reconf.", xy=(750, y), **annotate_style)

    # Recovery
    ax.axvline(2000, **vline_style)
    ax.annotate("Post-Reconf.", xy=(4000, y), **annotate_style)

# FIGSIZE=(utils.COLUMN_WIDTH/1.8, 1.5) # half column
FIGSIZE=(utils.COLUMN_WIDTH, 1.5) # full column

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csvs", nargs="+", help="Burst measure csvs")
    parser.add_argument("-b", action="store_true")
    parser.add_argument("-o")
    args = parser.parse_args()

    files = [parse_filename(csv) for csv in sorted(args.csvs)]
    tcp_files = [f for f in files if f is not None and f["protocol"] in "tcp"]
    packet_files = [f for f in files if f is not None and f["protocol"] == "tcp-packets"] # tcp, pcap-match
    udp_files = [f for f in files if f is not None and f["protocol"] == "udp"]

    tcp_args = list(zip(tcp_files, range(len(tcp_files))))
    df_tcp = utils.parse_csvs(tcp_args, parse_tcp_csv, cores=12)

    packet_args = list(zip(packet_files, range(len(packet_files))))
    df_queue = utils.parse_csvs(packet_args, process_tcp_packets, cores=12) if len(packet_args) > 0 else None

    udp_args = list(zip(udp_files, range(len(udp_files))))
    df_udp = utils.parse_csvs(udp_args, parse_udp_csv, cores=12) if len(udp_args) > 0 else None

    print(f"Grouping tcp")
    grp_tcp = group_tcp_df(df_tcp)
    print(f"Grouping queue")
    grp_queue = group_queue_df(df_queue) if df_queue is not None else None
    print(f"Grouping udp")
    grp_udp = group_udp_df(df_udp) if df_udp is not None else None
    print(f"done")

    if args.b:
        breakpoint()

    utils.set_plt_style(10)

    print("Plotting")
    figs = []

    if grp_udp is not None:
        gput = pd.concat([grp_udp["gput"], grp_tcp["gput"]]) # TODO: need to add axes?
    else:
        gput = grp_tcp["gput"]

    xlabel_recv = "Receive Time [ms]"
    xlabel_time = "Time [ms]"
    ylabel_gput = "Receive Rate [Mbps]"
    ylabel_queue = "Queue Size [Packets]"

    # gput_dl = pd.concat([grp_udp.loc["dl"]["gput"], grp_tcp.loc["dl"]["gput"]])
    figs.extend(plot(gput.loc["dl"], xlabel_recv, ylabel_gput))
    fig_legend = figs[0] # save reference to legend (first element from extend)
    figs[-1].get_axes()[0].set_ylim(0, 400)
    # annotate_phases(figs[-1].get_axes()[0])

    # Combined 2x2 figure — inserted after legend so it becomes page 2
    fig_combined = plot_combined(gput, grp_queue)
    figs.insert(1, fig_combined)

    # gput_ul = pd.concat([grp_udp.loc["ul"]["gput"], grp_tcp.loc["ul"]["gput"]])
    if "ul" in gput.index.levels[0]:
        figs.append(plot(gput.loc["ul"], xlabel_recv, ylabel_gput)[1])
        figs[-1].get_axes()[0].set_ylim(0, 80)
    # annotate_phases(figs[-1].get_axes()[0])

    if grp_queue is not None:
        figs.append(plot(grp_queue.loc["dl"], xlabel_time, ylabel_queue)[1])
        if "ul" in grp_queue.index.levels[0]:
            figs.append(plot(grp_queue.loc["ul"], xlabel_time, ylabel_queue)[1])

    figs.append(plot_rtt(grp_tcp.loc["dl"]["RTT"]))
    if "ul" in grp_tcp.index.levels[0]:
        figs.append(plot_rtt(grp_tcp.loc["ul"]["RTT"]))

    for fig in figs:
        try:
            ax = fig.get_axes()[0]
        except:
            # legend figure
            continue
        # ax.axvline(0, color="black", linewidth=2, zorder=0)
        # TODO: reenable
        # ax.set_xlim(-3000, 3000)
        # ax.set_xticks(list(range(-3000, 3001, 1500)))
        # ax.xaxis.set_major_locator(mticker.MultipleLocator(1500))
        # ax.xaxis.set_minor_locator(mticker.MultipleLocator(500))
        # ax.set_ylim(0, 300)
        # fig.tight_layout()

    if args.o:
        with PdfPages(args.o) as pdf:
            for i, fig in enumerate(figs):
                if fig is fig_combined:
                    for ax in fig.get_axes():
                        ax.set_xlim(-6000, 6000)
                        annotate_phases(ax)
                        ax.xaxis.set_major_locator(mticker.MultipleLocator(2000))
                        ax.xaxis.set_minor_locator(mticker.MultipleLocator(500))
                    pdf.savefig(fig, bbox_inches="tight", pad_inches=0)
                    continue
                try:
                    ax = fig.get_axes()[0]
                    ax.set_xlim(-500, 1000)
                    pdf.savefig(fig, bbox_inches="tight", pad_inches=0)
                except:
                    # legend figure
                    pdf.savefig(fig, bbox_inches="tight", pad_inches=0)
                    continue
                ax = fig.get_axes()[0]
                ax.set_xlim(-6000, 6000)
                ax.xaxis.set_major_locator(mticker.MultipleLocator(2000))
                ax.xaxis.set_minor_locator(mticker.MultipleLocator(500))
                annotate_phases(ax)
                pdf.savefig(fig, bbox_inches="tight", pad_inches=0)

if __name__ == "__main__":
    main()
