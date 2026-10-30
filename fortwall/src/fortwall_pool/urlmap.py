"""Parse stage2 URL->syscall maps and derive categories/intersection/clusters.

This is the pure-analysis half of the original ``intersection.py`` (the config
generation and system-deployment halves live in :mod:`fortwall_pool.generate`
and :mod:`fortwall_pool.deploy`). No function here touches system paths.

The interchange type is the original loose dict form, aliased as
:data:`UrlCategory`::

    {"associated_numbers": [int, ...], "urls": [str, ...]}
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Set, Union

try:  # TypedDict is documentation-only; fall back gracefully on old Pythons.
    from typing import TypedDict

    class UrlCategory(TypedDict):
        associated_numbers: List[int]
        urls: List[str]
except Exception:  # pragma: no cover
    UrlCategory = dict  # type: ignore

from . import config


def categorize_urls_by_numbers(file_path: Union[str, Path]) -> List[UrlCategory]:
    """Group URLs that share the exact same (sorted) syscall-number set.

    Lines whose trailing tokens are not all integers are skipped with a warning,
    matching the original. A URL with no trailing numbers groups under the empty
    set.
    """
    grouped_urls: Dict[tuple, List[str]] = defaultdict(list)

    with open(file_path, "r") as file:
        content = file.readlines()

    for line in content:
        parts = line.strip().split()
        url = parts[0]
        try:
            numbers = tuple(sorted(map(int, parts[1:])))
        except ValueError:
            print(f"Warning: Skipping malformed line: {line.strip()}")
            continue
        grouped_urls[numbers].append(url)

    return [
        {"associated_numbers": list(numbers), "urls": urls}
        for numbers, urls in grouped_urls.items()
    ]


def intersection_of_urls(categorized_urls: Sequence[UrlCategory]) -> Set[int]:
    """Syscall numbers common to *every* category (the baseline allow-list)."""
    data = [set(group["associated_numbers"]) for group in categorized_urls]
    intersection = set(data[0])
    for other in data[1:]:
        intersection.intersection_update(other)
    return intersection


def format_intersection_lines(intersection: Set[int]) -> List[str]:
    """Reproduce the original stdout for the intersection (parsed by report.py)."""
    return [
        f"Intersection of the associated system call numbers for all the sets: {intersection}",
        f"Intersection Length {len(intersection)}",
    ]


def write_intersection_to_file(intersection: Set[int], path: Union[str, Path]) -> None:
    """Write the intersection set using the original ``%s`` (set repr) format."""
    with open(path, "w") as f:
        f.write("%s" % intersection)


def calculate_urls_with_exact_intersection_set(
    categorized_urls: Sequence[UrlCategory], intersection: Set[int]
) -> List[str]:
    """URLs whose syscall set equals the intersection exactly."""
    urls: List[str] = []
    for group in categorized_urls:
        if set(group["associated_numbers"]) == intersection:
            urls.extend(group["urls"])
    return urls


def total_urls(url_categories: Sequence[UrlCategory]) -> int:
    """Total number of URLs across all categories."""
    return sum(len(category["urls"]) for category in url_categories)


@dataclass
class PercentageAnalysis:
    """Result of :func:`analyze_percentages`."""

    total_urls: int
    category_percentages: List[float]
    high_share_indices: List[int]  # categories with share >= threshold


def analyze_percentages(
    url_categories: Sequence[UrlCategory], threshold: float = config.URL_PCT_THRESHOLD
) -> PercentageAnalysis:
    """Compute each category's URL share and the indices at/above ``threshold``.

    Rounding matches the original (``round(pct, 6)``).
    """
    total = sum(len(category["urls"]) for category in url_categories)
    percentages = [
        round((len(category["urls"]) / total) * 100, 6) for category in url_categories
    ]
    high = [i for i, pct in enumerate(percentages) if pct >= threshold]
    return PercentageAnalysis(total_urls=total, category_percentages=percentages, high_share_indices=high)


def percentage_diagnostics_lines(
    url_categories: Sequence[UrlCategory], analysis: PercentageAnalysis
) -> List[str]:
    """Reproduce the stdout of the original ``calculate_url_categories_percentage``."""
    lines = [
        f"Total number of URLs: {analysis.total_urls}",
        f"Category percentages: {analysis.category_percentages}",
        f"the group with the highest percentage: {max(analysis.category_percentages)}",
    ]
    total_percentage = 0.0
    pools = 0
    for i in analysis.high_share_indices:
        total_percentage += analysis.category_percentages[i]
        lines.append(f"Category: {i} Percentage: {analysis.category_percentages[i]}")
        lines.append(
            f"Associated numbers: {len(url_categories[i]['associated_numbers'])} "
            f"percentage {round(len(url_categories[i]['associated_numbers']) / config.TOTAL_SYSCALLS, 4)}"
        )
        pools += 1
    lines.append(
        f"Sum of the percentages covered with total number of pool {pools}:  {total_percentage}"
    )
    return lines


def remove_intersection_set_from_associated_numbers(
    categorized_urls: Sequence[UrlCategory], intersection: Set[int]
) -> Sequence[UrlCategory]:
    """Subtract the intersection from every category's syscall set (mutates in place)."""
    for group in categorized_urls:
        group["associated_numbers"] = list(set(group["associated_numbers"]) - intersection)
    return categorized_urls


def create_new_categories(
    url_categories: Sequence[UrlCategory], cat_indices: Sequence[int]
) -> List[UrlCategory]:
    """Drop the high-share categories (they become their own dedicated pools)."""
    return [cat for i, cat in enumerate(url_categories) if i not in cat_indices]


def create_new_categories_with_clusters(
    url_categories: Sequence[UrlCategory],
    cat_indices: Sequence[int],
    cluster_urls: Dict[int, List[str]],
    supersets: Sequence[Set[int]],
) -> List[UrlCategory]:
    """Combine the dedicated high-share categories with the clustered pools."""
    new_categories: List[UrlCategory] = [url_categories[cat_indices[i]] for i in range(len(cat_indices))]
    for i in range(len(cluster_urls)):
        new_categories.append({"associated_numbers": list(supersets[i]), "urls": cluster_urls[i]})
    return new_categories


def remove_clusters_empty_syscalls(url_categories: Sequence[UrlCategory]) -> List[UrlCategory]:
    """Drop categories whose syscall set is empty."""
    return [category for category in url_categories if category["associated_numbers"]]


def sample_url_from_each_category(url_categories: Sequence[UrlCategory]) -> List[str]:
    """Return the first URL of each category (was a debug print in the original)."""
    return [category["urls"][0] for category in url_categories]
