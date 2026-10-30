# Vendored: Saphire

This directory contains a **vendored copy** of the Saphire project, on top of
which `fortwall/` is built. It is included here so the full evaluation pipeline
(stage1 trace → stage2 syscall profile → stage3 seccomp enforcement) is
reproducible alongside fortwall.

## Origin

Saphire — *"Saphire: Sandboxing PHP Applications with Tailored System Call
Allowlists"*, Alexander Bulekov, Rasoul Jahanshahi, Manuel Egele.
USENIX Security Symposium, 2020.

- Upstream repo: https://github.com/BUseclab/saphire (branch `main`)
- Vendored commit: `6ac8e1373211ab6f43da5dcbbf920b80917b6754` ("first commit",
  2021-08-12), with the local modifications listed below
- License: **MIT** — Copyright (c) 2021 BUseclab. Redistribution inside this repo
  is permitted provided the notice is retained; see [`./LICENSE`](./LICENSE).

## Contents (upstream)

- `stage1/` — application tracing (TR_strace, TE_xdebug, static analysis)
- `stage2/` — builds the per-application syscall profile (`stage2_out_*`)
- `stage3/` — PHP seccomp extension that enforces one global allow-list
- `go/`, `wordpress_exploits/`, `CVE-2018-12613.py` — exploit/validation harness
- `run_stage{1,2,3}.sh` — pipeline drivers (they reference `~/stage2`, `~/stage3`
  on the host, not repo-relative paths)
- `switch_to_*.sh` — webroot app-switch helpers

## Local modifications

Changes relative to the upstream commit above:

- **Upstream (unchanged):** `switch_to_wordpress.sh`, `switch_to_phpmyadmin.sh`
- **Added locally (not from upstream):** `switch_to_drupal.sh`,
  `switch_to_joomla.sh`, `switch_to_magento.sh`, `switch_to_moodle.sh`,
  `switch_to_prestashop.sh`
- **Modified:** `stage3/extension/seccomp.c` adds a
  `seccomp.intersect_profile_path` INI entry and pool-profile hooks used by
  FortWall's per-pool enforcement.
- **Relocated:** the stage-2 Go sources (`build-filters`, `scan-project`, …)
  live under `stage2/php-api-deps/` and `go/src/php-syscalls/` instead of
  directly in `stage2/`.
- **Not vendored:** upstream `img/`, `vm_scripts/`, `readme.md`, and editor swap
  files.

## Relationship to fortwall

fortwall consumes only Saphire's **stage2 output** (`../artifacts/stage2_out/`)
and replaces stage3 with per-URL php-fpm pooling. Do **not** renumber or rename
Saphire's stages, so the copy can be diffed against upstream and attribution
stays clear.
