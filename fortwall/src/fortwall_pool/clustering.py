"""Cluster URL syscall-sets into pools via Jaccard distance + agglomerative clustering.


A backward-compatible :func:`cluster` wrapper returns the original
``(supersets, cluster_urls, clusters_syscalls)`` triple.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set

import numpy as np
from scipy.spatial.distance import pdist, squareform
from sklearn.cluster import AgglomerativeClustering

from . import config, syscalls as syscalls_mod

# A "categorized url" is the loose dict form produced by urlmap:
#   {"associated_numbers": [int, ...], "urls": [str, ...]}
Categorized = Sequence[Dict[str, list]]


@dataclass
class ClusterResult:
    """Structured output of :func:`run_clustering`."""

    num_clusters: int
    labels: np.ndarray                      # cluster id per input group
    data: List[Set[int]]                    # syscall set per input group
    supersets: List[Set[int]]               # union of syscalls per cluster
    cluster_urls: Dict[int, List[str]]      # urls per cluster
    clusters_syscalls: Dict[int, List[Set[int]]]  # member syscall-sets per cluster

    def as_tuple(self):
        """Return the legacy ``(supersets, cluster_urls, clusters_syscalls)`` triple."""
        return self.supersets, self.cluster_urls, self.clusters_syscalls


def _to_binary_matrix(data: List[Set[int]], universal: Optional[List[int]] = None):
    """One-hot encode the syscall sets over their universal set of elements.

    ``universal`` optionally fixes the column order (needed when a per-column
    weight vector must line up with the same ordering); when omitted the
    original ``set().union`` ordering is used, preserving legacy behavior.
    """
    universal_set = universal if universal is not None else list(set().union(*data))
    element_to_index = {element: idx for idx, element in enumerate(universal_set)}
    binary_data = np.zeros((len(data), len(universal_set)), dtype=int)
    for i, s in enumerate(data):
        for element in s:
            if element in element_to_index:
                binary_data[i, element_to_index[element]] = 1
    return binary_data


def _weighted_jaccard_matrix(binary_data: "np.ndarray", weights: "np.ndarray") -> "np.ndarray":
    """Pairwise weighted-Jaccard *distance* matrix over one-hot rows.

    For rows ``a``/``b`` (0/1) with per-column weights ``w``::

        d(a, b) = 1 - (sum_j w_j * (a_j AND b_j)) / (sum_j w_j * (a_j OR b_j))

    Sensitive syscalls carry ``w_j = W > 1``, so two categories that differ on a
    sensitive syscall are pushed apart -- discouraging merges that would union a
    sensitive call into a pool that did not need it. With uniform ``w_j = 1`` this
    reduces exactly to the standard Jaccard distance.
    """
    wd = binary_data * weights  # rows scaled by column weight
    inter = wd @ binary_data.T  # sum_j w_j * a_j * b_j  (weighted intersection)
    row_w = wd.sum(axis=1)      # sum_j w_j * a_j  (weighted set size)
    union = row_w[:, None] + row_w[None, :] - inter
    with np.errstate(divide="ignore", invalid="ignore"):
        sim = np.where(union > 0, inter / union, 0.0)
    dist = 1.0 - sim
    np.fill_diagonal(dist, 0.0)
    # Symmetrize away any floating-point asymmetry so linkage is well-defined.
    dist = (dist + dist.T) / 2.0
    return dist


def run_clustering(
    categorized_urls: Categorized,
    num_clusters: int = 5,
    sensitive: Optional[Iterable[int]] = None,
    sensitivity_weight: float = 1.0,
) -> ClusterResult:
    """Cluster the categorized URL groups into ``num_clusters`` pools.

    By default (``sensitive is None`` or ``sensitivity_weight == 1.0``) this uses
    plain Jaccard distance over one-hot syscall vectors and agglomerative
    clustering with average linkage -- identical to the original implementation
    (the deprecated ``affinity=`` kwarg is spelled ``metric=`` for modern
    scikit-learn; the semantics are unchanged).

    When ``sensitive`` is provided and ``sensitivity_weight > 1``, the distance
    becomes a **weighted Jaccard** that up-weights the sensitive syscall columns
    (:func:`_weighted_jaccard_matrix`). This makes the clusterer sensitivity-aware:
    it avoids merging categories that differ on sensitive syscalls, reducing the
    worst-case sensitive inflation (ΔSN) a pool union introduces. The rest of the
    pipeline is unchanged.
    """
    data: List[Set[int]] = [set(group["associated_numbers"]) for group in categorized_urls]

    use_weighted = sensitive is not None and sensitivity_weight != 1.0

    if use_weighted:
        universal = list(set().union(*data))
        binary_data = _to_binary_matrix(data, universal=universal)
        sensitive_set = set(sensitive)
        weights = np.array(
            [sensitivity_weight if s in sensitive_set else 1.0 for s in universal],
            dtype=float,
        )
        jaccard_dist_matrix = _weighted_jaccard_matrix(binary_data, weights)
    else:
        binary_data = _to_binary_matrix(data)
        jaccard_distances = pdist(binary_data, metric="jaccard")
        jaccard_dist_matrix = squareform(jaccard_distances)

    clustering_model = AgglomerativeClustering(
        n_clusters=num_clusters, metric="precomputed", linkage="average"
    )
    cluster_labels = clustering_model.fit_predict(jaccard_dist_matrix)

    # Superset (union) of syscalls per cluster.
    supersets: List[Set[int]] = []
    for cluster_id in range(num_clusters):
        cluster_sets = [data[i] for i in range(len(data)) if cluster_labels[i] == cluster_id]
        supersets.append(set().union(*cluster_sets))

    # Member syscall-sets per cluster.
    clusters_syscalls: Dict[int, List[Set[int]]] = {}
    for cluster_id in range(num_clusters):
        clusters_syscalls[cluster_id] = [
            data[i] for i in range(len(data)) if cluster_labels[i] == cluster_id
        ]

    # URLs per cluster (matches original set-equality lookup, quirks preserved).
    cluster_urls: Dict[int, List[str]] = {}
    for cluster_id in range(num_clusters):
        cluster_sets = clusters_syscalls[cluster_id]
        urls: List[str] = []
        for cset in cluster_sets:
            for group in categorized_urls:
                if set(group["associated_numbers"]) == cset:
                    urls.extend(group["urls"])
        cluster_urls[cluster_id] = urls

    return ClusterResult(
        num_clusters=num_clusters,
        labels=cluster_labels,
        data=data,
        supersets=supersets,
        cluster_urls=cluster_urls,
        clusters_syscalls=clusters_syscalls,
    )


def diagnostics_lines(
    result: ClusterResult,
    sensitive_syscalls: Optional[Iterable[int]] = None,
    first_pool_number: int = 1,
) -> List[str]:
    """Reproduce the diagnostic stdout the original ``cluster.py`` printed.

    ``report.py`` parses some of these lines.

    ``sensitive_syscalls`` is the set of sensitive syscall *numbers* used for the
    "Max of sensitive syscalls" (ΔSN) figure. If omitted, it is loaded from
    :data:`config.WORK.syscall_table`.

    ``first_pool_number`` is the label of the first clustered pool. The original
    numbered clusters 1-based (default ``1``). When the clustered pools follow a
    set of dedicated high-share pools in an overall layout, pass the number of
    dedicated pools so these labels line up with the 0-based ``Cluster <i>``
    SP/SN lines the report also parses (see ``pipeline.build_pool_plan``).

    Note: the original ``cluster.py`` intersected the int difference set with the
    classification *dict* (string keys), so ΔSN was always 0.00%. That bug is
    fixed here -- ΔSN now reflects how many sensitive syscalls a pool actually
    adds to a member URL's allow-list.
    """
    if sensitive_syscalls is None:
        try:
            sensitive_syscalls = syscalls_mod.load_sensitive_syscalls(config.WORK.syscall_table)
        except OSError:
            sensitive_syscalls = []
    sensitive_set: Set[int] = set(sensitive_syscalls)
    lines: List[str] = []
    supersets = result.supersets
    num_clusters = result.num_clusters
    data = result.data
    labels = result.labels

    for i, superset in enumerate(supersets, start=1):
        lines.append(f"Superset {i}: {superset}")
        lines.append(f"length of the superset: {len(superset)}")

    for cluster_id in range(num_clusters):
        cluster_sets = [data[i] for i in range(len(data)) if labels[i] == cluster_id]
        lines.append(f"Cluster {first_pool_number + cluster_id}: {len(cluster_sets)} sets")

    for cluster_id in range(num_clusters):
        lines.append(f"Cluster {first_pool_number + cluster_id}: {len(result.cluster_urls[cluster_id])} urls")

    for cluster_id in range(num_clusters):
        cluster_sets = [data[i] for i in range(len(data)) if labels[i] == cluster_id]
        sizes = [len(group) for group in cluster_sets]
        lines.append(f"Cluster {first_pool_number + cluster_id} standard deviation: {round(np.std(sizes), 1)}")

    for cluster_id in range(num_clusters):
        cluster_sets = [data[i] for i in range(len(data)) if labels[i] == cluster_id]
        superset = supersets[cluster_id]
        max_sn_syscalls = max(
            len((superset - group) & sensitive_set) for group in cluster_sets
        )
        max_difference = max(len(superset - group) for group in cluster_sets)
        lines.append(
            f"Cluster {first_pool_number + cluster_id}: Max syscalls to add to any set: "
            f"{(max_difference / config.TOTAL_SYSCALLS) * 100:.2f}% of total syscalls, "
            f"Max of sensitive syscalls: {(max_sn_syscalls / config.SN_BASE) * 100:.2f}% of sensitive syscalls"
        )

    return lines


def cluster(categorized_urls: Categorized, num_clusters: int = 5):
    """Backward-compatible wrapper: returns ``(supersets, cluster_urls, clusters_syscalls)``."""
    return run_clustering(categorized_urls, num_clusters).as_tuple()
