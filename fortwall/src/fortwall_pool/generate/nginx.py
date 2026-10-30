"""Generate nginx artifacts: per-pool URL maps, nginx.conf, sites default.

Renderers are pure ``str -> str`` transforms so they can be unit-tested without
touching the filesystem; the ``write_*`` helpers persist them.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Sequence, Union

from .. import config


def render_url_map(urls: Sequence[str], pool_index: int) -> str:
    """Content of ``url_map_<pool_index>.conf`` mapping each URL to its pool socket."""
    sock = config.SYSTEM.pool_sock(pool_index)
    return "".join(f"{url} unix:{sock};\n" for url in urls)


def write_url_maps(categories: Sequence[dict], out_dir: Union[str, Path]) -> List[Path]:
    """Write one ``url_map_<i>.conf`` per category (1-based). Returns written paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    for i, category in enumerate(categories):
        path = out_dir / f"url_map_{i + 1}.conf"
        path.write_text(render_url_map(category["urls"], i + 1))
        written.append(path)
    return written


def render_nginx_conf(template_text: str, num_pools: int) -> str:
    """Insert ``include`` lines for each pool's URL map into nginx.conf.

    The include block is added immediately after the default upstream line,
    matching the original (9-space indentation preserved).
    """
    target = f"         default unix:{config.SYSTEM.php_default_sock};\n"
    url_map_dir = config.SYSTEM.nginx_url_map_dir
    out: List[str] = []
    for line in template_text.splitlines(keepends=True):
        out.append(line)
        if line == target:
            for i in range(num_pools):
                out.append(f"         include {url_map_dir}/url_map_{i + 1}.conf;\n")
    return "".join(out)


def render_sites_default(template_text: str) -> str:
    """Point the ``fastcgi_pass`` directive at the ``$upstream`` map variable."""
    target = f"\tfastcgi_pass unix:{config.SYSTEM.php_default_sock};\n"
    replacement = "\tfastcgi_pass $upstream;\n"
    return "".join(
        replacement if line == target else line
        for line in template_text.splitlines(keepends=True)
    )


def write_nginx_conf(template_path: Union[str, Path], num_pools: int, out_path: Union[str, Path]) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_nginx_conf(Path(template_path).read_text(), num_pools))
    return out_path


def write_sites_default(template_path: Union[str, Path], out_path: Union[str, Path]) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_sites_default(Path(template_path).read_text()))
    return out_path
