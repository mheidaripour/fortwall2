from pathlib import Path

import pytest

from fortwall_pool import syscalls
from fortwall_pool.config import SN_BASE

SYSCALL_TABLE = Path(__file__).resolve().parents[1] / "data" / "syscall_table" / "unistd_64_.h"


def test_read_syscall_table_basic():
    table = syscalls.read_syscall_table(SYSCALL_TABLE)
    # Well-known x86_64 syscall numbers.
    assert table[0] == "read"
    assert table[1] == "write"
    assert table[59] == "execve"
    # Only 3-token "#define __NR_ name number" lines are captured.
    assert all(isinstance(k, int) for k in table)


def test_read_syscall_table_from_fixture(tmp_path):
    header = tmp_path / "u.h"
    header.write_text(
        "#ifndef _X\n"
        "#define _X 1\n"           # 3 tokens but name has no __NR_ prefix -> skipped
        "#define __NR_read 0\n"
        "#define __NR_write 1\n"
        "garbage line\n"
    )
    table = syscalls.read_syscall_table(header)
    assert table == {0: "read", 1: "write"}


def test_parse_classifications_preserves_quirk():
    parsed = syscalls.parse_syscall_classifications()
    # Keys are only the first word of each classification name (preserved quirk).
    assert set(parsed.keys()) == {"Arbitrary", "Memory", "Privilege", "Networking"}
    # Real syscall names still show up in the token lists.
    assert "execve" in parsed["Arbitrary"]
    assert "mprotect" in parsed["Memory"]
    assert "socket" in parsed["Networking"]


def test_calculate_intersection_filters_to_real_names():
    table = syscalls.read_syscall_table(SYSCALL_TABLE)
    parsed = syscalls.parse_syscall_classifications()
    inter = syscalls.calculate_intersection(parsed, table)
    # Stray non-syscall words ("Code", "Execution", ...) are filtered out.
    assert "Code" not in inter["Arbitrary"]
    assert "execve" in inter["Arbitrary"]


def test_sensitive_syscalls_count_matches_sn_base():
    nums = syscalls.load_sensitive_syscalls(SYSCALL_TABLE)
    assert len(nums) == SN_BASE == 20
    table = syscalls.read_syscall_table(SYSCALL_TABLE)
    expected_names = {
        "execve", "execveat", "fork", "vfork", "clone", "ptrace",
        "mprotect", "mmap", "mremap", "remap_file_pages",
        "chmod", "setuid", "setgid", "setreuid",
        "socket", "bind", "connect", "listen", "accept", "accept4",
    }
    assert {table[n] for n in nums} == expected_names


def test_sensitive_syscalls_intersection():
    result = syscalls.sensitive_syscalls_intersection([1, 2, 3], {0: [1, 9], 1: [4, 5]})
    assert result == {0: [1], 1: []}
