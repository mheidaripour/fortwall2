"""Run the clustering ablation across apps and emit table + figure.

Outputs (into experiments/figures/):
  ablation.csv        -- per-app scores for every variant
  ablation_avg.csv    -- metrics averaged across apps
  ablation_curves.png -- ASP(k) sweep for key variants on one app

Offline, committed data only. Run:  .venv/bin/python experiments/run_ablation.py
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from fortwall_pool import ablation, autotune, config, syscalls

HERE = Path(__file__).resolve().parent
ART = HERE.parent.parent / "artifacts" / "stage2_out"
FIGDIR = HERE / "figures"

APP_FILES = {
    "wordpress": ART / "stage2_out_wordpress",
    "drupal": ART / "stage2_out_drupal",
    "joomla": ART / "stage2_out_joomla",
    "phpmyadmin": ART / "stage2_out_phpmyadmin",
    "moodle": ART / "stage2_out_moodle27",
}


def main() -> None:
    FIGDIR.mkdir(parents=True, exist_ok=True)
    sensitive = syscalls.load_sensitive_syscalls(str(config.WORK.syscall_table))

    res = ablation.run(APP_FILES, sensitive, budget_k=12, k_min=2)
    avg = ablation.average_across_apps(res)

    # per-app CSV
    with (FIGDIR / "ablation.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["app", "variant", "axis", "k_star", "SP%", "ASP%", "dSP%", "dSN%",
                    "meanASP", "ASP_std"])
        for app, scores in res.per_app.items():
            for s in scores:
                w.writerow([app, s.variant, s.axis, s.k_star, s.sp_pct, s.asp_pct,
                            s.delta_sp_pct, s.delta_sn_pct, s.mean_asp, s.asp_std])

    # averaged CSV
    base_asp = next(s.asp_pct for s in avg if s.variant == "full-method")
    with (FIGDIR / "ablation_avg.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["variant", "axis", "SP%", "ASP%", "dSP%", "dSN%", "meanASP", "dASP_vs_full"])
        for s in avg:
            w.writerow([s.variant, s.axis, s.sp_pct, s.asp_pct, s.delta_sp_pct,
                        s.delta_sn_pct, s.mean_asp, round(s.asp_pct - base_asp, 2)])

    _plot_curves(res, sensitive, "wordpress", APP_FILES["wordpress"],
                 FIGDIR / "ablation_curves.png")

    print(f"{'variant':20} {'axis':10} {'ASP%':>6} {'dSN%':>6} {'meanASP':>8} {'ΔvsFull':>8}")
    for s in avg:
        print(f"{s.variant:20} {s.axis:10} {s.asp_pct:>6.2f} {s.delta_sn_pct:>6.2f} "
              f"{s.mean_asp:>8.2f} {s.asp_pct - base_asp:>+8.2f}")
    print(f"\nwrote ablation.csv / ablation_avg.csv / ablation_curves.png to {FIGDIR}")


def _plot_curves(res, sensitive, app_name, app_path, out: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    app = ablation.load_app(app_path)
    show = ["full-method", "random-partition", "ward", "kmeans"]
    variants = {v.name: v for v in res.variants}
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ks = list(range(2, 13))
    for name in show:
        v = variants.get(name)
        if v is None:
            continue
        xs, ys = [], []
        for k in ks:
            labels = ablation.assign(app, k, v, seed=0)
            if labels is None:
                continue
            xs.append(k)
            ys.append(autotune.score_labels(app.profiles, labels, sensitive, k=k).asp_pct)
        style = "--" if name == "random-partition" else "-"
        ax.plot(xs, ys, marker="o", linestyle=style, label=name, linewidth=2)
    ax.set_xlabel("pool budget k")
    ax.set_ylabel("attack surface ASP% (request-weighted)")
    ax.set_title(f"Clustering ablation — ASP(k) on {app_name}")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
