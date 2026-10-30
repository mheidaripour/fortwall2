import re

import pytest

from fortwall_pool import pipeline


def _fixture(tmp_path):
    lines = []
    # Dominant category (>10% -> dedicated pool).
    for i in range(50):
        lines.append(f"/big{i} 1 2 3")
    # Small distinct categories to be clustered.
    for url, nums in [
        ("/a", "1 4"), ("/b", "1 5"), ("/c", "2 6"),
        ("/d", "2 7"), ("/e", "8 9"), ("/f", "8 10"),
    ]:
        lines.append(f"{url} {nums}")
    p = tmp_path / "stage2_out_app"
    p.write_text("\n".join(lines) + "\n")
    return p


def test_build_pool_plan_preserves_all_urls(tmp_path):
    f = _fixture(tmp_path)
    plan = pipeline.build_pool_plan(f, num_clusters=2)
    assert plan.total_urls == 56
    # Every URL ends up in exactly one pool (dedicated + clustered).
    covered = sum(len(c["urls"]) for c in plan.all_clusters)
    assert covered == 56
    assert isinstance(plan.intersection, set)
    assert len(plan.cat_indices) >= 1  # the dominant category is dedicated


def test_total_pools_convention_matches_num_clusters(tmp_path):
    f = _fixture(tmp_path)
    plan = pipeline.build_pool_plan(f, num_clusters=2)
    dedicated = len(plan.cat_indices)
    # total_pools = dedicated + clusters -> should yield the same layout size.
    plan2 = pipeline.build_pool_plan(f, total_pools=dedicated + 2)
    assert len(plan.all_clusters) == len(plan2.all_clusters)


def test_build_pool_plan_requires_exactly_one_arg(tmp_path):
    f = _fixture(tmp_path)
    with pytest.raises(ValueError):
        pipeline.build_pool_plan(f)
    with pytest.raises(ValueError):
        pipeline.build_pool_plan(f, num_clusters=2, total_pools=3)


def test_analyze_report_lines_have_parseable_tokens(tmp_path):
    f = _fixture(tmp_path)
    sensitive = [1, 2, 3, 8, 9]  # arbitrary sensitive set for the test
    lines = pipeline.analyze_report_lines(f, num_clusters=2, sensitive=sensitive)
    text = "\n".join(lines)
    assert "Total number of URLs: 56" in text
    assert "Intersection of the associated system call numbers" in text
    assert "Security Metric for Cluster 0(SN%):" in text
    assert "Cluster 0 SP%:" in text
    assert "STATISTICS FOR THE SYSFILTER" in text
    assert "SP% " in text


def test_report_delta_sn_is_nonzero_and_aligned(tmp_path):
    # One dominant (dedicated) category + small categories to cluster; /f forces
    # syscall 59 (sensitive) into a pool that other members didn't need.
    lines = [f"/big{i} 1 2 3" for i in range(50)]
    for url, nums in [("/a", "1 4"), ("/b", "1 5"), ("/c", "2 6"),
                      ("/d", "2 7"), ("/e", "8 9"), ("/f", "8 10 59")]:
        lines.append(f"{url} {nums}")
    f = tmp_path / "stage2_out_app"
    f.write_text("\n".join(lines) + "\n")

    out = "\n".join(pipeline.analyze_report_lines(f, num_clusters=2, sensitive=[59]))

    sp_pools = {int(n) for n in re.findall(r"Cluster (\d+) SP%", out)}
    delta = {
        int(n): float(p)
        for n, p in re.findall(
            r"Cluster (\d+): Max syscalls to add.*?Max of sensitive syscalls: ([0-9.]+)%", out
        )
    }
    assert delta, "expected per-pool delta diagnostic lines"
    # Fix #1: the merged sensitive syscall produces a non-zero ΔSN (was always 0).
    assert any(p > 0 for p in delta.values())
    # Fix #2: every pool with a ΔSN line shares its number with an SP% line (aligned).
    assert set(delta).issubset(sp_pools)
