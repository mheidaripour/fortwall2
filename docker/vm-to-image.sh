#!/usr/bin/env bash
#
# Convert the Saphire VM disk image into a Docker image (`saphire-vm:orig`) that
# reproduces the known-good environment exactly -- no from-scratch rebuild.
#
# A container reuses the host kernel, so we only need the VM's ROOT FILESYSTEM,
# not its kernel/bootloader. This script:
#   1. converts the disk (qcow2/vmdk/vdi/ova) to raw with qemu-img (on the host),
#   2. loop-mounts it read-only inside a throwaway *privileged* Linux container
#      (handles plain partitions and LVM), picks the root partition,
#   3. tars that rootfs and `docker import`s it as saphire-vm:orig.
#
# Then Dockerfile.vm (FROM saphire-vm:orig) adds the entrypoint/ports, and the
# existing docker-compose.yml grants SYS_PTRACE + seccomp=unconfined.
#
# Usage:
#   docker/vm-to-image.sh /path/to/saphire.qcow2 [output-image-tag]
#
# Requirements: qemu-img (e.g. `brew install qemu` or `apt install qemu-utils`) and a running
# Docker daemon. Needs free disk ~= the VM's *virtual* size for the raw copy.

set -euo pipefail

DISK="${1:?usage: vm-to-image.sh <disk-image> [tag]}"
TAG="${2:-saphire-vm:orig}"
[ -f "$DISK" ] || { echo "!! not a file: $DISK" >&2; exit 1; }

WORK="$(cd "$(dirname "$DISK")" && pwd)/.saphire-extract"
mkdir -p "$WORK"
RAW="$WORK/disk.raw"
SRC="$DISK"

echo ">> qemu-img info:"; qemu-img info "$DISK" | sed 's/^/     /'

# OVA is a tar of an OVF + vmdk(s): unpack and grab the first disk.
case "$DISK" in
  *.ova|*.OVA)
    echo ">> OVA detected, extracting embedded disk..."
    tar -xvf "$DISK" -C "$WORK"
    SRC="$(find "$WORK" -maxdepth 1 \( -iname '*.vmdk' -o -iname '*.qcow2' -o -iname '*.img' \) | head -1)"
    [ -n "$SRC" ] || { echo "!! no disk found inside OVA" >&2; exit 1; }
    echo "   using $SRC"
    ;;
esac

echo ">> converting to raw (this can take a while + needs space)..."
qemu-img convert -p -O raw "$SRC" "$RAW"

echo ">> extracting rootfs inside a privileged Linux helper container..."
# Everything below runs in linux/amd64 Debian with the work dir bind-mounted.
docker run --rm --privileged --platform=linux/amd64 \
  -v "$WORK":/work -w /work debian:11 bash -euxc '
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq kpartx lvm2 file e2fsprogs util-linux >/dev/null

    file disk.raw

    # Map partitions (device-mapper is more reliable than losetup -P here).
    kpartx -av disk.raw || true
    sleep 1
    ls -l /dev/mapper || true

    # Activate any LVM volume groups the image may use.
    vgscan --mknodes || true
    vgchange -ay || true

    pick_and_mount() {
      mkdir -p /mnt/root
      # Candidate block devices: kpartx mappings, LVM LVs, or the whole disk.
      for dev in /dev/mapper/loop*p* /dev/mapper/*-* /dev/loop0 disk.raw; do
        [ -e "$dev" ] || continue
        blkid "$dev" >/dev/null 2>&1 || continue
        # Try mounting read-only; a real rootfs has /etc and /bin (or /usr/bin).
        if mount -o ro "$dev" /mnt/root 2>/dev/null; then
          if [ -d /mnt/root/etc ] && { [ -d /mnt/root/bin ] || [ -d /mnt/root/usr/bin ]; }; then
            echo "   root filesystem = $dev"
            return 0
          fi
          umount /mnt/root 2>/dev/null || true
        fi
      done
      return 1
    }

    if ! pick_and_mount; then
      echo "!! could not locate the root partition automatically." >&2
      echo "   Inspect manually: kpartx -av /work/disk.raw ; lsblk ; blkid" >&2
      exit 2
    fi

    echo "   /etc/os-release:"; cat /mnt/root/etc/os-release 2>/dev/null | sed "s/^/     /" || true

    echo ">> taring rootfs -> /work/saphire-rootfs.tar.gz"
    tar -czf /work/saphire-rootfs.tar.gz --numeric-owner \
        --one-file-system \
        --exclude=./proc/* --exclude=./sys/* --exclude=./dev/* \
        --exclude=./run/* --exclude=./tmp/* \
        -C /mnt/root .

    umount /mnt/root || true
    kpartx -d disk.raw || true
  '

echo ">> docker import -> $TAG"
docker import \
  --change 'ENV PATH=/opt/php-7.1/bin:/opt/php-7.1/sbin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' \
  --change 'WORKDIR /home/paper' \
  --change 'CMD ["bash"]' \
  "$WORK/saphire-rootfs.tar.gz" "$TAG"

echo
echo "== done. imported image: $TAG =="
docker image inspect "$TAG" --format '   arch={{.Architecture}} os={{.Os}} size={{.Size}} bytes'
echo
echo "Next:"
echo "  1. Build the thin wrapper:   docker build --platform=linux/amd64 -t fortwall-lab -f docker/Dockerfile.vm ."
echo "  2. Or point compose at it (set 'image: saphire-vm:orig' + build dockerfile: docker/Dockerfile.vm)"
echo "  3. docker compose up -d && docker compose exec lab bash"
echo
echo "Cleanup the raw copy when satisfied:  rm -rf \"$WORK\""
