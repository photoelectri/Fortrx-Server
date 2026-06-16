#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: restore-stack.sh <snapshot-id>" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
SNAPSHOT_ID="$1"
ENV_FILE="${FORTRX_ENV_FILE:-$APP_DIR/.env.runtime}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source "$ENV_FILE"
set +a

RESTIC_REPOSITORY="${RESTIC_REPOSITORY:?Set RESTIC_REPOSITORY in .env.runtime}"
RESTIC_PASSWORD="${RESTIC_PASSWORD:?Set RESTIC_PASSWORD in .env.runtime}"
MINIO_VOLUME="${COMPOSE_PROJECT_NAME:-fortrx}_minio_data"
RESTORE_DIR="$(mktemp -d)"
trap 'rm -rf "$RESTORE_DIR"' EXIT

cd "$APP_DIR"

compose=(docker compose --profile prod --env-file "$ENV_FILE")

restic restore "$SNAPSHOT_ID" --target "$RESTORE_DIR"

metadata_path="$(find "$RESTORE_DIR" -type f -name metadata.txt -print -quit)"
if [[ -z "${metadata_path:-}" ]]; then
  echo "Snapshot does not contain metadata.txt." >&2
  exit 1
fi
restore_root="$(dirname "$metadata_path")"

if [[ -z "${restore_root:-}" || ! -f "$restore_root/postgres.sql" || ! -f "$restore_root/minio-data.tar.gz" ]]; then
  echo "Snapshot does not contain the expected backup files." >&2
  exit 1
fi

"${compose[@]}" up -d db redis minio
"${compose[@]}" stop fortrx minio || true

for attempt in $(seq 1 24); do
  if "${compose[@]}" exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
    break
  fi
  sleep 5
done

"${compose[@]}" exec -T db dropdb --if-exists -U "$POSTGRES_USER" "$POSTGRES_DB"
"${compose[@]}" exec -T db createdb -U "$POSTGRES_USER" "$POSTGRES_DB"
cat "$restore_root/postgres.sql" | "${compose[@]}" exec -T db psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"

docker run --rm \
  -v "$MINIO_VOLUME:/target" \
  -v "$restore_root:/restore:ro" \
  alpine:3.20 \
  sh -c "rm -rf /target/* /target/.[!.]* /target/..?* 2>/dev/null || true && tar xzf /restore/minio-data.tar.gz -C /target"

"${compose[@]}" up -d --remove-orphans
