#!/usr/bin/env bash

set -Eeuo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
test_root="$(mktemp -d /tmp/gongxing-offsite-test-XXXXXXXX)"
trap 'rm -rf -- "${test_root}"' EXIT INT TERM HUP

export GONGXING_DEPLOY_TEST_MODE=1
export GONGXING_DEPLOY_TEST_ROOT="${test_root}"
# shellcheck source=../scripts/common.sh
source "${repo_root}/deploy/scripts/common.sh"

fail() { echo "offsite backup behavior test failed: $*" >&2; exit 1; }

expect_rejected() {
    local approval="$1" repository="$2"
    if (OFFSITE_BACKUP_APPROVED="${approval}" RESTIC_REPOSITORY="${repository}" \
        require_approved_offsite_repository) >/dev/null 2>&1; then
        fail "repository gate accepted approval=${approval}, repository=${repository}"
    fi
}

for approval in "" 0 true yes 01 2; do
    expect_rejected "${approval}" "s3:https://backup.example.invalid/bucket"
done
for repository in \
    relative/path ./relative ../parent /var/backups/gongxing \
    'C:\backup' file:/var/backups local:/var/backups \
    sftp:localhost:/backup sftp:127.0.0.1:/backup sftp:127.1:/backup \
    sftp:2130706433:/backup 'sftp:[::1]:/backup' \
    'sftp:[0:0:0:0:0:0:0:1]:/backup' \
    'sftp:[::ffff:7f00:1]:/backup'; do
    expect_rejected 1 "${repository}"
done

(OFFSITE_BACKUP_APPROVED=1 \
    RESTIC_REPOSITORY="s3:https://192.0.2.1/bucket" \
    require_approved_offsite_repository)
(OFFSITE_BACKUP_APPROVED=1 \
    RESTIC_REPOSITORY="sftp:user@198.51.100.2:/backup" \
    require_approved_offsite_repository)

printf 'offsite backup behavior tests: ok\n'
