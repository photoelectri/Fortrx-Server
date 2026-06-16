#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="${FORTRX_ENV_FILE:-$APP_DIR/.env.runtime}"
DRY_RUN=false
ASSUME_YES=false

usage() {
  cat <<'EOF'
Usage: drain-stack.sh [--dry-run] [--yes]

  --dry-run   Report counts and matching backup snapshots without deleting data.
  --yes       Skip the interactive destructive confirmation for the real drain.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --yes)
      ASSUME_YES=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

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
POSTGRES_USER="${POSTGRES_USER:?Set POSTGRES_USER in .env.runtime}"
POSTGRES_DB="${POSTGRES_DB:?Set POSTGRES_DB in .env.runtime}"
S3_BUCKET_NAME="${S3_BUCKET_NAME:?Set S3_BUCKET_NAME in .env.runtime}"

compose=(docker compose --profile prod --env-file "$ENV_FILE")
TABLES=(
  users
  messages
  contacts
  key_bundles
  devices
  refresh_tokens
  pairing_codes
  action_tokens
  audit_log
)

say() {
  echo "==> $*"
}

run_psql() {
  "${compose[@]}" exec -T db psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@"
}

run_fortrx_python() {
  "${compose[@]}" run --rm --no-deps -T fortrx python - "$@"
}

wait_for_db() {
  for attempt in $(seq 1 24); do
    if "${compose[@]}" exec -T db pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null 2>&1; then
      return 0
    fi
    sleep 5
  done
  echo "Database did not become ready in time." >&2
  exit 1
}

ensure_core_services() {
  "${compose[@]}" up -d db redis minio
  wait_for_db
}

table_count() {
  local table="$1"
  run_psql -Atqc "SELECT COUNT(*) FROM \"$table\";"
}

redis_total_count() {
  local db_index="$1"
  "${compose[@]}" exec -T redis redis-cli -n "$db_index" DBSIZE | tr -d '\r'
}

redis_pattern_count() {
  local db_index="$1"
  local pattern="$2"
  "${compose[@]}" exec -T redis redis-cli -n "$db_index" --scan --pattern "$pattern" | wc -l | tr -d ' '
}

s3_message_object_count() {
  run_fortrx_python <<'PY'
from app.config import settings
from app.services.storage_service import get_s3_client

client = get_s3_client()
bucket = settings.S3_BUCKET_NAME
prefix = "messages/"
token = None
count = 0
while True:
    kwargs = {"Bucket": bucket, "Prefix": prefix}
    if token:
        kwargs["ContinuationToken"] = token
    response = client.list_objects_v2(**kwargs)
    count += len(response.get("Contents", []))
    if not response.get("IsTruncated"):
        break
    token = response.get("NextContinuationToken")
print(count)
PY
}

delete_s3_message_objects() {
  run_fortrx_python <<'PY'
from app.config import settings
from app.services.storage_service import get_s3_client

client = get_s3_client()
bucket = settings.S3_BUCKET_NAME
prefix = "messages/"
token = None

while True:
    kwargs = {"Bucket": bucket, "Prefix": prefix}
    if token:
        kwargs["ContinuationToken"] = token
    response = client.list_objects_v2(**kwargs)
    contents = response.get("Contents", [])
    if contents:
        objects = [{"Key": item["Key"]} for item in contents]
        client.delete_objects(Bucket=bucket, Delete={"Objects": objects, "Quiet": True})
    if not response.get("IsTruncated"):
        break
    token = response.get("NextContinuationToken")
print("deleted")
PY
}

snapshot_count_and_ids() {
  if ! restic snapshots --json >/dev/null 2>&1; then
    printf "0\n"
    return 0
  fi
  DEPLOY_ENV_VALUE="${DEPLOY_ENV:-prod}" restic snapshots --json | python3 - <<'PY'
import json
import os
import sys

deploy_env = os.environ.get("DEPLOY_ENV_VALUE", "prod")
snapshots = json.load(sys.stdin)
matched = []
for snapshot in snapshots:
    tags = snapshot.get("tags") or []
    if "fortrx" not in tags:
      continue
    if deploy_env and deploy_env not in tags:
      continue
    matched.append(snapshot["short_id"])

print(len(matched))
for item in matched:
    print(item)
PY
}

print_report() {
  say "PostgreSQL row counts"
  for table in "${TABLES[@]}"; do
    echo "  $table=$(table_count "$table")"
  done

  say "S3/MinIO message objects"
  echo "  bucket=$S3_BUCKET_NAME"
  echo "  prefix=messages/"
  echo "  objects=$(s3_message_object_count | tr -d '\r')"

  say "Redis key counts"
  echo "  db0_total=$(redis_total_count 0)"
  echo "  db0_presence=$(redis_pattern_count 0 'presence:*')"
  echo "  db0_device_last_seen=$(redis_pattern_count 0 'device:last_seen:*')"
  echo "  db0_user_events=$(redis_pattern_count 0 'user:*:events')"
  echo "  db1_total=$(redis_total_count 1)"

  say "Restic snapshot matches"
  local snapshot_report
  snapshot_report="$(snapshot_count_and_ids)"
  local snapshot_count
  snapshot_count="$(printf '%s\n' "$snapshot_report" | sed -n '1p')"
  echo "  matching_snapshots=$snapshot_count"
  if [[ "$snapshot_count" != "0" ]]; then
    printf '%s\n' "$snapshot_report" | tail -n +2 | sed 's/^/  snapshot_id=/'
  fi
}

confirm_drain() {
  cat <<'EOF'
Blast radius:
  - all accounts removed
  - all pending sealed-message blobs removed
  - all device/session/refresh state removed
  - all pairing/recovery/action token state removed
  - audit history removed
  - backup recovery path intentionally destroyed
EOF

  if [[ "$ASSUME_YES" == "true" ]]; then
    return 0
  fi

  printf "Type DRAIN-FORTRX to continue: "
  read -r confirmation
  if [[ "$confirmation" != "DRAIN-FORTRX" ]]; then
    echo "Confirmation did not match. Aborting." >&2
    exit 1
  fi
}

truncate_tables() {
  local quoted_tables
  quoted_tables=$(printf '"%s",' "${TABLES[@]}")
  quoted_tables="${quoted_tables%,}"
  run_psql -c "TRUNCATE TABLE ${quoted_tables} RESTART IDENTITY CASCADE;"
}

flush_redis() {
  "${compose[@]}" exec -T redis redis-cli -n 0 FLUSHDB >/dev/null
  "${compose[@]}" exec -T redis redis-cli -n 1 FLUSHDB >/dev/null
}

forget_matching_snapshots() {
  local snapshot_report
  snapshot_report="$(snapshot_count_and_ids)"
  local snapshot_count
  snapshot_count="$(printf '%s\n' "$snapshot_report" | sed -n '1p')"
  if [[ "$snapshot_count" == "0" ]]; then
    say "No matching restic snapshots to forget."
    return 0
  fi

  mapfile -t snapshot_ids < <(printf '%s\n' "$snapshot_report" | tail -n +2)
  restic forget "${snapshot_ids[@]}" --prune
}

verify_post_drain() {
  say "Verifying empty state after drain"
  for table in "${TABLES[@]}"; do
    local count
    count="$(table_count "$table")"
    echo "  $table=$count"
    if [[ "$count" != "0" ]]; then
      echo "Table $table is not empty after drain." >&2
      exit 1
    fi
  done

  local object_count
  object_count="$(s3_message_object_count | tr -d '\r')"
  echo "  message_objects=$object_count"
  if [[ "$object_count" != "0" ]]; then
    echo "Message objects remain in bucket after drain." >&2
    exit 1
  fi

  local redis0 redis1 snapshot_count
  redis0="$(redis_total_count 0)"
  redis1="$(redis_total_count 1)"
  echo "  redis_db0=$redis0"
  echo "  redis_db1=$redis1"
  if [[ "$redis0" != "0" || "$redis1" != "0" ]]; then
    echo "Redis still contains state after drain." >&2
    exit 1
  fi

  snapshot_count="$(snapshot_count_and_ids | sed -n '1p')"
  echo "  matching_snapshots=$snapshot_count"
  if [[ "$snapshot_count" != "0" ]]; then
    echo "Matching restic snapshots remain after drain." >&2
    exit 1
  fi
}

verify_healthz() {
  say "Verifying application health"
  "${compose[@]}" up -d --remove-orphans
  "${compose[@]}" exec -T fortrx python - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8000/healthz", timeout=10) as response:
    payload = json.loads(response.read().decode())
if payload.get("status") != "Fortrx is running":
    raise SystemExit("Unexpected healthz response")
print("healthz=ok")
PY
}

cd "$APP_DIR"
ensure_core_services
print_report

if [[ "$DRY_RUN" == "true" ]]; then
  say "Dry run complete. No data was changed."
  exit 0
fi

confirm_drain

say "Stopping ingress and application writes"
"${compose[@]}" stop caddy fortrx || true

say "Truncating PostgreSQL account-bearing tables"
truncate_tables

say "Deleting message objects from bucket prefix messages/"
delete_s3_message_objects >/dev/null

say "Flushing Redis presence, event, and rate-limit state"
flush_redis

say "Removing matching restic snapshots"
forget_matching_snapshots

verify_post_drain
verify_healthz
say "Drain complete."
