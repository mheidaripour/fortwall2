# FortWall / Saphire container runbook

This runbook describes a reproducible, disposable `linux/amd64` container for
running the Saphire stages and FortWall enforcement, as an alternative to the
prebuilt Saphire QEMU VM.

## Why x86_64

- **The constraint is the architecture.** Saphire's stage-1 static analysis
  disassembles the **x86_64** PHP binary and reads x86_64 syscall numbers; every
  `stage2_out_*` file and the `unistd_64` syscall table are x86_64. An arm64
  Linux environment would silently produce incompatible numbers, so the image is
  pinned to `linux/amd64`.
- On **Apple-Silicon** hosts the image runs emulated (Docker Desktop / Rosetta).
  This is fine for *functional* work: regenerating `stage2_out`, testing
  enforcement, running the exploit case studies.
- **Emulated timings are not representative.** Run performance benchmarks on a
  **native x86_64 Linux host** using the same image (see "Performance runs").

## What needs the container

| Task | Where it runs |
|---|---|
| FortWall clustering / metrics / report / pool planning | any host, natively (`fortwall/.venv`); the `stage2_out_*` files for all evaluated apps are in `artifacts/` |
| Generating a **new** `stage2_out` (new app or PHP version) | container (stages 1–2) |
| **Enforcement** (seccomp) + exploit validation | container (stage 3 / FortWall deploy) |
| **Performance** measurements | native x86_64 Linux host (this image) |

## First run

```bash
# from the repository root
docker compose build          # the first build compiles PHP 7.1 from source and takes a while
docker compose up -d
docker compose exec lab bash  # shell as user "paper", in /home/paper
```

Inside the container the layout matches upstream Saphire's on-host paths
(`~/php-src`, `~/stage1`, `~/stage2`, `~/stage3`, plus `~/fortwall`, `~/artifacts`).
The `fortwall/`, `artifacts/` and `saphire/` directories are bind-mounted, so
host edits are visible in the container without a rebuild. Create a separate
Linux virtualenv inside the container (a host `.venv` built on macOS will not
run there):

```bash
cd ~/fortwall && python3 -m venv .venv-linux && .venv-linux/bin/pip install -e ".[dev]"
```

## Alternative: import the prebuilt Saphire VM

Instead of building from scratch, the prebuilt Saphire VM can be converted into
a Docker image. This reproduces the original environment exactly. Do this on a
**native x86_64 Linux host**, which can then also be used for performance runs.

**Host requirements:**
- **Disk ≥ ~100 GB**: the qcow2 (several GB), a raw copy (the *virtual* size,
  tens of GB) and the resulting Docker image coexist briefly.
- RAM ≥ 4 GB, Docker, and `qemu-utils` (`qemu-img`).
- KVM / nested virtualization is needed **only** for Method A below; Method B
  works without it.

```bash
git clone <repo-url> && cd <repo>
sudo apt-get update && sudo apt-get install -y qemu-utils

# Download the prebuilt VM (Google Drive; ~4 GB+).
docker/fetch-vm.sh saphire.qcow2
```

### Method A: boot the VM and export its root filesystem (requires KVM)

Uses the VM's own userland, so no partition/LVM detection is needed. Credentials
from the Saphire README: user `paper`, password `saphire2021`.

```bash
# Boot headless with ssh forwarded to localhost:22222 (per Saphire's README).
qemu-system-x86_64 -machine q35 -accel kvm -m 4096M \
  -device virtio-net,netdev=n0 \
  -netdev user,id=n0,hostfwd=tcp:127.0.0.1:22222-:22,hostfwd=tcp:127.0.0.1:8000-:8000 \
  -nographic saphire.qcow2 &

ssh -p22222 paper@localhost   # password: saphire2021
#  --- inside the VM: ---
sudo tar -czf /tmp/rootfs.tar.gz --numeric-owner \
  --exclude=/proc --exclude=/sys --exclude=/dev --exclude=/run \
  --exclude=/tmp/rootfs.tar.gz --exclude=/mnt --exclude=/media /
exit
scp -P22222 paper@localhost:/tmp/rootfs.tar.gz .
docker import \
  --change 'ENV PATH=/opt/php-7.1/bin:/opt/php-7.1/sbin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' \
  --change 'WORKDIR /home/paper' --change 'CMD ["bash"]' \
  rootfs.tar.gz saphire-vm:orig
```

### Method B: offline extraction (no KVM required)

`docker/vm-to-image.sh` converts the disk, loop-mounts it, archives the root
filesystem and imports it in one step:

```bash
docker/vm-to-image.sh saphire.qcow2 saphire-vm:orig
```

### Build and run the wrapper image

```bash
docker build --platform=linux/amd64 -t fortwall-lab -f docker/Dockerfile.vm .
```

`docker-compose.yml` builds the from-scratch `docker/Dockerfile` by default. To
use the imported VM image instead, set the `lab` service's
`dockerfile: docker/Dockerfile.vm` (it is `FROM saphire-vm:orig`), then:

```bash
docker compose up -d
docker compose exec lab bash
```

To develop against a remote Linux host, VS Code Remote-SSH (optionally combined
with attaching to the `fortwall-lab` container) keeps the editor local while
the kernel, seccomp and php-fpm run on the x86_64 host.

## Running the Saphire stages

The upstream `run_stage*.sh` scripts are copied to `~`. They `sudo make install`
into `/opt/php-7.1`, so run them as `paper` (passwordless sudo is configured).

```bash
# Stage 1: build PHP 7.1 + tracing/static analysis and emit the stage-1 mapping.
# Compiles PHP and runs its test suite under a modified strace.
./run_stage1.sh /home/paper/artifacts/stage1_output

# Select the target web app.
./switch_to_wordpress.sh          # or drupal/joomla/magento/moodle/prestashop/phpmyadmin

# Stage 2: build the per-app syscall profile (the input to FortWall).
./run_stage2.sh /home/paper/artifacts/stage1_output \
                /home/paper/artifacts/stage2_out/stage2_out_wordpress_new

# Stage 3: Saphire's own single-filter enforcement (the comparison baseline).
./run_stage3.sh /home/paper/artifacts/stage2_out/stage2_out_wordpress
DISABLE_PROTECTION=1 ./run_stage3.sh ...   # run without the filter, e.g. to demonstrate an exploit
```

FortWall's pooled enforcement, the alternative to stage 3, runs from the
`fortwall/` layer:

```bash
cd ~/fortwall
.venv-linux/bin/fortwall analyze --app wordpress --clusters 5
.venv-linux/bin/fortwall switch --mode mpool --app wordpress -p 7 --dry-run
```

The web applications themselves (`/var/www/wordpress`, …) are **not** included
in this repository. Copy them into the container (e.g. via a mounted
`webroots/` directory or `docker cp`) and adjust the source path in the
`switch_to_*` scripts accordingly. The imported VM image already contains them.

## Performance runs

On a native x86_64 Linux host:

```bash
git clone <repo-url> && cd <repo>
docker compose build && docker compose up -d
docker compose exec lab bash
# bring up nginx + php-fpm for the mode under test, then:
cd ~/fortwall/experiments
python3 bigrun.py -t prt_pl -f pools-urls        # sweeps concurrency 1..32
```

## configure-flag → Debian package map (stage 1)

Reference for editing the Dockerfile if a `./configure` flag fails:

| PHP `./configure` flag | package |
|---|---|
| `--with-libxml-dir`, `--enable-soap` | `libxml2-dev` |
| `--with-openssl` | `libssl-dev` |
| `--with-curl` | `libcurl4-openssl-dev` |
| `--with-pcre-regex` | `libpcre3-dev` |
| `--with-zlib`, `--with-zlib-dir` | `zlib1g-dev` |
| `--with-bz2` | `libbz2-dev` |
| `--enable-zip` | `libzip-dev` |
| `--with-jpeg-dir` | `libjpeg-dev` |
| `--with-png-dir` | `libpng-dev` |
| `--with-freetype-dir` | `libfreetype6-dev` |
| `--with-mcrypt` | `libmcrypt-dev` |
| `--with-mhash` | `libmhash-dev` |
| `--with-pgsql`, `--with-pdo-pgsql` | `libpq-dev` |
| `--with-mysqli`, `--with-pdo-mysql` | `default-libmysqlclient-dev` |
| `--with-xsl`, `--with-xmlrpc` | `libxslt1-dev` |
| `--with-imap`, `--with-imap-ssl` | `libc-client2007e-dev` |
| `--with-kerberos` | `libkrb5-dev` |
| `--with-gettext` | `libgettextpo-dev` (glibc provides the runtime) |

## PHP version

The image pins PHP 7.1 because two C extensions target PHP 7.1's Zend ABI:
Saphire's stage-1 `TE_xdebug` tracing extension and the stage-3 `seccomp`
extension (`saphire/stage3/extension/seccomp.c`). Building against PHP 8.x
(`--build-arg PHP_REF=php-8.3.14`; php-src tags are lowercase) requires porting
both extensions' `zend_*` API calls (and a newer xdebug). FortWall's
pooling/clustering is independent of the PHP version.

## Troubleshooting

- **Debian stretch is EOL**: the Dockerfile points apt at `archive.debian.org`
  and disables the release-expiry check.
- **Go version**: stretch ships an old `golang-go`. If `stage2/php-api-deps`
  (uses `dep`/`Gopkg`) or `stage1/process-traces` fails to build, install a
  newer Go release tarball in the image instead of the apt package.
- **imap dev library**: named `libc-client2007e-dev` on stretch (not
  `libc-client-dev`).
- **php-src version**: `--build-arg PHP_REF=` selects a different tag if
  `PHP-7.1.33` does not match the environment being reproduced.
