"""Tests for the constrained-optimization pool-count auto-tuner."""

from __future__ import annotations

from pathlib import Path

import pytest

from fortwall_pool import autotune


# Sensitive syscalls used across these tests (the "SN" set).
SENSITIVE = [10, 20, 30, 40]


def _write_stage2(tmp_path: Path) -> Path:
    """Synthetic stage2_out: one dominant profile (dedicated pool) + a tail of
    distinct profiles (clustered), all sharing the baseline {0,1,2}."""
    lines = []
    # dominant profile -> becomes a dedicated high-share pool
    for i in range(20):
        lines.append(f"/big_{i}.php 0 1 2 10 11")
    # long tail of distinct profiles -> clustered
    tail = [
        "0 1 2 10 12", "0 1 2 20 21", "0 1 2 20 22", "0 1 2 30 31 32",
        "0 1 2 30 33", "0 1 2 40 41", "0 1 2 40 42 43",
    ]
    for i, prof in enumerate(tail):
        lines.append(f"/tail_{i}.php {prof}")
    f = tmp_path / "stage2_out_synthetic"
    f.write_text("\n".join(lines) + "\n")
    return f


def test_asp_is_non_increasing_in_k(tmp_path):
    f = _write_stage2(tmp_path)
    res = autotune.tune(f, SENSITIVE, budget_k=8, k_min=2)
    assert res.points, "sweep produced no feasible pool counts"
    asp = [p.asp_pct for p in res.points]
    # more pools -> tighter unions -> attack surface never increases
    assert all(b <= a + 1e-9 for a, b in zip(asp, asp[1:])), asp


def test_asp_is_sp_complement(tmp_path):
    f = _write_stage2(tmp_path)
    res = autotune.tune(f, SENSITIVE, budget_k=8, k_min=2)
    for p in res.points:
        # ASP% is exactly 100 - SP%, by construction
        assert p.asp_pct == pytest.approx(100 - p.sp_pct, abs=0.01)


def test_recommends_k_within_budget(tmp_path):
    f = _write_stage2(tmp_path)
    res = autotune.tune(f, SENSITIVE, budget_k=6, k_min=2)
    assert res.recommended_k is not None
    assert 2 <= res.recommended_k <= 6
    # the recommended k must be one of the evaluated (feasible) points
    assert res.recommended_k in {p.k for p in res.points if p.feasible}


def test_asp_matches_width(tmp_path):
    f = _write_stage2(tmp_path)
    res = autotune.tune(f, SENSITIVE, budget_k=6, k_min=2)
    from fortwall_pool import config
    for p in res.points:
        assert p.asp_pct == pytest.approx(p.width / config.TOTAL_SYSCALLS * 100, abs=0.01)


def test_tau_constrains_on_delta_sn(tmp_path):
    f = _write_stage2(tmp_path)
    loose = autotune.tune(f, SENSITIVE, budget_k=8, k_min=2, tau=None)
    # a zero ΔSN% budget must reject every pool count that adds any sensitive
    # syscall to some script via pooling
    strict = autotune.tune(f, SENSITIVE, budget_k=8, k_min=2, tau=0.0)
    infeasible = [p for p in strict.points if not p.feasible]
    assert any(p.delta_sn_pct > 0 for p in loose.points), "test data adds no sensitive infl"
    assert infeasible, "tau=0 should mark ΔSN%-positive pools infeasible"
    for p in strict.points:
        assert p.feasible == (p.delta_sn_pct <= 0.0)


def test_empty_input_yields_no_recommendation(tmp_path):
    f = tmp_path / "empty"
    f.write_text("")
    res = autotune.tune(f, SENSITIVE, budget_k=6)
    assert res.recommended_k is None
    assert "no usable" in res.reason
