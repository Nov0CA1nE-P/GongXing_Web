#!/usr/bin/env bash

set -Eeuo pipefail

readonly GONGXING_SERVICE="gongxing.service"
readonly OPS_LOCK_FILE="/run/lock/gongxing-ops.lock"
readonly MAINTENANCE_DIR="/run/gongxing"
readonly MAINTENANCE_FILE="${MAINTENANCE_DIR}/maintenance"
readonly DATA_DIR="/var/lib/gongxing/data"

require_root() {
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
