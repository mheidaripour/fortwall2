# syntax=docker/dockerfile:1
#
# Saphire + FortWall reproducible pipeline environment.
#
# IMPORTANT: this image MUST be x86_64. Saphire's stage-1 static analysis
# disassembles the x86_64 PHP binary and reads x86_64 syscall numbers, and every
# stage2_out_* profile + the unistd_64 syscall table are x86_64-specific. On an
# Apple-Silicon (arm64) Mac this therefore runs *emulated* via Docker Desktop /
# Rosetta. That is correct for functional work (regenerating profiles, testing
# enforcement, running exploits) but timings are NOT trustworthy under emulation
# -- run the performance benchmarks on a native x86_64 Linux host (same image).
#
# Build:  docker build --platform=linux/amd64 -t fortwall-lab -f docker/Dockerfile .
# (compose sets the platform for you.)

FROM --platform=linux/amd64 debian:9

# Debian 9 "stretch" is EOL: its packages now live on archive.debian.org and the
# repo metadata is expired, so we point apt there and disable the Valid-Until
# check. Stretch is the PHP-7.1-era release whose libs (libmcrypt, old freetype)
# match Saphire's ./configure flags.
RUN set -eux; \
    printf '%s\n' \
      'deb http://archive.debian.org/debian stretch main contrib non-free' \
      'deb http://archive.debian.org/debian-security stretch/updates main' \
      > /etc/apt/sources.list; \
    printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/10no-check-valid; \
    apt-get -o Acquire::Check-Valid-Until=false update

# --- Toolchain + every -dev lib the run_stage1.sh ./configure line needs -------
# Flag -> package mapping is documented in docker/RUNBOOK.md.
RUN set -eux; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates curl wget git sudo procps pkg-config file less vim-tiny \
        build-essential autoconf automake libtool bison re2c \
        libxml2-dev libssl-dev libcurl4-openssl-dev libpcre3-dev \
        zlib1g-dev libbz2-dev libzip-dev \
        libjpeg-dev libpng-dev libfreetype6-dev \
        libmcrypt-dev libmhash-dev \
        libpq-dev default-libmysqlclient-dev \
        libxslt1-dev libicu-dev libgettextpo-dev \
        libc-client2007e-dev libkrb5-dev \
        golang-go python3 python3-pip \
        nginx mariadb-server mariadb-client; \
    rm -rf /var/lib/apt/lists/*

# Match Saphire's on-host layout: it runs as user "paper" with sudo, and the
# run_stage*.sh scripts reference ~/php-src, ~/stage1, ~/stage2, ~/stage3.
RUN useradd -m -s /bin/bash paper \
    && echo 'paper ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/paper

# --- PHP 7.1 source ------------------------------------------------------------
# Pinned to the last 7.1 release. Override with --build-arg PHP_REF=... to try a
# different tag. NOTE: bumping to PHP 8.x also requires porting the TE_xdebug and
# stage3 seccomp extensions to the new Zend ABI -- see RUNBOOK.md ("Latest PHP").
ARG PHP_REF=php-7.1.33
RUN set -eux; \
    git clone --depth 1 --branch "${PHP_REF}" https://github.com/php/php-src.git /home/paper/php-src; \
    chown -R paper:paper /home/paper/php-src

# --- Vendored Saphire sources (built at runtime by run_stage*.sh) --------------
# Copied to the exact ~/stageN paths the upstream scripts expect. Building the
# PHP/Go extensions is deferred to run_stage*.sh so they compile against the
# php-7.1 install produced by stage 1 (matching the original workflow).
COPY --chown=paper:paper saphire/stage1 /home/paper/stage1
COPY --chown=paper:paper saphire/stage2 /home/paper/stage2
COPY --chown=paper:paper saphire/stage3 /home/paper/stage3
COPY --chown=paper:paper saphire/run_stage1.sh saphire/run_stage2.sh saphire/run_stage3.sh /home/paper/
COPY --chown=paper:paper saphire/switch_to_wordpress.sh saphire/switch_to_phpmyadmin.sh \
     saphire/switch_to_drupal.sh saphire/switch_to_joomla.sh saphire/switch_to_magento.sh \
     saphire/switch_to_moodle.sh saphire/switch_to_prestashop.sh /home/paper/

# FortWall's own layer (the Python package + data contract) lives here too, so
# you can run `fortwall analyze/switch` against freshly generated stage2_out
# inside the same container.
COPY --chown=paper:paper fortwall /home/paper/fortwall
COPY --chown=paper:paper artifacts /home/paper/artifacts

COPY --chown=root:root docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER paper
WORKDIR /home/paper

# Enforcement (seccomp) and tracing (ptrace) both need kernel access; the
# container is granted the caps in docker-compose.yml. php-fpm listens on 9000,
# nginx on 80 (mapped to 8000 on the host to match the experiment harness URLs).
EXPOSE 80 9000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["bash"]
