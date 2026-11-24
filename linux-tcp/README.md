# Linux Kernel with Additional TCP CCAs

This directory contains a sequence of git patches generated on top of the `bbrv3-2025-03-18` tag (commit `90210de4b779d40`) from the [Google BBR](https://github.com/google/bbr) repository.
These patches add the following TCP congestion controllers and slow start algorithms:

* BBRv1 and BBRv3 (already provided by the base repository)
* [LeoCC](https://github.com/SpaceNetLab/LeoCC): please see [hendrikcech/LeoCC](https://github.com/hendrikcech/LeoCC/blob/main/leocc/live_network/README.md) for additional instructions
* [SatPipe](https://github.com/dzhao99/SatPipe)
* [HyStart++](https://github.com/SUSSdeveloper/HyStartPP)
* [SUSS](https://github.com/SUSSdeveloper/SUSSprg)
* [SEARCH](https://github.com/Project-Faster/tcp_ss_search)

## Prerequisites

Clone the [Google BBR](https://github.com/google/bbr) repository at the tag these patches were generated from to avoid merge conflicts. You may add `--depth 1` to speed up the cloning process.

```bash
git clone --branch bbrv3-2025-03-18 https://github.com/google/bbr.git linux
cd linux
```

## How to Apply the Patches

The standard way to apply these patches is using `git am` (Apply Mailbox), which will recreate the commits in your repository.

Run the following command from the root of your repository, pointing it to the directory containing the patch files:

```bash
git am /path/to/patches/*.patch
```

Git will process the `.patch` files in alphabetical/numerical order (e.g., `0001-...`, `0002-...`) and apply them cleanly.

## Configure and Build

From the kernel source directory, start with a default configuration and open the configuration menu:

```bash
make defconfig
make menuconfig
```

To build for the current machine instead, you can use the running kernel's configuration as a starting point (if your distribution provides it):

```bash
cp "/boot/config-$(uname -r)" .config
make olddefconfig
make menuconfig
```

`olddefconfig` updates the configuration for this kernel, using defaults for new options. Review the result, especially drivers and distribution-specific settings, before installing or booting it.

Under **Networking support → Networking options → TCP: advanced congestion control**, enable the desired congestion controllers, including LeoCC, SatPipe, HyStart++, SUSS, and SEARCH. Select `M` to build them as modules or `Y` to build them into the kernel. Save the configuration and build the kernel and modules:

```bash
make -j"$(nproc)"
```

The default configuration may not include all drivers needed by your machine. Adjust it before installing or booting the kernel. Building requires the usual Linux kernel build dependencies, including a compiler, make, and development libraries for `menuconfig`.

## Troubleshooting Patch Conflicts

If any patch fails to apply cleanly (usually because your base code differs from what the patches expect), `git am` will pause.
1. Run `git status` to see which files have conflicts.
2. Open those files and resolve the conflicts manually.
3. Add the resolved files:
   ```bash
   git add <resolved-file>
   ```
4. Continue the patch application process:
   ```bash
   git am --continue
   ```

If you get completely stuck and want to abort applying the patches entirely, you can cancel the process and return to your original state:
```bash
git am --abort
```
