#!/usr/bin/env python3

import argparse
import os
from shutil import which

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.collections import LineCollection
from matplotlib.transforms import blended_transform_factory
from matplotlib.backends.backend_pdf import PdfPages

import utils

# overwritten in main()
freq_ms = 5 * 1.33
offset_ms = 0

def parse_csv(args):
    name, min_size, csv = args
    df = utils.parse_udp_csv(csv)
    if df is None:
        return None

    # Filter out spurious ACKs that were sent before the actual test starts
    df = df[df["size"] > min_size]
    if df.empty:
        return None

    if sum(df.owd_ms < 0) > 0:
        print(f"{csv}: {sum(df.owd_ms < 0)} negative latency samples")
        return None

    base_ts = df.ts_sent.min()
    df["ts_sent_rel"] = df.ts_sent - base_ts
    df["ts_rcvd_rel"] = df.ts_rcvd.dropna() - base_ts
    residx = pd.timedelta_range(df.ts_sent_rel.min(), df.ts_rcvd_rel.max(), freq=f"{freq_ms}ms")

    # tput = df.resample(f"{freq_ms}ms", on="ts_sent_rel")["size"].sum() * (1000/freq_ms) * 8 / 1e6
    tput = df.resample(f"{freq_ms}ms", on="ts_sent_rel")["size"].count().rename("tput")
    owd = df[~df.lost].resample(f"{freq_ms}ms", on="ts_sent_rel")["owd_ms"].mean().rename("owd")

    # df_sojourn = df[~df.lost].set_index("ts_sent_rel")["owd_ms"]
    df_sojourn = df[~df.lost]# .set_index("ts_rcvd_rel")["owd_ms"]
    df_sojourn = df_sojourn.set_index(df_sojourn.ts_rcvd_rel - pd.to_timedelta(df_sojourn.owd_ms.min(), unit="ms"))
    sojourn = df_sojourn["owd_ms"] - df_sojourn["owd_ms"].min()
    sojourn.loc[pd.Timedelta(0)] = np.nan
    sojourn = sojourn.resample(f"{freq_ms}ms").mean().rename("sojourn")

    df_loss = df[df.lost].set_index("ts_sent_rel")["size"].copy()
    df_loss.loc[pd.Timedelta(0)] = 0 # throughput and goodput should have same timestamps after resampling
    loss = df_loss.resample(f"{freq_ms}ms").count().rename("loss")
    loss.loc[pd.Timedelta(0)] -= 1

    df_gput = df[~df.lost].set_index("ts_rcvd_rel")["size"].copy()
    df_gput.loc[pd.Timedelta(0)] = 0 # throughput and goodput should have same timestamps after resampling
    # gput = df_gput.resample(f"{freq_ms}ms").sum() * (1000/freq_ms) * 8 / 1e6
    gput = df_gput.resample(f"{freq_ms}ms", offset=f"{offset_ms}ms").count().rename("gput")
    if offset_ms == 0 and len(gput) > 0:
        gput.loc[pd.Timedelta(0)] -= 1

    # queue_capped = utils.simulate_queue(df, max_queue=1500).resample(f"{freq_ms}ms").max().queue.rename("queue_capped")
    # queue_capped.index = queue_capped.index - queue_capped.index.min()

    # queue = utils.simulate_queue(df, max_queue=None).resample(f"{freq_ms}ms").max().queue.rename("queue")
    queue_df, arrivals, departures, lost = utils.simulate_queue(df, max_queue=None, return_parts=True,
                                                                ts_sent="ts_sent_rel", ts_rcvd="ts_rcvd_rel",
                                                                tail_drop=False)
    queue = queue_df.resample(f"{freq_ms}ms").max().queue.rename("queue")

    queue_arrivals = arrivals.resample(f"{freq_ms}ms").pif.count().rename("queue_arrivals")
    queue_arrivals.index -= queue_arrivals.index.min()

    departures.loc[pd.Timedelta(0)] = 0
    queue_departures = departures.resample(f"{freq_ms}ms").pif.count().rename("queue_departures")
    queue_departures.loc[pd.Timedelta(0)] -= 1

    lost.loc[pd.Timedelta(0)] = 0
    queue_drops = lost.resample(f"{freq_ms}ms").pif.count().rename("queue_drops")
    queue_drops.loc[pd.Timedelta(0)] -= 1

    df_queue_change = pd.concat([tput, loss, gput], axis=1).sort_index().ffill()
    queue_change = (df_queue_change.tput - df_queue_change.loss) - df_queue_change.gput
    queue_change = queue_change.rename("queue_change")

    # Same as sojourn: sojourn is already calculated as "sojourn time of that specific packets"
    sojourn_sim = pd.concat([departures.sojourn_ms, lost.sojourn_ms]).resample(f"{freq_ms}ms").mean().rename("sojourn_sim")

    result = pd.concat([tput, gput, owd, loss,
                        queue, queue_change, # queue_capped,
                        sojourn, sojourn_sim,
                        queue_drops, queue_departures, queue_arrivals], axis=1)

    result["queue_diff_ewm"] = result.queue.diff().ewm(5).mean()

    return name, base_ts, df.ts_sent.max(), result

# ----

def plot(ax_mbps, ax_ms, ax_packets, ax_sim, data):
    # name, min_ts, max_ts, tput, gput, owd, loss, queue_capped, queue, queue_change, sojourn = data
    name, min_ts, max_ts, df = data
    colors = dict(gput="blue", tput="orange", loss="black", queue="green")
    parts_mbps = []
    parts_ms = []
    parts_sim = []

    index = df.index.total_seconds()
    metrics = f"tput_q50={df.tput.median():.0f} gput_q50={df.gput.median():.0f} loss_q50={df.loss.median():.0f}"
    ax_mbps.set_title(f"{name}\n{metrics}")
    parts_mbps.append(ax_mbps.plot(index, df.tput, label="Send Rate", color=colors["tput"])[0])
    # parts_ms.append(ax_packets.plot(index, df.loss, label="Loss", color=colors["loss"])[0])
    parts_mbps.append(ax_mbps.plot(index, df.loss, label="Loss", color=colors["loss"])[0])
    parts_mbps.append(ax_mbps.plot(index, df.gput, label="Receive Rate", color=colors["gput"])[0])
    # parts_ms.append(ax_packets.plot(index, df.queue_capped, label="Estimated Queue (max 1500)", color=colors["queue"])[0])
    parts_ms.append(ax_packets.plot(index, df.queue, label="Estimated Queue", color=colors["queue"])[0])

    # if len(df.loss[df.loss > 0]) <= 15:
    #     for ts in df.loss[df.loss > 0].index:
    #         ax_ms.axvline(ts.total_seconds(), ymin=0, ymax=0.2, color="red", linewidth=1, alpha=0.5)
    # if "tcp" in name:
    # plot_losses(ax_ms, df.loss[df.loss > 0].index)
    loss_mask = df.queue_drops > 0
    if sum(loss_mask) > 0:
        parts_ms.append(plot_losses(ax_ms, df.queue_drops[loss_mask]))

    if ax_sim is not None:
        # parts_sim.append(ax_sim.plot(index, df.queue_drops, label="Drops", color="red", lw=1)[0])
        parts_sim.append(ax_sim.plot(index, df.queue_drops.rolling(3).mean().diff(), label="Drop Gradient", color="red", lw=1)[0])
        # parts_sim.append(ax_sim.plot(index, df.gput.diff().rolling(3).mean() * 3, label="BW Gradient", color="red", lw=1)[0])
        # parts_sim.append(ax_sim.plot(index, df.queue.diff(), label="Queue Gradient", color="grey", lw=1)[0])
        parts_sim.append(ax_sim.plot(index, df.queue.ewm(10).mean().diff(), label="Queue Gradient", color="grey", lw=1)[0])
        # parts_sim.append(ax_sim.plot(index, df.sojourn.ewm(10).mean().diff() * 10, label="Sojourn Gradient * 10", color="grey", lw=1)[0])
        # parts_sim.append(ax_sim.plot(index, df.queue_arrivals, label="Arrivals", color="grey", lw=1)[0])
        # parts_sim.append(ax_sim.plot(index, df.queue_departures, label="Departures", color="orange", lw=1)[0])
        # parts_sim.append(ax_sim.plot(index, df.queue_departures.diff().rolling(3).mean(), label="Departures Gradient", color="orange", lw=1)[0])
        # parts_sim.append(ax_sim.plot(index, df.queue_drops + df.queue_departures, label="Exits", color="black", lw=1)[0])

    # parts_ms.append(ax_ms.plot(index, df.owd, label="OWD")[0])
    sojourn_offset = df.owd.min()
    # parts_ms.append(ax_ms.plot(index, df.sojourn, label=f"Sojourn (offset {sojourn_offset:.0f} ms)")[0])
    parts_ms.append(ax_ms.plot(index, df.sojourn, label=f"Sojourn (offset {sojourn_offset:.0f} ms)")[0])
    # ax_packets.axhline(0, color="grey", lw=1, linestyle="dashed")

    # parts_mbps.append(ax_mbps.plot(queue_change.index.total_seconds(), queue_change, label="Queue Change", color="red")[0])

    title_queue = f"Queue: q10={df.queue.quantile(0.1):.0f} q50={df.queue.median():.0f} q90={df.queue.quantile(0.9):.0f} max={df.queue.max()}"
    title_sojourn = f"Sojourn: q10={df.sojourn.quantile(0.1):.0f} q50={df.sojourn.median():.0f} q90={df.sojourn.quantile(0.9):.0f} max={df.sojourn.max():.0f}"
    ax_ms.set_title(f"{title_queue} {title_sojourn}")

    scale_axes([ax_mbps, ax_ms, ax_packets, ax_sim], df.tput.index.max().total_seconds())

    return parts_mbps, parts_ms, parts_sim

def plot_losses(ax, series):
    tss, counts = series.index, series.values
    segments = [[(ts.total_seconds(), 0.9), (ts.total_seconds(), 1.0)] for ts in tss]
    alphas = [min(count * 0.1, 0.7) for count in counts]
    lc = LineCollection(segments, colors="red", linewidth=1, alpha=alphas,
                        label="Loss (head-drop ts)")
    trans = blended_transform_factory(ax.transData, ax.transAxes)
    lc.set_transform(trans)
    return ax.add_collection(lc)

def scale_axes(axes, duration):
    for ax in axes:
        if ax is None:
            continue
        ax.minorticks_on() # Enable minor ticks with auto placement
        if duration <= 2:
            ax.xaxis.set_major_locator(mticker.MultipleLocator(0.5))
            ax.xaxis.set_minor_locator(mticker.MultipleLocator(0.1))
        elif duration <= 11:
            ax.xaxis.set_major_locator(mticker.MultipleLocator(1))
            ax.xaxis.set_minor_locator(mticker.MultipleLocator(0.2))

# def format_series(ser, header=False):
#    return ser.describe().to_frame().transpose().to_string(float_format=lambda f: f"{f:.2f}", header=header, col_space=6) + "\n"

def info_str(data):
    # name, min_ts, max_ts, tput, gput, owd, loss, queue_capped, queue, queue_change, sojourn = data
    name, min_ts, max_ts, df = data
    info = f"{name}:\n"
    info += format_series(df.tput, header=True)
    info += format_series(df.gput)
    info += format_series(df.loss)
    info += format_series(df.owd)
    info += format_series(df.sojourn)
    info += format_series(df.queue)
    return info

def info_str(data):
    name, min_ts, max_ts, df = data
    info = f"{name}:\n"
    info += df.describe(percentiles=[.1,.5,.9]).transpose().to_string(float_format=lambda f: f"{f:.2f}")
    return info

def analyze(data):
    name, min_ts, max_ts, df = data
    df["queue_grad"] = df.queue.diff()
    df["sojourn_grad"] = df.sojourn.diff()
    loss_shift = df.loss.copy()
    loss_shift.index += pd.to_timedelta(df.owd.min(), unit="ms")

    loss_happened = loss_shift[loss_shift > 0]

    dfl = pd.concat([loss_shift[loss_shift > 0], df.queue, df.queue_grad, df.sojourn], axis=1).sort_index()
    pd.set_option("display.max_rows", 2000)
    breakpoint()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csvs", nargs="+", help="netmeas csvs")
    parser.add_argument("--freq-ms", default=5*1.33, type=float)
    parser.add_argument("--min-size", default=1200, type=int, help="Only consider packets larger than min-size")
    parser.add_argument("--offset-ms", default=0.0, type=float)
    parser.add_argument("--xlim", nargs=2, default=None, type=float)
    parser.add_argument("--sats", help="Path to csv file of connected satellites")
    parser.add_argument("--queue", help="Explicit queue measurements")
    parser.add_argument("-b", action="store_true")
    parser.add_argument("-o")
    args = parser.parse_args()

    utils.set_plt_style(10)

    global freq_ms
    freq_ms = args.freq_ms
    global offset_ms
    offset_ms = args.offset_ms

    sats = utils.Satellites()
    sats.parse(args.sats)

    queue = None
    if args.queue:
        queue = pd.read_csv(args.queue, names=["ts", "queue", "handle"])
        queue["ts_s"] = (queue.ts - queue.ts.min()) / 1e9
        queue["queue"] = queue.queue.astype(int)
        queue = queue.set_index("ts_s")["queue"]

        # Resample to ms
        queue.index = pd.to_timedelta(queue.index, unit="s")
        queue = queue.resample("1ms").max()
        queue.index = queue.index.total_seconds()

    map_args = [(os.path.splitext(csv)[0], args.min_size, csv) for csv in args.csvs]
    data = utils.parse_csvs(map_args, parse_csv, parallel=True, concat=False)
    if len(data) == 0:
        return

    if args.b:
        print(freq_ms)
        if len(data) > 0:
            analyze(data[0])
        else:
            breakpoint()

    if len(args.csvs) % 2 == 0:
        nrows = len(args.csvs) // 2 * 2
        ncols = 2
        figsize = (14, 2+2*nrows)
    else:
        nrows = len(args.csvs) * 2
        ncols = 1
        figsize = (8,2+2*len(args.csvs))

    fig, axes = plt.subplots(nrows=nrows, ncols=ncols,
                             squeeze=False,
                             figsize=figsize, sharex=True)
                             # gridspec_kw=dict(height_ratios=[2,2,1]))

    infos = []

    for i, d in enumerate(data):
        base_row = (i if ncols == 1 else i // 2) * 2
        col = 0 if ncols == 1 else i % 2
        ax_mbps = axes[base_row][col]
        ax_mbps.set_ylabel(f"Packets per {freq_ms} ms")
        ax_ms = axes[base_row+1][col]
        ax_ms.set_ylabel("ms")
        ax_packets = ax_ms.twinx()
        ax_packets.set_ylabel("Packets")
        # ax_sim = axes[base_row+2][col]
        # ax_sim.set_ylabel("Packets")
        # ax_packets.grid(axis="y") # turn grid off and use ax_ms grid
        # ax_sim.set_xlabel("Time [s]")

        parts_mbps, parts_ms, parts_sim = plot(ax_mbps, ax_ms, ax_packets, None, d)

        if args.sats is not None:
            matched = [sats.get_at(ts) for ts in [d[1], d[2]]]
            matched_str = set(f"{sat.Connected_Satellite} {sat.Generation}" for sat in matched for sat in matched)
            match_str = ",".join(matched_str)
            title = ax_mbps.get_title() + f" ({match_str})"
            ax_mbps.set_title(title)

        if queue is not None:
            parts_ms.append(ax_packets.plot(queue.index, queue.values, label="Measured Queue", color="tab:orange")[0])
            queue = None

        if i == 0:
            ax_mbps.legend(parts_mbps, [p.get_label() for p in parts_mbps], ncol=len(parts_mbps), loc="upper right")
            ax_ms.legend(parts_ms, [p.get_label() for p in parts_ms], ncol=len(parts_ms), loc="upper right")
            # ax_sim.legend(parts_sim, [p.get_label() for p in parts_sim], ncol=len(parts_sim), loc="upper right")

        if args.xlim is not None:
            ax_mbps.set_xlim(args.xlim[0], args.xlim[1])

        infos.append(info_str(d))

        # print("Throughput")
        # print(d[1].describe())

        # print("Queue")
        # print(d[6].describe())

    info_note = "\n".join(infos)

    if args.o:
        with PdfPages(args.o) as pdf:
            pdf.attach_note(info_note, [0,0,100,150])
            pdf.savefig(fig, pad_inches=0)
    else:
        plt.show()

if __name__ == "__main__":
    main()
