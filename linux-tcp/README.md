# Linux Kernel with Additional TCP CCAs

This directory contains a sequence of git patches generated on top of the `bbrv3-2025-03-18` tag (commit `90210de4b779d40`) from the [Google BBR](https://github.com/google/bbr) repository.
These patches add the following TCP congestion controllers and slow start algorithms:

* BBRv1 and BBRv3 (already provided by the base repository)
* [LeoCC](https://github.com/SpaceNetLab/LeoCC)
* [SatPipe](https://github.com/dzhao99/SatPipe)
* [HyStart++](https://github.com/SUSSdeveloper/HyStartPP)
* [SUSS](https://github.com/SUSSdeveloper/SUSSprg)
* [SEARCH](https://github.com/Project-Faster/tcp_ss_search)

## Prerequisites

Clone the [Google BBR](https://github.com/google/bbr) repository and checkout the tag these these patches were generated from to avoid merge conflicts. You may add `--depth 1` to speed up the cloning process.

```bash
git clone --branch bbrv3-2025-03-18 git@github.com:google/bbr.git linux
```

## How to Apply the Patches

The standard way to apply these patches is using `git am` (Apply Mailbox), which will recreate the commits in your repository.

Run the following command from the root of your repository, pointing it to the directory containing the patch files:

```bash
git am /path/to/patches/*.patch
```

Git will process the `.patch` files in alphabetical/numerical order (e.g., `0001-...`, `0002-...`) and apply them cleanly.

### Troubleshooting Conflicts

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
