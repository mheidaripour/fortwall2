# fortwall

A least-privilege deployment layer for PHP applications, built on top of the
**Saphire** syscall-profiling pipeline. Saphire (Bulekov et al., USENIX 2021)
derives a seccomp-BPF allow-list per **PHP script** but must restart the
interpreter whenever it serves a script with a different filter. fortwall
consumes those per-script profiles and consolidates them into a small set of
php-fpm **pools** — each a long-lived worker enforcing one union allow-list (via
nginx routing + per-pool seccomp) — removing Saphire's per-request restart while
measuring the resulting attack-surface reduction.

## Repository layout (two layers + a data contract)

```
<repo>/
├── saphire/             # VENDORED upstream (see saphire/UPSTREAM.md)
│   ├── stage1/ stage2/ stage3/     # trace -> syscall profile -> seccomp enforce
│   ├── go/ wordpress_exploits/ CVE-2018-12613.py
│   └── run_stage*.sh  switch_to_*.sh
├── artifacts/           # DATA CONTRACT between the two layers
│   ├── stage1_output               # saphire stage1 -> stage2
│   └── stage2_out/                 # saphire stage2 -> fortwall  (stage2_out_*)
└── fortwall/            # FortWall pooling layer
    ├── src/fortwall_pool/          # installable package
    ├── tests/                      # pytest suite (incl. byte-for-byte golden tests)
    ├── data/                       # fortwall-local inputs (syscall_table, url_lists)
    ├── experiments/                # evaluation harness (mpool vs saphire pl/npl)
    ├── legacy/                     # original standalone scripts (reference)
    └── pyproject.toml  README.md
```

**Why this shape:** fortwall is a *sibling alternative* to Saphire's stage3, not
a later stage — its only dependency on Saphire is the `stage2_out_*` data in
`artifacts/`. Keeping Saphire vendored and pristine (not renumbered) preserves
attribution and the ability to diff/update against upstream. See
[`saphire/UPSTREAM.md`](saphire/UPSTREAM.md).

## Quick start

```bash
cd fortwall                         # the project layer
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q

# analyze a saphire stage2 output (reads ../artifacts/stage2_out/ by default)
.venv/bin/fortwall analyze --app wordpress --clusters 5
```

Run `fortwall` commands from the `fortwall/` layer directory so the relative
`../artifacts` and `data/` paths resolve. See [`fortwall/README.md`](fortwall/README.md)
for the full CLI and package details, and
[`docker/RUNBOOK.md`](docker/RUNBOOK.md) for running the Saphire stages and
enforcement in a container.
