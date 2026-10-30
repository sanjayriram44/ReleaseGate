#!/usr/bin/env bash
# Nightly backup on the VM (CLAUDE.md §8), run as root by deploy/releasegate-backup.cron.
# Runs app/backup.py inside the api container: an online SQLite backup of /data/releasegate.db
# into /backups, keeping the newest 7. docker-compose.yml bind-mounts /backups from
# ${BACKUP_DIR:-./backups} (/opt/releasegate/backups on the VM), outside the data volume, so
# `docker compose down -v` keeps the copies.
set -euo pipefail

cd "$(dirname "$0")/.."
# The container runs as uid 10001 and writes into the bind mount.
install -d -m 0750 -o 10001 -g 10001 "${BACKUP_DIR:-./backups}"
docker compose exec -T api /srv/.venv/bin/python -m app.backup /data/releasegate.db /backups
