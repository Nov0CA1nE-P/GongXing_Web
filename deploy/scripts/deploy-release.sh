#!/usr/bin/env bash

set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

require_server_confirmation "${1:-}"
require_root
shift

artifact_dir=""
release_id=""
confirmed_backup=""
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --artifact)
            artifact_dir="${2:-}"
            shift 2
            ;;
        --release)
            release_id="${2:-}"
            shift 2
            ;;
        --confirmed-backup)
            confirmed_backup="${2:-}"
            shift 2
            ;;
        *)
            echo "error: unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

if [[ ! "${release_id}" =~ ^[0-9a-f]{7,40}$ ]]; then
    echo "error: --release must be a Git commit ID" >&2
    exit 2
fi
if [[ -z "${confirmed_backup}" ]]; then
    echo "error: --confirmed-backup is required" >&2
    exit 2
fi
if [[ ! "${confirmed_backup}" =~ ^[0-9a-f]{8,64}$ ]]; then
    echo "error: --confirmed-backup must be a verified restic snapshot ID" >&2
    exit 2
fi
artifact_dir="$(realpath -- "${artifact_dir}")"
if [[ ! -d "${artifact_dir}/backend" || ! -d "${artifact_dir}/frontend/dist" ]]; then
    echo "error: artifact is missing backend or frontend/dist" >&2
    exit 2
fi
if [[ ! -f "${artifact_dir}/backend/requirements.lock" ]]; then
    echo "error: artifact is missing backend/requirements.lock" >&2
    exit 2
fi
if [[ -e "${artifact_dir}/data" || -e "${artifact_dir}/.env" ]]; then
    echo "error: artifact must not contain data or .env" >&2
    exit 2
fi

acquire_ops_lock
assert_no_recovery_holds

releases_root="/opt/gongxing/releases"
release_dir="${releases_root}/${release_id}"
temporary_release="${releases_root}/.${release_id}.new"
current_link="/opt/gongxing/current"
previous_target=""
was_active=0
switched=0

install -d -m 0750 -o root -g gongxing "${releases_root}"
if [[ -e "${release_dir}" || -L "${release_dir}" ]]; then
    echo "error: release already exists" >&2
    exit 1
fi

cleanup() {
    local exit_code=$?
    local service_restored=1
    if [[ "${exit_code}" -ne 0 && "${switched}" -eq 1 ]]; then
        systemctl stop "${GONGXING_SERVICE}" || true
        if [[ -n "${previous_target}" ]]; then
            ln -sfn "${previous_target}" "${current_link}.rollback"
            mv -Tf "${current_link}.rollback" "${current_link}"
        else
            rm -f -- "${current_link}"
        fi
    fi
    if [[ "${was_active}" -eq 1 ]]; then
        if ! systemctl start "${GONGXING_SERVICE}"; then
            exit_code=1
            service_restored=0
            logger -p user.err -t gongxing-deploy \
                "service restore failed; maintenance mode remains enabled"
        fi
    fi
    if [[ "${exit_code}" -eq 0 && "${service_restored}" -eq 1 ]]; then
        disable_maintenance
    else
        logger -p user.warning -t gongxing-deploy \
            "deployment did not complete cleanly; maintenance mode remains enabled"
    fi
    if [[ -d "${temporary_release}" ]]; then
        rm -rf -- "${temporary_release}"
    fi
    exit "${exit_code}"
}
trap cleanup EXIT INT TERM HUP

if service_is_active; then
    was_active=1
fi
if [[ -L "${current_link}" ]]; then
    previous_target="$(readlink -f -- "${current_link}")"
fi

enable_maintenance
if [[ "${was_active}" -eq 1 ]]; then
    systemctl stop "${GONGXING_SERVICE}"
fi

install -d -m 0750 "${temporary_release}"
cp -a -- "${artifact_dir}/." "${temporary_release}/"
ln -s "${DATA_DIR}" "${temporary_release}/data"
printf '%s\n' "${release_id}" >"${temporary_release}/RELEASE_GIT_SHA"

python3.12 -m venv "${temporary_release}/.venv"
"${temporary_release}/.venv/bin/python" -m pip install \
    --require-hashes \
    --requirement "${temporary_release}/backend/requirements.lock"

chown -R root:gongxing "${temporary_release}"
find "${temporary_release}" -type d -exec chmod 0750 {} +
find "${temporary_release}" -type f -exec chmod 0640 {} +
find "${temporary_release}/.venv/bin" -type f -exec chmod 0750 {} +
chmod 0755 "${temporary_release}"
find "${temporary_release}/frontend" -type d -exec chmod 0755 {} +
find "${temporary_release}/frontend" -type f -exec chmod 0644 {} +
mv -- "${temporary_release}" "${release_dir}"

ln -s "${release_dir}" "${current_link}.next"
mv -Tf "${current_link}.next" "${current_link}"
switched=1

systemctl start "${GONGXING_SERVICE}"
curl --silent --show-error --fail --max-time 10 \
    http://127.0.0.1:8000/api/health >/dev/null
systemctl stop "${GONGXING_SERVICE}"

logger -t gongxing-deploy \
    "release ${release_id} installed after confirmed backup ${confirmed_backup}"
