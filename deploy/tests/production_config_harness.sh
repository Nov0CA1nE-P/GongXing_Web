#!/usr/bin/env bash

set -Eeuo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
test_root="$(mktemp -d /tmp/gongxing-config-test-XXXXXXXX)"
validator="${repo_root}/deploy/scripts/validate-production-config.py"

cleanup() { rm -rf -- "${test_root}"; }
trap cleanup EXIT INT TERM HUP
fail() { echo "production config behavior test failed: $*" >&2; exit 1; }

make_release() {
    local target="$1"
    mkdir -p "${target}/backend"
    ln -s /var/lib/gongxing/data "${target}/data"
    cat >"${target}/backend/dotenv.py" <<'PY'
def dotenv_values(path):
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values
PY
    cat >"${target}/backend/config.py" <<'PY'
import os
from pathlib import Path

APP_ENV = os.getenv("APP_ENV")
if APP_ENV != "production":
    raise RuntimeError("bad app env")
TRUSTED_ORIGINS = [value for value in os.getenv("TRUSTED_ORIGINS", "").split(",") if value]
CORS_ALLOWED_ORIGINS = [value for value in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if value]
TRUSTED_PROXY_IPS = [value for value in os.getenv("TRUSTED_PROXY_IPS", "").split(",") if value]
if len(os.getenv("ADMIN_PASSWORD", "")) < 12:
    raise RuntimeError("bad admin password")
ADMIN_COOKIE_SECURE = APP_ENV == "production"
UVICORN_PROXY_HEADERS = APP_ENV == "production"
DATABASE_PATH = os.getenv("DATABASE_PATH", "")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
UPLOADS_DIR = str(PROJECT_ROOT / "data" / "uploads")
COURSEWARE_TEMP_DIR = str(PROJECT_ROOT / "data" / "tmp" / "courseware")
PY
}

write_env() {
    local path="$1" app_env="${2:-production}" origin="${3:-https://test.novocaine.me}" \
        proxy="${4:-127.0.0.1}" database="${5:-/var/lib/gongxing/data/site.db}" \
        password="${6:-valid-password-123}"
    cat >"${path}" <<EOF
APP_ENV=${app_env}
TRUSTED_ORIGINS=${origin}
CORS_ALLOWED_ORIGINS=
TRUSTED_PROXY_IPS=${proxy}
DATABASE_PATH=${database}
ADMIN_PASSWORD=${password}
DEEPSEEK_API_KEY=SECRET-SENTINEL-MUST-NOT-LEAK
EOF
    chmod 0600 "${path}"
}

expect_failure() {
    local name="$1" env_file="$2" release="$3" output
    if output="$(GONGXING_DEPLOY_TEST_MODE=1 python3 "${validator}" --test-mode \
        --env-file "${env_file}" --release-dir "${release}" 2>&1)"; then
        fail "validator accepted ${name}"
    fi
    if [[ "${output}" == *SECRET-SENTINEL* ]]; then
        fail "validator leaked a secret for ${name}"
    fi
}

release="${test_root}/release"
make_release "${release}"
valid_env="${test_root}/valid.env"
write_env "${valid_env}"
GONGXING_DEPLOY_TEST_MODE=1 python3 "${validator}" --test-mode \
    --env-file "${valid_env}" --release-dir "${release}"

write_env "${test_root}/app.env" development
expect_failure app-env "${test_root}/app.env" "${release}"
write_env "${test_root}/origin.env" production https://wrong.example
expect_failure trusted-origin "${test_root}/origin.env" "${release}"
write_env "${test_root}/proxy.env" production https://test.novocaine.me 10.0.0.1
expect_failure trusted-proxy "${test_root}/proxy.env" "${release}"
write_env "${test_root}/data.env" production https://test.novocaine.me 127.0.0.1 /tmp/site.db
expect_failure data-path "${test_root}/data.env" "${release}"
write_env "${test_root}/password.env" production https://test.novocaine.me 127.0.0.1 /var/lib/gongxing/data/site.db short
expect_failure admin-password "${test_root}/password.env" "${release}"

cp "${valid_env}" "${test_root}/mode.env"
chmod 0664 "${test_root}/mode.env"
expect_failure env-mode "${test_root}/mode.env" "${release}"

python3 - "${validator}" "${valid_env}" <<'PY'
import importlib.util
import os
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("validator", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
try:
    module.validate_metadata(Path(sys.argv[2]), os.getuid() + 1, os.getgid())
except RuntimeError:
    raise SystemExit(0)
raise SystemExit(1)
PY

printf 'production config behavior tests: ok\n'
