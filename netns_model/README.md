# Network Namespace Queue Model

This directory contains a Linux network namespace model that emulates the Starlink network path to validate the queue behavior described in the paper (Figure 4).
The model creates a chain of five network namespaces connected by veth pairs:

```
Host 1 ←→ Dishy ←→ Satellite ←→ PoP ←→ Host 2
```

Traffic control (`tc`) is used to enforce rate limits and queue disciplines at the Dishy (uplink queue, 4000 packets at 70 Mbps) and Satellite (downlink queue, 1500 packets at 300 Mbps) hops. [NetScalpel](https://github.com/hendrikcech/NetScalpel) generates UDP traffic and records per-packet timestamps, while `bpftrace` monitors the kernel queue length in real time.

## Prerequisites

- **Linux** with network namespace and bpftrace support
- **Nix** (the environment is fully managed by the [flake](../flake.nix))
- **sudo** privileges (required for creating namespaces and applying traffic control)

No manual dependency installation is needed — `nix develop` provides NetScalpel, pcap-match, Python with plotting libraries, iproute2, nftables, bpftrace, and all other tools.

## Usage

All commands are defined in the [Taskfile.yml](Taskfile.yml) and should be run from within the `netns_model/` directory.

Prefix commands with `nix develop -c` to execute them inside the Nix environment:

```bash
cd netns_model

# Run all head-drop and tail-drop experiments (paper, Fig. 4)
nix develop -c task drop-all

# Or run individual experiments
nix develop -c task head-drop-ul
nix develop -c task head-drop-dl
nix develop -c task tail-drop-ul
nix develop -c task tail-drop-dl
```

If existing environment variables interfere (e.g., conflicting `PATH` or Python settings), use the `-i` flag to start from a clean environment:

```bash
nix develop -i -c task drop-all
```

For an interactive shell where you can run multiple tasks without the `nix develop -c` prefix:

```bash
nix develop       # or: nix develop -i
task head-drop-ul
task tail-drop-dl
```

## Results

After running, results are written to `netns_model/results/`. Each experiment produces up to three files:

| File | Description |
|------|-------------|
| `<name>.csv` | Per-packet log from NetScalpel (columns: `seq`, `ts_sent`, `ts_rcvd`, `owd_ms`, `size`, `lost`) |
| `<name>.queue.csv` | Kernel queue length trace from bpftrace (columns: nanosecond timestamp, queue length, tc handle) |
| `<name>.pdf` | Automatically generated plot showing send/receive rates, loss, estimated queue occupancy, and sojourn time |

## Tasks

### Paper experiments (`drop-all`)

These four experiments compare head-drop and tail-drop queuing on the uplink and downlink, validating the head-drop behavior observed in Starlink (Figure 4):

| Task | Queue Discipline | Direction | Send Rate |
|------|-----------------|-----------|-----------|
| `head-drop-ul` | `pfifo_head_drop` | Uplink | 200 Mbps |
| `head-drop-dl` | `pfifo_head_drop` | Downlink | 700 Mbps |
| `tail-drop-ul` | `pfifo` | Uplink | 200 Mbps |
| `tail-drop-dl` | `pfifo` | Downlink | 700 Mbps |

### Additional experiments (not in paper)

These are not part of the paper but may be useful for further exploration:

| Task | Description |
|------|-------------|
| `pop-all` (`pop-700`, `pop-600`) | Model PoP-side rate limiting with nftables-based per-flow metering and a secondary head-drop queue |
| `tcp-all` (`tcp-cubic`, `tcp-bbr`) | TCP experiments (Cubic, BBR) over the model with pcap-match post-processing |
| `fqcodel-ul` | fq_codel AQM on the uplink |
| `red-ul` | Adaptive RED AQM on the uplink |
| `fq`, `fq-dl` | Fair queuing experiments with concurrent elephant and mouse flows |

### Utility tasks

| Task | Description |
|------|-------------|
| `setup` | Create namespaces and apply traffic control (called automatically by experiment tasks) |
| `teardown` | Remove all namespaces |
| `all` | Run everything: `drop-all`, `pop-all`, and `tcp-all` |
