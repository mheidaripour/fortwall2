from fortwall_pool import urlmap


def _write(tmp_path, text):
    p = tmp_path / "stage2_out"
    p.write_text(text)
    return p


def test_categorize_groups_identical_sets(tmp_path):
    f = _write(
        tmp_path,
        "/a 1 2 3\n"
        "/b 3 2 1\n"       # same set as /a (order-insensitive)
        "/c 1 2\n"
    )
    cats = urlmap.categorize_urls_by_numbers(f)
    by_key = {tuple(c["associated_numbers"]): set(c["urls"]) for c in cats}
    assert by_key[(1, 2, 3)] == {"/a", "/b"}
    assert by_key[(1, 2)] == {"/c"}


def test_categorize_skips_malformed(tmp_path, capsys):
    f = _write(tmp_path, "/a 1 2\n/bad x y\n/c 5\n")
    cats = urlmap.categorize_urls_by_numbers(f)
    keys = {tuple(c["associated_numbers"]) for c in cats}
    assert keys == {(1, 2), (5,)}
    assert "Skipping malformed" in capsys.readouterr().out


def test_categorize_url_with_no_numbers(tmp_path):
    f = _write(tmp_path, "/empty\n/a 1\n")
    cats = urlmap.categorize_urls_by_numbers(f)
    empty = [c for c in cats if c["associated_numbers"] == []]
    assert empty and empty[0]["urls"] == ["/empty"]


def test_intersection_of_urls():
    cats = [
        {"associated_numbers": [1, 2, 3, 9], "urls": ["/a"]},
        {"associated_numbers": [2, 3, 4], "urls": ["/b"]},
        {"associated_numbers": [3, 2, 5], "urls": ["/c"]},
    ]
    assert urlmap.intersection_of_urls(cats) == {2, 3}


def test_write_intersection_uses_set_repr(tmp_path):
    p = tmp_path / "intersection"
    urlmap.write_intersection_to_file({1, 2}, p)
    assert p.read_text() == "%s" % {1, 2}


def test_analyze_percentages_and_indices():
    cats = [
        {"associated_numbers": [1], "urls": ["/a"] * 80},   # 80%
        {"associated_numbers": [2], "urls": ["/b"] * 15},   # 15%
        {"associated_numbers": [3], "urls": ["/c"] * 5},    # 5%
    ]
    analysis = urlmap.analyze_percentages(cats, threshold=10)
    assert analysis.total_urls == 100
    assert analysis.category_percentages == [80.0, 15.0, 5.0]
    assert analysis.high_share_indices == [0, 1]


def test_diagnostics_lines_are_parseable():
    cats = [
        {"associated_numbers": [1], "urls": ["/a"] * 80},
        {"associated_numbers": [2], "urls": ["/b"] * 20},
    ]
    analysis = urlmap.analyze_percentages(cats)
    lines = urlmap.percentage_diagnostics_lines(cats, analysis)
    text = "\n".join(lines)
    assert "Total number of URLs: 100" in text
    assert "Category: 0 Percentage: 80.0" in text


def test_remove_intersection_and_build_categories():
    cats = [
        {"associated_numbers": [1, 2, 3], "urls": ["/a"]},
        {"associated_numbers": [1, 2, 9], "urls": ["/b"]},
    ]
    urlmap.remove_intersection_set_from_associated_numbers(cats, {1, 2})
    assert set(cats[0]["associated_numbers"]) == {3}
    assert set(cats[1]["associated_numbers"]) == {9}


def test_create_categories_with_clusters_and_prune_empty():
    cats = [
        {"associated_numbers": [100], "urls": ["/big"]},   # high-share, index 0
        {"associated_numbers": [], "urls": ["/x"]},
    ]
    cluster_urls = {0: ["/c0"], 1: ["/c1"]}
    supersets = [{7, 8}, set()]
    combined = urlmap.create_new_categories_with_clusters(cats, [0], cluster_urls, supersets)
    # dedicated category + 2 clusters
    assert len(combined) == 3
    pruned = urlmap.remove_clusters_empty_syscalls(combined)
    # the empty-superset cluster is dropped
    assert all(c["associated_numbers"] for c in pruned)
    assert len(pruned) == 2
