#!/usr/bin/env bash

set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
deploy_script="${repo_root}/deploy/scripts/deploy-release.sh"
test_parent="$(mktemp -d /tmp/gongxing-deploy-test-XXXXXXXX)"

cleanup() {
    rm -rf -- "${test_parent}"
}
trap cleanup EXIT INT TERM HUP

fail() {
    echo "deploy behavior test failed: $*" >&2
    exit 1
}

assert_eq() {
    local expected="$1"
    local actual="$2"
    local message="$3"
    [[ "${actual}" == "${expected}" ]] ||
        fail "${message}: expected=${expected}, actual=${actual}"
}

assert_exists() {
    [[ -e "$1" || -L "$1" ]] || fail "expected path to exist: $1"
}

assert_absent() {
    [[ ! -e "$1" && ! -L "$1" ]] || fail "expected path to be absent: $1"
}

new_case() {
    local name="$1"
    local root="${test_parent}/${name}"
    local fake_bin="${root}/fake-bin"
    mkdir -p "${fake_bin}" "${root}/var/lib/gongxing/data/uploads"
    printf 'stopped\n' >"${root}/service-state"
    printf '0\n' >"${root}/start-count"
    : >"${root}/start-targets"
    printf '0\n' >"${root}/maintenance-delete-attempts"

    cat >"${fake_bin}/systemctl" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
case "${1:-}" in
    is-active)
        [[ "$(cat "${TEST_SERVICE_STATE}")" == "running" ]]
        ;;
    start)
        count="$(( $(cat "${TEST_START_COUNT}") + 1 ))"
        printf '%s\n' "${count}" >"${TEST_START_COUNT}"
        target="$(readlink -f -- "${TEST_CURRENT_LINK}" 2>/dev/null || echo missing)"
        printf '%s:%s\n' "${count}" "${target}" >>"${TEST_START_TARGETS}"
        if [[ "${TEST_START_FAIL_ON:-}" == "${count}" ]]; then
            exit 1
        fi
        printf 'running\n' >"${TEST_SERVICE_STATE}"
        ;;
    stop)
        printf 'stopped\n' >"${TEST_SERVICE_STATE}"
        ;;
    *)
        echo "unexpected systemctl command: $*" >&2
        exit 2
        ;;
esac
EOF

    cat >"${fake_bin}/curl" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "${TEST_HEALTH_FAIL:-0}" == "1" ]]; then
    exit 1
fi
if [[ "${TEST_EXIT_AFTER_HEALTH:-0}" == "1" ]]; then
    printf 'stopped\n' >"${TEST_SERVICE_STATE}"
fi
EOF

    cat >"${fake_bin}/logger" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

    cat >"${fake_bin}/rm" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
for argument in "$@"; do
    if [[ "${argument}" == "${TEST_MAINTENANCE_FILE}" ]]; then
        attempts="$(( $(cat "${TEST_MAINTENANCE_DELETE_ATTEMPTS}") + 1 ))"
        printf '%s\n' "${attempts}" >"${TEST_MAINTENANCE_DELETE_ATTEMPTS}"
        if [[ "${TEST_MAINTENANCE_DELETE_FAIL:-0}" == "1" ]]; then
            exit 1
        fi
    fi
done
exec /usr/bin/rm "$@"
EOF

    cat >"${fake_bin}/python3.12" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "${1:-}" != "-m" || "${2:-}" != "venv" || -z "${3:-}" ]]; then
    echo "unexpected python3.12 command: $*" >&2
    exit 2
fi
target="$3"
mkdir -p "${target}/bin"
cat >"${target}/bin/python" <<'INNER'
#!/usr/bin/env bash
exit 0
INNER
chmod 0750 "${target}/bin/python"
EOF
    chmod 0750 "${fake_bin}/systemctl" "${fake_bin}/curl" \
        "${fake_bin}/logger" "${fake_bin}/rm" "${fake_bin}/python3.12"
    printf '%s\n' "${root}"
}

make_artifact() {
    local root="$1"
    local name="$2"
    local artifact="${root}/artifacts/${name}"
    mkdir -p "${artifact}/backend" "${artifact}/frontend/dist"
    printf '# test lock\n' >"${artifact}/backend/requirements.lock"
    printf '<!doctype html>\n' >"${artifact}/frontend/dist/index.html"
    printf '%s\n' "${artifact}"
}

run_deploy() {
    local root="$1"
    shift
    env \
        GONGXING_DEPLOY_TEST_MODE=1 \
        GONGXING_DEPLOY_TEST_ROOT="${root}" \
        TEST_SERVICE_STATE="${root}/service-state" \
        TEST_START_COUNT="${root}/start-count" \
        TEST_START_TARGETS="${root}/start-targets" \
        TEST_CURRENT_LINK="${root}/opt/gongxing/current" \
        TEST_HEALTH_FAIL="${TEST_HEALTH_FAIL:-0}" \
        TEST_EXIT_AFTER_HEALTH="${TEST_EXIT_AFTER_HEALTH:-0}" \
        TEST_START_FAIL_ON="${TEST_START_FAIL_ON:-}" \
        TEST_MAINTENANCE_DELETE_FAIL="${TEST_MAINTENANCE_DELETE_FAIL:-0}" \
        TEST_MAINTENANCE_FILE="${root}/run/gongxing/maintenance" \
        TEST_MAINTENANCE_DELETE_ATTEMPTS="${root}/maintenance-delete-attempts" \
        PATH="${root}/fake-bin:${PATH}" \
        bash "${deploy_script}" --confirm-server "$@"
}

test_initial_success() {
    local root artifact release current
    root="$(new_case initial-success)"
    artifact="$(make_artifact "${root}" release)"
    release="1111111111111111111111111111111111111111"
    current="${root}/opt/gongxing/current"

    run_deploy "${root}" \
        --initial-deploy --artifact "${artifact}" --release "${release}"

    assert_exists "${current}"
    assert_eq \
        "${root}/opt/gongxing/releases/${release}" \
        "$(readlink -f -- "${current}")" \
        "initial deployment current target"
    assert_eq "running" "$(cat "${root}/service-state")" \
        "initial deployment service state"
    assert_absent "${root}/run/gongxing/maintenance"
    assert_eq "1" "$(cat "${root}/maintenance-delete-attempts")" \
        "initial success did not clear maintenance exactly once"
}

test_initial_failure() {
    local root artifact release current
    root="$(new_case initial-failure)"
    artifact="$(make_artifact "${root}" release)"
    release="2222222222222222222222222222222222222222"
    current="${root}/opt/gongxing/current"

    if TEST_HEALTH_FAIL=1 run_deploy "${root}" \
        --initial-deploy --artifact "${artifact}" --release "${release}"; then
        fail "initial deployment unexpectedly survived a failed health check"
    fi

    assert_absent "${current}"
    assert_eq "stopped" "$(cat "${root}/service-state")" \
        "failed initial deployment service state"
    assert_exists "${root}/run/gongxing/maintenance"
}

test_initial_final_liveness_failure() {
    local root artifact release current
    root="$(new_case initial-final-liveness-failure)"
    artifact="$(make_artifact "${root}" release)"
    release="eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
    current="${root}/opt/gongxing/current"

    if TEST_EXIT_AFTER_HEALTH=1 run_deploy "${root}" \
        --initial-deploy --artifact "${artifact}" --release "${release}"; then
        fail "initial deployment ignored a final liveness failure"
    fi

    assert_absent "${current}"
    assert_eq "stopped" "$(cat "${root}/service-state")" \
        "final liveness failure did not stop the initial service"
    assert_exists "${root}/run/gongxing/maintenance"
}

test_initial_maintenance_clear_failure() {
    local root artifact release current
    root="$(new_case initial-maintenance-clear-failure)"
    artifact="$(make_artifact "${root}" release)"
    release="1357913579135791357913579135791357913579"
    current="${root}/opt/gongxing/current"

    if TEST_MAINTENANCE_DELETE_FAIL=1 run_deploy "${root}" \
        --initial-deploy --artifact "${artifact}" --release "${release}"; then
        fail "initial deployment ignored a maintenance clear failure"
    fi

    assert_absent "${current}"
    assert_eq "stopped" "$(cat "${root}/service-state")" \
        "maintenance clear failure did not stop the initial service"
    assert_exists "${root}/run/gongxing/maintenance"
    assert_eq "1" "$(cat "${root}/maintenance-delete-attempts")" \
        "initial failure retried maintenance clear after rollback"
}

test_repeated_initial_deploy() {
    local root first_artifact second_artifact first_release second_release current
    root="$(new_case repeated-initial)"
    first_artifact="$(make_artifact "${root}" first)"
    second_artifact="$(make_artifact "${root}" second)"
    first_release="3333333333333333333333333333333333333333"
    second_release="4444444444444444444444444444444444444444"
    current="${root}/opt/gongxing/current"

    run_deploy "${root}" --initial-deploy \
        --artifact "${first_artifact}" --release "${first_release}"
    if run_deploy "${root}" --initial-deploy \
        --artifact "${second_artifact}" --release "${second_release}"; then
        fail "repeated initial deployment was not rejected"
    fi

    assert_eq \
        "${root}/opt/gongxing/releases/${first_release}" \
        "$(readlink -f -- "${current}")" \
        "repeated initial deployment changed current"
    assert_eq "running" "$(cat "${root}/service-state")" \
        "repeated initial deployment changed service state"
}

test_initial_persistent_data_guards() {
    local kind root artifact release
    for kind in release service database upload other-data; do
        root="$(new_case "initial-guard-${kind}")"
        artifact="$(make_artifact "${root}" release)"
        release="5555555555555555555555555555555555555555"
        case "${kind}" in
            release)
                mkdir -p "${root}/opt/gongxing/releases/existing"
                ;;
            service)
                printf 'running\n' >"${root}/service-state"
                ;;
            database)
                printf 'not-a-real-db\n' \
                    >"${root}/var/lib/gongxing/data/site.db"
                ;;
            upload)
                printf 'test\n' \
                    >"${root}/var/lib/gongxing/data/uploads/existing.pdf"
                ;;
            other-data)
                printf 'test\n' \
                    >"${root}/var/lib/gongxing/data/unexpected.data"
                ;;
        esac
        if run_deploy "${root}" --initial-deploy \
            --artifact "${artifact}" --release "${release}"; then
            fail "initial deployment accepted existing ${kind}"
        fi
        if [[ "${kind}" == "service" ]]; then
            assert_eq "running" "$(cat "${root}/service-state")" \
                "initial guard changed a pre-existing running service"
        else
            assert_eq "stopped" "$(cat "${root}/service-state")" \
                "initial guard changed service state for ${kind}"
        fi
        assert_absent "${root}/opt/gongxing/current"
    done
}

prepare_subsequent_case() {
    local name="$1"
    local old_release="$2"
    local root
    root="$(new_case "${name}")"
    mkdir -p "${root}/opt/gongxing/releases/${old_release}"
    ln -s "${root}/opt/gongxing/releases/${old_release}" \
        "${root}/opt/gongxing/current"
    printf 'running\n' >"${root}/service-state"
    printf 'existing-db\n' >"${root}/var/lib/gongxing/data/site.db"
    printf '%s\n' "${root}"
}

test_subsequent_requires_backup() {
    local root artifact old_release new_release current
    old_release="6666666666666666666666666666666666666666"
    new_release="7777777777777777777777777777777777777777"
    root="$(prepare_subsequent_case subsequent-no-backup "${old_release}")"
    artifact="$(make_artifact "${root}" release)"
    current="${root}/opt/gongxing/current"

    if run_deploy "${root}" \
        --artifact "${artifact}" --release "${new_release}"; then
        fail "subsequent deployment without backup was not rejected"
    fi
    assert_eq \
        "${root}/opt/gongxing/releases/${old_release}" \
        "$(readlink -f -- "${current}")" \
        "backup gate changed current"
    assert_eq "running" "$(cat "${root}/service-state")" \
        "backup gate changed service state"
    assert_absent "${root}/run/gongxing/maintenance"

    if run_deploy "${root}" --initial-deploy \
        --confirmed-backup abcdef12 \
        --artifact "${artifact}" --release "${new_release}"; then
        fail "mutually exclusive deployment modes were accepted"
    fi
}

test_subsequent_success() {
    local root artifact old_release new_release current
    old_release="8888888888888888888888888888888888888888"
    new_release="9999999999999999999999999999999999999999"
    root="$(prepare_subsequent_case subsequent-success "${old_release}")"
    artifact="$(make_artifact "${root}" release)"
    current="${root}/opt/gongxing/current"

    run_deploy "${root}" \
        --confirmed-backup abcdef1234567890 \
        --artifact "${artifact}" --release "${new_release}"

    assert_eq \
        "${root}/opt/gongxing/releases/${new_release}" \
        "$(readlink -f -- "${current}")" \
        "subsequent deployment current target"
    assert_eq "running" "$(cat "${root}/service-state")" \
        "subsequent deployment did not restore service state"
    assert_absent "${root}/run/gongxing/maintenance"
    assert_eq "1" "$(cat "${root}/maintenance-delete-attempts")" \
        "subsequent success did not clear maintenance exactly once"
}

test_subsequent_stopped_state() {
    local root artifact old_release new_release current
    old_release="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    new_release="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    root="$(prepare_subsequent_case subsequent-stopped "${old_release}")"
    artifact="$(make_artifact "${root}" release)"
    current="${root}/opt/gongxing/current"
    printf 'stopped\n' >"${root}/service-state"

    run_deploy "${root}" \
        --confirmed-backup abcdef1234567890 \
        --artifact "${artifact}" --release "${new_release}"

    assert_eq \
        "${root}/opt/gongxing/releases/${new_release}" \
        "$(readlink -f -- "${current}")" \
        "stopped subsequent deployment current target"
    assert_eq "stopped" "$(cat "${root}/service-state")" \
        "subsequent deployment changed an originally stopped service"
    assert_absent "${root}/run/gongxing/maintenance"
}

test_subsequent_failure_rolls_back() {
    local root artifact old_release new_release current
    old_release="cccccccccccccccccccccccccccccccccccccccc"
    new_release="dddddddddddddddddddddddddddddddddddddddd"
    root="$(prepare_subsequent_case subsequent-failure "${old_release}")"
    artifact="$(make_artifact "${root}" release)"
    current="${root}/opt/gongxing/current"

    if TEST_HEALTH_FAIL=1 run_deploy "${root}" \
        --confirmed-backup abcdef1234567890 \
        --artifact "${artifact}" --release "${new_release}"; then
        fail "subsequent deployment unexpectedly survived a failed health check"
    fi

    assert_eq \
        "${root}/opt/gongxing/releases/${old_release}" \
        "$(readlink -f -- "${current}")" \
        "failed subsequent deployment did not roll back current"
    assert_eq "running" "$(cat "${root}/service-state")" \
        "failed subsequent deployment did not restore service state"
    assert_exists "${root}/run/gongxing/maintenance"
}

test_subsequent_final_restore_failure_rolls_back() {
    local root artifact old_release new_release current second_target third_target
    old_release="ffffffffffffffffffffffffffffffffffffffff"
    new_release="0123456789abcdef0123456789abcdef01234567"
    root="$(prepare_subsequent_case subsequent-final-restore-failure "${old_release}")"
    artifact="$(make_artifact "${root}" release)"
    current="${root}/opt/gongxing/current"

    if TEST_START_FAIL_ON=2 run_deploy "${root}" \
        --confirmed-backup abcdef1234567890 \
        --artifact "${artifact}" --release "${new_release}"; then
        fail "subsequent deployment ignored a failed final new-release start"
    fi

    assert_eq \
        "${root}/opt/gongxing/releases/${old_release}" \
        "$(readlink -f -- "${current}")" \
        "final restore failure did not roll back current"
    assert_eq "running" "$(cat "${root}/service-state")" \
        "old release was not restarted after final restore failure"
    assert_exists "${root}/run/gongxing/maintenance"
    assert_eq "3" "$(cat "${root}/start-count")" \
        "final restore failure did not make three distinct start attempts"
    second_target="$(sed -n '2p' "${root}/start-targets")"
    third_target="$(sed -n '3p' "${root}/start-targets")"
    assert_eq \
        "2:${root}/opt/gongxing/releases/${new_release}" \
        "${second_target}" \
        "second start did not target the new release"
    assert_eq \
        "3:${root}/opt/gongxing/releases/${old_release}" \
        "${third_target}" \
        "third start did not target the rolled-back release"
}

test_subsequent_maintenance_clear_failure_rolls_back() {
    local root artifact old_release new_release current
    old_release="2468024680246802468024680246802468024680"
    new_release="abcdefabcdefabcdefabcdefabcdefabcdefabcd"
    root="$(prepare_subsequent_case subsequent-maintenance-clear-failure "${old_release}")"
    artifact="$(make_artifact "${root}" release)"
    current="${root}/opt/gongxing/current"

    if TEST_MAINTENANCE_DELETE_FAIL=1 run_deploy "${root}" \
        --confirmed-backup abcdef1234567890 \
        --artifact "${artifact}" --release "${new_release}"; then
        fail "subsequent deployment ignored a maintenance clear failure"
    fi

    assert_eq \
        "${root}/opt/gongxing/releases/${old_release}" \
        "$(readlink -f -- "${current}")" \
        "maintenance clear failure did not roll back current"
    assert_eq "running" "$(cat "${root}/service-state")" \
        "old release was not restarted after maintenance clear failure"
    assert_exists "${root}/run/gongxing/maintenance"
    assert_eq "3" "$(cat "${root}/start-count")" \
        "maintenance clear rollback did not restart the old release"
    assert_eq "1" "$(cat "${root}/maintenance-delete-attempts")" \
        "subsequent failure retried maintenance clear after rollback"
}

test_initial_success
test_initial_failure
test_initial_final_liveness_failure
test_initial_maintenance_clear_failure
test_repeated_initial_deploy
test_initial_persistent_data_guards
test_subsequent_requires_backup
test_subsequent_success
test_subsequent_stopped_state
test_subsequent_failure_rolls_back
test_subsequent_final_restore_failure_rolls_back
test_subsequent_maintenance_clear_failure_rolls_back
printf 'deploy release behavior tests: ok\n'
