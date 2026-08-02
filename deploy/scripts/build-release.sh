#!/usr/bin/env bash

set -Eeuo pipefail

if [[ "$#" -ne 2 ]]; then
    echo "usage: build-release.sh <git-sha> <output-directory>" >&2
    exit 2
fi

release_id="$1"
output_dir="$2"
repo_root="$(git rev-parse --show-toplevel)"
validation_root=""

cleanup() {
    if [[ -n "${validation_root}" && -d "${validation_root}" ]]; then
        rm -rf -- "${validation_root}"
    fi
}
trap cleanup EXIT INT TERM HUP

if [[ ! "${release_id}" =~ ^[0-9a-f]{7,40}$ ]]; then
    echo "error: release ID must be a Git commit ID" >&2
    exit 2
fi
if [[ -n "$(git -C "${repo_root}" status --porcelain)" ]]; then
    echo "error: release packages require a clean worktree" >&2
    exit 1
fi
if [[ "$(git -C "${repo_root}" rev-parse "${release_id}^{commit}")" != \
      "$(git -C "${repo_root}" rev-parse HEAD)" ]]; then
    echo "error: release ID must match the checked-out commit" >&2
    exit 1
fi
if [[ -e "${output_dir}" ]]; then
    echo "error: output directory already exists" >&2
    exit 1
fi

# shellcheck disable=SC1091
source "${repo_root}/deploy/runtime-versions.conf"
if [[ "$(node --version)" != "v${NODE_VERSION}" ]]; then
    echo "error: Node.js ${NODE_VERSION} is required" >&2
    exit 1
fi
if [[ "$(npm --version)" != "${NPM_VERSION}" ]]; then
    echo "error: npm ${NPM_VERSION} is required" >&2
    exit 1
fi
if [[ "$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" \
      != "${PYTHON_VERSION}" ]]; then
    echo "error: Linux Python ${PYTHON_VERSION} is required" >&2
    exit 1
fi

(
    cd "${repo_root}/frontend"
    npm ci
    npm run lint
    npm run build
)

validation_root="$(mktemp -d)"
wheelhouse="${validation_root}/wheelhouse"
mkdir -p "${wheelhouse}"
python3 -m pip download \
    --require-hashes \
    --only-binary=:all: \
    --requirement "${repo_root}/backend/requirements.lock" \
    --dest "${wheelhouse}"
if find "${wheelhouse}" -maxdepth 1 -type f ! -name '*.whl' -print -quit | grep -q . || \
   [[ -z "$(find "${wheelhouse}" -maxdepth 1 -type f -name '*.whl' -print -quit)" ]]; then
    echo "error: wheelhouse must contain wheels only" >&2
    exit 1
fi
(
    cd "${wheelhouse}"
    sha256sum -- *.whl | LC_ALL=C sort -k2 \
        >"${validation_root}/WHEELHOUSE_SHA256SUMS"
)
python3 -m venv "${validation_root}/venv"
"${validation_root}/venv/bin/python" -m pip install \
    --no-index \
    --find-links "${wheelhouse}" \
    --require-hashes \
    --requirement "${repo_root}/backend/requirements.lock"
(
    cd "${repo_root}"
    "${validation_root}/venv/bin/python" -m compileall -q \
        backend deploy/scripts
    "${validation_root}/venv/bin/python" -m unittest discover \
        -s backend/tests -p 'test_*.py'
)
mkdir -p "${output_dir}"
git -C "${repo_root}" archive "${release_id}" | tar -x -C "${output_dir}"
rm -rf -- "${output_dir}/data"
cp -a -- "${repo_root}/frontend/dist" "${output_dir}/frontend/dist"
cp -a -- "${wheelhouse}" "${output_dir}/wheelhouse"
cp -- "${validation_root}/WHEELHOUSE_SHA256SUMS" \
    "${output_dir}/WHEELHOUSE_SHA256SUMS"

if find "${output_dir}" \
    \( -name .env -o -name '*.htpasswd' -o -name '*.db' -o -name '*.pdf' \) \
    -print -quit | grep -q .; then
    echo "error: release artifact contains forbidden data" >&2
    exit 1
fi

cat >"${output_dir}/RELEASE_BUILD_MANIFEST.txt" <<EOF
git_sha=${release_id}
node_version=$(node --version)
npm_version=$(npm --version)
python_version=$(python3 --version)
requirements_lock_sha256=$(sha256sum "${repo_root}/backend/requirements.lock" | cut -d' ' -f1)
package_lock_sha256=$(sha256sum "${repo_root}/frontend/package-lock.json" | cut -d' ' -f1)
wheelhouse_sha256s_sha256=$(sha256sum "${output_dir}/WHEELHOUSE_SHA256SUMS" | cut -d' ' -f1)
built_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

rm -rf -- "${validation_root}"
validation_root=""
