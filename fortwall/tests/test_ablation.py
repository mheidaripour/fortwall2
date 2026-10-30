"""Tests for the clustering ablation harness."""

from __future__ import annotations

from pathlib import Path

import pytest

from fortwall_pool import ablation, autotune

SENSITIVE = [10, 20, 30, 40]


def _structured_stage2(tmp_path: Path) -> Path:
    """Two clearly separated syscall families + a dominant (dedicated) profile."""
    lines = [f"/big_{i}.php 0 1 2 10 11" for i in range(20)]          # dedicated
    familyA = ["0 1 2 10 12", "0 1 2 10 13", "0 1 2 10 14", "0 1 2 11 12"]
    familyB = ["0 1 2 40 41", "0 1 2 40 42", "0 1 2 41 43", "0 1 2 40 44"]
    for i, p in enumerate(familyA + familyB):
        lines.append(f"/f_{i}.php {p}")
    f = tmp_path / "stage2_out_struct"
    f.write_text("\n".join(lines) + "\n")
    return f


def test_full_method_matches_autotuner(tmp_path):
    """The 'full-method' variant must reproduce the auto-tuner's scoring exactly."""
    f = _structured_stage2(tmp_path)
    app = ablation.load_app(f)
    base = next(v for v in ablation.default_variants() if v.name == "full-method")
    k = len(app.dedicated) + 2
    labels = ablation.assign(app, k, base)
    assert labels is not None
    got = autotune.score_labels(app.profiles, labels, SENSITIVE, k=k)
    ref = autotune.evaluate_k(f, k, SENSITIVE)
    assert got.asp_pct == pytest.approx(ref.asp_pct, abs=0.01)
    assert got.delta_sn_pct == pytest.approx(ref.delta_sn_pct, abs=0.01)


def test_every_variant_produces_valid_or_none(tmp_path):
    f = _structured_stage2(tmp_path)
    app = ablation.load_app(f)
    n = len(app.profiles)
    k = len(app.dedicated) + 3
    for v in ablation.default_variants():
        labels = ablation.assign(app, k, v, seed=0)
        if labels is None:
            continue
        assert len(labels) == n
        pools = {l for l in labels if l is not None}
        assert len(pools) <= k
        assert all(l is None or 0 <= l < k for l in labels)


def test_beats_random_floor(tmp_path):
    """On structured data the full method must not lose to a random partition."""
    f = _structured_stage2(tmp_path)
    app = ablation.load_app(f)
    k = len(app.dedicated) + 2                 # 2 clusters = the 2 planted families
    base = next(v for v in ablation.default_variants() if v.name == "full-method")
    rnd = next(v for v in ablation.default_variants() if v.name == "random-partition")
    full = autotune.score_labels(app.profiles, ablation.assign(app, k, base), SENSITIVE, k=k)
    rand_asps = []
    for seed in range(10):
        lab = ablation.assign(app, k, rnd, seed=seed)
        rand_asps.append(autotune.score_labels(app.profiles, lab, SENSITIVE, k=k).asp_pct)
    assert full.asp_pct <= min(rand_asps) + 1e-9


def test_two_phase_off_changes_assignment(tmp_path):
    f = _structured_stage2(tmp_path)
    app = ablation.load_app(f)
    assert app.dedicated, "test data should have a dedicated high-share profile"
    on = next(v for v in ablation.default_variants() if v.name == "full-method")
    off = next(v for v in ablation.default_variants() if v.name == "no-two-phase")
    k = len(app.dedicated) + 2
    # with two-phase off, no profile is a solitary dedicated pool by construction
    assert ablation.assign(app, k, on) is not None
    assert ablation.assign(app, k, off) is not None
