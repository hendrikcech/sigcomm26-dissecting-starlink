# Dissecting the StarLink: Scripts

This repository contains the scripts accompanying the SIGCOMM'26 paper "Dissecting the StarLink: Characterizing Queuing and Flow Dynamics in the Starlink Network".

If you use this repository or dataset in your research, please cite our paper:

<details>
<summary>BibTeX</summary>

```bibtex
@inproceedings{cech2026starlink,
  title={Dissecting the StarLink: Characterizing Queuing and Flow Dynamics in the Starlink Network},
  author={Cech, Hendrik and Mohan, Nitinder and Ott, J\"{o}rg},
  booktitle={Proceedings of the 2026 ACM SIGCOMM Conference},
  year={2026}
}
```

</details>

## Overview

The `Taskfile` is the central point of this repository. It provides the commands required to process TCP measurement data and replot the figures presented in the paper.

## Prerequisites and Setup

To replot the figures, you will first need to get the measurement dataset onto your local disk. A task action will be implemented to automate this process.

You must configure the local paths by creating a `.env` file in the root directory, as the dataset location will be custom for each user. Furthermore, the `RESULTS` path should ideally point to a directory outside of this repository (e.g., `../`) so that Nix does not copy the generated results to the Nix store.

Example `.env`:

```env
DATASET=/path/to/your/local/dataset
RESULTS=/path/to/your/local/results
```

The environment dependencies are managed with Nix. Use `nix develop` to enter an interactive shell, or `nix develop -c <CMD>` to run a one-off command.


## Satellite Tracking
In our paper, we analyze Starlink reconfigurations to distinguish between events that result in a satellite handoff and those that maintain the same satellite connection.

To infer our dish's satellite assignment, we applied the methodology introduced by Ahangarpour et al. (LEO-NET'24, *"Trajectory-based Serving Satellite Identification with User Terminal's Field-of-View"*).
We adapted their original codebase and enhanced the data processing pipeline for our specific analysis.

The modified code and complete instructions for data collection and processing are available in the [hendrikcech/SatInView](https://github.com/hendrikcech/SatInView) repository.


## Evaluating TCP Performance
Our study includes a performance measurement of different TCP congestion control algorithms (CCAs) over Starlink.
To conduct these tests, we created a custom Linux kernel incorporating several CCAs and slow-start algorithms.
Instructions for rebuilding this kernel are available in [./linux-tcp](linux-tcp/).
