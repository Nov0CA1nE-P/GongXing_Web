#!/usr/bin/env bash

set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PYTHON_BIN="${GONGXING_PYTHON_BIN:-python3.12}"

if [[ "$#" -ne 8 ]]; then
    echo "usage: verify-release-package.sh --archive PATH --checksum PATH --release SHA --output DIR" >&2
    exit 2
fi
if [[ "${1:-}" != "--archive" || "${3:-}" != "--checksum" || \
      "${5:-}" != "--release" || "${7:-}" != "--output" ]]; then
    echo "error: invalid arguments" >&2
    exit 2
fi
if [[ "${EUID}" -ne 0 && "${GONGXING_DEPLOY_TEST_MODE:-0}" != "1" ]]; then
    echo "error: release verification must run as root" >&2
    exit 1
fi

output_dir="$8"
integrity_manifest="${output_dir}.integrity.json"
owner_args=()
if [[ "${GONGXING_DEPLOY_TEST_MODE:-0}" == "1" ]]; then
    owner_args+=(--allow-test-owner)
fi
"${PYTHON_BIN}" "${SCRIPT_DIR}/verify_release_archive.py" \
    --archive "$2" \
    --checksum "$4" \
    --release "$6" \
    --output-dir "${output_dir}" \
    --integrity-manifest "${integrity_manifest}" \
    "${owner_args[@]}"
if [[ "${GONGXING_DEPLOY_TEST_MODE:-0}" != "1" ]]; then
    chown -R root:root "${output_dir}" "${integrity_manifest}"
fi
chmod 0750 "${output_dir}"
find "${output_dir}" -type d -exec chmod 0750 {} +
find "${output_dir}" -type f -exec chmod 0640 {} +
chmod 0600 "${integrity_manifest}"
printf 'verified release directory: %s\n' "${output_dir}"
printf 'integrity manifest: %s\n' "${integrity_manifest}"
