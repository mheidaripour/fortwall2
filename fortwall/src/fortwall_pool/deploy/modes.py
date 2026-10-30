"""Switch modes: mpool / saphire / default (was ``switch.py``).

Local config *generation* is separated from *deployment*:

* :func:`generate_mpool` writes all artifacts into the local staging area and
  returns their paths (no system mutation).
* :func:`switch_mpool` / :func:`switch_saphire` / :func:`switch_default` drive a
  :class:`~fortwall_pool.deploy.system.Deployer` to apply them (honoring dry-run).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from .. import config, pipeline, urlmap
from ..generate import nginx as gen_nginx
from ..generate import phpfpm as gen_phpfpm
from ..generate import stage2out as gen_stage2out
from .system import Deployer

PathLike = Union[str, Path]


@dataclass
class MpoolArtifacts:
    """Paths and metadata produced by :func:`generate_mpool`."""

    app: str
    pool_count: int
    plan: pipeline.PoolPlan
    intersection_file: Path
    stage2_out_file: Path
    url_map_dir: Path
    php_fpm_dir: Path
    nginx_conf: Path
    sites_default: Path

    @property
    def diagnostics(self) -> List[str]:
        return self.plan.diagnostics


def generate_mpool(
    app: str,
    pools_num: int = config.DEFAULT_NUM_POOLS,
    *,
    work: config.WorkPaths = config.WORK,
    system: config.SystemPaths = config.SYSTEM,
    stage2_out_path: Optional[PathLike] = None,
    www_template: Optional[PathLike] = None,
    nginx_template: Optional[PathLike] = None,
    sites_template: Optional[PathLike] = None,
) -> MpoolArtifacts:
    """Build every mpool artifact locally (no system writes).

    ``pools_num`` is the total pool budget; the number of *clustered* pools is
    ``pools_num - <dedicated high-share categories>`` (matching ``switch.py``).
    """
    stage2_out_path = Path(stage2_out_path) if stage2_out_path else system.stage2_out(app)
    www_template = Path(www_template) if www_template else system.php_fpm_dir / "www.conf"
    nginx_template = Path(nginx_template) if nginx_template else system.nginx_conf
    sites_template = Path(sites_template) if sites_template else system.nginx_sites_default

    plan = pipeline.build_pool_plan(stage2_out_path, total_pools=pools_num)

    # Persist the intersection (baseline filter) and a serialized stage2_out.
    Path(work.generated).mkdir(parents=True, exist_ok=True)
    urlmap.write_intersection_to_file(plan.intersection, work.intersection_file)
    stage2_out_file = Path(work.generated) / f"stage2_out_{app}"
    gen_stage2out.write_stage2_out(plan.all_clusters, stage2_out_file)

    # Pools that actually restrict syscalls (drop empty-superset clusters).
    nginx_pools_map = urlmap.remove_clusters_empty_syscalls(plan.all_clusters)
    pool_count = len(nginx_pools_map)

    gen_nginx.write_url_maps(nginx_pools_map, work.nginx_url_map_dir)
    gen_phpfpm.write_pool_configs(pool_count, www_template, work.php_fpm_config_dir)
    nginx_conf = gen_nginx.write_nginx_conf(nginx_template, pool_count, work.nginx_conf)
    sites_default = gen_nginx.write_sites_default(sites_template, work.nginx_sites_default)

    return MpoolArtifacts(
        app=app,
        pool_count=pool_count,
        plan=plan,
        intersection_file=Path(work.intersection_file),
        stage2_out_file=stage2_out_file,
        url_map_dir=Path(work.nginx_url_map_dir),
        php_fpm_dir=Path(work.php_fpm_config_dir),
        nginx_conf=nginx_conf,
        sites_default=sites_default,
    )


def switch_mpool(
    app: str,
    pools_num: int = config.DEFAULT_NUM_POOLS,
    *,
    deployer: Optional[Deployer] = None,
    **generate_kwargs,
) -> MpoolArtifacts:
    """Clean, generate, deploy and restart -- the full mpool switch."""
    deployer = deployer or Deployer()
    system = deployer.system

    deployer.clean_configs(app)
    stage2_out_path = generate_kwargs.pop("stage2_out_path", None) or system.stage2_out(app)
    deployer.backup_stage2_out(stage2_out_path)

    arts = generate_mpool(
        app, pools_num, work=deployer.work, system=system,
        stage2_out_path=stage2_out_path, **generate_kwargs,
    )

    deployer.copy_intersection_file(arts.intersection_file)
    deployer.replace_nginx_conf(arts.nginx_conf)
    deployer.replace_sites_default(arts.sites_default)
    deployer.copy_nginx_url_maps(arts.url_map_dir)
    deployer.copy_php_fpm_configs(arts.php_fpm_dir)
    deployer.restart_nginx()
    return arts


def switch_saphire(app: str, *, deployer: Optional[Deployer] = None) -> None:
    """Revert to the saphire baseline: clean configs and restart nginx."""
    deployer = deployer or Deployer()
    deployer.clean_configs(app)
    deployer.restart_nginx()


def switch_default(*, deployer: Optional[Deployer] = None) -> None:
    """Restore the default php-fpm ``www.conf``."""
    deployer = deployer or Deployer()
    deployer.change_php_fpm_www_conf_to_default()
