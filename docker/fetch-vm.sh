#!/usr/bin/env bash
#
# Download the Saphire prebuilt VM (qcow2) from Google Drive.
#   Source: https://github.com/BUseclab/saphire  (file id below)
#   ~4 GB+ download; the qcow2's *virtual* size is larger -- see disk sizing in
#   RUNBOOK.md ("Native x86_64 Linux host"). Run this ON the Linux host.
#
# Usage: docker/fetch-vm.sh [output-path]   (default ./saphire.qcow2)
#
# Google Drive large-file downloads need a confirm-token dance; `gdown` handles
# it reliably, so we prefer it and fall back to curl only if gdown is absent.

set -euo pipefail

FILE_ID="1SZs3xss4ADnc6pb0uUJxjpfA2FCWvG1K"
OUT="${1:-saphire.qcow2}"

if [ -f "$OUT" ]; then
  echo ">> $OUT already exists ($(du -h "$OUT" | cut -f1)); skipping download."
  exit 0
fi

if command -v gdown >/dev/null 2>&1; then
  echo ">> downloading with gdown -> $OUT"
  gdown "$FILE_ID" -O "$OUT"
elif command -v pipx >/dev/null 2>&1; then
  echo ">> installing gdown via pipx"
  pipx install gdown && gdown "$FILE_ID" -O "$OUT"
elif command -v pip3 >/dev/null 2>&1; then
  echo ">> installing gdown via pip"
  pip3 install --user gdown
  "$(python3 -m site --user-base)/bin/gdown" "$FILE_ID" -O "$OUT"
else
  echo ">> gdown/pip unavailable; falling back to curl confirm-token flow"
  COOKIE="$(mktemp)"
  curl -sL -c "$COOKIE" "https://drive.google.com/uc?export=download&id=${FILE_ID}" -o /dev/null
  CONFIRM="$(awk '/download/{print $NF}' "$COOKIE" | tail -1)"
  curl -L -b "$COOKIE" \
    "https://drive.usercontent.google.com/download?id=${FILE_ID}&export=download&confirm=${CONFIRM:-t}" \
    -o "$OUT"
  rm -f "$COOKIE"
fi

echo ">> done: $OUT ($(du -h "$OUT" | cut -f1))"
echo "   verify it's a QEMU image:"
command -v qemu-img >/dev/null 2>&1 && qemu-img info "$OUT" | sed 's/^/     /' || \
  echo "   (install qemu-utils to run 'qemu-img info')"
