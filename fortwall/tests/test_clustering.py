from fortwall_pool import clustering


def _categorized():
    # Two well-separated pairs; all sets distinct so URL lookup is 1:1.
    return [
        {"associated_numbers": [1, 2, 3], "urls": ["/a"]},
        {"associated_numbers": [1, 2, 3, 4], "urls": ["/b"]},
        {"associated_numbers": [20, 21], "urls": ["/c"]},
        {"associated_numbers": [20, 21, 22], "urls": ["/d"]},
    ]


def test_run_clustering_separates_two_groups():
    result = clustering.run_clustering(_categorized(), num_clusters=2)

    assert result.num_clusters == 2
    # Superset content is order-independent across the two clusters.
    supersets = {frozenset(s) for s in result.supersets}
    assert supersets == {frozenset({1, 2, 3, 4}), frozenset({20, 21, 22})}

    # URLs of each true group stay together.
    url_groups = {frozenset(v) for v in result.cluster_urls.values()}
    assert url_groups == {frozenset({"/a", "/b"}), frozenset({"/c", "/d"})}


def test_superset_is_union_of_members():
    result = clustering.run_clustering(_categorized(), num_clusters=2)
    for cid, members in result.clusters_syscalls.items():
        union = set().union(*members) if members else set()
        assert result.supersets[cid] == union


def test_cluster_wrapper_matches_run_clustering():
    cats = _categorized()
    supersets, cluster_urls, clusters_syscalls = clustering.cluster(cats, num_clusters=2)
    result = clustering.run_clustering(cats, num_clusters=2)
    assert supersets == result.supersets
    assert cluster_urls == result.cluster_urls


def test_diagnostics_lines_shape():
    result = clustering.run_clustering(_categorized(), num_clusters=2)
    lines = clustering.diagnostics_lines(result, sensitive_syscalls=[])
    text = "\n".join(lines)
    assert "Superset 1:" in text
    assert "Cluster 1:" in text
    # No sensitive syscalls supplied -> 0.00%.
    assert "Max of sensitive syscalls: 0.00% of sensitive syscalls" in text


def test_diagnostics_delta_sn_reflects_sensitive_syscalls():
    # Pooling /a with /b forces syscall 59 (execve, sensitive) into /a's allow-list.
    cats = [
        {"associated_numbers": [1, 2], "urls": ["/a"]},
        {"associated_numbers": [1, 2, 59], "urls": ["/b"]},
    ]
    result = clustering.run_clustering(cats, num_clusters=1)
    text = "\n".join(clustering.diagnostics_lines(result, sensitive_syscalls=[59]))
    # 1 sensitive syscall added out of SN_BASE=20 -> 5.00%  (was always 0.00% before the fix)
    assert "Max of sensitive syscalls: 5.00% of sensitive syscalls" in text
