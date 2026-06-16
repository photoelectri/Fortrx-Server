#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:?Usage: install-cron.sh /srv/fortrx}"
CRON_LINE="0 3 * * * cd $APP_DIR && $APP_DIR/ops/host/backup-stack.sh nightly >> /var/log/fortrx-backup.log 2>&1"

{
  crontab -l 2>/dev/null | grep -v 'fortrx-backup.log' || true
  echo "$CRON_LINE"
} | crontab -

echo "Installed nightly backup cron for $APP_DIR"
