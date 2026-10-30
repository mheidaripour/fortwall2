# fortwall

The **FortWall** project layer: automated *pool-level* system-call filtering for
PHP applications.

FortWall builds on **Saphire** (Bulekov et al., USENIX 2021), which derives a
seccomp-BPF allow-list per **PHP script**. Saphire's cost is that the interpreter
must be restarted whenever it serves a script with a different filter — in the
worst case, on every request. FortWall consumes those per-script allow-lists and
**consolidates them into a few PHP-FPM pools**, each enforcing one seccomp-BPF
policy on a *long-lived* worker. A pool's policy is the **union** of its members'
profiles, so no script loses a syscall it needs — only precision may widen
(quantified as ΔSP/ΔSN). This removes the per-request restart while keeping close
to script-level tightness.

This package implements FortWall's **clustering** and **deployment** stages plus
the security metrics; profiling (Stage 1) is Saphire's, and enforcement (Stage 4)
a seccomp-BPF filter installed in each long-lived pool worker.


## How it works — the four FortWall stages

| Stage | What it does | Code |
|---|---|---|
| **1. Profile ingestion** | per-script syscall allow-lists from Saphire | input file `../artifacts/stage2_out/stage2_out_<app>` (one line: `url syscall_nums…`) |
| **2. Clustering** | *Phase I* — group scripts with an identical profile, give the largest categories their own dedicated pools; *Phase II* — cluster the rest by **Jaccard** similarity (agglomerative), each pool's policy = **union/superset** of members | `urlmap.py` (categorize, intersection), `clustering.py` (Jaccard + agglomerative + superset), `pipeline.build_pool_plan` (two-phase orchestration under a pool budget) |
| **3. Deployment** | auto-generate PHP-FPM pool configs + Nginx URL→pool routing | `generate/` (renders url maps, `pool_N.conf`, the `$upstream` map) → `deploy/` (copies to `/etc/nginx`, `/opt/php-7.1`, restarts nginx) |
| **4. Enforcement** | one seccomp-BPF filter per long-lived pool worker | `native/seccomp/intrsec-seccomp.c`; generated pools set `pm.max_requests=0` so workers stay alive to hold the filter |

The **intersection** (syscalls common to *every* script) is the global baseline
every pool inherits; Phase I peels off the high-share identical-profile
categories into dedicated pools; Phase II clusters the long tail. The pool budget
is a knob (`-p` for `switch`, `--clusters` for `analyze`).

## Install

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"      # runtime + test deps
```

This exposes the `fortwall` console command.

## CLI

```bash
# Stage 2: cluster scripts into pools and score them (intersection, categories,
# clusters, per-pool SP/SN + ΔSP/ΔSN diagnostics)
fortwall analyze --app phpmyadmin --clusters 5

# Script-level (pre-clustering) SP/SN — the Saphire-equivalent baseline
fortwall baseline --app wordpress

# Stage 3: generate + deploy a pooling mode (--dry-run previews system changes)
fortwall switch --mode mpool --app wordpress -p 7 --dry-run   # build pools + deploy
fortwall switch --mode saphire --app wordpress                # revert to Saphire baseline
fortwall switch --mode default                                # revert to plain PHP-FPM

# Turn analysis stdout into LaTeX / Markdown result tables
fortwall analyze --app phpmyadmin --clusters 5 | fortwall report
```

`--syscall-table` defaults to `data/syscall_table/unistd_64_.h`.
`analyze`/`baseline` default their input to `../artifacts/stage2_out/stage2_out_<app>`
(the saphire->fortwall data contract) unless `--file` is given. `switch`
reads/writes the on-host path `/home/paper/stage2_out_<app>` for deployment. Run
`fortwall` from the `fortwall/` layer directory so the relative `../artifacts`
and `data/` paths resolve.

## Metrics

* **SP%** — attack-surface reduction: share of all `TOTAL_SYSCALLS` (333) blocked,
  `(TOTAL - |pool profile|)/TOTAL`.
* **SN%** — sensitive-call reduction: share of the `SN_BASE` (20 sensitive
  syscalls, per Bastion) blocked, `(SN_BASE - |profile ∩ sensitive|)/SN_BASE`.
* **ΔSP / ΔSN** — worst-case *inflation from pooling*: the most extra syscalls
  (resp. sensitive syscalls) any script gains because its pool's allow-list is a
  superset of its own profile. `fortwall report` computes both per pool. `baseline` reports the pre-clustering (script-level)
  SP/SN — i.e. the Saphire-equivalent numbers.

## Package layout

```
src/fortwall_pool/
├── config.py         # all paths + constants (TOTAL_SYSCALLS, SN_BASE, pool budget…)
├── syscalls.py       # kernel syscall table + the 20 sensitive syscalls
├── urlmap.py         # Stage 2 input: parse stage2_out, group identical profiles, intersection
├── clustering.py     # Stage 2: Jaccard distance + agglomerative clustering → pool supersets
├── metrics.py        # SP% / SN% (and ΔSP/ΔSN) math
├── pipeline.py       # Stage 2 orchestration: Phase I (dedicated) + Phase II (clustered)
├── generate/         # Stage 3 (pure): render nginx url maps, pool_N.conf, $upstream map
├── deploy/           # Stage 3 (effects): apply configs to the host + restart nginx (dry-run aware)
├── report.py         # results → LaTeX/Markdown tables
└── cli.py            # unified `fortwall` entrypoint (analyze / baseline / switch / report)

data/        # inputs: stage2_out/, url_lists/, syscall_table/
generated/   # (gitignored) artifacts produced by `fortwall switch`
backups/     # (gitignored) system config captured before deployment
native/seccomp/  # intrsec-seccomp.c: loads a pool's syscall list for seccomp-BPF enforcement
experiments/ # evaluation scripts, result CSVs, and figures
legacy/      # original standalone scripts, kept for reference (superseded by src/)
tests/       # pytest suite incl. byte-for-byte golden config tests
```

## Legacy script mapping

The `legacy/` scripts are superseded by the package as follows:

| Original file            | Now lives in                                             |
|--------------------------|----------------------------------------------------------|
| `intersection.py`        | `urlmap.py` + `generate/` + `deploy/system.py`           |
| `cluster.py`             | `clustering.py`                                           |
| `sen_syscalls.py`        | `syscalls.py` (+ analysis in `pipeline.py`/`cli.py`)     |
| `saphire.py`             | `metrics.py` (`category_metrics`) + `fortwall baseline`  |
| `urlanalyze.py`          | `pipeline.build_pool_plan`                                |
| `switch.py`              | `deploy/modes.py` + `fortwall switch`                    |
| `report.py`              | `report.py` (packaged) + `fortwall report`               |
| `pools_expe.py`          | `experiments/`                                           |

## Testing

```bash
.venv/bin/python -m pytest -q
```

The suite includes **golden tests** that assert the nginx/php-fpm/url-map
renderers reproduce the committed reference artifacts exactly.

## Differences from the legacy scripts

Generated configs are byte-identical to the legacy output, with one documented
behavior kept for compatibility:

- **www.conf `pm.max_children`** is not rewritten (the legacy condition lacked
  a trailing newline); the per-pool configs do rewrite it.

Two legacy bugs are fixed:

- **Clustering "Max of sensitive syscalls" (ΔSN)** — the original intersected an
  int set with a string-keyed dict, so ΔSN was always `0.00%`. Now
  `clustering.diagnostics_lines()` uses the sensitive syscall *numbers*, so ΔSN
  reflects how many sensitive syscalls a pool actually adds to a member URL
  (e.g. up to 40–45% on some pools).
- **Report cluster-index misalignment** — the SP/SN lines were 0-based over all
  pools while the ΔSP/ΔSN diagnostics were 1-based over clustered pools only, so
  the corrected ΔSN landed in the wrong table row (and the first clustered
  pool's value was dropped into the hardcoded-zero "Category 1" row).
  `pipeline.build_pool_plan` now numbers the clustered pools starting after the
  dedicated pools (`first_pool_number`), so ΔSP/ΔSN align with SP/SN in the
  report table.
