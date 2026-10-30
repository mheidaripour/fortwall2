"""Ablation harness for the clustering method.

Evaluates the clustering design by changing ONE design
axis at a time from FortWall's full method and scoring each variant against the
SAME objective the auto-tuner uses (:func:`autotune.score_labels`: SP/ASP/ΔSP/
ΔSN, request-weighted). The baseline is the deployed method:

    two-phase = on, intersection-subtraction = on,
    algorithm = agglomerative, distance = Jaccard, linkage = average.

Axes ablated (one at a time):

* **algorithm**   : agglomerative | kmeans | spectral | greedy | random
* **distance**    : jaccard | cosine | hamming | overlap   (agglomerative only)
* **linkage**     : average | complete | single | ward     (ward => euclidean)
* **two_phase**   : on | off   (off = cluster all categories, no dedicated pools)
* **subtract_intersection** : on | off (subtract the global baseline before clustering)

``random`` is the must-have naive floor: if the method does not beat a random
k-partition, the clustering is not justified. Everything runs offline on the
committed ``stage2_out`` data (no VM; performance is measured separately by the
experiments harness). Each variant is scored at each
app's auto-tuned k*, and also report the mean ASP over the whole k-sweep
(``mean_asp``) as a k-independent robustness number.
"""

from __future__ import annotations

import random as _random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple, Union

import numpy as np
from scipy.spatial.distance import pdist, squareform
from sklearn.cluster import AgglomerativeClustering, KMeans, SpectralClustering

from . import autotune, config, urlmap
from .autotune import _Profile


# --- one variant = one point in the design space ---------------------------

@dataclass(frozen=True)
class Variant:
    name: str
    algo: str = "agglomerative"
    distance: str = "jaccard"
    linkage: str = "average"
    two_phase: bool = True
    subtract_intersection: bool = True
    axis: str = "baseline"          # which axis this variant ablates (for grouping)


def default_variants() -> List[Variant]:
    """The confirmed core set: baseline + one-at-a-time changes on 5 axes."""
    return [
        Variant("full-method", axis="baseline"),
        # algorithm axis
        Variant("kmeans", algo="kmeans", axis="algorithm"),
        Variant("spectral", algo="spectral", axis="algorithm"),
        Variant("greedy-union", algo="greedy", axis="algorithm"),
        Variant("random-partition", algo="random", axis="algorithm"),
        # distance axis (agglomerative)
        Variant("cosine", distance="cosine", axis="distance"),
        Variant("hamming", distance="hamming", axis="distance"),
        Variant("overlap", distance="overlap", axis="distance"),
        # linkage axis
        Variant("complete", linkage="complete", axis="linkage"),
        Variant("single", linkage="single", axis="linkage"),
        Variant("ward", linkage="ward", axis="linkage"),
        # structural axes
        Variant("no-two-phase", two_phase=False, axis="structure"),
        Variant("no-intersection-sub", subtract_intersection=False, axis="structure"),
    ]


# --- feature + distance helpers -------------------------------------------

def _binary(sets: Sequence[Set[int]]) -> np.ndarray:
    """One-hot encode syscall sets over their shared universe."""
    universe = sorted(set().union(*sets)) if sets else []
    index = {e: i for i, e in enumerate(universe)}
    M = np.zeros((len(sets), max(1, len(universe))), dtype=float)
    for i, s in enumerate(sets):
        for e in s:
            M[i, index[e]] = 1.0
    return M


def _overlap_matrix(sets: Sequence[Set[int]]) -> np.ndarray:
    """Overlap-coefficient distance: 1 - |A∩B| / min(|A|,|B|)."""
    n = len(sets)
    D = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            a, b = sets[i], sets[j]
            m = min(len(a), len(b)) or 1
            d = 1.0 - len(a & b) / m
            D[i, j] = D[j, i] = d
    return D


def _cluster_tail(sets: List[Set[int]], m: int, v: Variant, seed: int) -> Optional[np.ndarray]:
    """Cluster ``len(sets)`` tail profiles into ``m`` clusters per the variant.

    Returns integer labels in [0, m) or ``None`` if the variant is not
    applicable / fails for this input (e.g. spectral on a degenerate matrix).
    """
    n = len(sets)
    if m <= 0 or m > n:
        return None
    if m == 1:
        return np.zeros(n, dtype=int)
    if n == 0:
        return None

    if v.algo == "random":
        rng = _random.Random(seed)
        order = list(range(n))
        rng.shuffle(order)
        labels = np.empty(n, dtype=int)
        for pos, idx in enumerate(order):
            labels[idx] = pos % m          # round-robin => all m clusters used
        return labels

    if v.algo == "greedy":                  # union-growth-minimizing agglomeration
        clusters: List[Set[int]] = [set(s) for s in sets]
        members: List[List[int]] = [[i] for i in range(n)]
        while len(clusters) > m:
            best = None
            best_growth = None
            for a in range(len(clusters)):
                for b in range(a + 1, len(clusters)):
                    grow = len(clusters[a] | clusters[b]) - max(len(clusters[a]), len(clusters[b]))
                    if best_growth is None or grow < best_growth:
                        best_growth, best = grow, (a, b)
            a, b = best
            clusters[a] |= clusters[b]
            members[a] += members[b]
            del clusters[b]
            del members[b]
        labels = np.empty(n, dtype=int)
        for cid, mem in enumerate(members):
            for i in mem:
                labels[i] = cid
        return labels

    if v.algo == "kmeans":
        X = _binary(sets)
        return KMeans(n_clusters=m, n_init=10, random_state=seed).fit_predict(X)

    if v.algo == "spectral":
        dist = squareform(pdist(_binary(sets), metric="jaccard"))
        sim = 1.0 - dist
        try:
            return SpectralClustering(n_clusters=m, affinity="precomputed",
                                      random_state=seed).fit_predict(sim)
        except Exception:
            return None

    # agglomerative (default): distance x linkage
    if v.linkage == "ward":                 # ward requires euclidean features
        X = _binary(sets)
        try:
            return AgglomerativeClustering(n_clusters=m, linkage="ward").fit_predict(X)
        except Exception:
            return None
    if v.distance == "overlap":
        D = _overlap_matrix(sets)
    else:
        D = squareform(pdist(_binary(sets), metric=v.distance))
    try:
        return AgglomerativeClustering(n_clusters=m, metric="precomputed",
                                       linkage=v.linkage).fit_predict(D)
    except Exception:
        return None


# --- assemble a full per-profile pool assignment ---------------------------

@dataclass
class AppData:
    profiles: List[_Profile]
    intersection: Set[int]
    dedicated: List[int]        # profile indices that get their own dedicated pool


def load_app(file_path: Union[str, Path]) -> AppData:
    """Categories (aligned with profiles) + intersection + high-share indices.

    Mirrors ``pipeline.build_pool_plan``: high-share categories are computed on
    the raw categories (pre-intersection-removal), so indices align 1:1 with the
    profile list.
    """
    cats = urlmap.categorize_urls_by_numbers(file_path)
    profiles = [_Profile(numbers=set(c["associated_numbers"]),
                        weight=len(c["urls"]), first_url=c["urls"][0])
                for c in cats if c["urls"]]
    intersection = urlmap.intersection_of_urls(cats)
    dedicated = urlmap.analyze_percentages(cats).high_share_indices
    return AppData(profiles=profiles, intersection=intersection, dedicated=list(dedicated))


def assign(app: AppData, k: int, v: Variant, seed: int = 0) -> Optional[List[Optional[int]]]:
    """Per-profile pool ids for pool budget ``k`` under variant ``v``.

    Returns ``None`` if ``k`` is infeasible for the variant (e.g. two-phase with
    k <= #dedicated pools, or the clusterer failed).
    """
    n = len(app.profiles)
    dedicated = app.dedicated if v.two_phase else []
    tail_idx = [i for i in range(n) if i not in set(dedicated)]
    m = k - len(dedicated)                  # clusters to form from the tail
    if m < 1 or m > len(tail_idx):
        return None

    def feat(i: int) -> Set[int]:
        s = app.profiles[i].numbers
        return (s - app.intersection) if v.subtract_intersection else set(s)

    tail_sets = [feat(i) for i in tail_idx]
    tail_labels = _cluster_tail(tail_sets, m, v, seed)
    if tail_labels is None:
        return None

    labels: List[Optional[int]] = [None] * n
    for pool_id, i in enumerate(dedicated):
        labels[i] = pool_id
    offset = len(dedicated)
    for pos, i in enumerate(tail_idx):
        labels[i] = offset + int(tail_labels[pos])
    return labels


# --- scoring a variant on an app -------------------------------------------

@dataclass
class VariantScore:
    variant: str
    axis: str
    k_star: int
    sp_pct: float = float("nan")
    asp_pct: float = float("nan")
    delta_sp_pct: float = float("nan")
    delta_sn_pct: float = float("nan")
    mean_asp: float = float("nan")      # mean ASP over the k-sweep (k-independent)
    asp_std: float = 0.0                # std over seeds (random only)
    applicable: bool = True


def score_variant(
    app: AppData,
    v: Variant,
    sensitive: Sequence[int],
    k_star: int,
    k_min: int,
    k_max: int,
    seeds: Sequence[int] = (0,),
) -> VariantScore:
    """Score a variant at k* and its mean ASP over [k_min, k_max]."""
    profiles = app.profiles

    def score_at(k: int, seed: int):
        labels = assign(app, k, v, seed=seed)
        if labels is None:
            return None
        return autotune.score_labels(profiles, labels, sensitive, k=k)

    # k* metrics (averaged over seeds for the random variant)
    pts = [score_at(k_star, s) for s in seeds]
    pts = [p for p in pts if p is not None]
    if not pts:
        return VariantScore(v.name, v.axis, k_star, applicable=False)

    asp_star = float(np.mean([p.asp_pct for p in pts]))
    out = VariantScore(
        variant=v.name, axis=v.axis, k_star=k_star,
        sp_pct=round(float(np.mean([p.sp_pct for p in pts])), 2),
        asp_pct=round(asp_star, 2),
        delta_sp_pct=round(float(np.mean([p.delta_sp_pct for p in pts])), 2),
        delta_sn_pct=round(float(np.mean([p.delta_sn_pct for p in pts])), 2),
        asp_std=round(float(np.std([p.asp_pct for p in pts])), 2),
    )

    # mean ASP over the full sweep (k-independent robustness)
    sweep_asp: List[float] = []
    for k in range(k_min, k_max + 1):
        seed_asps = [p.asp_pct for p in (score_at(k, s) for s in seeds) if p is not None]
        if seed_asps:
            sweep_asp.append(float(np.mean(seed_asps)))
    out.mean_asp = round(float(np.mean(sweep_asp)), 2) if sweep_asp else float("nan")
    return out


# --- run across apps -------------------------------------------------------

@dataclass
class AblationResult:
    per_app: Dict[str, List[VariantScore]] = field(default_factory=dict)
    variants: List[Variant] = field(default_factory=list)


def run(
    app_files: Dict[str, Union[str, Path]],
    sensitive: Sequence[int],
    budget_k: int = 12,
    k_min: int = 2,
    variants: Optional[List[Variant]] = None,
    random_seeds: Sequence[int] = tuple(range(10)),
) -> AblationResult:
    """Score every variant on every app at that app's auto-tuned k*."""
    variants = variants or default_variants()
    res = AblationResult(variants=variants)
    for app_name, path in app_files.items():
        app = load_app(path)
        tuned = autotune.tune(path, sensitive, budget_k=budget_k, k_min=k_min)
        if tuned.recommended_k is None:
            continue
        k_star = tuned.recommended_k
        scores: List[VariantScore] = []
        for v in variants:
            seeds = random_seeds if v.algo == "random" else (0,)
            scores.append(
                score_variant(app, v, sensitive, k_star, k_min, budget_k, seeds=seeds)
            )
        res.per_app[app_name] = scores
    return res


@dataclass
class StageScore:
    """One config in the component build-up (adds one pipeline stage at a time)."""

    stage: str
    n_pools: float
    sp_pct: float
    asp_pct: float
    delta_sp_pct: float
    delta_sn_pct: float


def stage_buildup(
    app: AppData,
    sensitive: Sequence[int],
    k_star: int,
    full_variant: Optional[Variant] = None,
) -> List[StageScore]:
    """Score the design-faithful stages of the FortWall pipeline.

    Follows the actual pipeline direction (granularity reduction), not a
    synthetic bottom-up build:

    * ``saphire-per-script`` -- one minimal filter per script (#pools = #scripts);
      attack surface is the ideal (zero pooling inflation).
    * ``exact-categories``   -- group scripts with identical profiles (exact match);
      **security-equivalent** to per-script (lossless dedup), fewer distinct
      filters (#pools = #categories, same ASP).
    * ``cluster-all@k*``     -- consolidate to k* pools WITHOUT excluding high-share
      categories first (Phase I OFF); isolates Phase I's contribution at matched k.
    * ``full-method@k*``     -- exclude high-share (Phase I) then cluster (Phase II)
      to k* pools; the deployed method.
    * ``single-pool``        -- one global-union pool (k=1): the worst-case anchor.

    per-script and exact-categories sit at the SAME (ideal) ASP -- the only
    difference is filter count. The trade-off begins only when clustering
    consolidates below #categories.
    """
    profiles = app.profiles
    n = len(profiles)
    total_scripts = sum(p.weight for p in profiles)     # #scripts = total URLs

    def sc(labels, name, npools) -> StageScore:
        p = autotune.score_labels(profiles, labels, sensitive)
        return StageScore(name, float(npools), p.sp_pct, p.asp_pct,
                          p.delta_sp_pct, p.delta_sn_pct)

    # each category its own pool == per-script security (the ideal surface)
    ideal = sc(list(range(n)), "exact-categories", n)
    per_script = StageScore("saphire-per-script", float(total_scripts),
                            ideal.sp_pct, ideal.asp_pct,
                            ideal.delta_sp_pct, ideal.delta_sn_pct)

    full = full_variant or default_variants()[0]
    no_phase1 = next(v for v in default_variants() if v.name == "no-two-phase")

    out: List[StageScore] = [per_script, ideal]
    lab_noex = assign(app, k_star, no_phase1)
    if lab_noex is not None:
        out.append(sc(lab_noex, "cluster-all@k*", k_star))
    lab_full = assign(app, k_star, full)
    if lab_full is not None:
        out.append(sc(lab_full, "full-method@k*", k_star))
    out.append(sc([0] * n, "single-pool", 1))
    return out


def average_across_apps(res: AblationResult) -> List[VariantScore]:
    """Mean of each metric across apps (for the summary ablation table)."""
    out: List[VariantScore] = []
    for i, v in enumerate(res.variants):
        rows = [scores[i] for scores in res.per_app.values()
                if i < len(scores) and scores[i].applicable]
        if not rows:
            out.append(VariantScore(v.name, v.axis, 0, applicable=False))
            continue
        def m(attr):
            vals = [getattr(r, attr) for r in rows if not np.isnan(getattr(r, attr))]
            return round(float(np.mean(vals)), 2) if vals else float("nan")
        out.append(VariantScore(
            variant=v.name, axis=v.axis, k_star=0,
            sp_pct=m("sp_pct"), asp_pct=m("asp_pct"),
            delta_sp_pct=m("delta_sp_pct"), delta_sn_pct=m("delta_sn_pct"),
            mean_asp=m("mean_asp"),
        ))
    return out
