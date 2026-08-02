#!/usr/bin/env bash

set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_server_confirmation "${1:-}"
require_root
acquire_ops_lock
assert_no_recovery_holds

: "${RESTIC_PASSWORD_FILE:?RESTIC_PASSWORD_FILE is required}"
require_approved_offsite_repository

readonly DATABASE_PATH="/var/lib/gongxing/data/site.db"
readonly UPLOADS_DIR="/var/lib/gongxing/data/uploads"
readonly BACKEND_DIR="/opt/gongxing/current/backend"
readonly PYTHON_BIN="/opt/gongxing/current/.venv/bin/python"
readonly BACKUP_ROOT="/var/backups/gongxing"

install -d -m 0700 "${BACKUP_ROOT}"
staging_parent="$(mktemp -d "${BACKUP_ROOT}/.backup-XXXXXXXX")"
snapshot_dir="${staging_parent}/snapshot"
was_active=0

cleanup() {
    local exit_code=$?
    local service_restored=1
    if [[ "${was_active}" -eq 1 ]]; then
        if ! systemctl start "${GONGXING_SERVICE}"; then
            exit_code=1
            service_restored=0
            logger -p user.err -t gongxing-backup \
                "service restore failed; maintenance mode remains enabled"
        fi
    fi
    if [[ "${service_restored}" -eq 1 ]]; then
        disable_maintenance
    fi
    rm -rf -- "${staging_parent}"
    exit "${exit_code}"
}
trap cleanup EXIT INT TERM HUP

if service_is_active; then
    was_active=1
fi

enable_maintenance
if [[ "${was_active}" -eq 1 ]]; then
    systemctl stop "${GONGXING_SERVICE}"
fi

"${PYTHON_BIN}" "${SCRIPT_DIR}/backup_snapshot.py" \
    --database "${DATABASE_PATH}" \
    --uploads-dir "${UPLOADS_DIR}" \
    --backend-dir "${BACKEND_DIR}" \
    --output-dir "${snapshot_dir}"

(
    cd "${snapshot_dir}"
    release_id="$(
        head -n 1 /opt/gongxing/current/RELEASE_GIT_SHA 2>/dev/null \
            || echo unknown
    )"
    restic backup . \
        --tag gongxing \
        --tag "git-${release_id}"
)

restic forget \
    --keep-daily 7 \
    --keep-weekly 4 \
    --keep-monthly 3 \
    --dry-run

if [[ "${RESTIC_PRUNE_ENABLED:-0}" == "1" ]]; then
    restic forget \
        --keep-daily 7 \
        --keep-weekly 4 \
        --keep-monthly 3 \
        --prune
fi

logger -t gongxing-backup "consistent encrypted backup completed"
