# SIGCOMM'26: Dissecting the StarLink

This repository contains the scripts and references accompanying the SIGCOMM'26 paper "Dissecting the StarLink: Characterizing Queuing and Flow Dynamics in the Starlink Network" ([ACM](https://dl.acm.org/doi/abs/10.1145/3789240.3829162)).

> **Measurement Tool** -- [NetScalpel](https://github.com/hendrikcech/NetScalpel), the custom network measurement tool used for all experiments in this paper.
>
> **Dataset** -- [mediaTUM](https://doi.org/10.14459/2026mp1856124), the complete measurement dataset analyzed in the paper.

If you use this repository or dataset in your research, please cite our paper:

<details>
<summary>BibTeX</summary>

```bibtex
@inbook{cech2026starlink,
author = {Cech, Hendrik and Mohan, Nitinder and Ott, J{\"o}rg},
title = {Dissecting the StarLink: Characterizing Queuing and Flow Dynamics in the Starlink Network},
year = {2026},
isbn = {9798400724671},
publisher = {Association for Computing Machinery},
address = {New York, NY, USA},
url = {https://doi.org/10.1145/3789240.3829162},
abstract = {Starlink has become the largest commercial LEO satellite network, yet little is known about its internal queue management and bandwidth allocation mechanisms. Prior measurement studies have documented performance variations but lack the granularity to explain the underlying causes. We present the first microscopic characterization of Starlink's transmission behavior, using controlled measurements from multiple terminals to capture per-packet dynamics at microsecond precision. Our analysis uncovers several previously undocumented mechanisms. Starlink employs head-drop queuing rather than tail-drop, with capacities of approximately 1500 and 4000 packets on downlink and uplink, respectively. Bandwidth allocation is demand-driven, starting from a baseline of 100/30 Mbps on the downlink and uplink that ramps up by 3.4{\texttimes}/2{\texttimes} over 400 ms when flows sustain queue pressure. Active queue management aggressively induces packet loss to control queue occupancy, especially on the uplink. These mechanisms reset every 15 seconds during Starlink's reconfiguration cycle. We also find flow-level queuing that isolates latency between concurrent flows while coupling their loss on the downlink. These findings reveal that Starlink's queue management creates fundamentally different operating conditions than terrestrial networks.},
booktitle = {Proceedings of the ACM SIGCOMM 2026 Conference},
pages = {1475–1495},
numpages = {21}
}
```

</details>

## Repository Structure

```
figures/       Figure-generation scripts (one per paper figure)
tcp/           TCP pcap-matching script
netns_model/   Network namespace model for queue validation experiments (Fig. 4)
linux-tcp/     Kernel patches for additional TCP CCAs and slow-start algorithms
```

## Dataset
The dataset is hosted on [mediaTUM](https://doi.org/10.14459/2026mp1856124) and can be downloaded in whole or in part using `rsync`.
The full dataset has a size of 456 GB.
The plotting scripts, however, **only require the csv files from the dataset**.
Cloning only the csv files reduces the download to 173 GB (see the last example below).

```bash
# List the contents of the dataset
$ rsync rsync://m1856124@dataserv.ub.tum.de/m1856124/

# Download a specific subset (e.g., the netns results)
$ rsync -Pr rsync://m1856124@dataserv.ub.tum.de/m1856124/netns .

# Only download csv files (sufficient for all plotting tasks)
$ rsync -Pr rsync://m1856124@dataserv.ub.tum.de/m1856124/ . --include='*/' --include='*.csv' --exclude='*'
```

### Dataset Folders

The folders contain data from our vantage point (VP) in Munich, Germany, if not otherwise noted.

| Folder | Full Size | CSV-only Size | Tasks | Description |
|--------|-----------|---------------|-------|-------------|
| `burst` | 1.7 GB | 660 MB | `fig-03` | Burst-size probing experiments |
| `cooldown_highrate` | 59 GB | 19 GB | `fig-06` | Cooldown experiments with high send rates (UL=140, DL=500 Mbps) |
| `cooldown_lowrate` | 38 GB | 12 GB | `fig-16` | Cooldown experiments with lower send rates (UL=70, DL=300 Mbps) |
| `mouseeleph_dl_250` | 9.5 GB | 3.0 GB | `fig-10-15`, `fig-10-15-stat` | Mouse/elephant fair-queuing experiments, downlink data |
| `mouseeleph_ul` | 7.7 GB | 2.2 GB | `fig-10-15`, `fig-10-15-stat` | Mouse/elephant fair-queuing experiments, uplink data |
| `multidurrate_1s` | 26 GB | 8.4 GB | `fig-02` | Multi-duration/rate experiments with 1 s duration |
| `multidurrate_4s` | 41 GB | 14 GB | `fig-05`, `fig-08`, `aqm-input`, `aqm-input-satpipe` | Multi-duration/rate experiments with 4 s duration |
| `netns` | 12 MB | 12 MB | `fig-04` | Head-drop vs. tail-drop comparison from `netns_model/` experiments |
| `owd` | 4.0 GB | 2.5 GB | `fig-18-owd`, `fig-18-idle` | One-way delay measurements |
| `rate` | 18 GB | 18 GB | `fig-09-rate`, `fig-09-rateri` | Sustained send-rate experiments |
| `sats_2026-01-11` | 46 MB | 9.3 MB | `fig-18-owd` | Satellite identification data from 2026-01-11 |
| `sats_2026-02-02` | 44 MB | 8.9 MB | `fig-09-rate`, `fig-09-rateri` | Satellite identification data from 2026-02-02 |
| `switchflow` | 2.0 GB | 632 MB | `fig-13` | Flow-switching experiments |
| `tcp` | 54 GB | 19 GB | `aqm-input`, `tcp-stat-jan`, `tcp-metrics-jan` | TCP CCA performance experiments |
| `tcp-satpipe` | 56 GB | 20 GB | `aqm-input-satpipe`, `fig-11`, `fig-12`, `tcp-stat`, `tcp-metrics` | TCP CCA performance experiments including SatPipe CCA |
| `vic` | 39 GB | 24 GB | `fig-03-vic`, `fig-06-vic`, `fig-09-rate-vic`, `fig-09-rateri-vic`, `fig-10-15-vic` | Measurement data from our VP in Victoria, Canada |
| `wat` | 104 GB | 34 GB | `fig-02-wat`, `fig-05-wat`, `fig-08-wat`, `fig-18-owd-wat`, `fig-18-idle-wat` | Measurement data from our VP in Waterloo, Canada |
| Sum | 456 GB | 173 GB | |

### Experiment Data

All experiments were conducted with [NetScalpel](https://github.com/hendrikcech/NetScalpel).
Each experiment run is stored in its own folder.
For example, `20260203T031812_multidurrate_dl` in `multidurrate_4s/` was created by the `multidurrate` experiment running in the downlink (DL) direction on 2026-02-03 at 03:18:12 UTC.
The experiment folders contain the following types of files:
- `info.txt`: Lists information about each measurement that was run as part of the experiment, including the measurement's output file.
- `*.csv`, e.g., `owd-udp_dl_050_4000.csv`: Per-packet information. The filename encodes the measurement parameters.
- `stltrace_client.log` and `stltrace_server.log`: NetScalpel client and server output.
- `tcpdump_local.pcap.zst` and `tcpdump_remote.pcap.zst`: Packet captures from client and server, compressed with Zstandard.

## Prerequisites and Setup

The environment dependencies are managed with Nix.
Use `nix develop` to enter an interactive shell, or `nix develop -c <CMD>` to run a one-off command. 
On first run, `nix` will fetch all required dependenices which might take a while (typically 5-15 minutes).

To replot the figures, you need the measurement dataset on your local disk. Configure the local paths by creating a `.env` file in the root directory:

```env
DATASET=/path/to/your/local/dataset
RESULTS=/path/to/your/local/results
SAMPLE=
```

`DATASET` should point to the downloaded [mediaTUM dataset](https://doi.org/10.14459/2026mp1856124). `RESULTS` should ideally point to a directory outside of this repository (e.g., `../results`) so that Nix does not copy the generated results to the Nix store.

## System Requirements

The plotting scripts typically parse csv files generated by [NetScalpel](https://github.com/hendrikcech/NetScalpel) in parallel on all available CPU cores.
Consider only downloading these files to reduce space demand.
The peak memory usage typically stays below 6 GB, but certain scripts require up to 80 GB of memory (e.g., `task fig-12`).

Please see the "Resource Usage" table blelow for typical task durations and memory usage patterns.
To reduce the runtime and peak memory usage at the expense of result accuracy, set `SAMPLE` to any value in `.env`, e.g., `SAMPLE=t` (Note: defining `SAMPLE` with any value, even `false` or `0`, enables sampling).

## Usage

The `Taskfile` is the central point of this repository. It provides the commands required to process TCP measurement data and replot the figures presented in the paper. Prefix your commands with `nix develop -c` (e.g., `nix develop -c task fig-02`) to execute the analysis scripts within the Nix environment, ensuring all dependencies are met.

The measurements were conducted with [NetScalpel](https://github.com/hendrikcech/NetScalpel).

To generate individual figures:

```
task fig-02              Generate Figure 2
task fig-03              Generate Figure 3
task fig-04              Generate Figure 4       # depends on: fig-02 (headdrop.pickle)
task fig-05              Generate Figure 5
task fig-06              Generate Figure 6
task fig-07-14           Generate Figures 7 & 14  # depends on: aqm-input
task fig-08              Generate Figure 8
task fig-09-rate         Generate Figure 9 (rate)
task fig-09-rateri       Generate Figure 9 (rateri)
task fig-10-15           Generate Figures 10 & 15
task fig-11              Generate Figure 11
task fig-12              Generate Figure 12
task fig-13              Generate Figure 13
task fig-16              Generate Figure 16
task fig-18-owd          Generate Figure 18 (OWD)
task fig-18-idle         Generate Figure 18 (idle)
```

Preprocessing and statistical analysis:

```
task aqm-input           Generate AQM input data   # required by: fig-07-14
task aqm-input-satpipe   Generate AQM input data (SatPipe)
task fig-10-15-stat      Run significance tests for Figures 10 & 15
task tcp-stat            Run TCP significance tests
task tcp-stat-jan        Run TCP significance tests (January data)
task tcp-metrics         Gather TCP metrics
task tcp-metrics-jan     Gather TCP metrics (January data)
```

To generate all figures and results at once:

```
task plot-all            Plot all paper figures and results
task plot-other          Plot figures with data captured at other vantage points
```

To process new TCP measurements with (pcap-match)[https://github.com/hendrikcech/pcap-match] to generate per-packet information:

```
task process-tcp:<DIR>   Process NetScalpel TCP measurements with pcap-match
```

### Resource Usage

The following table lists execution times and peak memory demand on our 32-core machine to give a rough idea of each script's demand.
The last two columns address the `SAMPLE` mode.

| Task | Execution Time (minutes) | Peak Memory | Execution Time (minutes, sampled) | Peak Memory (sampled) |
|---|---|---|---|---|
| `task tcp-stat` | 0:26.43 | 5.1 GB | 0:18.27 | 2.8 GB |
| `task tcp-stat-jan` | 0:44.39 | 4.8 GB | 0:16.46 | 2.8 GB |
| `task tcp-metrics` | 0:57.95 | 6.2 GB | 0:27.74 | 3.3 GB |
| `task tcp-metrics-jan` | 0:57.56 | 5.8 GB | 1:22.27 | 3.4 GB |
| `task fig-18-owd` | 4:19.14 | 5.1 GB | 2:09.36 | 2.1 GB |
| `task fig-18-owd-wat` | 0:59.84 | 1.3 GB | 0:59.87 | 1.3 GB |
| `task fig-18-idle-wat` | 0:08.30 | 1.1 GB | 0:05.49 | 1.1 GB |
| `task fig-18-idle` | 0:20.12 | 3.8 GB | 0:19.95 | 3.5 GB |
| `task fig-13` | 0:38.41 | 2.8 GB | 0:21.36 | 2.8 GB |
| `task fig-12` | 18:28.82 | 73.7 GB | 1:59.82 | 5.6 GB |
| `task fig-11` | 0:53.24 | 5.5 GB | 0:22.93 | 3.0 GB |
| `task fig-10-15-vic` | 0:51.86 | 0.3 GB | 0:54.94 | 0.3 GB |
| `task fig-10-15` | 1:22.79 | 0.3 GB | 1:14.41 | 0.3 GB |
| `task fig-10-15-stat` | 0:56.48 | 0.2 GB | 0:56.44 | 0.2 GB |
| `task fig-09-rate-vic` | 4:18.19 | 28.2 GB | 1:25.53 | 7.8 GB |
| `task fig-09-rateri-vic` | 2:35.11 | 7.8 GB | 0:51.29 | 2.3 GB |
| `task fig-09-rateri` | 4:51.22 | 14.8 GB | 0:35.78 | 1.2 GB |
| `task fig-09-rate` | 13:02.82 | 62.9 GB | 0:37.88 | 3.7 GB |
| `task fig-08-wat` | 0:33.43 | 7.0 GB | 0:11.97 | 2.4 GB |
| `task fig-08` | 1:37.66 | 14.8 GB | 0:28.25 | 4.2 GB |
| `task fig-16` | 3:00.00 | 0.2 GB | 2:35.29 | 0.2 GB |
| `task fig-07-14` | 0:31.50 | 9.7 GB | 0:23.65 | 5.1 GB |
| `task fig-06-vic` | 2:08.17 | 0.2 GB | 2:01.35 | 0.2 GB |
| `task fig-05-wat` | 2:15.77 | 19.3 GB | 0:19.69 | 3.1 GB |
| `task fig-04` | 0:05.90 | 0.2 GB | 0:05.79 | 0.2 GB |
| `task fig-05` | 1:58.57 | 12.4 GB | 0:39.24 | 3.6 GB |
| `task fig-06` | 3:22.29 | 0.2 GB | 3:16.83 | 0.2 GB |
| `task fig-03` | 0:36.52 | 3.8 GB | 0:24.96 | 3.8 GB |
| `task fig-03-vic` | 0:13.35 | 1.4 GB | 0:10.85 | 1.4 GB |
| `task fig-02` | 3:47.51 | 5.0 GB | 3:12.29 | 4.0 GB |
| `task fig-02-wat` | 13:03.67 | 16.7 GB | 2:52.92 | 3.7 GB |
| `task aqm-input-satpipe` | 4:24.53 | 6.3 GB | 1:34.57 | 4.1 GB |
| `task aqm-input` | 4:58.93 | 6.3 GB | 2:03.07 | 4.0 GB |


## Satellite Tracking

In our paper, we analyze Starlink reconfigurations to distinguish between events that result in a satellite handoff and those that maintain the same satellite connection.

To infer our dish's satellite assignment, we applied the methodology introduced by Ahangarpour et al. (LEO-NET'24, *"Trajectory-based Serving Satellite Identification with User Terminal's Field-of-View"*).
We adapted their original codebase and enhanced the data processing pipeline for our specific analysis.

The modified code and complete instructions for data collection and processing are available in the [hendrikcech/SatInView](https://github.com/hendrikcech/SatInView#measure-and-process-obstruction-data) repository.


## Evaluating TCP Performance

Our study includes a performance measurement of different TCP congestion control algorithms (CCAs) over Starlink.
To conduct these tests, we created a custom Linux kernel incorporating several CCAs and slow-start algorithms.
Instructions for rebuilding this kernel are available in [./linux-tcp](linux-tcp/).

Evaluating LeoCC requires additional setup steps.
We publish and document our changes in [hendrikcech/LeoCC](https://github.com/hendrikcech/LeoCC/tree/main/leocc/live_network).
