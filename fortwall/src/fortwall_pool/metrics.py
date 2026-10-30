"""Attack-surface reduction metrics: SP% and SN%.

Consolidates the metric math that was duplicated across ``saphire.py``,
``urlanalyze.py`` and the ``sen_syscalls.py`` driver.

* **SP%** -- share of all syscalls *blocked*: ``(TOTAL - |profile|) / TOTAL``.
* **SN%** -- share of *sensitive* syscalls blocked:
  ``(SN_BASE - |profile ∩ sensitive|) / SN_BASE``.

Both are rounded to two decimals, matching the originals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Collection, List, Sequence

from . import config


def sp_percent(profile: Collection[int], total: int = config.TOTAL_SYSCALLS) -> float:
    """Specificity metric: percentage of all syscalls blocked for ``profile``."""
    return round(((total - len(profile)) / total) * 100, 2)


def sensitive_hits(profile: Collection[int], sensitive: Sequence[int]) -> List[int]:
    """Sensitive syscalls present in ``profile`` (order follows ``sensitive``)."""
    profile_set = set(profile)
    return [s for s in sensitive if s in profile_set]


def sn_percent(
    profile: Collection[int], sensitive: Sequence[int], sn_base: int = config.SN_BASE
) -> float:
    """Sensitive-blocking metric: percentage of sensitive syscalls blocked."""
    hits = len(sensitive_hits(profile, sensitive))
    return round(((sn_base - hits) / sn_base) * 100, 2)


@dataclass
class CategoryMetrics:
    """Per-category SP/SN values plus averages and maxima (the saphire baseline)."""

    sp_values: List[float]
    sn_values: List[float]
    avg_sp: float
    avg_sn: float
    max_sp: float
    max_sn: float


def category_metrics(
    categorized_urls: Sequence[dict], sensitive: Sequence[int]
) -> CategoryMetrics:
    """Compute per-category SP/SN for a categorized URL set (was ``saphire.py``)."""
    sp_values: List[float] = []
    sn_values: List[float] = []
    for group in categorized_urls:
        profile = group["associated_numbers"]
        sp_values.append(sp_percent(profile))
        sn_values.append(sn_percent(profile, sensitive))
    avg_sp = round(sum(sp_values) / len(sp_values), 2)
    avg_sn = round(sum(sn_values) / len(sn_values), 2)
    return CategoryMetrics(
        sp_values=sp_values,
        sn_values=sn_values,
        avg_sp=avg_sp,
        avg_sn=avg_sn,
        max_sp=max(sp_values),
        max_sn=max(sn_values),
    )


@dataclass
class BaselineMetrics:
    sp: float
    sn: float


def sysfilter_metrics(
    sensitive: Sequence[int],
    sysfilter_syscalls: Sequence[int] = config.SYSFILTER_SYSCALLS,
) -> BaselineMetrics:
    """SP%/SN% for sysfilter's static whole-interpreter allow-list baseline."""
    sp = sp_percent(sysfilter_syscalls)
    sn = sn_percent(sysfilter_syscalls, sensitive)
    return BaselineMetrics(sp=sp, sn=sn)
