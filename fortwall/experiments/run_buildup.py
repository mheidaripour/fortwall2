"""Design-faithful component build-up for the FortWall pipeline.

Follows the actual pipeline: per-script (Saphire) -> exact-match categorization
(lossless dedup, same surface) -> exclude high-share (Phase I) + cluster (Phase
II) to k*. Shows that categorization is free (a flat ideal plateau) and that
surface only rises when clustering consolidates below #categories; isolates
Phase I at matched k*.

Emits buildup_avg.csv and buildup_*.png figures. Offline, committed data.
Run:  .venv/bin/python -m experiments.run_buildup
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from fortwall_pool import ablation, autotune, config, syscalls
from experiments.run_ablation import APP_FILES, FIGDIR

ORDER = ["saphire-per-script", "exact-categories", "cluster-all@k*",
         "full-method@k*", "single-pool"]
LABEL = {
    "saphire-per-script": "Saphire (per-script filters)",
    "exact-categories": "Exact-match categorization (lossless dedup)",
    "cluster-all@k*": "Cluster to k* WITHOUT Phase I (no exclusion)",
    "full-method@k*": "Full method: Phase I + II to k*",
    "single-pool": "Single global-union pool",
}


def main() -> None:
    FIGDIR.mkdir(parents=True, exist_ok=True)
    sensitive = syscalls.load_sensitive_syscalls(str(config.WORK.syscall_table))

    per_app = {}
    for name, path in APP_FILES.items():
        app = ablation.load_app(path)
        tuned = autotune.tune(path, sensitive, budget_k=12, k_min=2)
        if tuned.recommended_k is None:
            continue
        stages = {s.stage: s for s in ablation.stage_buildup(app, sensitive, tuned.recommended_k)}
        per_app[name] = (app, tuned.recommended_k, stages)

    def avg(stage, attr):
        vals = [s[2][stage].__dict__[attr] for s in per_app.values() if stage in s[2]]
        return float(np.mean(vals))

    with (FIGDIR / "buildup_avg.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["stage", "n_pools", "SP%", "ASP%", "dSP%", "dSN%"])
        for st in ORDER:
            w.writerow([st, round(avg(st, "n_pools"), 1), round(avg(st, "sp_pct"), 2),
                        round(avg(st, "asp_pct"), 2), round(avg(st, "delta_sp_pct"), 2),
                        round(avg(st, "delta_sn_pct"), 2)])

    _plot_main(per_app, sensitive, "wordpress", FIGDIR / "buildup_wordpress.png")
    _plot_sweep(per_app, sensitive, "wordpress", FIGDIR / "buildup_sweep_wordpress.png")
    _plot_main_asp_unweighted(per_app, sensitive, "wordpress",
                              FIGDIR / "buildup_asp_unweighted_wordpress.png")

    print(f"{'stage':44} {'#pools':>8} {'ASP%':>6} {'dSP%':>6} {'dSN%':>6}")
    for st in ORDER:
        print(f"{LABEL[st]:44} {avg(st,'n_pools'):>8.1f} {avg(st,'asp_pct'):>6.2f} "
              f"{avg(st,'delta_sp_pct'):>6.2f} {avg(st,'delta_sn_pct'):>6.2f}")
    print(f"\nwrote buildup_avg.csv / buildup_*.png to {FIGDIR}")


# Palette: one method-path hue (blue) + neutral reference ink; orange is reserved
# for the Phase-I contrast in the supplementary sweep. Text in neutral ink, not
# the series colour.
BLUE = "#1f77b4"
ORANGE = "#e8710a"
INK = "#333333"
MUTED = "#888888"

# Plot rcParams: serif + Computer-Modern-style math (no LaTeX toolchain
# required), TrueType (Type 42) font embedding in PDFs.
PUB_RC = {
    "font.family": "serif",
    "font.serif": ["DejaVu Serif"],
    "mathtext.fontset": "cm",
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "axes.linewidth": 0.8,
}


def _full_curve(app, sensitive):
    """True full-method ASP(k) over k = #dedicated+1 .. #categories."""
    full_v = next(v for v in ablation.default_variants() if v.name == "full-method")
    xs, ys = [], []
    for k in range(len(app.dedicated) + 1, len(app.profiles) + 1):
        lab = ablation.assign(app, k, full_v)
        if lab is None:
            continue
        xs.append(k)
        ys.append(autotune.score_labels(app.profiles, lab, sensitive).asp_pct)
    return xs, ys


def _plot_main(per_app, sensitive, app_name, out: Path) -> None:
    """Publication figure: the true ASP(k) curve drawn faintly, with the three
    milestone configs bold-labeled on top. Exports vector PDF + PNG preview."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    app, k_star, stages = per_app[app_name]
    n_cat = len(app.profiles)
    n_scripts = int(sum(p.weight for p in app.profiles))
    ideal = stages["exact-categories"].asp_pct
    cx, cy = _full_curve(app, sensitive)

    # Read-in-place: short direct labels next to each milestone (leader line when
    # the label is lifted into the empty upper region). Points share one hue; the
    # ASP(k) curve gets its own colour and is the sole legend entry.
    CURVE = "#d1495b"                      # muted red, distinct from the point hues
    # each milestone a distinct CVD-safe (Okabe-Ito) colour + shape; amber (not
    # vermilion) for the middle point so it doesn't clash with the red curve.
    pts = [
        (1, stages["single-pool"].asp_pct, "#0072B2", "o",
         "single pool ($k=1$)", (11, -3), "left"),
        (k_star, stages["full-method@k*"].asp_pct, "#E69F00", "s",
         f"Phase I + Phase II ($k^\\star={k_star}$)", (0, 34), "center"),
        (n_cat, ideal, "#009E73", "^",
         "Phase I: exact categories", (-2, 30), "right"),
    ]

    with plt.rc_context(PUB_RC):
        fig, ax = plt.subplots(figsize=(5.6, 3.7))

        # ideal-surface reference line, labeled simply "Saphire (per-script)"
        ax.axhline(ideal, color=MUTED, linestyle="--", linewidth=1.0, zorder=1)
        ax.annotate("Saphire (per-script)", xy=(1.05, ideal),
                    textcoords="offset points", xytext=(0, 3),
                    ha="left", va="bottom", fontsize=8.5, color=MUTED)

        # the TRUE ASP(k) curve, coloured, kept in the legend
        ax.plot(cx, cy, "-", color=CURVE, linewidth=1.4, alpha=0.85, zorder=2,
                label="attack surface across $k$")

        # milestone points with read-in-place labels; distinct colour + shape
        for x, y, color, marker, label, off, ha in pts:
            ax.scatter([x], [y], s=80, color=color, marker=marker, zorder=4,
                       edgecolor="white", linewidth=1.0)
            arrow = dict(arrowstyle="-", color=MUTED, lw=0.6,
                         shrinkA=2, shrinkB=4) if abs(off[1]) > 20 else None
            ax.annotate(label, (x, y), textcoords="offset points", xytext=off,
                        fontsize=8.5, color=INK, ha=ha, arrowprops=arrow)

        ax.axvline(k_star, color=MUTED, linestyle=":", linewidth=0.8, zorder=1)

        ax.set_xscale("log")
        ax.set_xlim(0.7, n_cat * 1.7)
        ax.set_xlabel("number of distinct pools / filters (log scale)")
        ax.set_ylabel("attack surface ASP% (request-weighted)")
        ax.grid(True, which="both", axis="both", alpha=0.18, linewidth=0.6)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.legend(loc="upper right", frameon=False, fontsize=8.5)
        fig.tight_layout()
        fig.savefig(out.with_suffix(".pdf"))
        fig.savefig(out, dpi=200)
    plt.close(fig)


def _asp_uw_curve(app, sensitive):
    """True full-method ASP% (= 100 - SP%), unweighted over profiles, over k."""
    full_v = next(v for v in ablation.default_variants() if v.name == "full-method")
    xs, ys = [], []
    for k in range(len(app.dedicated) + 1, len(app.profiles) + 1):
        lab = ablation.assign(app, k, full_v)
        if lab is None:
            continue
        xs.append(k)
        ys.append(100 - autotune.score_labels(app.profiles, lab, sensitive).sp_pct_unweighted)
    return xs, ys


def _plot_main_asp_unweighted(per_app, sensitive, app_name, out: Path) -> None:
    """Companion to _plot_main using ASP% (= 100 - SP%) averaged UNWEIGHTED over
    distinct profiles -- each profile counts once, regardless of how many scripts
    share it (contrast the request-weighted ASP% figure). Lower ASP% is better,
    so the ideal (per-script) sits at the BOTTOM, mirroring the weighted figure.
    Self-contained; does not touch the existing plotting functions."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    app, k_star, _ = per_app[app_name]
    n = len(app.profiles)
    full_v = next(v for v in ablation.default_variants() if v.name == "full-method")

    def asp_uw(labels):
        return 100 - autotune.score_labels(app.profiles, labels, sensitive).sp_pct_unweighted

    asp_single = asp_uw([0] * n)
    asp_full = asp_uw(ablation.assign(app, k_star, full_v))
    asp_exact = asp_uw(list(range(n)))        # ideal: each profile its own pool (lowest ASP)
    cx, cy = _asp_uw_curve(app, sensitive)

    CURVE = "#d1495b"
    pts = [
        (1, asp_single, "#0072B2", "o", "single pool ($k=1$)", (11, -3), "left"),
        (k_star, asp_full, "#E69F00", "s",
         f"Phase I + Phase II ($k^\\star={k_star}$)", (0, -30), "center"),
        (n, asp_exact, "#009E73", "^",
         "Phase I: exact categories", (-2, 30), "right"),
    ]

    with plt.rc_context(PUB_RC):
        fig, ax = plt.subplots(figsize=(5.6, 3.7))

        ax.axhline(asp_exact, color=MUTED, linestyle="--", linewidth=1.0, zorder=1)
        ax.annotate("Saphire (per-script)", xy=(1.05, asp_exact),
                    textcoords="offset points", xytext=(0, 3),
                    ha="left", va="bottom", fontsize=8.5, color=MUTED)

        ax.plot(cx, cy, "-", color=CURVE, linewidth=1.4, alpha=0.85, zorder=2,
                label="ASP% across $k$")

        for x, y, color, marker, label, off, ha in pts:
            ax.scatter([x], [y], s=80, color=color, marker=marker, zorder=4,
                       edgecolor="white", linewidth=1.0)
            arrow = dict(arrowstyle="-", color=MUTED, lw=0.6,
                         shrinkA=2, shrinkB=4) if abs(off[1]) > 20 else None
            ax.annotate(label, (x, y), textcoords="offset points", xytext=off,
                        fontsize=8.5, color=INK, ha=ha, arrowprops=arrow)

        ax.axvline(k_star, color=MUTED, linestyle=":", linewidth=0.8, zorder=1)

        ax.set_xscale("log")
        ax.set_xlim(0.7, n * 1.7)
        ax.set_ylim(asp_exact - 3, asp_single + 3)
        ax.set_xlabel("number of distinct pools / filters (log scale)")
        ax.set_ylabel("attack surface ASP% (unweighted)")
        ax.grid(True, which="both", axis="both", alpha=0.18, linewidth=0.6)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.legend(loc="upper right", frameon=False, fontsize=8.5)
        fig.tight_layout()
        fig.savefig(out.with_suffix(".pdf"))
        fig.savefig(out, dpi=200)
    plt.close(fig)


def _plot_sweep(per_app, sensitive, app_name, out: Path) -> None:
    """Supplementary sensitivity view: ASP across every k, full vs no-Phase-I.
    Thin lines, no per-point markers; isolates the Phase I effect across budgets."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    app, k_star, stages = per_app[app_name]
    n_cat = len(app.profiles)
    ideal = stages["exact-categories"].asp_pct
    V = {v.name: v for v in ablation.default_variants()}

    def curve(variant, k_lo):
        xs, ys = [], []
        for k in range(k_lo, n_cat + 1):
            lab = ablation.assign(app, k, variant)
            if lab is None:
                continue
            xs.append(k)
            ys.append(autotune.score_labels(app.profiles, lab, sensitive).asp_pct)
        return xs, ys

    fx, fy = curve(V["full-method"], len(app.dedicated) + 1)
    nx, ny = curve(V["no-two-phase"], 1)

    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    ax.axhline(ideal, color=MUTED, linestyle="--", linewidth=1.1, zorder=1)
    ax.annotate("ideal surface", (n_cat, ideal), textcoords="offset points",
                xytext=(-4, 4), ha="right", fontsize=8, color=MUTED)
    ax.plot(nx, ny, "-", color=ORANGE, linewidth=1.6, label="cluster-all (no Phase I)")
    ax.plot(fx, fy, "-", color=BLUE, linewidth=1.8, label="full method (Phase I + II)")
    ax.axvline(k_star, color=MUTED, linestyle=":", linewidth=1)
    ax.annotate(f"k*={k_star}", (k_star, ax.get_ylim()[1]), textcoords="offset points",
                xytext=(4, -12), fontsize=9, color=INK)

    ax.set_xscale("log")
    ax.set_xlabel("pool budget k (log scale)")
    ax.set_ylabel("attack surface ASP% (request-weighted)")
    ax.set_title(f"Sensitivity: ASP across pool budget, Phase I on vs off ({app_name})")
    ax.grid(True, which="both", alpha=0.2)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(loc="upper right", frameon=False)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
