"""System-level deployment operations (the side-effecting half of intersection.py).

All filesystem/service mutations funnel through :class:`Deployer`, whose
primitive ops (:meth:`_copy`, :meth:`_copytree`, :meth:`_rmtree`, :meth:`_remove`,
:meth:`_run`) log every action and record it in :attr:`operations`. With
``dry_run=True`` nothing is actually changed -- useful for tests and previews.

Destinations match the originals exactly; only the *local* backup/staging
sources were relocated under ``backups/`` and ``generated/`` (see
:mod:`fortwall_pool.config`).
"""

from __future__ import annotations

import glob
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Union

from .. import config

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]


@dataclass
class Deployer:
    """Executes (or, in ``dry_run``, records) system deployment operations."""

    system: config.SystemPaths = field(default_factory=lambda: config.SYSTEM)
    work: config.WorkPaths = field(default_factory=lambda: config.WORK)
    dry_run: bool = False
    operations: List[Tuple[str, tuple]] = field(default_factory=list)

    # --- primitive operations -------------------------------------------------
    def _record(self, verb: str, *args) -> None:
        self.operations.append((verb, args))
        logger.info("%s%s %s", "[dry-run] " if self.dry_run else "", verb, " ".join(map(str, args)))

    def _copy(self, src: PathLike, dst: PathLike) -> None:
        self._record("copy", src, dst)
        if not self.dry_run:
            shutil.copy(src, dst)

    def _copytree(self, src: PathLike, dst: PathLike) -> None:
        self._record("copytree", src, dst)
        if not self.dry_run:
            shutil.copytree(src, dst)

    def _rmtree(self, path: PathLike) -> None:
        self._record("rmtree", path)
        if not self.dry_run and os.path.exists(path):
            shutil.rmtree(path)

    def _remove(self, path: PathLike) -> None:
        self._record("remove", path)
        if not self.dry_run:
            try:
                os.remove(path)
            except OSError as e:  # pragma: no cover - matches original leniency
                logger.warning("Error removing %s: %s", path, e)

    def _run(self, command: str) -> None:
        self._record("run", command)
        if not self.dry_run:
            os.system(command)

    # --- backups --------------------------------------------------------------
    def backup_stage2_out(self, source_path: PathLike) -> None:
        dest = self.work.stage2_out_backup_dir / Path(source_path).name
        Path(self.work.stage2_out_backup_dir).mkdir(parents=True, exist_ok=True)
        self._copy(source_path, dest)

    def backup_nginx_defaults(self) -> None:
        Path(self.work.nginx_defaults_dir).mkdir(parents=True, exist_ok=True)
        self._copy(self.system.nginx_conf, self.work.nginx_defaults_dir / "nginx.conf")
        self._copy(self.system.nginx_sites_default, self.work.nginx_defaults_dir / "default")

    def backup_php_fpm_defaults(self) -> None:
        Path(self.work.php_fpm_defaults_dir).mkdir(parents=True, exist_ok=True)
        for name in os.listdir(self.system.php_fpm_dir):
            full = os.path.join(self.system.php_fpm_dir, name)
            if os.path.isfile(full):
                self._copy(full, self.work.php_fpm_defaults_dir)

    # --- deploy generated artifacts to the host -------------------------------
    def copy_intersection_file(self, source_path: PathLike) -> None:
        self._copy(source_path, self.system.intersect_filter)

    def replace_nginx_conf(self, source_path: PathLike) -> None:
        self._copy(source_path, self.system.nginx_conf)

    def replace_sites_default(self, source_path: PathLike) -> None:
        self._copy(source_path, self.system.nginx_sites_default)

    def copy_nginx_url_maps(self, source_dir: PathLike) -> None:
        # Original used copytree into a fresh dir; clear it first for idempotency.
        self._rmtree(self.system.nginx_url_map_dir)
        self._copytree(source_dir, self.system.nginx_url_map_dir)

    def copy_php_fpm_configs(self, source_dir: PathLike) -> None:
        for name in os.listdir(source_dir):
            full = os.path.join(source_dir, name)
            if os.path.isfile(full):
                self._copy(full, self.system.php_fpm_dir)

    def restart_nginx(self) -> None:
        self._run("sudo systemctl restart nginx")

    def change_php_fpm_www_conf_to_default(self) -> None:
        self._copy(self.work.php_fpm_defaults_dir / "wwwdefault.conf", self.system.php_fpm_dir / "www.conf")

    # --- teardown / restore ---------------------------------------------------
    def remove_local_pooling_configs(self) -> None:
        self._rmtree(self.work.nginx_url_map_dir)
        self._rmtree(self.work.php_fpm_config_dir)

    def clean_configs(self, app_name: str) -> None:
        """Revert nginx + php-fpm to defaults and restore the app's stage2_out."""
        self._rmtree(self.system.nginx_url_map_dir)
        self._copy(self.work.nginx_defaults_dir / "nginx.conf", self.system.nginx_conf)
        self._copy(self.work.nginx_defaults_dir / "default", self.system.nginx_sites_default)

        for pool_file in glob.glob(str(self.system.php_fpm_dir / "pool*.conf")):
            self._remove(pool_file)
        self._copy(self.work.php_fpm_defaults_dir / "www.conf", self.system.php_fpm_dir / "www.conf")

        self._copy(
            self.work.stage2_out_backup_dir / f"stage2_out_{app_name}",
            self.system.stage2_out(app_name),
        )
        self.remove_local_pooling_configs()
