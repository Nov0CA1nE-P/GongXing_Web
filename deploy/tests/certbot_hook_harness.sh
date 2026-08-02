#!/usr/bin/env bash

set -Eeuo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
test_root="$(mktemp -d /tmp/gongxing-certbot-test-XXXXXXXX)"
fake_bin="${test_root}/bin"
mkdir -p "${fake_bin}"

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
