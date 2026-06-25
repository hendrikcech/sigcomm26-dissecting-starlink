#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "matplotlib",
#     "numpy",
#     "pandas",
#     "tqdm",
#     "pyarrow",
#     "numba",
# ]
# ///

import argparse
import os
import time

import pandas as pd
import numpy as np

import utils

# --- Step 1: Netmeas Processing
def parse_csv(args, freq_ms=1*1.33):
    path, idx = args
    csv_df = utils.parse_udp_csv(path)
    if csv_df is None:
        return csv_df

    base_ts = csv_df.ts_sent.min()
    csv_df["ts_sent_rel"] = csv_df.ts_sent - base_ts
    csv_df["ts_rcvd_rel"] = csv_df.ts_rcvd.dropna() - base_ts

    queue, arrivals, departures, lost = utils.simulate_queue(csv_df, return_parts=True)

    queue = queue.queue.copy()
    queue.index -= base_ts
    queue_res = queue.resample(f"{freq_ms}ms").last().ffill().rename("queue")

    arrivals.index -= base_ts
    arrivals_res = arrivals.resample(f"{freq_ms}ms").pif.count().fillna(0).rename("arrivals")

    departures.index -= base_ts
    departures.loc[pd.Timedelta(0)] = 0
    departures_res = departures.resample(f"{freq_ms}ms").pif.count().fillna(0).rename("departures")
    departures_res.loc[pd.Timedelta(0)] -= 1

    lost.index -= base_ts
    lost.loc[pd.Timedelta(0)] = 0
    try:
        lost_res = lost.resample(f"{freq_ms}ms").pif.count().fillna(0).rename("drops")
    except:
        print("Exception!") # no clue why that happens in a single case
        # print(f"{args}")
        # print(lost)
        # print(csv_df)
        return None
    lost_res.loc[pd.Timedelta(0)] -= 1

    # Timestamps are NaN, if no packet was sent or dropped -> ffill to close gaps
    sojourn_sim = pd.concat([departures.sojourn_ms, lost.sojourn_ms]).resample(f"{freq_ms}ms").mean().ffill().rename("sojourn_ms")

    df = pd.concat([queue_res, arrivals_res, departures_res, lost_res, sojourn_sim], axis=1)
    df = df.fillna(0).set_index(df.index.total_seconds())
    df.index.name = "ts_s"

    df["idx"] = idx

    # Assume for now
    # rate_direction_mbps_duration
    # tcp_ul_illinois_12000.packets.csv
    parts = os.path.splitext(os.path.basename(path))[0].split("_")
    # if parts[0] == "rate":
    #     # df["proto"] = "udp"
    #     # df["rate"] = int(parts[-2]) # rate or cca
    # elif parts[0] == "tcp":
    #     # df["proto"] = "tcp"
    #     # df["cca"] = parts[-2] # rate or cca
    # else:
    #     print(f"Unknown proto of {path}")
    #     return None
    df["test"] = parts[-2] # rate of UDP test or CCA of TCP test
    df["direction"] = parts[-3]
    df["duration"] = int(parts[-1].split(".")[0]) # remove possible trailing .packets
    df["hour"] = base_ts.hour

    return df

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csvs", nargs="+", help="netmeas link log files")
    parser.add_argument("-o", help="Write data to parquet file")
    parser.add_argument("-b", action="store_true")
    args = parser.parse_args()

    # utils.set_plt_style(10)
    if not args.o and not args.b:
        print(f"Why am I running?")
        return

    parse_args = list(zip(args.csvs, range(len(args.csvs))))
    df = utils.parse_csvs(parse_args, parse_csv, parallel=True)
    dfi = df.reset_index()#.set_index(["direction", "duration", "rate", "idx", "ts_s"])

    df_args = pd.DataFrame(parse_args, columns=["path", "idx"]).set_index("idx")

    if args.o:
        df_args.to_csv(args.o + ".csv")
        dfi.to_parquet(args.o)

    if args.b:
        breakpoint()

if __name__ == "__main__":
    main()
