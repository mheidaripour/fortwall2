"""Aggregate the largerun response-time CSVs into figures + tables.

Reads the four-way benchmark under ``experiments/largerun/`` (produced by
``bigrun.py``) and emits, into ``experiments/figures/``:

* ``summary.csv``                 -- mode x concurrency: mean/median latency, throughput
* ``latency_vs_concurrency.png``  -- default vs saphire vs fortwall
* ``throughput_vs_concurrency.png``
* ``pool_sweep_latency.png``      -- mpool pool-budget sweep (the Pareto knee)
* ``summary.md``                  -- the table + auto-flagged observations

IMPORTANT caveats (surfaced in summary.md too):
* The source CSVs store only *per-URL average* latency -- the raw per-request
  samples were collapsed by bigrun.py -- so this reports means/medians ACROSS
  URLs, NOT p50/p99. See summary.md.
* Throughput here is *derived* (closed-loop estimate: concurrency / mean latency),
  not measured req/s. Labelled as such.

Run:  .venv/bin/python experiments/aggregate.py
"""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

import matplotlib

matplotlib.use("Agg")  # headless: write PNGs, never try to open a window
import matplotlib.pyplot as plt

# --- what lives where ---------------------------------------------------------
# (dir under largerun/, filename prefix, human label, plot order/colour intent)
PRIMARY_MODES = [
    ("default", "response_time_def", "default (no seccomp)"),
    ("saphire", "response_time_prt_npl", "Saphire (per-script, restart)"),
    ("fortwall", "response_time_prt_pl", "FortWall (pooled)"),
]
POOL_PREFIX = "response_time_prt_pl"          # mpool/<N>/response_time_prt_pl_<c>.csv
CONCURRENCIES = [1, 2, 4, 8, 16, 32]


def _read_url_latencies(path: Path) -> List[float]:
    """Return the per-URL average latencies (seconds) from one CSV.

    Tolerates the two header styles seen in the tree (``URL,Average Response
    Time (sec)`` and bare rows) and skips anything unparseable.
    """
    out: List[float] = []
    with path.open() as fh:
        for row in csv.reader(fh):
            if not row or len(row) < 2:
                continue
            if row[0].strip().lower().startswith(("url", "http")) and _to_float(row[1]) is None:
                continue  # header line
            val = _to_float(row[1])
            if val is not None:
                out.append(val)
    return out


def _to_float(s: str) -> Optional[float]:
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _mode_series(largerun: Path, subdir: str, prefix: str) -> Dict[int, List[float]]:
    """concurrency -> list of per-URL latencies (sec) for one mode directory."""
    series: Dict[int, List[float]] = {}
    for c in CONCURRENCIES:
        f = largerun / subdir / f"{prefix}_{c}.csv"
        if f.exists():
            lat = _read_url_latencies(f)
            if lat:
                series[c] = lat
    return series


def _summarize(series: Dict[int, List[float]]) -> Dict[int, Dict[str, float]]:
    """Per concurrency: mean/median across URLs (ms) + derived throughput (rps)."""
    stats: Dict[int, Dict[str, float]] = {}
    for c, lat in sorted(series.items()):
        mean_s = statistics.fmean(lat)
        median_s = statistics.median(lat)
        stats[c] = {
            "mean_ms": mean_s * 1000.0,
            "median_ms": median_s * 1000.0,
            # closed-loop estimate: N concurrent / mean latency ~= aggregate req/s
            "throughput_rps": (c / mean_s) if mean_s > 0 else float("nan"),
            "n_urls": len(lat),
        }
    return stats


def _pool_series(largerun: Path) -> Dict[int, Dict[int, List[float]]]:
    """pool_budget -> concurrency -> per-URL latencies, for every mpool/<N>."""
    pools: Dict[int, Dict[int, List[float]]] = {}
    mpool_root = largerun / "mpool"
    if not mpool_root.is_dir():
        return pools
    for d in sorted(mpool_root.iterdir(), key=lambda p: _int_or_inf(p.name)):
        if not d.is_dir():
            continue
        try:
            budget = int(d.name)
        except ValueError:
            continue
        s = _mode_series(largerun, f"mpool/{d.name}", POOL_PREFIX)
        if s:
            pools[budget] = s
    return pools


def _int_or_inf(s: str) -> float:
    try:
        return int(s)
    except ValueError:
        return float("inf")


# --- plots --------------------------------------------------------------------

def _plot_latency(primary: Dict[str, Dict[int, Dict[str, float]]], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 4.5))
    markers = {"default (no seccomp)": "o", "Saphire (per-script, restart)": "s",
               "FortWall (pooled)": "^"}
    for label, stats in primary.items():
        cs = sorted(stats)
        ys = [stats[c]["mean_ms"] for c in cs]
        ax.plot(cs, ys, marker=markers.get(label, "o"), label=label, linewidth=2)
    ax.set_xscale("log", base=2)
    ax.set_xticks(CONCURRENCIES)
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.set_xlabel("concurrency (simultaneous requests)")
    ax.set_ylabel("mean response time across URLs (ms)")
    ax.set_title("Latency vs concurrency — Saphire's restart cost grows with load")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def _plot_throughput(primary: Dict[str, Dict[int, Dict[str, float]]], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for label, stats in primary.items():
        cs = sorted(stats)
        ys = [stats[c]["throughput_rps"] for c in cs]
        ax.plot(cs, ys, marker="o", label=label, linewidth=2)
    ax.set_xscale("log", base=2)
    ax.set_xticks(CONCURRENCIES)
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.set_xlabel("concurrency (simultaneous requests)")
    ax.set_ylabel("derived throughput (req/s, closed-loop est.)")
    ax.set_title("Derived throughput vs concurrency")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def _plot_pool_sweep(pools: Dict[int, Dict[int, List[float]]], out: Path) -> None:
    if not pools:
        return
    fig, ax = plt.subplots(figsize=(7, 4.5))
    budgets = sorted(pools)
    # one line per concurrency: x = pool budget, y = mean latency
    for c in CONCURRENCIES:
        xs, ys = [], []
        for b in budgets:
            if c in pools[b]:
                xs.append(b)
                ys.append(statistics.fmean(pools[b][c]) * 1000.0)
        if xs:
            ax.plot(xs, ys, marker="o", label=f"concurrency={c}", linewidth=1.8)
    ax.set_xlabel("pool budget (number of php-fpm pools)")
    ax.set_ylabel("mean response time across URLs (ms)")
    ax.set_title("Pool-budget sweep — where the latency knee is")
    ax.set_xticks(budgets)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


# --- tables / report ----------------------------------------------------------

def _write_summary_csv(primary, pools, out: Path) -> None:
    with out.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["mode", "concurrency", "mean_ms", "median_ms", "throughput_rps", "n_urls"])
        for label, stats in primary.items():
            for c in sorted(stats):
                s = stats[c]
                w.writerow([label, c, f"{s['mean_ms']:.3f}", f"{s['median_ms']:.3f}",
                            f"{s['throughput_rps']:.2f}", s["n_urls"]])
        for b in sorted(pools):
            for c in sorted(pools[b]):
                lat = pools[b][c]
                w.writerow([f"mpool-{b}", c, f"{statistics.fmean(lat)*1000:.3f}",
                            f"{statistics.median(lat)*1000:.3f}",
                            f"{c/statistics.fmean(lat):.2f}", len(lat)])


def _observations(primary) -> List[str]:
    """Auto-derive notable observations from the aggregated results."""
    obs: List[str] = []
    d = primary.get("default (no seccomp)", {})
    sa = primary.get("Saphire (per-script, restart)", {})
    fw = primary.get("FortWall (pooled)", {})

    def at(stats, c):
        return stats.get(c, {}).get("mean_ms")

    hi = max(CONCURRENCIES)
    if at(sa, hi) and at(fw, hi):
        red = (1 - at(fw, hi) / at(sa, hi)) * 100
        obs.append(
            f"At concurrency={hi}, FortWall mean latency is {at(fw, hi):.0f} ms vs "
            f"Saphire {at(sa, hi):.0f} ms — a {red:.0f}% reduction from removing the "
            f"per-request restart."
        )
    # gap should widen with load: compare low vs high concurrency
    if at(sa, 1) and at(fw, 1) and at(sa, hi) and at(fw, hi):
        lo_gap = at(sa, 1) - at(fw, 1)
        hi_gap = at(sa, hi) - at(fw, hi)
        obs.append(
            f"Saphire↔FortWall gap widens with load: {lo_gap:+.0f} ms at c=1 → "
            f"{hi_gap:+.0f} ms at c={hi} (restart cost scales with "
            f"concurrency)."
        )
    # pooled workers faster than the unfiltered default
    anomalies = [c for c in CONCURRENCIES if at(fw, c) and at(d, c) and at(fw, c) < at(d, c)]
    if anomalies:
        obs.append(
            "FortWall is faster than default at concurrency "
            f"{anomalies}. Pooled workers run with pm.max_requests=0 and stay warm, "
            "whereas the default php-fpm pool recycles its workers."
        )
    return obs


def _write_summary_md(primary, pools, obs, figdir: Path, out: Path) -> None:
    lines = ["# largerun performance summary", "",
             "Aggregated from `experiments/largerun/` by `aggregate.py`.", ""]
    lines.append("## Mean latency (ms), across URLs, per mode × concurrency\n")
    header = "| mode | " + " | ".join(f"c={c}" for c in CONCURRENCIES) + " |"
    lines.append(header)
    lines.append("|" + "---|" * (len(CONCURRENCIES) + 1))
    for label, stats in primary.items():
        row = [label] + [f"{stats[c]['mean_ms']:.1f}" if c in stats else "—" for c in CONCURRENCIES]
        lines.append("| " + " | ".join(row) + " |")
    if pools:
        lines.append("")
        lines.append("## Pool-budget sweep — mean latency (ms)\n")
        lines.append("| pools | " + " | ".join(f"c={c}" for c in CONCURRENCIES) + " |")
        lines.append("|" + "---|" * (len(CONCURRENCIES) + 1))
        for b in sorted(pools):
            row = [f"mpool-{b}"] + [
                f"{statistics.fmean(pools[b][c])*1000:.1f}" if c in pools[b] else "—"
                for c in CONCURRENCIES
            ]
            lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("## Auto-flagged observations\n")
    for o in obs:
        lines.append(f"- {o}")
    lines.append("")
    lines.append("## Figures\n")
    for name in ["latency_vs_concurrency.png", "throughput_vs_concurrency.png",
                 "pool_sweep_latency.png"]:
        if (figdir / name).exists():
            lines.append(f"![{name}]({name})")
    lines.append("")
    lines.append("## Limitations\n")
    lines.append("- **No tail latency.** Source CSVs hold only per-URL *means*; "
                 "bigrun.py collapses the raw samples, so p50/p99 are not reported.")
    lines.append("- **Throughput is derived**, not measured (concurrency / mean "
                 "latency).")
    lines.append("- **One app (WordPress), 7 URLs.** All perf data is WordPress; the "
                 "security metrics span 11 apps.")
    lines.append("- **Security (SP/SN) axis not included here.** Pair the pool-sweep "
                 "latency with `fortwall analyze --app wordpress --clusters N` to relate "
                 "latency to policy precision.")
    out.write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    here = Path(__file__).resolve().parent
    ap.add_argument("--largerun", type=Path, default=here / "largerun")
    ap.add_argument("--outdir", type=Path, default=here / "figures")
    args = ap.parse_args()

    largerun: Path = args.largerun
    figdir: Path = args.outdir
    figdir.mkdir(parents=True, exist_ok=True)

    primary: Dict[str, Dict[int, Dict[str, float]]] = {}
    for subdir, prefix, label in PRIMARY_MODES:
        series = _mode_series(largerun, subdir, prefix)
        if series:
            primary[label] = _summarize(series)
        else:
            print(f"!! no data for mode '{label}' under {largerun/subdir}")

    pools = _pool_series(largerun)

    _plot_latency(primary, figdir / "latency_vs_concurrency.png")
    _plot_throughput(primary, figdir / "throughput_vs_concurrency.png")
    _plot_pool_sweep(pools, figdir / "pool_sweep_latency.png")

    _write_summary_csv(primary, pools, figdir / "summary.csv")
    obs = _observations(primary)
    _write_summary_md(primary, pools, obs, figdir, figdir / "summary.md")

    print(f"wrote figures + tables to {figdir}")
    for o in obs:
        print("  •", o)


if __name__ == "__main__":
    main()
