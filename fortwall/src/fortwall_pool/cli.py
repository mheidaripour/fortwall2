"""Unified ``fortwall`` command-line entrypoint.

Replaces the scattered ad-hoc ``__main__`` blocks (``switch.py``,
``sen_syscalls.py``, ``saphire.py``, ``report.py``, ``pools_expe.py``) with a
single subcommand interface::

    fortwall analyze  --app wordpress --clusters 5
    fortwall baseline --file stage2_out_wordpress
    fortwall switch   --mode mpool --app wordpress -p 7 [--dry-run]
    fortwall report   analysis.txt
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import List, Optional

from . import autotune, config, metrics, pipeline, report, syscalls, urlmap
from .deploy import modes
from .deploy.system import Deployer

APPS = ["wordpress", "joomla", "drupal", "phpmyadmin", "moodle"]


def _resolve_file(args) -> str:
    # Local analysis reads from the repo's data dir; deployment (switch) still
    # uses the on-host SYSTEM path.
    return args.file or str(config.WORK.stage2_out(args.app))


def cmd_analyze(args) -> int:
    """Reproduce the sen_syscalls.py analysis report (parseable by `report`)."""
    sensitive = syscalls.load_sensitive_syscalls(args.syscall_table)
    print(f"Total Sensitive Syscalls: {sensitive}")
    weight = args.sensitivity_weight if args.sensitivity_aware else 1.0
    for line in pipeline.analyze_report_lines(
        _resolve_file(args), args.clusters, sensitive, sensitivity_weight=weight
    ):
        print(line)
    return 0


def cmd_baseline(args) -> int:
    """Per-category SP/SN averages and maxima (the former saphire.py)."""
    sensitive = syscalls.load_sensitive_syscalls(args.syscall_table)
    cats = urlmap.categorize_urls_by_numbers(_resolve_file(args))
    m = metrics.category_metrics(cats, sensitive)
    print(f"Average SP Rate: {m.avg_sp:.2f}%")
    print(f"Average SN Rate: {m.avg_sn:.2f}%")
    print(f"Max SP Rate: {m.max_sp:.2f}%")
    print(f"Max SN Rate: {m.max_sn:.2f}%")
    return 0


def cmd_switch(args) -> int:
    deployer = Deployer(dry_run=args.dry_run)
    if args.mode == "mpool":
        arts = modes.switch_mpool(args.app, args.pools_num, deployer=deployer)
        for line in arts.diagnostics:
            print(line)
        print(f"Deployed {arts.pool_count} pools for {args.app}"
              + (" (dry-run)" if args.dry_run else ""))
    elif args.mode == "saphire":
        modes.switch_saphire(args.app, deployer=deployer)
        print("Switched to saphire mode" + (" (dry-run)" if args.dry_run else ""))
    elif args.mode == "default":
        modes.switch_default(deployer=deployer)
        print("Restored default www.conf" + (" (dry-run)" if args.dry_run else ""))
    return 0


def cmd_autotune(args) -> int:
    """Auto-select the pool count k by constrained optimization."""
    sensitive = syscalls.load_sensitive_syscalls(args.syscall_table)
    weight = args.sensitivity_weight if args.sensitivity_aware else 1.0
    res = autotune.tune(
        _resolve_file(args),
        sensitive,
        budget_k=args.max_pools,
        tau=args.tau,
        k_min=args.min_pools,
        sensitivity_weight=weight,
    )
    for line in autotune.format_lines(res):
        print(line)
    if args.plot:
        autotune.plot(res, args.plot)
        print(f"\nwrote figure to {args.plot}")
    return 0 if res.recommended_k is not None else 1


def cmd_report(args) -> int:
    report.main([args.file] if args.file else [])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fortwall", description=__doc__.splitlines()[0])
    parser.add_argument("-v", "--verbose", action="store_true", help="enable info logging")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p):
        p.add_argument("--app", choices=APPS, default="wordpress", help="application name")
        p.add_argument("--file", help="stage2_out path (overrides --app default location)")
        p.add_argument("--syscall-table", default=str(config.WORK.syscall_table),
                       help="path to unistd_64 header")
        p.add_argument("--sensitivity-aware", action="store_true",
                       help="cluster with a sensitivity-weighted Jaccard distance "
                            "(up-weights sensitive syscalls to reduce pool ΔSN)")
        p.add_argument("--sensitivity-weight", type=float, default=8.0,
                       help="weight W>1 for sensitive syscall columns when "
                            "--sensitivity-aware is set (default 8.0)")

    p_analyze = sub.add_parser("analyze", help="cluster + score, emit analysis report")
    add_common(p_analyze)
    p_analyze.add_argument("--clusters", type=int, default=5, help="number of clustered pools")
    p_analyze.set_defaults(func=cmd_analyze)

    p_baseline = sub.add_parser("baseline", help="per-URL saphire SP/SN baseline")
    add_common(p_baseline)
    p_baseline.set_defaults(func=cmd_baseline)

    p_switch = sub.add_parser("switch", help="generate + deploy a pooling mode")
    p_switch.add_argument("-m", "--mode", choices=["mpool", "saphire", "default"], required=True)
    p_switch.add_argument("--app", choices=APPS, default="wordpress")
    p_switch.add_argument("-p", "--pools_num", type=int, default=config.DEFAULT_NUM_POOLS)
    p_switch.add_argument("--dry-run", action="store_true", help="record actions without applying")
    p_switch.set_defaults(func=cmd_switch)

    p_auto = sub.add_parser("autotune",
                            help="constrained-optimization: auto-select pool count k")
    add_common(p_auto)
    p_auto.add_argument("-K", "--max-pools", type=int, default=config.DEFAULT_NUM_POOLS,
                        help="pool budget K (hard upper bound on k)")
    p_auto.add_argument("--min-pools", type=int, default=2, help="smallest k to evaluate")
    p_auto.add_argument("--tau", type=float, default=None,
                        help="sensitive budget: ΔSN%% (worst-case) <= tau percent, e.g. 40")
    p_auto.add_argument("--plot", help="write the width-vs-k figure to this path")
    p_auto.set_defaults(func=cmd_autotune)

    p_report = sub.add_parser("report", help="turn analysis output into LaTeX/Markdown tables")
    p_report.add_argument("file", nargs="?", help="analysis text file (stdin if omitted)")
    p_report.set_defaults(func=cmd_report)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
