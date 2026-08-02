#!/usr/bin/env bash

set -Eeuo pipefail

readonly GONGXING_SERVICE="gongxing.service"

if [[ "${GONGXING_DEPLOY_TEST_MODE:-0}" == "1" ]]; then
    readonly GONGXING_TEST_ROOT="${GONGXING_DEPLOY_TEST_ROOT:?test root is required}"
    case "${GONGXING_TEST_ROOT}" in
        /tmp/*) ;;
        *)
            echo "error: deployment test root must be below /tmp" >&2
            exit 2
            ;;
    esac
    readonly OPS_LOCK_FILE="${GONGXING_TEST_ROOT}/run/lock/gongxing-ops.lock"
    readonly MAINTENANCE_DIR="${GONGXING_TEST_ROOT}/run/gongxing"
    readonly DATA_DIR="${GONGXING_TEST_ROOT}/var/lib/gongxing/data"
else
    readonly OPS_LOCK_FILE="/run/lock/gongxing-ops.lock"
    readonly MAINTENANCE_DIR="/run/gongxing"
    readonly DATA_DIR="/var/lib/gongxing/data"
fi

readonly MAINTENANCE_FILE="${MAINTENANCE_DIR}/maintenance"

require_root() {
    if [[ "${GONGXING_DEPLOY_TEST_MODE:-0}" == "1" ]]; then
        return
    fi
    if [[ "${EUID}" -ne 0 ]]; then
        echo "error: this operation must run as root" >&2
        exit 1
    fi
}

require_server_confirmation() {
    if [[ "${1:-}" != "--confirm-server" ]]; then
        echo "error: refusing to run without --confirm-server" >&2
        exit 2
    fi
}

acquire_ops_lock() {
    install -d -m 0755 "$(dirname "${OPS_LOCK_FILE}")"
    exec 9>"${OPS_LOCK_FILE}"
    if ! flock -n 9; then
        echo "error: another deploy, backup, or restore operation is active" >&2
        exit 75
    fi
}

ops_lock_is_held() {
    install -d -m 0755 "$(dirname "${OPS_LOCK_FILE}")"
    exec 8>"${OPS_LOCK_FILE}"
    if flock -n 8; then
        flock -u 8
        return 1
    fi
    return 0
}

assert_no_recovery_holds() {
    local hold_file
    hold_file="$(
        find "${DATA_DIR}" -type f -name '.recover-*.hold' -print -quit \
            2>/dev/null || true
    )"
    if [[ -n "${hold_file}" ]]; then
        echo "error: a recovery hold exists; manual handling is required" >&2
        logger -t gongxing-ops \
            "blocked because a .recover-*.hold file requires manual review"
        exit 65
    fi
}

enable_maintenance() {
    install -d -m 0755 "${MAINTENANCE_DIR}"
    install -m 0644 /dev/null "${MAINTENANCE_FILE}"
}

disable_maintenance() {
    rm -f -- "${MAINTENANCE_FILE}"
}

service_is_active() {
    systemctl is-active --quiet "${GONGXING_SERVICE}"
}

require_approved_offsite_repository() {
    if [[ "${OFFSITE_BACKUP_APPROVED:-}" != "1" ]]; then
        echo "error: offsite backup has not been explicitly approved" >&2
        exit 78
    fi
    : "${RESTIC_REPOSITORY:?RESTIC_REPOSITORY is required}"
    python3 - "${RESTIC_REPOSITORY}" <<'PY'
import re
import sys

repository = sys.argv[1]
lowered = repository.lower()
if repository != repository.strip() or not repository:
    raise SystemExit("error: restic repository is malformed")
if repository.startswith(("/", "./", "../", "~", "\\")):
    raise SystemExit("error: local restic repositories are forbidden")
if re.match(r"^[a-zA-Z]:[\\/]", repository):
    raise SystemExit("error: local restic repositories are forbidden")
if ":" not in repository or lowered.startswith(("file:", "local:")):
    raise SystemExit("error: an approved remote restic repository is required")
if re.search(r"(^|[^a-z0-9])localhost([^a-z0-9]|$)", lowered):
    raise SystemExit("error: loopback restic repositories are forbidden")
if re.search(r"(^|[^0-9])127(?:\.[0-9]{1,3}){3}([^0-9]|$)", lowered):
    raise SystemExit("error: loopback restic repositories are forbidden")
if "::1" in lowered:
    raise SystemExit("error: loopback restic repositories are forbidden")
PY
}
