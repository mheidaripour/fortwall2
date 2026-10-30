"""End-to-end pool-planning orchestration.

Consolidates the three near-duplicate flows from the original code base:

* ``url_analysis`` (``urlanalyze.py``),
* the mpool pipeline inside ``switch.py``, and
* the analysis driver in ``sen_syscalls.py``.

:func:`build_pool_plan` produces the pool layout (dedicated high-share
categories + clustered pools) plus the diagnostic stdout the originals printed.
:func:`analyze_report_lines` reproduces the full ``sen_syscalls.py`` report text
so ``report.py`` keeps parsing identical output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Set, Union

from . import clustering, config, metrics, urlmap


@dataclass
class PoolPlan:
    """The computed pool layout and the diagnostics emitted while building it."""

    categorized: list                 # categories after intersection removal (mutated)
    intersection: Set[int]
    cat_indices: List[int]            # dedicated high-share category indices
    all_clusters: list                # dedicated categories + clustered pools
    total_urls: int
    diagnostics: List[str] = field(default_factory=list)


def build_pool_plan(
    file_path: Union[str, Path],
    num_clusters: Optional[int] = None,
    total_pools: Optional[int] = None,
    sensitive: Optional[Sequence[int]] = None,
    sensitivity_weight: float = 1.0,
) -> PoolPlan:
    """Categorize -> intersect -> split high-share -> cluster the remainder.

    Provide exactly one of:

    * ``num_clusters`` -- number of clustered pools directly (reporting flow), or
    * ``total_pools``  -- total pool budget; clusters = ``total_pools - dedicated``
      (deploy flow, matching ``switch.py``).

    ``sensitive`` + ``sensitivity_weight`` are forwarded to
    :func:`clustering.run_clustering`; with the defaults (``None`` / ``1.0``) the
    clustering is the unchanged plain-Jaccard path.
    """
    if (num_clusters is None) == (total_pools is None):
        raise ValueError("Provide exactly one of num_clusters or total_pools")

    diagnostics: List[str] = []

    categorized = urlmap.categorize_urls_by_numbers(file_path)
    total = urlmap.total_urls(categorized)

    intersection = urlmap.intersection_of_urls(categorized)
    diagnostics.extend(urlmap.format_intersection_lines(intersection))

    exact = urlmap.calculate_urls_with_exact_intersection_set(categorized, intersection)
    diagnostics.append(f"URLs with exact intersection set: {len(exact)}")

    analysis = urlmap.analyze_percentages(categorized)
    diagnostics.extend(urlmap.percentage_diagnostics_lines(categorized, analysis))
    cat_indices = analysis.high_share_indices

    if num_clusters is None:
        num_clusters = total_pools - len(cat_indices)

    # Subtract the common baseline from every category (mutates in place).
    urlmap.remove_intersection_set_from_associated_numbers(categorized, intersection)
    new_categories = urlmap.create_new_categories(categorized, cat_indices)
    diagnostics.append(
        f"Number of new categories after removing the high percentage categories: {len(new_categories)}"
    )

    result = clustering.run_clustering(
        new_categories, num_clusters,
        sensitive=sensitive, sensitivity_weight=sensitivity_weight,
    )
    # Number the clustered pools starting after the dedicated high-share pools so
    # the ΔSP/ΔSN diagnostic labels line up with the 0-based "Cluster <i> SP%"
    # lines that report.py parses (dedicated pools occupy indices 0..len-1).
    diagnostics.extend(clustering.diagnostics_lines(result, first_pool_number=len(cat_indices)))

    # url_analysis's own extra diagnostics.
    for cid in result.cluster_urls:
        pct = round((len(result.cluster_urls[cid]) / total) * 100, 2)
        diagnostics.append(f"Cluster {cid}: {pct} urls")
    for i, superset in enumerate(result.supersets, start=1):
        pct = round(((len(superset) + len(intersection)) / config.TOTAL_SYSCALLS) * 100, 2)
        diagnostics.append(f"Superset {i}:  Length of the superset: {len(superset)} and the percentage : {pct} ")

    all_clusters = urlmap.create_new_categories_with_clusters(
        categorized, cat_indices, result.cluster_urls, result.supersets
    )

    return PoolPlan(
        categorized=categorized,
        intersection=intersection,
        cat_indices=cat_indices,
        all_clusters=all_clusters,
        total_urls=total,
        diagnostics=diagnostics,
    )


def analyze_report_lines(
    file_path: Union[str, Path],
    num_clusters: int,
    sensitive: Sequence[int],
    sensitivity_weight: float = 1.0,
) -> List[str]:
    """Reproduce the full ``sen_syscalls.py`` report stdout (parsed by report.py).

    The intersection (baseline) is added back to each pool before scoring, so
    per-cluster SP%/SN% reflect the effective allow-list -- matching the original.

    ``sensitivity_weight > 1`` enables sensitivity-aware clustering (the sensitive
    set is already available here); the default ``1.0`` keeps the plain path.
    """
    plan = build_pool_plan(
        file_path, num_clusters=num_clusters,
        sensitive=sensitive if sensitivity_weight != 1.0 else None,
        sensitivity_weight=sensitivity_weight,
    )
    lines = list(plan.diagnostics)
    all_clusters = plan.all_clusters
    intersection = plan.intersection

    # Add the baseline back to every pool's allow-list.
    for cluster in all_clusters:
        cluster["associated_numbers"] = set(cluster["associated_numbers"]) | intersection

    total = sum(len(c["urls"]) for c in all_clusters)
    for cluster in all_clusters:
        lines.append(f"Cluster:{len(cluster['urls'])}")
        lines.append(f"Cluster URL Percentage: {round((len(cluster['urls']) / total) * 100, 2)}")

    for i, cluster in enumerate(all_clusters):
        profile = cluster["associated_numbers"]
        lines.append(f"Security Metric for Cluster {i}(SN%): {metrics.sn_percent(profile, sensitive)}")
        lines.append(f"Cluster {i} SP%: {metrics.sp_percent(profile)}")

    baseline = metrics.sysfilter_metrics(sensitive)
    lines.append("STATISTICS FOR THE SYSFILTER")
    lines.append(f"SP% {baseline.sp}")
    lines.append(f"SN% {baseline.sn}")

    return lines
