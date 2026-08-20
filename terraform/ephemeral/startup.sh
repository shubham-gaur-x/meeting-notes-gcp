#!/usr/bin/env bash
# Memgraph VM bootstrap. Runs on every boot; idempotent throughout.
#
# Mirrors docker-compose.local.yml so local and deployed behave identically —
# the image tag is passed in from Terraform, which takes it from the same
# variable the local compose file pins (CLAUDE.md: MAGE procedure availability
# must not differ between environments).
set -euo pipefail

DATA_DEVICE="/dev/disk/by-id/google-memgraph-data"
MOUNT_POINT="/var/lib/memgraph"

# ─── Format the data disk on first boot only ─────────────────────────────────
# blkid returns non-zero on an unformatted device. Formatting an already-
# formatted disk would destroy a restored snapshot, so this check is critical.
if ! blkid "$${DATA_DEVICE}" >/dev/null 2>&1; then
  echo "Data disk is blank — formatting ext4."
  mkfs.ext4 -m 0 -F -E lazy_itable_init=0,lazy_journal_init=0,discard "$${DATA_DEVICE}"
else
  echo "Data disk already has a filesystem — leaving it alone."
fi

mkdir -p "$${MOUNT_POINT}"
if ! mountpoint -q "$${MOUNT_POINT}"; then
  mount -o discard,defaults "$${DATA_DEVICE}" "$${MOUNT_POINT}"
fi
grep -q "$${DATA_DEVICE}" /etc/fstab || \
  echo "$${DATA_DEVICE} $${MOUNT_POINT} ext4 discard,defaults,nofail 0 2" >> /etc/fstab

# Memgraph runs as uid 101 in the official image.
chown -R 101:101 "$${MOUNT_POINT}"

# ─── Docker ───────────────────────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
  apt-get update
  apt-get install -y ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg | \
    gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/debian $(. /etc/os-release && echo "$${VERSION_CODENAME}") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

systemctl enable --now docker

# ─── The stack ────────────────────────────────────────────────────────────────
mkdir -p /opt/memgraph
cat > /opt/memgraph/docker-compose.yml <<'COMPOSE'
services:
  memgraph:
    image: ${memgraph_image}
    container_name: memgraph
    restart: unless-stopped
    ports:
      - "7687:7687"
      - "7444:7444"
    volumes:
      - /var/lib/memgraph:/var/lib/memgraph
    command: ["--log-level=WARNING"]

  lab:
    image: memgraph/lab:3.11.0
    container_name: memgraph-lab
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      QUICK_CONNECT_MG_HOST: memgraph
      QUICK_CONNECT_MG_PORT: "7687"
    depends_on:
      - memgraph
COMPOSE

cd /opt/memgraph
docker compose up -d

echo "Memgraph bootstrap complete."
