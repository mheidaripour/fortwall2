"""Side-effecting deployment: copy generated configs to the host, restart nginx.

Everything that writes outside the local staging area lives here. The
:class:`~fortwall_pool.deploy.system.Deployer` supports ``dry_run`` so the full
sequence can be exercised (and asserted on) without mutating the system.
"""

from .system import Deployer  # noqa: F401
from . import modes  # noqa: F401
