#!/usr/bin/env python3
"""Sensitivity-aware clustering sweep: ΔSN / ASP / reintroduction vs weight W.

For each application and each weight ``W`` (1 = the plain-Jaccard baseline,
larger = more sensitivity-aware, ``inf`` = never merge across differing sensitive
sets), cluster into a fixed pool budget ``k`` and report:

  * dSN  -- worst-case sensitive inflation (max over scripts), the primary metric
  * dSP  -- worst-case total inflation
  * SP   -- unweighted mean blocked-syscall share (security level, higher better)
  * wSP  -- request-weighted SP
  * reintro_execve -- # scripts whose OWN Saphire profile blocked execve(59) but
            whose pool union restores it (the "consolidation regression" count)

W=1 must reproduce the plain baseline exactly. Emits a Markdown table, a CSV, and
(if matplotlib is available) the ΔSN-vs-ASP tradeoff figure.

Run from the ``fortwall/`` layer dir:
    .venv/bin/python experiments/sensitivity_sweep.py --apps wordpress joomla --k 7
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Dict, List, Optional, Set

from fortwall_pool import config, metrics, pipeline, syscalls

EXECVE, SOCKET, CONNECT = 59, 41, 42

APP_FILES = {
    "wordpress": "stage2_out_wordpress",
    "phpmyadmin": "stage2_out_phpmyadmin",
    "joomla": "stage2_out_joomla",
    "drupal": "stage2_out_drupal",
    "magento": "stage2_out_magento19",
    "moodle": "stage2_out_moodle27",
}

WEIGHTS = [1.0, 2.0, 4.0, 8.0, 16.0, math.inf]


def _own_profiles(path: Path) -> Dict[str, Set[int]]:
    """url -> its own Saphire per-script syscall set."""
    out: Dict[str, Set[int]] = {}
    for line in open(path):
        parts = line.split()
        if not parts:
            continue
        try:
            out[parts[0]] = set(map(int, parts[1:]))
        except ValueError:
            continue
    return out


def evaluate(path: Path, k: int, sensitive, weight: float) -> dict:
    """Cluster at (k, weight) and compute the sweep metrics."""
    # inf => a very large finite weight; distances are ratios so this saturates
    # to "identical sensitive-set required to merge" without overflow.
    w = 1e9 if math.isinf(weight) else weight
    plan = pipeline.build_pool_plan(
        path, total_pools=k,
        sensitive=sensitive if w != 1.0 else None,
        sensitivity_weight=w,
    )
    inter = plan.intersection
    pool_prof = [set(c["associated_numbers"]) | inter for c in plan.all_clusters]

    # url -> pool index
    url_pool: Dict[str, int] = {}
    for i, c in enumerate(plan.all_clusters):
        for u in c["urls"]:
            url_pool.setdefault(u, i)

    sens = set(sensitive)
    own = _own_profiles(path)

    # per-pool SP/SN
    sp_vals = [metrics.sp_percent(p) for p in pool_prof]
    sn_vals = [metrics.sn_percent(p, sensitive) for p in pool_prof]
    urls_per_pool = [len(c["urls"]) for c in plan.all_clusters]
    tot_urls = sum(urls_per_pool) or 1
    wsp = sum(s * n for s, n in zip(sp_vals, urls_per_pool)) / tot_urls

    # worst-case inflation over member scripts
    max_dsp = max_dsn = 0.0
    for u, prof in own.items():
        pi = url_pool.get(u)
        if pi is None:
            continue
        added = pool_prof[pi] - prof
        max_dsp = max(max_dsp, len(added) / config.TOTAL_SYSCALLS * 100)
        max_dsn = max(max_dsn, len(added & sens) / config.SN_BASE * 100)

    # reintroduction: own blocked it, pool restores it
    def reintro(nr: int) -> int:
        c = 0
        for u, prof in own.items():
            pi = url_pool.get(u)
            if pi is None or nr in prof:
                continue
            if nr in pool_prof[pi]:
                c += 1
        return c

    return {
        "sp": round(sum(sp_vals) / len(sp_vals), 2),
        "wsp": round(wsp, 2),
        "sn": round(sum(sn_vals) / len(sn_vals), 2),
        "dsp": round(max_dsp, 2),
        "dsn": round(max_dsn, 2),
        "reintro_execve": reintro(EXECVE),
        "reintro_socket": reintro(SOCKET),
        "n_pools": len(plan.all_clusters),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apps", nargs="+", default=["wordpress", "joomla", "phpmyadmin"],
                    choices=list(APP_FILES))
    ap.add_argument("--k", type=int, default=7, help="pool budget")
    ap.add_argument("--syscall-table", default=str(config.WORK.syscall_table))
    ap.add_argument("--art-dir", default=str(config.WORK.stage2_out_dir))
    ap.add_argument("--csv", default="experiments/figures/sensitivity_sweep.csv")
    ap.add_argument("--fig", default="experiments/figures/sensitivity_tradeoff.png")
    args = ap.parse_args()

    sensitive = syscalls.load_sensitive_syscalls(args.syscall_table)
    art = Path(args.art_dir)

    rows: List[dict] = []
    print(f"# sensitivity-aware sweep, k={args.k}, sensitive={len(sensitive)} syscalls\n")
    for app in args.apps:
        path = art / APP_FILES[app]
        print(f"## {app}")
        print(f"{'W':>6} {'SP%':>7} {'wSP%':>7} {'dSP%':>7} {'dSN%':>7} "
              f"{'reintro_execve':>15} {'reintro_socket':>15}")
        for weight in WEIGHTS:
            m = evaluate(path, args.k, sensitive, weight)
            wlabel = "inf" if math.isinf(weight) else f"{weight:g}"
            print(f"{wlabel:>6} {m['sp']:>7.2f} {m['wsp']:>7.2f} {m['dsp']:>7.2f} "
                  f"{m['dsn']:>7.2f} {m['reintro_execve']:>15} {m['reintro_socket']:>15}")
            rows.append({"app": app, "k": args.k, "weight": wlabel, **m})
        print()

    # CSV
    Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
    with open(args.csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {args.csv}")

    # Figure: ASP (=100-SP) vs dSN, one line per app across weights.
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(6, 4))
        for app in args.apps:
            ar = [r for r in rows if r["app"] == app]
            asp = [100 - r["sp"] for r in ar]
            dsn = [r["dsn"] for r in ar]
            ax.plot(dsn, asp, marker="o", label=app)
            for r, x, y in zip(ar, dsn, asp):
                ax.annotate(r["weight"], (x, y), fontsize=7,
                            textcoords="offset points", xytext=(3, 3))
        ax.set_xlabel(r"worst-case sensitive inflation $\Delta$SN (%)")
        ax.set_ylabel("attack surface ASP = 100 - SP (%)")
        ax.set_title(f"Sensitivity-aware clustering tradeoff (k={args.k})")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(args.fig, dpi=150)
        print(f"wrote {args.fig}")
    except Exception as e:  # pragma: no cover
        print(f"(figure skipped: {e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
