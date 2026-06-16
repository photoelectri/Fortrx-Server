#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: ./ops/restore.sh <snapshot-id>" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SNAPSHOT_ID="$1"

exec bash "$SCRIPT_DIR/host/restore-stack.sh" "$SNAPSHOT_ID"
