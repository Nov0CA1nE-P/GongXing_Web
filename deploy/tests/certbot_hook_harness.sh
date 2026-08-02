#!/usr/bin/env bash

set -Eeuo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
test_root="$(mktemp -d /tmp/gongxing-certbot-test-XXXXXXXX)"
fake_bin="${test_root}/bin"
hook_parent="${test_root}/hooks"
mkdir -p "${fake_bin}" "${hook_parent}"
chmod 0755 "${hook_parent}"

cleanup() { rm -rf -- "${test_root}"; }
trap cleanup EXIT INT TERM HUP
fail() { echo "certbot hook behavior test failed: $*" >&2; exit 1; }

cat >"${fake_bin}/nginx" <<'EOF'
#!/usr/bin/env bash
printf 'nginx\n' >>"${HOOK_CALLS}"
[[ "${HOOK_NGINX_FAIL:-0}" != "1" ]]
EOF
cat >"${fake_bin}/systemctl" <<'EOF'
#!/usr/bin/env bash
printf 'systemctl:%s\n' "$*" >>"${HOOK_CALLS}"
EOF
chmod 0750 "${fake_bin}/nginx" "${fake_bin}/systemctl"

validator="${repo_root}/deploy/scripts/verify-certbot-hook.py"
uid="$(id -u)"
gid="$(id -g)"
verify_hook() {
    GONGXING_DEPLOY_TEST_MODE=1 python3 "${validator}" --hook "$1" \
        --test-uid "$2" --test-gid "$3"
}
expect_install_failure() {
    if verify_hook "$1" "${2:-${uid}}" "${3:-${gid}}" >/dev/null 2>&1; then
        fail "hook installation validation unexpectedly succeeded: $1"
    fi
}

install -m 0755 "${repo_root}/deploy/scripts/certbot-reload-nginx.sh" \
    "${hook_parent}/valid.sh"
verify_hook "${hook_parent}/valid.sh" "${uid}" "${gid}"
expect_install_failure "${hook_parent}/valid.sh" "$((uid + 1))" "${gid}"
cp "${hook_parent}/valid.sh" "${hook_parent}/group-write.sh"
chmod 0775 "${hook_parent}/group-write.sh"
expect_install_failure "${hook_parent}/group-write.sh"
cp "${hook_parent}/valid.sh" "${hook_parent}/other-write.sh"
chmod 0757 "${hook_parent}/other-write.sh"
expect_install_failure "${hook_parent}/other-write.sh"
ln -s "${hook_parent}/valid.sh" "${hook_parent}/linked.sh"
expect_install_failure "${hook_parent}/linked.sh"
mkdir -m 0755 "${test_root}/real-hooks"
cp "${hook_parent}/valid.sh" "${test_root}/real-hooks/hook.sh"
ln -s "${test_root}/real-hooks" "${test_root}/linked-hooks"
expect_install_failure "${test_root}/linked-hooks/hook.sh"

calls="${test_root}/calls"
: >"${calls}"
if HOOK_CALLS="${calls}" HOOK_NGINX_FAIL=1 PATH="${fake_bin}:${PATH}" \
    bash "${repo_root}/deploy/scripts/certbot-reload-nginx.sh"; then
    fail "hook ignored nginx configuration failure"
fi
if grep -q systemctl "${calls}"; then
    fail "hook reloaded Nginx after a failed syntax check"
fi

: >"${calls}"
HOOK_CALLS="${calls}" PATH="${fake_bin}:${PATH}" \
    bash "${repo_root}/deploy/scripts/certbot-reload-nginx.sh"
[[ "$(sed -n '1p' "${calls}")" == nginx ]] || fail "nginx -t was not first"
[[ "$(sed -n '2p' "${calls}")" == 'systemctl:reload nginx.service' ]] || \
    fail "successful validation did not reload Nginx"

printf 'certbot hook behavior tests: ok\n'
