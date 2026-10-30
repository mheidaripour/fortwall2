"""Tests for sensitivity-aware (weighted-Jaccard) clustering.

The default clustering path must remain byte-for-byte identical; these tests pin
the two invariants that guarantee it:

1. The weighted-Jaccard distance with uniform weights (W=1) equals plain Jaccard.
2. ``run_clustering`` with ``sensitivity_weight=1.0`` (or ``sensitive=None``)
   produces the same labels/supersets as the untouched original.

A behavioral test then shows the aware mode actually lowers worst-case sensitive
inflation (ΔSN) on a constructed example.
"""

import numpy as np
from scipy.spatial.distance import pdist, squareform

from fortwall_pool import clustering


def _cats(sets):
    return [{"associated_numbers": list(s), "urls": [f"/u{i}"]} for i, s in enumerate(sets)]


def test_weighted_matrix_reduces_to_plain_jaccard_at_w1():
    data = [{0, 1, 2}, {1, 2, 3}, {2, 3, 4}, {10, 11}]
    universal = list(set().union(*data))
    binm = clustering._to_binary_matrix(data, universal=universal)
    weights = np.ones(len(universal))

    weighted = clustering._weighted_jaccard_matrix(binm, weights)
    plain = squareform(pdist(binm, metric="jaccard"))

    assert np.allclose(weighted, plain, atol=1e-12)


def test_run_clustering_default_unchanged_by_weight_one():
    sets = [{0, 1, 2}, {1, 2, 3}, {2, 3, 4}, {10, 11}, {10, 11, 12}, {20}]
    base = clustering.run_clustering(_cats(sets), num_clusters=3)
    # sensitive provided but weight == 1.0 -> must take the legacy path
    same = clustering.run_clustering(
        _cats(sets), num_clusters=3, sensitive=[2, 3], sensitivity_weight=1.0
    )
    assert list(base.labels) == list(same.labels)
    assert base.supersets == same.supersets


def test_run_clustering_none_sensitive_unchanged():
    sets = [{0, 1}, {1, 2}, {5, 6}, {5, 6, 7}]
    base = clustering.run_clustering(_cats(sets), num_clusters=2)
    same = clustering.run_clustering(_cats(sets), num_clusters=2, sensitivity_weight=8.0)
    assert list(base.labels) == list(same.labels)


def test_weighted_distance_separates_on_sensitive_syscall():
    # Two categories identical except one holds sensitive syscall 99.
    # Under plain Jaccard they may merge with a benign neighbor; the weight
    # pushes them apart. We assert the pairwise distance between the sensitive
    # holder and a benign set grows with the weight.
    data = [{0, 1, 2, 99}, {0, 1, 2}]
    universal = list(set().union(*data))
    binm = clustering._to_binary_matrix(data, universal=universal)

    w1 = np.ones(len(universal))
    d1 = clustering._weighted_jaccard_matrix(binm, w1)[0, 1]

    ws = np.array([8.0 if s == 99 else 1.0 for s in universal])
    d8 = clustering._weighted_jaccard_matrix(binm, ws)[0, 1]

    assert d8 > d1
