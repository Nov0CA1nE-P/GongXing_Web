#!/usr/bin/env bash

set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_server_confirmation "${1:-}"
require_root
snapshot_id="${2:-latest}"

: "${RESTIC_PASSWORD_FILE:?RESTIC_PASSWORD_FILE is required}"
require_approved_offsite_repository

acquire_ops_lock
assert_no_recovery_holds

restore_root="/var/lib/gongxing/restore-drill"
restore_target="${restore_root}/${snapshot_id}-$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 0700 "${restore_target}"

cleanup() {
    disable_maintenance
}
trap cleanup EXIT INT TERM HUP

enable_maintenance
restic restore "${snapshot_id}" --target "${restore_target}"

mapfile -t manifests < <(find "${restore_target}" -type f -name manifest.json)
if [[ "${#manifests[@]}" -ne 1 ]]; then
    echo "error: expected exactly one restored manifest" >&2
    exit 1
fi

snapshot_dir="$(dirname -- "${manifests[0]}")"
python3.12 "${SCRIPT_DIR}/verify_snapshot.py" \
    --snapshot-dir "${snapshot_dir}"

logger -t gongxing-restore \
    "isolated restore drill verified; manual review and cleanup are required"
printf 'verified restore directory: %s\n' "${snapshot_dir}"
