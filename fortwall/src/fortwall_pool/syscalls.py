"""Syscall table and sensitive-syscall classification.

Ported from the original ``sen_syscalls.py`` with behavior preserved.

The public helpers let callers:

* read the kernel syscall-number table (``read_syscall_table``),
* parse the human-readable sensitive-syscall classification text
  (``parse_syscall_classifications``), and
* resolve the classification into concrete syscall *numbers*
  (``sensitive_syscall_numbers``) -- the 20-element set used by the SN% metric.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Set, Union

# Sensitive-syscall classification table (verbatim from the original).
#
# Note: the first line is a header and is skipped by the parser. Only the first
# word of each classification name becomes the dict key; the remaining words end
# up inside the value list. Those stray words are not real syscall names, so
# they are filtered out by ``calculate_intersection`` / ``sensitive_syscall_numbers``
# and do not affect the resulting syscall-number set. Kept as-is for parity.
SYSCALL_CLASSIFICATIONS = """
System Call Classification Applicable System Calls
Arbitrary Code Execution execve, execveat, fork, vfork, clone, ptrace
Memory Permissions mprotect, mmap, mremap, remap_file_pages
Privilege Escalation chmod, setuid, setgid, setreuid
Networking socket, bind, connect, listen, accept, accept4
"""


def read_syscall_table(file_path: Union[str, Path]) -> Dict[int, str]:
    """Parse a kernel ``unistd_64.h``-style header into ``{number: name}``.

    Only ``#define __NR_<name> <number>`` lines with exactly three
    whitespace-separated tokens are considered.
    """
    syscall_table: Dict[int, str] = {}
    with open(file_path, "r") as file:
        for line in file:
            if line.startswith("#define __NR_"):
                parts = line.split()
                if len(parts) == 3:
                    name = parts[1].replace("__NR_", "")
                    number = int(parts[2])
                    syscall_table[number] = name
    return syscall_table


def parse_syscall_classifications(classifications: str = SYSCALL_CLASSIFICATIONS) -> Dict[str, List[str]]:
    """Parse the classification text into ``{classification: [tokens]}``.

    Behavior is identical to the original: the header line is dropped, the line
    is split on the first space, and ``\\w+`` tokens are extracted from the
    remainder.
    """
    classification_dict: Dict[str, List[str]] = {}
    lines = classifications.strip().split("\n")[1:]  # Skip the header line
    for line in lines:
        parts = line.split(" ", 1)
        classification = parts[0]
        syscalls = re.findall(r"\w+", parts[1])
        classification_dict[classification] = syscalls
    return classification_dict


def calculate_intersection(
    classification_dict: Dict[str, List[str]], syscall_table: Dict[int, str]
) -> Dict[str, List[str]]:
    """Keep only tokens that are real syscall names present in ``syscall_table``."""
    intersect_dict: Dict[str, List[str]] = {}
    syscall_set = set(syscall_table.values())
    for classification, syscalls in classification_dict.items():
        intersection = [sc for sc in syscalls if sc in syscall_set]
        intersect_dict[classification] = intersection
    return intersect_dict


def sensitive_syscall_numbers(
    classification_dict: Dict[str, List[str]], syscall_table: Dict[int, str]
) -> List[int]:
    """Resolve the classification into a flat list of syscall *numbers*.

    Mirrors the derivation used in the original ``sen_syscalls`` / ``saphire``
    scripts. Produces the 20-element sensitive-syscall set (see
    :data:`fortwall_pool.config.SN_BASE`).
    """
    numbers: List[int] = []
    for _classification, syscalls in classification_dict.items():
        numbers.extend([num for num, name in syscall_table.items() if name in syscalls])
    return numbers


def load_sensitive_syscalls(syscall_table_path: Union[str, Path]) -> List[int]:
    """Convenience: read the table and return the sensitive syscall numbers."""
    syscall_table = read_syscall_table(syscall_table_path)
    classification_dict = parse_syscall_classifications()
    return sensitive_syscall_numbers(classification_dict, syscall_table)


def sensitive_syscalls_intersection(
    sensitive_syscalls: List[int], clusters_syscalls: Dict[int, List[int]]
) -> Dict[int, List[int]]:
    """Intersect each cluster's syscalls with the sensitive-syscall set."""
    intersect_dict: Dict[int, List[int]] = {}
    sensitive_syscall_set: Set[int] = set(sensitive_syscalls)
    for cluster, syscalls in clusters_syscalls.items():
        intersect_dict[cluster] = [sc for sc in syscalls if sc in sensitive_syscall_set]
    return intersect_dict
