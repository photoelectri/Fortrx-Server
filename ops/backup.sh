#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_TAG="${1:-manual}"

exec bash "$SCRIPT_DIR/host/backup-stack.sh" "$BACKUP_TAG"
