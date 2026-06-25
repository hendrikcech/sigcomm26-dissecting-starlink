#!/usr/bin/env python3

import os
import itertools
import warnings
import multiprocessing
import random

import matplotlib.pyplot as plt
import numpy as np
from cycler import cycler
import matplotlib.ticker as mticker
from scipy.stats import binom, norm, bootstrap
import pandas as pd
from tqdm import tqdm

def mpl_colors():
    return plt.rcParams['axes.prop_cycle'].by_key()['color']

def set_tab20(ax):
    colors = plt.cm.tab20(np.linspace(0, 1, 20))
    ax.set_prop_cycle(cycler("color", colors))

def plot_external_legend(parts, figsize=None, **kwargs): # ncol =
    fig = plt.figure(figsize=figsize, layout="constrained")
    lgd = fig.legend(parts, [p.get_label() for p in parts], bbox_to_anchor=(0.2, 0.5), **kwargs)
    lgd.set_in_layout(True)
    # fig.subplots_adjust(left=0.5)
    # fig.tight_layout()
    return fig

# --- Stats ---

def get_stats(d, use_bootstrap=True, statistic=np.mean, method="percentile"):
    """
    Computes statistics and the confidence interval either
    using bootstraping (slow) or by relying on the assumption
    of normal distribution. Requires scipy.

    method: "percentile" is fasted, "BCa" most accurate
    """
    kwargs = dict(method=method, statistic=statistic)
    if isinstance(d, pd.Series):
        return pd.Series(get_stats_single_col(d, use_bootstrap, **kwargs))
    results = {}
    for column in d.columns:
        # vals = d[col_name].dropna()
        res = get_stats_single_col(d[column], use_bootstrap, **kwargs)
        for k, v in res.items():
            results[(column, k)] = v
    return pd.Series(results)

def get_stats_single_col(data, use_bootstrap, **kwargs):
    result = {
        "mean": data.mean(),
        "median": data.median(),
        "std": data.std(),
        "count": data.count(),
    }
    if len(data) > 1:
        if use_bootstrap:
            res = bootstrap(
                (data,), 
                n_resamples=1000, 
                **kwargs
            )
            result["ci_low"] = res.confidence_interval.low
            result["ci_high"]  = res.confidence_interval.high
        else:
            result["ci_low"], result["ci_high"] = compute_ci(result)
    else:
        result["ci_low"] = np.nan
        result["ci_high"]  = np.nan
    return result

def compute_ci(grp):
    """Expects datframe with std, count, and mean columns"""
    ci = 1.96 * (grp["std"] / np.sqrt(grp["count"]))
    return grp["mean"] - ci, grp["mean"] + ci

def compute_median_ci(df, alpha=0.05):
    """
    df must have columns: 'mean', 'std', 'median', 'count'
    Uses the normal-data approximation.
    """
    df = df.copy()
    z = norm.ppf(1 - alpha/2)
    # valid when n > 1 and std not NaN
    valid = (df["count"] > 1) & df["std"].notna()
    se_med = np.where(valid, 1.253 * df["std"] / np.sqrt(df["count"]), np.nan)
    margin = z * se_med
    return (df["median"] - margin, df["median"] + margin)

def median_ci_raw_data(x, alpha=0.05):
    """
    Exact (distribution-free) CI for the population median using order statistics.
    x: 1D array-like of raw values (NaNs ignored)
    Returns (ci_low, ci_high).
    """
    x = np.asarray(x)
    x = x[~np.isnan(x)]
    n = len(x)
    if n == 0:
        return (np.nan, np.nan)
    x_sorted = np.sort(x)

    # smallest k such that P(Bin(n, 0.5) <= k-1) <= alpha/2
    k = int(np.floor(binom.ppf(alpha/2, n, 0.5))) + 1
    # clamp k to valid range [1, ceil(n/2)]
    k = max(1, min(k, int(np.ceil(n/2))))

    L = k
    U = n - k + 1
    return (x_sorted[L-1], x_sorted[U-1])

def mcil(x, alpha=0.05): # raw data
    return median_ci_raw_data(x, alpha)[0]

def mcih(x, alpha=0.05): # raw data
    return median_ci_raw_data(x, alpha)[1]


# --- Stats --- 

def plot_cdf_smoothed(ax, data, **kwargs):
    x = np.sort(data)
    fx = np.array(range(len(data))) / float(len(data))
    return ax.plot(x, fx, **kwargs)[0]

def plot_cdf(ax, data, ci=True, **kwargs):
    """
    Plots an emperical CDF in an (accurate) step-wise style (not smoothed).
    With ci=True (default), a 95% confidence interval is plotted which is
    estimated by bootstrapping.
    """
    x_grid = np.sort(data)
    n = len(data)
    y = np.arange(1, n + 1) / n
    
    if ci:
        # This function takes a resampled array and calculates the CDF 
        # at our fixed 'x_grid' points.
        def ecdf_statistic(resampled_data):
            # Sort the resampled batch
            sorted_sample = np.sort(resampled_data)

            # 'searchsorted' tells us how many items in the sample are <= x_grid
            # This effectively gives us the Cumulative Probability for the grid
            return np.searchsorted(sorted_sample, x_grid, side='right') / len(resampled_data)

        res = bootstrap((data,), 
                        ecdf_statistic, 
                        n_resamples=1000, 
                        confidence_level=0.95,
                        method="percentile", # BCa often fails
                        vectorized=False)

        ci_low = res.confidence_interval.low
        ci_high = res.confidence_interval.high

        ax.fill_between(x_grid, ci_low, ci_high, 
                        step="post", color=kwargs.get("color"), alpha=0.2)


    return ax.step(x_grid, y, where="post", **kwargs)[0]

# For use in groupby agg, quantile: 0-1
def groupby_q(quantile):
    fn = lambda v: v.quantile(quantile)
    fn.__name__ = f"q{quantile*100:02g}"
    return fn

# --- plot style ---
# 
# pt to inch: divide by 72
# acmsmall textwidth 395.8225pt = 5.4975347222 inch
#  
FIGSIZE = (5.5 * 0.49, 2.0)
FULL_WIDTH = 7.03 # acm double column textwidth 506.295pt = 7.03 inch;
COLUMN_WIDTH = 3.34 # single col 241.14749pt = 3.34 inch

def set_plt_style(n=6):
    pd.set_option("display.max_rows", 610)

    colors = None
    facecolor = None
    if n <= 6:
        # plt.style.use("petroff6")
        plt.style.use({
            "axes.prop_cycle": cycler('color', ['#5790fc', '#f89c20', '#e42536', '#964a8b', '#9c9ca1', '#7a21dd']),
            "patch.facecolor": "5790fc",
        })
    elif n <= 8:
        # plt.style.use("petroff8")
        plt.style.use({
            "axes.prop_cycle": cycler('color', ['#1845fb', '#ff5e02', '#c91f16', '#c849a9', '#adad7d', '#86c8dd', '#578dff', '#656364']),
            "patch.facecolor": "1845fb",
        })
    elif n <= 10:
        plt.style.use("petroff10")
    else:
        plt.style.use("petroff10")
        print(f"petroff10 colormap does not support enough colors!")

    params = {
        "axes.grid": True,
        "grid.alpha":     0.5, # 1.0
        "figure.figsize": FIGSIZE,  # (6.4, 4.8)
        # "font.family": "Linux Libertine O",
        "font.family": "Linux Biolinum O",
        "font.size": 8,
        "axes.titlepad": 4.0,      # 6.0 pad between axes and title in points
        "axes.labelpad": 2.0,      # 4.0 space between label and axis

        "legend.labelspacing": 0.25, # 0.5  # the vertical space between the legend entries
        "legend.handlelength":  1.25,  # 2.0, the length of the legend lines
        "legend.handletextpad": 0.4,  # 0.8, the space between the legend line and legend text
        ## Dimensions as fraction of font size:
        #legend.borderpad:     0.4  # border whitespace
        #legend.labelspacing:  0.5  # the vertical space between the legend entries
        #legend.handlelength:  2.0  # the length of the legend lines
        #legend.handleheight:  0.7  # the height of the legend handle
        #legend.handletextpad: 0.8  # the space between the legend line and legend text
        #legend.borderaxespad: 0.5  # the border between the axes and legend edge
        "legend.columnspacing": 1.0,  # 2.0  # column separation

        "savefig.bbox": "tight",
        "figure.constrained_layout.use": True,

        "figure.dpi": 300,
    }
    plt.style.use(params)

# First two colors from petroff6
DL_COLOR = "#5790fc"
UL_COLOR = "#f89c20"

def direction_color(direction):
    if direction.lower() == "ul":
        return UL_COLOR
    elif direction.lower() == "dl":
        return DL_COLOR
    else:
        print(f"direction_color({direction}) not found")
        return None

# SUBPLOT_LABEL_STYLE = dict(xy=(0.05, 0.95), weight="bold", ha="left", va="top", xycoords="axes fraction")
SUBPLOT_TOP_STYLE = dict(xycoords="axes fraction", xy=(0.02, 0.98), weight="bold", ha="left", va="top", size="large", zorder=20)
SUBPLOT_BOTTOM_STYLE = dict(xycoords="subfigure fraction", xy=(0.01, 0.01), weight="bold", ha="left", va="bottom", size="large", zorder=20)

# --- TCP helpers ---
# BBR1
# CUBIC
# HYSTARTPP
# SEARCH
# UDP
# BBR3
# CUBIC-NOHY

# SUSS
def cca_label(name):
    name = name.upper()
    if name == "BBR1":
        return "BBRv1"
    if name == "BBR3":
        return "BBRv3"
    if name == "HYSTARTPP":
        return "HyStart++"
    if name == "CUBIC-NOHY":
        return "CUBIC"
    if name == "CUBIC":
        return "HyStart"
    if name == "ILLINOIS":
        return "Illinois"
    if name == "LEOCC":
        return "LeoCC"
    if name == "SATPIPE":
        return "SatPipe"
    return name

def calc_tcp_gput(df):
    """
    Compute the goodput over a 100 ms window based on the number of acknowledged bytes.
    """
    df["ThruBytesAckedDiff"] = df.ThruBytesAcked - df.ThruBytesAcked.shift()
    df["tsDiffSec"] = (df.ts - df.ts.shift()).dt.total_seconds()
    roll = df.rolling(window="100ms", on="ts")[["tsDiffSec", "ThruBytesAckedDiff"]].sum()
    return roll["ThruBytesAckedDiff"] / roll["tsDiffSec"] * 8 / 1e6

def parse_tcp_csv(args):
    """
(Pdb) df.dtypes
Time                        object
State                       object
SenderMSS                    int64
ReceiverMSS                  int64
RTT                        float64
RTTVar                     float64
RTO                          int64
ATO                          int64
LastDataSent                 int64
LastDataReceived             int64
LastAckReceived              int64
ReceiverWindow               int64
SenderSSThreshold            int64 -- slow start threshold
ReceiverSSThreshold          int64
SenderWindowBytes            int64 -- always 0
SenderWindowSegs             int64 -- congestion window (cwnd)
PathMTU                      int64
CAState                     object -- open / disorder / recovery
Retransmissions              int64 -- always 0?
Backoffs                     int64
WindowOrKeepAliveProbes      int64
UnackedSegs                  int64 -- inflight
SackedSegs                   int64 -- number of currently sacked segs - correlates with CAState
LostSegs                     int64
RetransSegs                  int64 -- not monotonically, for a few measurements 1-3
ForwardAckSegs               int64 -- always 0
ReorderedSegs                int64 -- always 300
ReceiverRTT                  int64
TotalRetransSegs             int64 -- cummulative LostSegs
PacingRate                   int64
ThruBytesAcked               int64 -- Increasing
ThruBytesReceived            int64
SegsOut                      int64 -- increasing
SegsIn                       int64 -- increasing
NotSentBytes                 int64 -- send queue size?
MinRTT                     float64 -- unit ms; first packet apparently not minRTT``
DataSegsOut                  int64 -- increasing; multiply by SenderMSS for data?
DataSegsIn                   int64
BBRMaxBW                     int64 -- unit bytes per second
BBRMinRTT                  float64
BBRPacingGain                int64
BBRCongWindowGain            int64

https://pkg.go.dev/github.com/mikioh/tcpinfo#Info
https://pkg.go.dev/github.com/mikioh/tcpinfo#SysInfo
    """
    path, idx = args

    try:
        df = pd.read_csv(path)
    except Exception as e:
        print(f"Failed to parse {path}: {e}")
        return None

    if len(df) == 0:
        return None

    parts = os.path.splitext(os.path.basename(path))[0].split("_")
    df["direction"], df["cca"], df["duration_ms"] = parts[1], parts[2], int(parts[3])

    try:
        df["Time"] = pd.to_datetime(df.Time, format="ISO8601")
        df["ts"] = df.Time - df.Time.min()

        df["CAState"] = df.CAState.astype("category")
        # df["SenderWindowBytes"] = df.SenderWindowSegs * mss
        df["BBRPacingGain"] = df.BBRPacingGain / 256
        df["BBRCongWindowGain"] = df.BBRCongWindowGain / 256
        df["BBRMaxBW"] = df.BBRMaxBW * 8 / 1e6

        df["ThruBytesAckedDiff"] = df.ThruBytesAcked - df.ThruBytesAcked.shift()
        df["tsDiffSec"] = (df.ts - df.ts.shift()).dt.total_seconds()

        df["TotalRetransSegsDiff"] = (df.TotalRetransSegs - df.TotalRetransSegs.shift()).fillna(0)
    except Exception as e:
        print(f"Failed processing {path}: {e}")
        return None

    df["gput"] = calc_tcp_gput(df)

    df["idx"] = idx

    "SenderWindowSegs"
    return df[["direction", "cca", "duration_ms",
               "ts", "CAState", "SenderMSS",
               "SenderWindowSegs", "SenderSSThreshold",
               "UnackedSegs", "TotalRetransSegs", "TotalRetransSegsDiff",
               "ThruBytesAcked", "DataSegsOut",
               "ThruBytesAckedDiff", "tsDiffSec",
               "MinRTT", "RTT",
               "gput",
               "BBRMaxBW", "BBRMinRTT", "BBRPacingGain", "BBRCongWindowGain",
               "idx"]]

# ---

def parse_filename(path):
    # expects csvs file names of this pattern:
    # rate_{ul,dl}*.csv
    # owd-icmp_{ul,dl}*.csv
    # owd-udp_{ul,dl}*.csv
    filename = os.path.basename(path)
    dirname = os.path.dirname(path)
    parts = os.path.splitext(filename)[0].split("_")
    try:
        if parts[0] == "rate":
            proto = "rate"
        else:
            proto = parts[0].split("-")[1]
            assert proto in ["udp", "icmp"]
        direction = parts[1]
        assert direction in ["ul", "dl"]
        key = dirname + "_" + "_".join(parts[1:])
        return dict(direction=direction, proto=proto, key=key, path=path, parts=parts)
    except Exception as e:
        print(f"Invalid filename {filename}: {e}")
        return None

def group_files(csvs, len_grp=2):
    files = [parse_filename(csv) for csv in sorted(csvs)]
    files = [f for f in files if f is not None]
    grps_all = [[e for e in g] for (k, g) in itertools.groupby(sorted(files, key=lambda f: f["key"]), key=lambda f: f["key"])]
    grps = [g for g in grps_all if len(g) == 2]
    if len(grps_all) != len(grps):
        print(f"Incomplete groups: {len(grps_all)=} != {len(grps)=}")
    for idx, grp in enumerate(grps):
        for f in grp:
            f["idx"] = idx
    return grps

def parse_csvs(map_args, parse_fn, parallel=True, concat=True, cores=multiprocessing.cpu_count(), sample=None):
    warnings.filterwarnings("error")
    map_args = random.sample(map_args, sample) if sample is not None else map_args
    if len(map_args) == 0:
        return None
    if parallel:
        threads = min(cores, len(map_args))
        with multiprocessing.Pool(threads) as pool:
            dfs = list(tqdm(pool.imap_unordered(parse_fn, map_args), total=len(map_args), desc="parsing csvs"))
    else:
        dfs = list(tqdm(map(parse_fn, map_args), total=len(map_args)))
    warnings.resetwarnings()
    if len(dfs) == 0:
        return None
    if concat:
        return pd.concat([df for df in dfs if df is not None])
    else:
        return [df for df in dfs if df is not None]

def parse_udp_csv(path):
    try:
        df = pd.read_csv(path)
    except Exception as e:
        print(f"Failed to parse {path}: {e}")
        return None
    # Hack, if ts is a realtive ms timestamp
    if df.ts_sent.dtype == "float64":
        df["ts_sent"] = pd.to_datetime(df.ts_sent, unit="ms")
        df["ts_rcvd"] = pd.to_datetime(df.ts_rcvd, unit="ms")
    else:
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
    return df

# ---

def calc_ssexit(df, index):
    # index=["direction", "cca", "duration_ms", "idx"]
    level_all = list(range(len(index)))
    level_all_but_last = list(range(len(index) - 1))
    dfi = df.set_index(index)
    dfl = dfi[dfi.SenderSSThreshold < 2147483647]
    ssexit = dfl.groupby(level=level_all).first()[["ts", "SenderWindowSegs"]]
    ssexit["ts"] = ssexit["ts"].apply(lambda df: df.total_seconds() * 1000)
    stat = ssexit.groupby(level=level_all_but_last).agg(["mean", "median", "std", "count"])

    # Show where SS has not been left
    not_exited = dfi.groupby(level=level_all).filter(lambda df: df["SenderSSThreshold"].nunique() == 1).reset_index()["idx"].unique()
    if len(not_exited) > 0:
        total = len(dfi.index.levels)
        print(f"{len(not_exited)}/{total} runs have not exited slow start")

    return stat

# ---
def plot_ri_change(df, xlabel, xmajorticks=None, xminorticks=None):
    """Used to plot OWD bandwidth from owd.py and rate.py"""
    fig, ax = plt.subplots(figsize=(FIGSIZE[0]*2/3, 1.5*2/3))
    ax.set_ylabel("CDF")
    ax.set_xlabel(xlabel)
    if xmajorticks is not None:
        ax.xaxis.set_major_locator(mticker.MultipleLocator(xmajorticks))
    if xminorticks is not None:
        ax.xaxis.set_minor_locator(mticker.MultipleLocator(xminorticks))
    ax.yaxis.set_major_locator(mticker.MultipleLocator(0.5))
    ax.yaxis.set_minor_locator(mticker.MultipleLocator(0.1))
    for idx in df.index.levels[0]:
        data = df.loc[idx].dropna().array
        color = direction_color(idx)
        plot_cdf(ax, data, label=idx, color=color)
    return fig

def plot_ri_change_with_handovers(df, column, xlabel, xmajorticks=None, xminorticks=None):
    """
    Used to plot OWD bandwidth from owd.py and rate.py.
    df has index of (direction, ...) and columns "handover" (boolean) and `column` 
    """
    fig, ax = plt.subplots(figsize=(FULL_WIDTH/4, FULL_WIDTH/4 / 1.5)) # (FIGSIZE[0]*2/3, 1.5*2/3)
    ax.set_ylabel("CDF")
    ax.set_xlabel(xlabel)
    if xmajorticks is not None:
        ax.xaxis.set_major_locator(mticker.MultipleLocator(xmajorticks))
    if xminorticks is not None:
        ax.xaxis.set_minor_locator(mticker.MultipleLocator(xminorticks))
    ax.yaxis.set_major_locator(mticker.MultipleLocator(0.5))
    ax.yaxis.set_minor_locator(mticker.MultipleLocator(0.1))
    for idx in df.index.levels[0]: # directions
        data = df.loc[idx]
        color = direction_color(idx)
        plot_cdf(ax, data[data.handover][column], label=idx, color=color)
        plot_cdf(ax, data[~data.handover][column], color=color, linestyle="dashed")
    return fig

# --- Estimate queue size from netmeas run ---
# Requires numba dependency
def simulate_queue(df, max_queue=None, return_parts=False, ts_sent="ts_sent", ts_rcvd="ts_rcvd", tail_drop=False):
    df = df.copy()

    # If the underlying OWD rises, the queue size drops a bit earlier
    # since the queue drops are timed a bit earlier.
    # If the actual OWD drops, the estimated queue size is higher for too long.
    df["sojourn_ms"] = df["owd_ms"] - df["owd_ms"].min()

    base_owd = pd.Timedelta(df[~df.lost].owd_ms.min(), unit="ms")

    if tail_drop:
        arrivals = pd.DataFrame(df[~df.lost][[ts_sent, "seq", "owd_ms"]])
    else:
        # Packets arriving at the queue: Assume all packets (also eventually lost ones) reach the queue (i.e., ignore random in-flight packet loss)
        arrivals = pd.DataFrame(df[[ts_sent, "seq", "owd_ms"]])
    arrivals.set_index(ts_sent, inplace=True)
    arrivals["pif"] = 1

    # Packets leaving the queue: Assume that the packets have been dequeued `base_owd` before they arrive.
    # If a DL queue is simulated, the packets are dequeued a bit too early: approx. half of base_owd is probably spent on the satellite link.
    # On the UL, it's realistic.
    departures = pd.DataFrame(df[~df.lost][["seq", "owd_ms", "sojourn_ms"]])
    departures.set_index(df[~df.lost][ts_rcvd] - base_owd, inplace=True)
    departures["pif"] = -1

    if tail_drop:
        # If tail drop is simulated, dropped packets never enter the queue
        queued = pd.concat([arrivals, departures]).sort_index()
        # Fabricate empty lost dataframe
        lost = pd.DataFrame(df[df.lost][["seq", "owd_ms", "sojourn_ms"]])
        lost["pif"] = -1
        lost = lost[0:0]
    else:
        # Assume that lost packets are dropped from the queue just before they would
        # have been transmitted.
        df["sojourn_ffill_ms"] = df.sojourn_ms.interpolate()
        dfl = df[df.lost]
        lost = pd.DataFrame(dfl[["seq", "owd_ms", "sojourn_ffill_ms"]])
        lost.set_index((dfl[ts_sent] + pd.to_timedelta(dfl.sojourn_ffill_ms, unit="ms")).values, drop=True, inplace=True)
        lost.rename(columns=dict(sojourn_ffill_ms="sojourn_ms"), inplace=True)
        lost["pif"] = -1

        queued = pd.concat([arrivals, departures, lost]).sort_index()

    if max_queue is None:
        queued["queue"] = queued.pif.expanding().sum().astype(int)
    else:
        from numba import jit
        fn = jit(capped_cumsum, nopython=True)
        queued["queue"] = fn(
            queued["pif"].values,
            min_cap=0,
            max_cap=max_queue
        )

    if not return_parts:
        return queued.queue.to_frame()
    else:
        return queued.queue.to_frame(), arrivals, departures, lost

# @numba.jit(nopython=True)
def capped_cumsum(values, min_cap=0, max_cap=1500):
    n = len(values)
    result = np.empty(n, dtype=np.int64)
    current_sum = 0
    for i in range(n):
        current_sum += values[i]
        if current_sum < min_cap:
            current_sum = min_cap
        elif current_sum > max_cap:
            current_sum = max_cap
        result[i] = current_sum
    return result



class Satellites:
    """Consumes csv files produced by SatInView"""
    def parse(self, paths):
        if paths is None:
            return
        if type(paths) is not list:
            paths = [paths]
        dfs = []
        for path in paths:
            df = pd.read_csv(path)
            dfs.append(df.set_index(pd.to_datetime(df.pop("Timestamp"))))
        self.df = pd.concat(dfs).sort_index()
        # self.df = df.set_index(pd.to_datetime(df.pop("Timestamp")))

    def get_at(self, ts):
        if self.df is None:
            return None
        ts_idx = ts.floor("s").tz_localize("utc")
        try:
            return self.df.loc[ts_idx]
        except:
            print(f"Failed to find satellite at ts={ts}")
            return None
