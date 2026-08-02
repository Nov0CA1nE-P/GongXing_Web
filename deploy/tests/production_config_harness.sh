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
def dotenv_values(path=None, stream=None):
    values = {}
    source = stream.read() if stream is not None else path.read_text(encoding="utf-8")
    for line in source.splitlines():
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

ln -s "${valid_env}" "${test_root}/linked.env"
expect_failure env-symlink "${test_root}/linked.env" "${release}"
ln -s "${test_root}/missing.env" "${test_root}/dangling.env"
expect_failure dangling-env-symlink "${test_root}/dangling.env" "${release}"

mkdir -m 0700 "${test_root}/real-parent"
write_env "${test_root}/real-parent/parent.env"
ln -s "${test_root}/real-parent" "${test_root}/linked-parent"
expect_failure parent-symlink "${test_root}/linked-parent/parent.env" "${release}"

python3 - "${validator}" "${valid_env}" "${test_root}" <<'PY'
import importlib.util
import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("validator", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
try:
    stream = module.open_verified_environment(Path(sys.argv[2]), os.getuid() + 1, os.getgid())
except RuntimeError:
    pass
else:
    stream.close()
    raise SystemExit(1)

race_parent = Path(sys.argv[3]) / "race-parent"
race_parent.mkdir(mode=0o700)
race_env = race_parent / "race.env"
shutil.copyfile(sys.argv[2], race_env)
race_env.chmod(0o600)
old_parent = race_parent.with_name("race-parent-old")
original_open = os.open
replaced = False
def replacing_open(path, flags, *args, **kwargs):
    global replaced
    if flags & os.O_DIRECTORY and not replaced:
        race_parent.rename(old_parent)
        race_parent.mkdir(mode=0o700)
        shutil.copyfile(old_parent / "race.env", race_parent / "race.env")
        (race_parent / "race.env").chmod(0o600)
        replaced = True
    return original_open(path, flags, *args, **kwargs)

with patch.object(module.os, "open", replacing_open):
    try:
        module.open_verified_environment(race_env, os.getuid(), os.getgid())
    except RuntimeError:
        raise SystemExit(0)
raise SystemExit(1)
PY

printf 'production config behavior tests: ok\n'
