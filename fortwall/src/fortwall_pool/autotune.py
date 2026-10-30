"""Auto-tuner: choose the pool count k by constrained optimization.

FortWall's clustering takes a pool budget (``--clusters`` / ``-p``). This module
frames that choice as an optimization and picks k automatically:

    minimize   ASP%(k)                  (attack surface = 100 - SP%)
    subject to dSN%(k) <= tau           (sensitive-syscall inflation budget)
               k       <= K             (pool budget: memory / worker fragmentation)

**Metrics are FortWall's standard SP/SN metrics; no new definitions.** For a pooling
of the scripts into k pools, each distinct syscall profile ``c`` (a stage2
"category") has minimal set ``s_c`` and weight ``w_c`` = number of URLs with that
profile; its pool's *effective* policy is ``P(c) = union(members) | intersection``
(the baseline every pool inherits; the same "add the intersection back" that
``pipeline.analyze_report_lines`` does before scoring), so ``P(c) >= s_c`` always.

* **SP%(k)**  = request-weighted mean of ``(TOTAL - |P(c)|)/TOTAL`` -- the standard
  SP% (share of syscalls blocked), weighted by traffic instead of averaged
  unweighted over pools. **ASP%(k) = 100 - SP%(k)** is what the knee minimises.
* **dSP%(k)** = ``max_c |P(c) - s_c| / TOTAL``   -- ΔSP (worst case).
* **dSN%(k)** = ``max_c |(P(c)-s_c) & SN| / SN_BASE`` -- ΔSN (worst
  case); this is the constraint metric.

So ASP is not a new metric -- it is exactly ``100 - SP%``; dSP%/dSN% use the
worst-case (max) convention (matching ``clustering
.diagnostics_lines``). The only intentional departure is that SP% is
**request-weighted** (surface actually exposed to traffic); the unweighted number
is reported alongside for direct comparison with the existing tables.

ASP% decreases as k grows (more pools -> tighter unions), from the single-pool
global union toward the Saphire per-script ideal. The *knee* is the smallest k
capturing most of the reduction; past it, extra pools buy little surface but cost
memory / worker fragmentation (the empirical p8 degradation in the perf sweep).
Minimizing sum_j |P_j| over k-partitions is NP-hard (union-cost / correlation
clustering), so the clustering stays a heuristic solver -- this tunes its one
free parameter. Runs offline on the committed ``stage2_out`` data (no VM needed).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple, Union

from . import config, pipeline, urlmap


@dataclass
class ObjectivePoint:
    """Metric scores at one pool count k (SP%, ASP%, ΔSP%, ΔSN%)."""

    k: int                      # total pools (dedicated + clustered)
    sp_pct: float               # SP% (request-weighted): share of syscalls blocked
    asp_pct: float              # ASP% = 100 - SP%: attack surface (what the knee minimises)
    sp_pct_unweighted: float    # SP% averaged unweighted over pools (for table parity)
    delta_sp_pct: float         # ΔSP% (worst case): max width inflation from pooling
    delta_sn_pct: float         # ΔSN% (worst case): max sensitive inflation -> constraint
    width: float                # weighted mean |P(c)| in syscalls (ASP% expressed as a count)
    feasible: bool = True       # satisfies the ΔSN% <= tau constraint


@dataclass
class TuneResult:
    """Full sweep plus the selected k and why."""

    points: List[ObjectivePoint]
    recommended_k: Optional[int]
    reason: str
    budget_k: int
    tau: Optional[float]


# --- one profile = one stage2 category -------------------------------------

@dataclass
class _Profile:
    numbers: Set[int]           # minimal syscall set s_c (full, incl. baseline)
    weight: int                 # w_c = number of URLs with this profile
    first_url: str


def _load_profiles(file_path: Union[str, Path]) -> List[_Profile]:
    """Full per-profile minimal sets + URL weights, straight from stage2_out."""
    cats = urlmap.categorize_urls_by_numbers(file_path)
    profs: List[_Profile] = []
    for c in cats:
        urls = c["urls"]
        if not urls:
            continue
        profs.append(_Profile(numbers=set(c["associated_numbers"]),
                              weight=len(urls), first_url=urls[0]))
    return profs


def _pool_policies(plan) -> Tuple[List[Set[int]], Dict[str, int]]:
    """Effective (baseline-restored) policy per pool + a url -> pool-index map."""
    policies: List[Set[int]] = []
    url_to_pool: Dict[str, int] = {}
    for p, cluster in enumerate(plan.all_clusters):
        policies.append(set(cluster["associated_numbers"]) | plan.intersection)
        for url in cluster["urls"]:
            url_to_pool[url] = p
    return policies, url_to_pool


def score_labels(
    profiles: Sequence["_Profile"],
    assignment: Sequence[Optional[int]],
    sensitive: Sequence[int],
    k: Optional[int] = None,
) -> ObjectivePoint:
    """Score ANY pooling of ``profiles`` in the standard metrics (SP/ASP/ΔSP/ΔSN).

    ``assignment[i]`` is the pool id of ``profiles[i]`` (``None`` to exclude a
    profile). A pool's effective policy is the union of its members' minimal
    sets (which already contain the global intersection, so it is baseline-
    restored by construction). This is the shared objective used by BOTH the
    auto-tuner and the ablation harness, so they cannot diverge.
    """
    sens: Set[int] = set(sensitive)
    # pool id -> union of member profiles' syscall sets (the effective policy)
    pools: Dict[int, Set[int]] = {}
    for prof, pid in zip(profiles, assignment):
        if pid is None:
            continue
        pools.setdefault(pid, set()).update(prof.numbers)

    tot_w = 0
    sum_width = 0.0            # for request-weighted SP%
    sum_sp_unweighted = 0.0    # for unweighted (per-profile) SP%, table parity
    n_scored = 0
    max_dsp = 0.0              # ΔSP% worst case (share of TOTAL added)
    max_dsn = 0.0              # ΔSN% worst case (share of SN_BASE added)
    for prof, pid in zip(profiles, assignment):
        if pid is None:
            continue
        policy = pools[pid]
        added = policy - prof.numbers
        tot_w += prof.weight
        n_scored += 1
        sum_width += prof.weight * len(policy)
        sum_sp_unweighted += (config.TOTAL_SYSCALLS - len(policy)) / config.TOTAL_SYSCALLS * 100
        max_dsp = max(max_dsp, len(added) / config.TOTAL_SYSCALLS * 100)
        max_dsn = max(max_dsn, len(added & sens) / config.SN_BASE * 100)

    kk = k if k is not None else len(pools)
    if tot_w == 0:
        return ObjectivePoint(kk, 100.0, 0.0, 100.0, 0.0, 0.0, 0.0)
    width = sum_width / tot_w
    asp = width / config.TOTAL_SYSCALLS * 100
    return ObjectivePoint(
        k=kk,
        sp_pct=round(100 - asp, 2),
        asp_pct=round(asp, 2),
        sp_pct_unweighted=round(sum_sp_unweighted / n_scored, 2),
        delta_sp_pct=round(max_dsp, 2),
        delta_sn_pct=round(max_dsn, 2),
        width=round(width, 2),
    )


def evaluate_k(
    file_path: Union[str, Path],
    k: int,
    sensitive: Sequence[int],
    profiles: Optional[List[_Profile]] = None,
    sensitivity_weight: float = 1.0,
) -> ObjectivePoint:
    """Score the FortWall two-phase pooling at pool count ``k``.

    ``k`` is the *total* pool budget (dedicated high-share pools + clustered
    pools), matching ``pipeline.build_pool_plan(total_pools=k)``. Delegates the
    metric math to :func:`score_labels` so it stays identical to the ablation.

    ``sensitivity_weight > 1`` clusters with the sensitivity-aware distance; the
    default keeps the plain-Jaccard path.
    """
    if profiles is None:
        profiles = _load_profiles(file_path)

    plan = pipeline.build_pool_plan(
        file_path, total_pools=k,
        sensitive=sensitive if sensitivity_weight != 1.0 else None,
        sensitivity_weight=sensitivity_weight,
    )
    _, url_to_pool = _pool_policies(plan)
    assignment = [url_to_pool.get(prof.first_url) for prof in profiles]
    return score_labels(profiles, assignment, sensitive, k=k)


def _knee_index(ks: List[int], ws: List[float]) -> int:
    """Kneedle-lite: index of the point of max drop below the endpoint chord.

    Works on the decreasing convex width curve; no external dependency. If the
    curve is flat/degenerate, returns the smallest-k index.
    """
    n = len(ks)
    if n <= 2:
        return 0
    x0, x1 = ks[0], ks[-1]
    y0, y1 = ws[0], ws[-1]
    dx = (x1 - x0) or 1
    best_i, best_dist = 0, -1.0
    for i in range(n):
        # chord value at ks[i], then vertical distance of the point below it
        chord = y0 + (y1 - y0) * (ks[i] - x0) / dx
        dist = chord - ws[i]        # positive when the curve dips below the chord
        if dist > best_dist:
            best_dist, best_i = dist, i
    return best_i


def tune(
    file_path: Union[str, Path],
    sensitive: Sequence[int],
    budget_k: int,
    tau: Optional[float] = None,
    k_min: int = 2,
    sensitivity_weight: float = 1.0,
) -> TuneResult:
    """Sweep k in [k_min, budget_k], score each, and select the knee under tau.

    ``budget_k`` is the hard pool budget K. ``tau`` (optional) caps the weighted
    sensitive inflation W_SN(k). Pools that fail tau are marked infeasible and
    excluded from selection.

    ``sensitivity_weight > 1`` runs the whole sweep with sensitivity-aware
    clustering, so tau can be met at a smaller k than the plain path needs.
    """
    profiles = _load_profiles(file_path)
    n_profiles = len(profiles)
    if n_profiles == 0:
        return TuneResult([], None,
                          f"input {file_path} has no usable syscall profiles (empty file?)",
                          budget_k, tau)
    # AgglomerativeClustering needs n_clusters <= n_samples; also build_pool_plan
    # needs clusters = total_pools - dedicated >= 1. Cap the sweep accordingly.
    k_hi = min(budget_k, max(k_min, n_profiles))

    points: List[ObjectivePoint] = []
    for k in range(k_min, k_hi + 1):
        try:
            pt = evaluate_k(file_path, k, sensitive, profiles=profiles,
                            sensitivity_weight=sensitivity_weight)
        except Exception:
            # k is infeasible for this app: either k <= #dedicated pools (no
            # clusters left) or k > #distinct profiles. Skip and keep scanning.
            continue
        if tau is not None:
            pt.feasible = pt.delta_sn_pct <= tau
        points.append(pt)

    feasible = [p for p in points if p.feasible]
    if not feasible:
        return TuneResult(points, None,
                          f"no k in [{k_min},{k_hi}] satisfies ΔSN% <= {tau}",
                          budget_k, tau)

    ks = [p.k for p in feasible]
    ws = [p.asp_pct for p in feasible]          # minimise attack surface (ASP%)
    knee = feasible[_knee_index(ks, ws)]
    reason = (
        f"knee of the ASP% curve at k={knee.k} "
        f"(SP {knee.sp_pct:.1f}%, ASP {knee.asp_pct:.1f}%, ΔSN {knee.delta_sn_pct:.1f}%); "
        f"largest feasible k={ks[-1]} reaches ASP {feasible[-1].asp_pct:.1f}% — "
        f"the extra {ks[-1]-knee.k} pools cut only "
        f"{knee.asp_pct - feasible[-1].asp_pct:.1f} more ASP%."
    )
    return TuneResult(points, knee.k, reason, budget_k, tau)


def format_lines(res: TuneResult) -> List[str]:
    """Human-readable sweep table + recommendation."""
    lines = [
        f"pool budget K = {res.budget_k}"
        + (f", sensitive budget τ = ΔSN% ≤ {res.tau}" if res.tau is not None else ""),
        "",
        f"{'k':>3}  {'SP%':>6}  {'ASP%':>6}  {'SP%(uw)':>7}  {'ΔSP%':>6}  {'ΔSN%':>6}  feasible",
    ]
    for p in res.points:
        lines.append(
            f"{p.k:>3}  {p.sp_pct:>6.2f}  {p.asp_pct:>6.2f}  {p.sp_pct_unweighted:>7.2f}  "
            f"{p.delta_sp_pct:>6.2f}  {p.delta_sn_pct:>6.2f}  {'yes' if p.feasible else 'NO'}"
        )
    lines.append("")
    if res.recommended_k is not None:
        lines.append(f"RECOMMENDED k = {res.recommended_k} — {res.reason}")
    else:
        lines.append(f"NO RECOMMENDATION — {res.reason}")
    return lines


def plot(res: TuneResult, out_path: Union[str, Path]) -> None:
    """Write the width-vs-k curve with the knee + budget marked (optional)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ks = [p.k for p in res.points]
    asp = [p.asp_pct for p in res.points]
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(ks, asp, marker="o", linewidth=2, label="ASP% (attack surface)")
    infeas = [(p.k, p.asp_pct) for p in res.points if not p.feasible]
    if infeas:
        ax.scatter(*zip(*infeas), color="red", zorder=5, label="infeasible (ΔSN% > τ)")
    if res.recommended_k is not None:
        rp = next(p for p in res.points if p.k == res.recommended_k)
        ax.axvline(res.recommended_k, color="green", linestyle="--",
                   label=f"selected k={res.recommended_k}")
        ax.scatter([rp.k], [rp.asp_pct], color="green", zorder=6, s=80)
    ax.set_xlabel("pool budget k")
    ax.set_ylabel("attack surface (ASP%, request-weighted)")
    ax.set_title("Auto-tuner: security width vs pool count (knee = selected k)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
