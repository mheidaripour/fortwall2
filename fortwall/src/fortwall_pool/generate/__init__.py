"""Pure config-file generation (renders text; thin writers persist it).

No module here touches system destinations -- generation writes only to the
local staging directory. Deployment (copying to ``/etc/nginx`` etc.) lives in
:mod:`fortwall_pool.deploy`.
"""

from . import nginx, phpfpm, stage2out  # noqa: F401
