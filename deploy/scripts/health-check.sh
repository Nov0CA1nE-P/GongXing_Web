#!/usr/bin/env bash

set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_server_confirmation "${1:-}"
require_root

if [[ -e "${MAINTENANCE_FILE}" ]] || ops_lock_is_held; then
    logger -t gongxing-health "health observation skipped during planned operation"
    exit 0
fi

if curl \
    --silent \
    --show-error \
    --fail \
    --max-time 5 \
    http://127.0.0.1:8000/api/health \
    >/dev/null; then
    logger -t gongxing-health "local HTTP health check passed"
    exit 0
fi

logger -p user.warning -t gongxing-health \
    "local HTTP health check failed; no automatic restart was attempted"
exit 1
