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
initial_deploy=0
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
        --initial-deploy)
            initial_deploy=1
            shift
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
if [[ "${initial_deploy}" -eq 1 && -n "${confirmed_backup}" ]]; then
    echo "error: --initial-deploy and --confirmed-backup are mutually exclusive" >&2
    exit 2
fi
if [[ "${initial_deploy}" -eq 0 ]]; then
    if [[ -z "${confirmed_backup}" ]]; then
        echo "error: subsequent deployments require --confirmed-backup" >&2
        exit 2
    fi
    if [[ ! "${confirmed_backup}" =~ ^[0-9a-f]{8,64}$ ]]; then
        echo "error: --confirmed-backup must be a verified restic snapshot ID" >&2
        exit 2
    fi
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

if [[ "${GONGXING_DEPLOY_TEST_MODE:-0}" == "1" ]]; then
    releases_root="${GONGXING_TEST_ROOT}/opt/gongxing/releases"
    current_link="${GONGXING_TEST_ROOT}/opt/gongxing/current"
else
    releases_root="/opt/gongxing/releases"
    current_link="/opt/gongxing/current"
fi
release_dir="${releases_root}/${release_id}"
temporary_release="${releases_root}/.${release_id}.new"
previous_target=""
was_active=0
switched=0

if [[ "${initial_deploy}" -eq 1 ]]; then
    if [[ -e "${current_link}" || -L "${current_link}" ]]; then
        echo "error: initial deployment requires no current release" >&2
        exit 1
    fi
    if service_is_active; then
        echo "error: initial deployment requires a stopped service" >&2
        exit 1
    fi
    if [[ -d "${releases_root}" ]] && \
       [[ -n "$(find "${releases_root}" -mindepth 1 -print -quit)" ]]; then
        echo "error: initial deployment requires an empty releases directory" >&2
        exit 1
    fi
    if [[ -L "${DATA_DIR}" ]]; then
        echo "error: initial deployment refuses a symlinked data directory" >&2
        exit 1
    fi
    if [[ -e "${DATA_DIR}/site.db" || -L "${DATA_DIR}/site.db" ]]; then
        echo "error: initial deployment requires no database" >&2
        exit 1
    fi
    if [[ -L "${DATA_DIR}/uploads" ]] || {
        [[ -d "${DATA_DIR}/uploads" ]] &&
        [[ -n "$(find "${DATA_DIR}/uploads" -mindepth 1 -print -quit)" ]]
    }; then
        echo "error: initial deployment requires an empty uploads directory" >&2
        exit 1
    fi
    if [[ -d "${DATA_DIR}" ]] && \
       [[ -n "$(
           find "${DATA_DIR}" -mindepth 1 \
               \( -type f -o -type l -o -type p -o -type s \) \
               -print -quit
       )" ]]; then
        echo "error: initial deployment refuses existing persistent data" >&2
        exit 1
    fi
fi

if [[ "${GONGXING_DEPLOY_TEST_MODE:-0}" == "1" ]]; then
    install -d -m 0750 "${releases_root}"
else
    install -d -m 0750 -o root -g gongxing "${releases_root}"
fi
if [[ -e "${release_dir}" || -L "${release_dir}" ]]; then
    echo "error: release already exists" >&2
    exit 1
fi

cleanup() {
    local original_exit=$?
    local final_exit="${original_exit}"
    local rollback_link_restored=1
    local rollback_service_stopped=1
    local maintenance_cleared=1

    trap - EXIT INT TERM HUP
    set +e

    # 第一阶段：主流程成功后，再确认新 release 达到最终服务状态。
    if [[ "${final_exit}" -eq 0 ]]; then
        if [[ "${initial_deploy}" -eq 1 ]]; then
            if ! service_is_active; then
                final_exit=1
                logger -p user.err -t gongxing-deploy \
                    "initial release exited before final validation"
            fi
        elif [[ "${was_active}" -eq 1 ]]; then
            if ! systemctl start "${GONGXING_SERVICE}" || ! service_is_active; then
                final_exit=1
                logger -p user.err -t gongxing-deploy \
                    "new release could not restore the pre-deploy running state"
            fi
        else
            if service_is_active; then
                systemctl stop "${GONGXING_SERVICE}" || true
            fi
            if service_is_active; then
                final_exit=1
                logger -p user.err -t gongxing-deploy \
                    "new release could not preserve the pre-deploy stopped state"
            fi
        fi
    fi

    # 第二阶段：服务状态成功后，解除维护并确认标记确实不存在。
    if [[ "${final_exit}" -eq 0 ]]; then
        if ! disable_maintenance; then
            maintenance_cleared=0
        fi
        if [[ -e "${MAINTENANCE_FILE}" || -L "${MAINTENANCE_FILE}" ]]; then
            maintenance_cleared=0
        fi
        if [[ "${maintenance_cleared}" -ne 1 ]]; then
            final_exit=1
            logger -p user.err -t gongxing-deploy \
                "maintenance mode could not be cleared after deployment"
            if [[ ! -e "${MAINTENANCE_FILE}" && ! -L "${MAINTENANCE_FILE}" ]]; then
                if ! enable_maintenance; then
                    logger -p user.err -t gongxing-deploy \
                        "maintenance mode could not be restored after clear failure"
                fi
            fi
        fi
    fi

    # 第三阶段：最终失败时统一停止新服务并回滚 current。
    if [[ "${final_exit}" -ne 0 && "${switched}" -eq 1 ]]; then
        systemctl stop "${GONGXING_SERVICE}" || true
        if service_is_active; then
            rollback_service_stopped=0
            logger -p user.err -t gongxing-deploy \
                "failed to stop the new release before rollback"
        fi
        if [[ "${initial_deploy}" -eq 1 ]]; then
            rm -f -- "${current_link}"
            if [[ -e "${current_link}" || -L "${current_link}" ]]; then
                rollback_link_restored=0
                logger -p user.err -t gongxing-deploy \
                    "failed to remove current after initial deployment failure"
            fi
        elif [[ -n "${previous_target}" ]]; then
            rm -f -- "${current_link}.rollback"
            if ! ln -s "${previous_target}" "${current_link}.rollback" || \
               ! mv -Tf "${current_link}.rollback" "${current_link}"; then
                rollback_link_restored=0
                rm -f -- "${current_link}.rollback" "${current_link}"
                logger -p user.err -t gongxing-deploy \
                    "failed to restore the previous release link"
            fi
        else
            rollback_link_restored=0
            rm -f -- "${current_link}"
            logger -p user.err -t gongxing-deploy \
                "no previous release link was available for rollback"
        fi
    fi

    # 第四阶段：失败后恢复部署前服务状态；成功时只记录完成。
    if [[ "${final_exit}" -ne 0 ]]; then
        if [[ "${initial_deploy}" -eq 1 ]]; then
            systemctl stop "${GONGXING_SERVICE}" || true
            if service_is_active; then
                logger -p user.err -t gongxing-deploy \
                    "initial deployment failed and the service could not be stopped"
            fi
        elif [[ "${was_active}" -eq 1 ]]; then
            if [[ "${rollback_service_stopped}" -ne 1 ]]; then
                systemctl stop "${GONGXING_SERVICE}" || true
                if ! service_is_active; then
                    rollback_service_stopped=1
                fi
            fi
            if [[ "${rollback_link_restored}" -ne 1 ]] || \
               [[ "${rollback_service_stopped}" -ne 1 ]] || \
               ! systemctl start "${GONGXING_SERVICE}" || \
               ! service_is_active; then
                logger -p user.err -t gongxing-deploy \
                    "previous release could not be restarted after rollback"
            fi
        else
            systemctl stop "${GONGXING_SERVICE}" || true
            if service_is_active; then
                logger -p user.err -t gongxing-deploy \
                    "pre-deploy stopped state could not be restored after rollback"
            fi
        fi
        logger -p user.warning -t gongxing-deploy \
            "deployment failed; maintenance mode remains enabled"
    else
        if [[ "${initial_deploy}" -eq 1 ]]; then
            logger -t gongxing-deploy \
                "initial release ${release_id} installed without pre-existing data"
        else
            logger -t gongxing-deploy \
                "release ${release_id} installed after a confirmed backup"
        fi
    fi
    if [[ -d "${temporary_release}" ]]; then
        rm -rf -- "${temporary_release}"
    fi
    exit "${final_exit}"
}
trap cleanup EXIT
trap 'exit 130' INT TERM HUP

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

if [[ "${GONGXING_DEPLOY_TEST_MODE:-0}" != "1" ]]; then
    chown -R root:gongxing "${temporary_release}"
fi
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
if [[ "${initial_deploy}" -eq 0 ]]; then
    systemctl stop "${GONGXING_SERVICE}"
fi
