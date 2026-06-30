#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "matplotlib",
#     "numpy",
#     "pandas",
#     "tqdm"
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
        dfs = list(tqdm(pool.imap_unordered(parse_csv, map_args), total=len(csvs), desc="parsing csvs"))
        # results = list(tqdm(map(parse_csv, map_args), total=len(csvs)))
        # dfs, losses = zip(*[res for res in results if res is not None])
        return pd.concat([df for df in dfs if df is not None])

def parse_csv(args):
    path, idx = args
    df = pd.read_csv(path)

    df["idx"] = idx

    # burst_ul_6000_0000.csv
    parts = os.path.splitext(os.path.basename(path))[0].split("_")
    df["direction"] = parts[1]
    df["size"] = int(parts[2])
    df["pad"] = int(parts[3])

    if len(df) != int(parts[2]):
        print(f"{path}: invalid size {len(df)} != {parts[2]}")
        return None

    # return df, df.lost.array
    return df

def imshow(losses):
    fig, ax = plt.subplots(dpi=300)
    ax.set_ylabel("Burst number")
    ax.set_xlabel("Packet Sequence Number")
    ax.grid(visible=False)
    # if args.size == 3000:
    #     ax.xaxis.set_ticks(list(range(0, 3001, 500)))
    # else:
    #     ax.xaxis.set_major_locator(mticker.MultipleLocator(base=500))
    ax.imshow(np.array(losses), aspect="auto", interpolation="none")
    return fig

def imshow_group(dfi, groups, samples, xmajor, xminor):
    fig, axes = plt.subplots(dpi=300, nrows=len(groups), figsize=(utils.COLUMN_WIDTH/2, 1.4), layout="none")
    fig.subplots_adjust(hspace=0.1)
    ax = None
    size = 0
    for i, (direction, size, pad) in enumerate(groups):
        ax = axes[i]
        ax.grid(visible=False)
        ax.set_ylabel(f"{pad}B")
        ax.set_xticks([])
        ax.set_yticks([])

        data = dfi.loc[direction, size, pad]
        losses = data.array.reshape(-1, size)
        print(f"{direction.upper()} {size=} {pad=}: {losses.shape[0]} samples (selected {samples})")

        # Select a random subset of rows
        #jlosses[np.random.choice(losses.shape[0], min(samples, len(losses)), replace=False), :]

        ax.imshow(losses[:samples], aspect="auto", interpolation="none", cmap="binary_r")

    if ax:
        ax.xaxis.set_major_locator(mticker.MultipleLocator(xmajor))
        ax.xaxis.set_minor_locator(mticker.MultipleLocator(xminor))
        ax.set_xlim(0, size)
        ax.set_xlabel("Sequence Number")

    return fig

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csvs", nargs="+", help="Burst measure csvs")
    parser.add_argument("-b", action="store_true")
    parser.add_argument("-o")
    args = parser.parse_args()

    df = parse_csvs(args.csvs)

    if len(df) == 0:
        print(f"No data found")
        return

    dfi = df.set_index(["direction", "size", "pad", "idx", "seq"])
    dfi = dfi["lost"]

    if args.b:
        breakpoint()

    utils.set_plt_style()

    figs = []

    dl_groups = [("dl", 3000, 0),
                 ("dl", 3000, 700),
                 ("dl", 3000, 1400)]
    ul_groups = [("ul", 10000, 0),
                 ("ul", 10000, 700),
                 ("ul", 10000, 1400)]

    try:
        figs.append(imshow_group(dfi, dl_groups, 35, 1500, 500))
        figs[-1].get_axes()[0].annotate(text=f"DL", **utils.SUBPLOT_BOTTOM_STYLE)
        figs.append(imshow_group(dfi, ul_groups, 35, 5000, 1000))
        figs[-1].get_axes()[0].annotate(text=f"UL", **utils.SUBPLOT_BOTTOM_STYLE)
    except Exception as e:
        print(f"Failed imshow_group: {e}")

    for i, direction in enumerate(dfi.index.levels[0]):
        for j, size in enumerate(dfi.index.levels[1]):
            for k, pad in enumerate(dfi.index.levels[2]):
                try:
                    data = dfi.loc[direction, size, pad]
                except:
                    continue
                print(f"{direction} {size=} {pad=}")
                losses = data.array.reshape(-1, size)
                fig = imshow(losses)
                fig.get_axes()[0].set_title(f"{direction.upper()} {size}P {pad}B")
                figs.append(fig)

    if args.o:
        with PdfPages(args.o) as pdf:
            for fig in figs:
                # fig.tight_layout()
                pdf.savefig(fig, bbox_inches="tight", pad_inches=0)
    else:
        plt.show()


if __name__ == "__main__":

    main()
