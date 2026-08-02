#!/usr/bin/env bash

set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

readonly HEALTH_WAIT_BUDGET_SECONDS=30
readonly HEALTH_CONNECT_TIMEOUT_SECONDS=1
readonly HEALTH_REQUEST_TIMEOUT_SECONDS=1
readonly HEALTH_RETRY_INTERVAL_SECONDS=1
readonly HEALTH_MAX_ATTEMPTS=$((
    HEALTH_WAIT_BUDGET_SECONDS /
    (HEALTH_REQUEST_TIMEOUT_SECONDS + HEALTH_RETRY_INTERVAL_SECONDS)
))

wait_for_application_health() {
    local attempt
    for ((attempt = 1; attempt <= HEALTH_MAX_ATTEMPTS; attempt++)); do
        if ! service_is_active; then
            logger -p user.err -t gongxing-deploy \
                "application service exited before becoming healthy"
            return 1
        fi
        if curl --silent --show-error --fail \
            --connect-timeout "${HEALTH_CONNECT_TIMEOUT_SECONDS}" \
            --max-time "${HEALTH_REQUEST_TIMEOUT_SECONDS}" \
            http://127.0.0.1:8000/api/health >/dev/null; then
            return 0
        fi
        if [[ "${attempt}" -lt "${HEALTH_MAX_ATTEMPTS}" ]]; then
            sleep "${HEALTH_RETRY_INTERVAL_SECONDS}"
        fi
    done
    logger -p user.err -t gongxing-deploy \
        "application health did not become ready within the fixed wait budget"
    return 1
}

require_server_confirmation "${1:-}"
require_root
shift

artifact_dir=""
artifact_manifest=""
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
        --artifact-manifest)
            artifact_manifest="${2:-}"
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
artifact_manifest="$(realpath -- "${artifact_manifest}")"
if [[ ! -d "${artifact_dir}/backend" || ! -d "${artifact_dir}/frontend/dist" ]]; then
    echo "error: artifact is missing backend or frontend/dist" >&2
    exit 2
fi
if [[ ! -f "${artifact_dir}/backend/requirements.lock" ]]; then
    echo "error: artifact is missing backend/requirements.lock" >&2
    exit 2
fi
if [[ ! -d "${artifact_dir}/wheelhouse" || \
      ! -f "${artifact_dir}/WHEELHOUSE_SHA256SUMS" || \
      ! -f "${artifact_manifest}" ]]; then
    echo "error: artifact is missing its offline wheelhouse or integrity manifest" >&2
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
    environment_file="${GONGXING_TEST_ROOT}/etc/gongxing/gongxing.env"
else
    releases_root="/opt/gongxing/releases"
    current_link="/opt/gongxing/current"
    environment_file="/etc/gongxing/gongxing.env"
fi
release_dir="${releases_root}/${release_id}"
temporary_release="${releases_root}/.${release_id}.new"
previous_target=""
was_active=0
switched=0
transaction_started=0

cleanup_failed_release() {
    local current_target=""
    local failed_release_real=""
    local releases_root_real=""

    if [[ "${release_dir}" != "${releases_root}/${release_id}" ]]; then
        logger -p user.err -t gongxing-deploy \
            "refusing to clean a failed release with an unexpected path"
        return 1
    fi
    if [[ ! -d "${releases_root}" || -L "${releases_root}" ]]; then
        logger -p user.err -t gongxing-deploy \
            "refusing to clean a failed release below an unsafe root"
        return 1
    fi
    if [[ ! -e "${release_dir}" && ! -L "${release_dir}" ]]; then
        return 0
    fi
    if [[ ! -d "${release_dir}" || -L "${release_dir}" ]]; then
        logger -p user.err -t gongxing-deploy \
            "refusing to clean a failed release that is not a directory"
        return 1
    fi

    releases_root_real="$(realpath -e -- "${releases_root}")" || return 1
    failed_release_real="$(realpath -e -- "${release_dir}")" || return 1
    if [[ "$(dirname -- "${failed_release_real}")" != "${releases_root_real}" ]]; then
        logger -p user.err -t gongxing-deploy \
            "refusing to clean a failed release outside the releases root"
        return 1
    fi
    if [[ -L "${current_link}" ]]; then
        current_target="$(readlink -f -- "${current_link}" 2>/dev/null || true)"
    fi
    if [[ -n "${current_target}" && "${failed_release_real}" == "${current_target}" ]]; then
        logger -p user.err -t gongxing-deploy \
            "refusing to clean the release selected by current"
        return 1
    fi
    if [[ -n "${previous_target}" && "${failed_release_real}" == "${previous_target}" ]]; then
        logger -p user.err -t gongxing-deploy \
            "refusing to clean the previous release"
        return 1
    fi

    rm -rf -- "${release_dir}"
    if [[ -e "${release_dir}" || -L "${release_dir}" ]]; then
        logger -p user.err -t gongxing-deploy \
            "failed release cleanup did not complete"
        return 1
    fi
}

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

    # 预检查失败发生在维护和服务切换之前，不得影响现有服务或 current。
    if [[ "${transaction_started}" -eq 0 ]]; then
        if [[ -d "${temporary_release}" ]]; then
            rm -rf -- "${temporary_release}"
        fi
        exit "${final_exit}"
    fi

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
        if ! cleanup_failed_release; then
            logger -p user.err -t gongxing-deploy \
                "failed release cleanup requires manual review"
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

# 所有耗时和可失败的发布预检查都在旧服务仍正常运行时完成。
integrity_owner_args=()
if [[ "${GONGXING_DEPLOY_TEST_MODE:-0}" != "1" ]]; then
    integrity_owner_args+=(--require-root-owner)
fi
python3.12 "${SCRIPT_DIR}/release_integrity.py" verify \
    --directory "${artifact_dir}" \
    --manifest "${artifact_manifest}" \
    --release "${release_id}" \
    "${integrity_owner_args[@]}"
install -d -m 0750 "${temporary_release}"
cp -a -- "${artifact_dir}/." "${temporary_release}/"
python3.12 "${SCRIPT_DIR}/release_integrity.py" verify \
    --directory "${temporary_release}" \
    --manifest "${artifact_manifest}" \
    --release "${release_id}" \
    "${integrity_owner_args[@]}"
ln -s "${DATA_DIR}" "${temporary_release}/data"
printf '%s\n' "${release_id}" >"${temporary_release}/RELEASE_GIT_SHA"

python3.12 -m venv "${temporary_release}/.venv"
"${temporary_release}/.venv/bin/python" -m pip install \
    --no-index \
    --find-links "${temporary_release}/wheelhouse" \
    --require-hashes \
    --requirement "${temporary_release}/backend/requirements.lock"
"${temporary_release}/.venv/bin/python" \
    "${SCRIPT_DIR}/validate-production-config.py" \
    --env-file "${environment_file}" \
    --release-dir "${temporary_release}"

if [[ "${GONGXING_DEPLOY_TEST_MODE:-0}" != "1" ]]; then
    chown -R root:gongxing "${temporary_release}"
fi
find "${temporary_release}" -type d -exec chmod 0750 {} +
find "${temporary_release}" -type f -exec chmod 0640 {} +
find "${temporary_release}/.venv/bin" -type f -exec chmod 0750 {} +
chmod 0755 "${temporary_release}"
find "${temporary_release}/frontend" -type d -exec chmod 0755 {} +
find "${temporary_release}/frontend" -type f -exec chmod 0644 {} +

if service_is_active; then
    was_active=1
fi
if [[ -L "${current_link}" ]]; then
    previous_target="$(readlink -f -- "${current_link}")"
fi
transaction_started=1
enable_maintenance
if [[ "${was_active}" -eq 1 ]]; then
    systemctl stop "${GONGXING_SERVICE}"
fi
mv -- "${temporary_release}" "${release_dir}"

ln -s "${release_dir}" "${current_link}.next"
mv -Tf "${current_link}.next" "${current_link}"
switched=1

systemctl start "${GONGXING_SERVICE}"
wait_for_application_health
if [[ "${initial_deploy}" -eq 0 ]]; then
    systemctl stop "${GONGXING_SERVICE}"
fi
