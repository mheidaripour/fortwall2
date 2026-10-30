"""Centralized paths and constants for fortwall-pool.

Every value that used to be a hardcoded literal scattered across the original
scripts (``/opt/php-7.1/...``, ``/etc/nginx/...``, ``333``, ``20``, ``10``,
socket templates, ...) is collected here so behavior can be tuned in one place.

Two groups of paths exist:

* **System destinations** (``SystemPaths``) -- the real locations the deploy
  step writes to on the target host. These match the originals exactly so
  deployment behavior is preserved.
* **Local working paths** (``WorkPaths``) -- staging/backup directories the
  tooling uses locally. Defaults point at organized ``generated/`` and
  ``backups/`` folders; they are intermediate and do not affect what lands on
  the deployed system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


# --- Syscall accounting constants (were duplicated in sen_syscalls/saphire/urlanalyze) ---
TOTAL_SYSCALLS = 333
"""Total number of syscalls used as the denominator for the SP% metric."""

SN_BASE = 20
"""Number of "sensitive" syscalls used as the denominator for the SN% metric."""

URL_PCT_THRESHOLD = 10
"""URL-share percentage at/above which a category gets its own dedicated pool."""

DEFAULT_NUM_POOLS = 7
"""Default total number of php-fpm pools (matches the original switch.py default)."""


# --- Static baseline dataset: sysfilter's whole-interpreter allow-list ---
# Kept verbatim from sen_syscalls.py for the sysfilter comparison baseline.
SYSFILTER_SYSCALLS = [
    0, 1, 3, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 24, 25, 28,
    32, 33, 37, 38, 39, 41, 42, 43, 44, 45, 47, 48, 49, 50, 51, 52, 53, 54, 55,
    56, 59, 60, 61, 62, 63, 72, 73, 74, 75, 77, 79, 80, 81, 82, 83, 84, 86, 87,
    88, 89, 90, 91, 92, 93, 94, 95, 96, 98, 99, 100, 102, 104, 105, 106, 107,
    108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 119, 121, 124, 137, 138,
    140, 141, 142, 143, 144, 145, 146, 147, 157, 161, 186, 201, 202, 203, 204,
    217, 228, 230, 231, 234, 257, 259, 262, 270, 273, 280, 293, 302, 307, 318,
    326, 334, 435, 436,
]


@dataclass(frozen=True)
class SystemPaths:
    """Real destinations on the target host (identical to the originals)."""

    php_fpm_dir: Path = Path("/opt/php-7.1/etc/php-fpm.d")
    php_socket_dir: Path = Path("/opt/php-7.1/var/run/php")
    php_default_sock: Path = Path("/opt/php-7.1/var/run/php/php7.1-fpm.sock")

    nginx_conf: Path = Path("/etc/nginx/nginx.conf")
    nginx_sites_default: Path = Path("/etc/nginx/sites-enabled/default")
    nginx_url_map_dir: Path = Path("/etc/nginx/urlmapphp")

    intersect_filter: Path = Path("/var/www/intersect_filter")
    stage2_out_dir: Path = Path("/home/paper")

    def stage2_out(self, app: str) -> Path:
        """Path to the stage2 syscall-mapping file for ``app``."""
        return self.stage2_out_dir / f"stage2_out_{app}"

    def pool_sock(self, pool_index: int) -> str:
        """Socket path string for pool number ``pool_index`` (1-based)."""
        return f"{self.php_socket_dir}/pool_{pool_index}.sock"


@dataclass(frozen=True)
class WorkPaths:
    """Local staging/backup directories used by the tooling."""

    root: Path = Path(".")
    generated: Path = field(default_factory=lambda: Path("generated"))
    backups: Path = field(default_factory=lambda: Path("backups"))

    # Data inputs
    syscall_table: Path = field(default_factory=lambda: Path("data/syscall_table/unistd_64_.h"))
    # The stage2_out_* files are the saphire->fortwall data contract; they live
    # in the repo-level artifacts/ dir, i.e. ../artifacts relative to this layer.
    stage2_out_dir: Path = field(default_factory=lambda: Path("../artifacts/stage2_out"))

    def stage2_out(self, app: str) -> Path:
        """Local stage2 syscall-mapping input file for ``app`` (saphire output)."""
        return self.stage2_out_dir / f"stage2_out_{app}"

    @property
    def nginx_url_map_dir(self) -> Path:
        return self.generated / "nginx-url-map-files"

    @property
    def php_fpm_config_dir(self) -> Path:
        return self.generated / "php-fpm-config-files"

    @property
    def intersection_file(self) -> Path:
        return self.generated / "intersection"

    @property
    def nginx_conf(self) -> Path:
        return self.generated / "nginx.conf"

    @property
    def nginx_sites_default(self) -> Path:
        return self.generated / "default"

    @property
    def stage2_out_backup_dir(self) -> Path:
        return self.backups / "stage2_out_backup"

    @property
    def nginx_defaults_dir(self) -> Path:
        return self.backups / "nginxdefaults"

    @property
    def php_fpm_defaults_dir(self) -> Path:
        return self.backups / "php-fpm-defaults"


# Convenient module-level singletons.
SYSTEM = SystemPaths()
WORK = WorkPaths()
