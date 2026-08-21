# SIGCOMM'26: Dissecting the StarLink

This repository contains the scripts and references accompanying the SIGCOMM'26 paper "Dissecting the StarLink: Characterizing Queuing and Flow Dynamics in the Starlink Network" ([ACM](https://dl.acm.org/doi/abs/10.1145/3789240.3829162)).

> **Measurement Tool** -- [NetScalpel](https://github.com/hendrikcech/NetScalpel), the custom network measurement tool used for all experiments in this paper.
>
> **Dataset** -- [mediaTUM](https://doi.org/10.14459/2026mp1856124), the complete measurement dataset analyzed in the paper (available starting at Aug 25 2026).

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

## Prerequisites and Setup

The environment dependencies are managed with Nix. Use `nix develop` to enter an interactive shell, or `nix develop -c <CMD>` to run a one-off command.

To replot the figures, you need the measurement dataset on your local disk. Configure the local paths by creating a `.env` file in the root directory:

```env
DATASET=/path/to/your/local/dataset
RESULTS=/path/to/your/local/results
```

`DATASET` should point to the downloaded [mediaTUM dataset](https://doi.org/10.14459/2026mp1856124). `RESULTS` should ideally point to a directory outside of this repository (e.g., `../results`) so that Nix does not copy the generated results to the Nix store.

## Usage

The `Taskfile` is the central point of this repository. It provides the commands required to process TCP measurement data and replot the figures presented in the paper.
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

## Satellite Tracking

In our paper, we analyze Starlink reconfigurations to distinguish between events that result in a satellite handoff and those that maintain the same satellite connection.

To infer our dish's satellite assignment, we applied the methodology introduced by Ahangarpour et al. (LEO-NET'24, *"Trajectory-based Serving Satellite Identification with User Terminal's Field-of-View"*).
We adapted their original codebase and enhanced the data processing pipeline for our specific analysis.

The modified code and complete instructions for data collection and processing are available in the [hendrikcech/SatInView](https://github.com/hendrikcech/SatInView) repository.


## Evaluating TCP Performance

Our study includes a performance measurement of different TCP congestion control algorithms (CCAs) over Starlink.
To conduct these tests, we created a custom Linux kernel incorporating several CCAs and slow-start algorithms.
Instructions for rebuilding this kernel are available in [./linux-tcp](linux-tcp/).

Evaluating LeoCC requires additional setup steps.
We publish and document our changes in [hendrikcech/LeoCC](https://github.com/hendrikcech/LeoCC/tree/main/leocc/live_network).
