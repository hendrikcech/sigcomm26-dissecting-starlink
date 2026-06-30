#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "matplotlib",
#     "numpy",
#     "pandas",
#     "tqdm",
#     "scipy",
#     "tqdm",
# ]
# ///

import argparse

import numpy as np
import pandas as pd
from pandas.api.types import CategoricalDtype
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from scipy import stats
from tqdm.auto import tqdm

import utils

def parse_csv(args):
    path, idx, group = args

    df = utils.parse_tcp_csv((path, idx))
    if df is None:
        return None

    df["group"] = group
    # if "nopacing" in path:
    #     df["pacing"] = False
    # elif "pacing" in path:
    #     df["pacing"] = True
    # else:
    #     print(f"Failed to find (no)pacing in path: {path}")
    #     return None

    return df

def scratchpad(df):
    # dfl = df[df.idx == 0]
    # dff = dfl[["ts", "TotalRetransSegs", "SenderWindowSegs", "CAState", "SenderSSThreshold", "RTT"]]
    # dff.groupby([(dff.TotalRetransSegs.shift() != dff.TotalRetransSegs).cumsum()])["SenderWindowSegs"].last()
    # Look at cwnd and not PIF: PIF is inflated by the retransmission of packets
    grp = df.groupby(["direction", "cca", "duration_ms", (df.TotalRetransSegs.shift() != df.TotalRetransSegs).cumsum()])["SenderWindowSegs"].last()
    grpagg = grp.loc[:,:,3000].groupby(level=[0,1])
    print(grpagg.describe())
    # grpagg.hist(cumulative=True, density=True, histtype='step', bins=100, legend=True) # CDF
    grpagg.hist(cumulative=False, density=True, histtype='bar', bins=100, legend=True) # CDF
    plt.savefig("/tmp/tcp.pdf")
    plt.clf()

def gput_ack(df):
    # mss = df.SenderMSS.unique()[0]
    return df.set_index("ts").ThruBytesAcked.diff().fillna(0).resample("100ms").sum() * 8 / 1e6
    # return df.set_index("ts").DataSegsOut.diff().fillna(0).resample("100ms").sum() * mss * 8 / 1e6

def gput_raw(df, index_cols):
    dfi = df.set_index(index_cols)
    dfg = dfi.groupby(level=list(range(len(index_cols))), observed=True).rolling(window="100ms", on="ts")[["tsDiffSec", "ThruBytesAckedDiff"]].sum()
    return dfg["ThruBytesAckedDiff"] / dfg["tsDiffSec"] * 8 / 1e6

def group_gput(gput):
    return gput.groupby(level=list(range(len(gput.index.levels)-1)), observed=True).agg(["mean", "median", "std", "count"])

    # data = df[df.idx == 0]
    # data["ThruBytesAckedDiff"] = data.ThruBytesAcked - data.ThruBytesAcked.shift()
    # data["tsDiffSec"] = (data.ts - data.ts.shift()).dt.total_seconds()
    # # data.rolling(window="100ms", on="ts").ThruBytesAckedDiff.sum()
    # # data.rolling(window="100ms", on="ts")[["tsDiff", "ThruBytesAckedDiff"]].apply(lambda df: df.ThruBytesAckedDiff.sum())
    # roll = data.rolling(window="100ms", on="ts")[["tsDiffSec", "ThruBytesAckedDiff"]].sum()
    # gput = roll["ThruBytesAckedDiff"] / roll["tsDiffSec"] * 8 / 1e6 # data["gput"]

    # Estimate rate
    # (df.SenderWindowSegs * df.SenderMSS) / (df.RTT / 1000) * 8 / 1e6
    # (df.UnackedSegs * df.SenderMSS) / (df.RTT / 1000) * 8 / 1e6
    # (df.ThruBytesAcked - df.ThruBytesAcked.shift()) / ((df.ts - df.ts.shift()).dt.total_seconds() / 1) * 8 / 1e6

def size_of_loss_groups(df):
    dfi = df.set_index(index_cols)
    # only consider transfers where at least one packet was dropped
    # dfi[(dfi.TotalRetransSegsDiff > 0) & ].groupby(level=[0,1,2]).TotalRetransSegsDiff.describe()
    grp = dfi.groupby(level=list(range(len(index_cols))))["TotalRetransSegs"].agg(["min", "max"])
    grp["total"] = grp["max"] - grp["min"]
    return grp.groupby(level=[0,1,2,3]).total.describe()
    # return dfi.groupby(level=list(range(len(index_cols))))["TotalRetransSegs"].max().groupby(level=[0,1,2,3]).describe()

def calc_ssexit(df):
    return utils.calc_ssexit(df, ["direction", "cca", "duration_ms", "group", "idx"])

# ---- stats ----

def compute_p(df, effect_size=False, alternative="greater"):
    tests = df.reset_index().set_index(["direction", "cca"]).index.unique()
    result = []
    it = tqdm(tests, desc="compute_p") if effect_size else tests
    for (direction, cca) in it:
        if effect_size:
            print((direction, cca))
        pacing = df.loc[direction, cca, :, "a"].dropna()
        nopacing = df.loc[direction, cca, :, "b"].dropna()
        stat = stats.mannwhitneyu(pacing, nopacing, alternative=alternative)
        count_pacing = pacing.index.get_level_values(1).nunique() # count unique idx
        count_nopacing = nopacing.index.get_level_values(1).nunique() # count unique idx
        effect = cliffs_delta(pacing, nopacing) if effect_size else -1
        result.append((direction, cca, stat.pvalue, stat.pvalue < 0.05, effect, pacing.mean(), nopacing.mean(), count_pacing, count_nopacing))
    return pd.DataFrame(result, columns=["direction", "cca", "pvalue", "significant", "effect_size", "pacing_mean", "nopacing_mean", "pacing_count", "nopacing_count"])

def cliffs_delta(lst1, lst2):
    """
    Calculates Cliff's Delta statistic.
    Interpretation:
    - 0: Distributions overlap completely.
    - 1 or -1: No overlap at all.
    """
    m, n = len(lst1), len(lst2)
    lst2 = np.array(lst2) # Use numpy for speed
    
    more = 0
    less = 0
    
    # Compare every item in lst1 to every item in lst2
    # (Note: This simple loop can be slow for massive N > 10,000)
    for x in lst1:
        more += np.sum(x > lst2)
        less += np.sum(x < lst2)
        
    d = (more - less) / (m * n)
    return d

# ----

def label_phases(df, tss):
    phases = CategoricalDtype(categories=["ss", "pre", "reconf", "post"], ordered=True)
    df.loc[(tss < pd.Timedelta("1s")), "phase"] = "ss" # slow start
    df.loc[(pd.Timedelta("1s") < tss) & (tss <= pd.Timedelta("5500ms")), "phase"] = "pre" # pre-reconf
    df.loc[(pd.Timedelta("5500ms") < tss) & (tss <= pd.Timedelta("7s")), "phase"] = "reconf" # reconf
    df.loc[(pd.Timedelta("7s") < tss) & (tss <= pd.Timedelta("11s")), "phase"] = "post" # post-reconf
    df["phase"] = df["phase"].astype(phases)
    return df

index_cols = ["direction", "cca", "duration_ms", "group", "idx"]
index_cols_phases = ["direction", "phase", "cca", "duration_ms", "group", "idx"]

def main():
    parser = argparse.ArgumentParser()
    # parser.add_argument("csvs", nargs="+", help="TCP csvs")
    # parser.add_argument("-a", nargs="+", help="TCP csvs of group A")
    # parser.add_argument("-b", nargs="+", help="TCP csvs of group B")
    parser.add_argument("-g", "--group", action="append", nargs="+", 
                        help="Group name followed by its CSVs. e.g., -g A file1.csv file2.csv")
    parser.add_argument("-b", action="store_true")
    # parser.add_argument("--ccas", nargs="*", help="Filter specific CCAs")
    parser.add_argument("-o")
    args = parser.parse_args()

    pd.set_option("display.max_rows", 610)
    pd.set_option('display.float_format', lambda x: '%.3f' % x)

    map_args = []
    for group in args.group:
        group_name = group[0]
        group_files = group[1:]
        map_args += list(zip(group_files, range(len(group_files)), [group_name] * len(group_files)))
    df = utils.parse_csvs(map_args, parse_csv)

    if df is None:
        return
    group_type = CategoricalDtype(categories=[g[0] for g in args.group], ordered=True)
    df["group"] = df.group.astype(group_type)

    df = df.reset_index(drop=True)
    df = label_phases(df, df.ts)
    dfi = df.set_index(index_cols)

    results = []

    print("Grouping")
    gput = gput_raw(df, index_cols=index_cols)
    grp_gput = group_gput(gput)

    gput_phases = gput_raw(df, index_cols=index_cols_phases)
    grp_gput_phases = group_gput(gput_phases)
    gput_phases = grp_gput_phases\
        .groupby(level=list(range(len(grp_gput_phases.index.levels)-1)), observed=True)\
        .mean()
        # .loc[:,:,:,12000, "b"] # select nopacing
    results.append("Receive Rate [Mbps]")
    results.append(gput_phases.to_string())

    # ssexit = calc_ssexit(df)
    
    # size_loss_groups = size_of_loss_groups(df)
    # total_retrans = dfi.groupby(level=list(range(len(index_cols))))["TotalRetransSegs"].max()
    # compute_p(total_retrans, effect_size=True) # not significant

    # How often do retransmissions occur? Not significant: why is pacing yielding a higher receive rate?
    # retrans_count = dfi.groupby(level=list(range(len(index_cols)))).apply(lambda df: (df.TotalRetransSegsDiff != 0).sum())
    # compute_p(retrans_count, effect_size=True) # not significant
    retrans_phases = df.groupby(index_cols_phases, observed=True)\
                       .apply(lambda df: (df.TotalRetransSegsDiff != 0).sum(), include_groups=False)\
                       .groupby(level=[0,1,2,3,4], observed=True)\
                       .describe()
                       # .loc[:,:,:,12000, "b"] # select nopacing
    results.append("Number of Retransmission Occurrences")
    results.append(retrans_phases.to_string())

    retrans_packets_phases = df.groupby(index_cols_phases, observed=True)\
                               .TotalRetransSegsDiff.sum() \
                               .groupby(level=[0,1,2,3,4], observed=True)\
                               .describe()
                               # .loc[:,:,:,12000, "b"] # select nopacing
    results.append("Number of Retransmitted Packets")
    results.append(retrans_packets_phases.to_string())

    if args.b:
        # BBR example:
        # dfi.loc["dl", "bbr3", 6000, 619][["ts", "CAState", "SenderSSThreshold", "SenderWindowSegs", "UnackedSegs", "TotalRetransSegs", "RTT", "gput", 'BBRMaxBW', 'BBRMinRTT', 'BBRPacingGain', 'BBRCongWindowGain']]
        breakpoint()

    if args.o:
        with open(args.o, "w") as f:
            result_str = "\n".join(results)
            print(result_str)
            f.write(result_str)
            f.write("\n")

    # rtt_mean = dfi.groupby(level=[0,1,2,3,4]).RTT.mean() / median
    # compute_p(rtt_median, effect_size=False, alternative="less") # is significant for all on the DL
    #


    # groupby_levels = [0,1,2,3,4]
    # grp_gput_idx = gput.groupby(level=groupby_levels).mean()
    # gput_phases = split_into_phases(gput, gput.index.get_level_values(5))
    # gput_phases = [ v.groupby(level=groupby_levels).mean() for v in gput_phases]

    # try:
    #     print(f"""
    # ssexit:
    # {ssexit.astype(int)}

    # goodput:
    # {grp_gput.astype(int)}

    # size loss groups:
    # {size_loss_groups.astype(int)}
    #     """)
    # except:
    #     print(f"Failed to print dfs")

    # print("Computing stats")
    # stat_result_full = compute_p(grp_gput_idx, effect_size=True)

    # stat_result_phases = [compute_p(v, effect_size=True) for v in gput_phases]
    # print(stat_result_full)
    # for i, v in enumerate(stat_result_phases):
    #     print(f"Phase {i}\n{v}")
            # f.write(stat_result_full.set_index(["direction", "cca"]).to_string())
            # f.write("\n\nA\n")
            # f.write(stat_result_a.set_index(["direction", "cca"]).to_string())
            # f.write("\n\nB\n")
            # f.write(stat_result_b.set_index(["direction", "cca"]).to_string())
            # f.write("\n\nC\n")
            # f.write(stat_result_c.set_index(["direction", "cca"]).to_string())
            # f.write("\n\nD\n")
            # f.write(stat_result_d.set_index(["direction", "cca"]).to_string())

if __name__ == "__main__":
    main()
