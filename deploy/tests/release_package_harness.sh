#!/usr/bin/env bash

set -Eeuo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
test_root="$(mktemp -d /tmp/gongxing-package-test-XXXXXXXX)"
release_id="3030303030303030303030303030303030303030"

cleanup() { rm -rf -- "${test_root}"; }
trap cleanup EXIT INT TERM HUP
fail() { echo "release package behavior test failed: $*" >&2; exit 1; }

make_release() {
    local target="$1"
    mkdir -p "${target}/backend" "${target}/frontend/dist" \
        "${target}/frontend/src/data" "${target}/wheelhouse"
    printf '# lock\n' >"${target}/backend/requirements.lock"
    printf '<!doctype html>\n' >"${target}/frontend/dist/index.html"
    printf 'export const fixture = true;\n' \
        >"${target}/frontend/src/data/fixture.ts"
    printf 'wheel\n' >"${target}/wheelhouse/example-1.0-py3-none-any.whl"
    (
        cd "${target}/wheelhouse"
        sha256sum example-1.0-py3-none-any.whl >"${target}/WHEELHOUSE_SHA256SUMS"
    )
    printf 'git_sha=%s\n' "${release_id}" >"${target}/RELEASE_BUILD_MANIFEST.txt"
}

checksum_archive() {
    local archive="$1"
    printf '%s  %s\n' "$(sha256sum "${archive}" | cut -d' ' -f1)" \
        "$(basename -- "${archive}")" >"${archive}.sha256"
}

verify_package() {
    local archive="$1" output="$2"
    GONGXING_DEPLOY_TEST_MODE=1 GONGXING_PYTHON_BIN=python3 \
        bash "${repo_root}/deploy/scripts/verify-release-package.sh" \
        --archive "${archive}" --checksum "${archive}.sha256" \
        --release "${release_id}" --output "${output}"
}

expect_verify_failure() {
    local archive="$1" output="$2"
    if verify_package "${archive}" "${output}" >/dev/null 2>&1; then
        fail "verification unexpectedly accepted $(basename -- "${archive}")"
    fi
}

valid="${test_root}/valid"
make_release "${valid}"
bash "${repo_root}/deploy/scripts/package-release.sh" \
    "${valid}" "${release_id}" "${test_root}/valid.tar.gz"
verify_package "${test_root}/valid.tar.gz" "${test_root}/verified" >/dev/null
python3 "${repo_root}/deploy/scripts/release_integrity.py" verify \
    --directory "${test_root}/verified" --release "${release_id}" \
    --manifest "${test_root}/verified.integrity.json"

cp "${test_root}/valid.tar.gz" "${test_root}/tampered.tar.gz"
cp "${test_root}/valid.tar.gz.sha256" "${test_root}/tampered.tar.gz.sha256"
printf 'tamper' >>"${test_root}/tampered.tar.gz"
sed -i 's/valid\.tar\.gz/tampered.tar.gz/' "${test_root}/tampered.tar.gz.sha256"
expect_verify_failure "${test_root}/tampered.tar.gz" "${test_root}/tampered-out"

cp "${test_root}/valid.tar.gz" "${test_root}/wrong-digest.tar.gz"
printf '%064d  wrong-digest.tar.gz\n' 0 >"${test_root}/wrong-digest.tar.gz.sha256"
expect_verify_failure "${test_root}/wrong-digest.tar.gz" "${test_root}/digest-out"

for case_name in wrong-sha forbidden-env forbidden-data forbidden-db forbidden-pdf \
    forbidden-key wheel-missing wheel-digest sdist symlink; do
    source_dir="${test_root}/${case_name}-source"
    make_release "${source_dir}"
    case "${case_name}" in
        wrong-sha) sed -i 's/^git_sha=.*/git_sha=4040404040404040404040404040404040404040/' "${source_dir}/RELEASE_BUILD_MANIFEST.txt" ;;
        forbidden-env) printf 'secret\n' >"${source_dir}/.env" ;;
        forbidden-data) mkdir "${source_dir}/data" ;;
        forbidden-db) printf 'database\n' >"${source_dir}/site.db" ;;
        forbidden-pdf) printf 'pdf\n' >"${source_dir}/course.pdf" ;;
        forbidden-key) printf 'key\n' >"${source_dir}/backup.key" ;;
        wheel-missing) rm "${source_dir}/wheelhouse/example-1.0-py3-none-any.whl" ;;
        wheel-digest) printf 'changed\n' >>"${source_dir}/wheelhouse/example-1.0-py3-none-any.whl" ;;
        sdist) printf 'source\n' >"${source_dir}/wheelhouse/example-1.0.tar.gz" ;;
        symlink) ln -s backend "${source_dir}/backend-link" ;;
    esac
    archive="${test_root}/${case_name}.tar.gz"
    tar -C "${source_dir}" -czf "${archive}" .
    checksum_archive "${archive}"
    expect_verify_failure "${archive}" "${test_root}/${case_name}-out"
done

python3 - "${test_root}/traversal.tar.gz" <<'PY'
import io
import sys
import tarfile

with tarfile.open(sys.argv[1], "w:gz") as bundle:
    info = tarfile.TarInfo("../escape")
    payload = b"escape"
    info.size = len(payload)
    bundle.addfile(info, io.BytesIO(payload))
PY
checksum_archive "${test_root}/traversal.tar.gz"
expect_verify_failure "${test_root}/traversal.tar.gz" "${test_root}/traversal-out"

python3 - "${test_root}/absolute.tar.gz" <<'PY'
import io
import sys
import tarfile

with tarfile.open(sys.argv[1], "w:gz") as bundle:
    info = tarfile.TarInfo("/absolute/escape")
    payload = b"escape"
    info.size = len(payload)
    bundle.addfile(info, io.BytesIO(payload))
PY
checksum_archive "${test_root}/absolute.tar.gz"
expect_verify_failure "${test_root}/absolute.tar.gz" "${test_root}/absolute-out"

for mutation in add modify delete; do
    output="${test_root}/mutation-${mutation}"
    verify_package "${test_root}/valid.tar.gz" "${output}" >/dev/null
    case "${mutation}" in
        add) printf 'new\n' >"${output}/unexpected.txt" ;;
        modify) printf 'changed\n' >>"${output}/frontend/dist/index.html" ;;
        delete) rm "${output}/backend/requirements.lock" ;;
    esac
    if python3 "${repo_root}/deploy/scripts/release_integrity.py" verify \
        --directory "${output}" --release "${release_id}" \
        --manifest "${output}.integrity.json" >/dev/null 2>&1; then
        fail "integrity verification ignored ${mutation} mutation"
    fi
done

printf 'release package behavior tests: ok\n'
