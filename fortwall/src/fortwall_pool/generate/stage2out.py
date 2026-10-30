"""Serialize a pool layout back to the ``stage2_out`` URL->syscall format."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union


def render_stage2_out(categories: Sequence[dict]) -> str:
    """Each URL followed by its category's syscall numbers, one per line."""
    lines = []
    for category in categories:
        numbers = " ".join(map(str, category["associated_numbers"]))
        for url in category["urls"]:
            lines.append(f"{url} {numbers}\n")
    return "".join(lines)


def write_stage2_out(categories: Sequence[dict], out_path: Union[str, Path]) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_stage2_out(categories))
    return out_path
