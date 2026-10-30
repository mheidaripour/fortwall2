from fortwall_pool import metrics
from fortwall_pool.config import TOTAL_SYSCALLS, SN_BASE


def test_sp_percent():
    assert metrics.sp_percent(range(33)) == round(((TOTAL_SYSCALLS - 33) / TOTAL_SYSCALLS) * 100, 2)
    assert metrics.sp_percent([]) == 100.0
    assert metrics.sp_percent(range(TOTAL_SYSCALLS)) == 0.0


def test_sensitive_hits_order_follows_sensitive():
    sensitive = [59, 9, 41]
    assert metrics.sensitive_hits({41, 59, 100}, sensitive) == [59, 41]


def test_sn_percent():
    sensitive = list(range(1, 21))  # 20 sensitive syscalls
    # profile hits 5 of them -> 15/20 blocked -> 75%
    assert metrics.sn_percent(set(range(1, 6)), sensitive) == 75.0
    assert metrics.sn_percent(set(), sensitive) == 100.0
    assert metrics.sn_percent(set(range(1, 21)), sensitive) == 0.0


def test_category_metrics_avg_and_max():
    sensitive = list(range(1, 21))
    cats = [
        {"associated_numbers": list(range(10)), "urls": ["/a"]},
        {"associated_numbers": list(range(20)), "urls": ["/b"]},
    ]
    m = metrics.category_metrics(cats, sensitive)
    assert len(m.sp_values) == 2
    assert m.avg_sp == round(sum(m.sp_values) / 2, 2)
    assert m.max_sp == max(m.sp_values)
    assert m.max_sn == max(m.sn_values)


def test_sysfilter_metrics_matches_manual():
    sensitive = [1, 2, 3, 59, 9]
    b = metrics.sysfilter_metrics(sensitive)
    assert b.sp == metrics.sp_percent(metrics.config.SYSFILTER_SYSCALLS)
    assert b.sn == metrics.sn_percent(metrics.config.SYSFILTER_SYSCALLS, sensitive)
    assert 0.0 <= b.sp <= 100.0 and 0.0 <= b.sn <= 100.0
    assert SN_BASE == 20
