#!/bin/bash
# Compute Engine startup script: runs as root on every boot of the ReleaseGate VM.
# Installs Docker once, clones the repo once, then (re)starts the compose stack.
# Data lives in the compose named volume, so reboots and rebuilds keep it.
set -euxo pipefail

meta() {
  curl -fs -H "Metadata-Flavor: Google" \
    "http://metadata.google.internal/computeMetadata/v1/instance/attributes/$1" || echo "$2"
}

if ! command -v docker >/dev/null; then
  apt-get update
  apt-get install -y ca-certificates curl git
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc]" \
    "https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
fi

APP=/opt/releasegate
if [ ! -d "$APP/.git" ]; then
  git clone --branch "$(meta repo-branch main)" "$(meta repo-url https://github.com/sanjayriram44/ReleaseGate.git)" "$APP"
fi

cd "$APP"
# Evaluation deployment: synthetic data only, so the shared test endpoints are on.
printf 'ENABLE_TEST_ENDPOINTS=%s\nPORT=8080\n' "$(meta enable-test-endpoints true)" > .env
docker compose up -d --build
