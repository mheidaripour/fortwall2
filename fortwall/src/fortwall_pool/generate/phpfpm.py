"""Generate php-fpm pool configuration files from the www.conf template.

Renderers are pure ``str -> str`` transforms. Behavior is preserved verbatim,
including the original quirk where the ``www.conf`` rewrite never matched the
``pm.max_children`` line (its condition lacked a trailing newline) while the
per-pool rewrite does.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Sequence, Union

from .. import config


def render_www_conf(template_text: str) -> str:
    """Render the shared ``www.conf`` (max_requests -> 0, spare_servers -> 1).

    Preserved quirk: ``pm.max_children`` is intentionally *not* rewritten here.
    """
    out: List[str] = []
    for line in template_text.splitlines(keepends=True):
        if line == "pm.max_requests = 1\n":
            out.append(line.replace("pm.max_requests = 1", "pm.max_requests = 0"))
        elif line == "pm.max_children = 8":  # preserved: never matches a real line
            out.append(line.replace("pm.max_children = 8", "pm.max_children = 1"))
        elif line == "pm.max_spare_servers = 3\n":
            out.append(line.replace("pm.max_spare_servers = 3", "pm.max_spare_servers = 1"))
        else:
            out.append(line)
    return "".join(out)


def render_pool_conf(template_text: str, pool_index: int) -> str:
    """Render ``pool_<pool_index>.conf``: rename pool, unique socket, tuned pm.*."""
    listen_from = f"listen = {config.SYSTEM.php_default_sock}\n"
    listen_to = f"listen = {config.SYSTEM.php_socket_dir}/pool_{pool_index}.sock\n"
    out: List[str] = []
    for line in template_text.splitlines(keepends=True):
        if line == "[www]\n":
            out.append(line.replace("[www]\n", f"[pool_{pool_index}]\n"))
        elif line == listen_from:
            out.append(line.replace(listen_from, listen_to))
        elif line == "pm.max_requests = 1\n":
            out.append(line.replace("pm.max_requests = 1", "pm.max_requests = 0"))
        elif line == "pm.max_children = 8\n":
            out.append(line.replace("pm.max_children = 8", "pm.max_children = 1"))
        elif line == "pm.max_spare_servers = 3\n":
            out.append(line.replace("pm.max_spare_servers = 3", "pm.max_spare_servers = 1"))
        else:
            out.append(line)
    return "".join(out)


def write_pool_configs(
    num_pools: int, template_path: Union[str, Path], out_dir: Union[str, Path]
) -> List[Path]:
    """Write ``www.conf`` plus ``pool_1..num_pools.conf`` into ``out_dir``."""
    template_text = Path(template_path).read_text()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written: List[Path] = []
    www = out_dir / "www.conf"
    www.write_text(render_www_conf(template_text))
    written.append(www)

    for i in range(num_pools):
        path = out_dir / f"pool_{i + 1}.conf"
        path.write_text(render_pool_conf(template_text, i + 1))
        written.append(path)
    return written
