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
    printf '{"lockfileVersion":3}\n' >"${target}/frontend/package-lock.json"
    printf '<!doctype html>\n' >"${target}/frontend/dist/index.html"
    printf 'export const fixture = true;\n' \
        >"${target}/frontend/src/data/fixture.ts"
    printf 'wheel\n' >"${target}/wheelhouse/example-1.0-py3-none-any.whl"
    wheel_digest="$(sha256sum "${target}/wheelhouse/example-1.0-py3-none-any.whl" | cut -d' ' -f1)"
    printf 'example==1.0 \\\n    --hash=sha256:%s\n' "${wheel_digest}" \
        >"${target}/backend/requirements.lock"
    (
        cd "${target}/wheelhouse"
        sha256sum example-1.0-py3-none-any.whl >"${target}/WHEELHOUSE_SHA256SUMS"
    )
    cat >"${target}/RELEASE_BUILD_MANIFEST.txt" <<EOF
git_sha=${release_id}
node_version=v24.18.0
npm_version=11.16.0
python_version=Python 3.12.13
requirements_lock_sha256=$(sha256sum "${target}/backend/requirements.lock" | cut -d' ' -f1)
package_lock_sha256=$(sha256sum "${target}/frontend/package-lock.json" | cut -d' ' -f1)
wheelhouse_sha256s_sha256=$(sha256sum "${target}/WHEELHOUSE_SHA256SUMS" | cut -d' ' -f1)
built_at_utc=2026-08-02T00:00:00Z
EOF
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
    [[ ! -e "${output}" && ! -L "${output}" ]] || \
        fail "failed verification left an output directory"
    [[ ! -e "${output}.integrity.json" && ! -L "${output}.integrity.json" ]] || \
        fail "failed verification left an integrity manifest"
    if compgen -G "$(dirname -- "${output}")/.$(basename -- "${output}").extracting-*" >/dev/null; then
        fail "failed verification left a temporary extraction directory"
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

for case_name in wrong-sha forbidden-env forbidden-env-production forbidden-data \
    forbidden-db forbidden-pdf forbidden-key wheel-missing wheel-extra wheel-duplicate \
    wheel-digest sdist symlink nested-wheelhouse lock-digest package-lock-digest \
    manifest-missing manifest-duplicate case-collision unicode-collision \
    backslash duplicate-member prefix-conflict; do
    source_dir="${test_root}/${case_name}-source"
    make_release "${source_dir}"
    case "${case_name}" in
        wrong-sha) sed -i 's/^git_sha=.*/git_sha=4040404040404040404040404040404040404040/' "${source_dir}/RELEASE_BUILD_MANIFEST.txt" ;;
        forbidden-env) printf 'secret\n' >"${source_dir}/.env" ;;
        forbidden-env-production) printf 'secret\n' >"${source_dir}/frontend/.env.production" ;;
        forbidden-data) mkdir "${source_dir}/data" ;;
        forbidden-db) printf 'database\n' >"${source_dir}/site.db" ;;
        forbidden-pdf) printf 'pdf\n' >"${source_dir}/course.pdf" ;;
        forbidden-key) printf 'key\n' >"${source_dir}/backup.key" ;;
        wheel-missing) rm "${source_dir}/wheelhouse/example-1.0-py3-none-any.whl" ;;
        wheel-extra)
            printf 'extra\n' >"${source_dir}/wheelhouse/extra-1.0-py3-none-any.whl"
            (cd "${source_dir}/wheelhouse" && sha256sum -- *.whl | LC_ALL=C sort -k2 \
                >"${source_dir}/WHEELHOUSE_SHA256SUMS")
            sed -i "s/^wheelhouse_sha256s_sha256=.*/wheelhouse_sha256s_sha256=$(sha256sum "${source_dir}/WHEELHOUSE_SHA256SUMS" | cut -d' ' -f1)/" \
                "${source_dir}/RELEASE_BUILD_MANIFEST.txt"
            ;;
        wheel-duplicate)
            printf 'duplicate\n' >"${source_dir}/wheelhouse/example-1.0-py2-none-any.whl"
            (cd "${source_dir}/wheelhouse" && sha256sum -- *.whl | LC_ALL=C sort -k2 \
                >"${source_dir}/WHEELHOUSE_SHA256SUMS")
            sed -i "s/^wheelhouse_sha256s_sha256=.*/wheelhouse_sha256s_sha256=$(sha256sum "${source_dir}/WHEELHOUSE_SHA256SUMS" | cut -d' ' -f1)/" \
                "${source_dir}/RELEASE_BUILD_MANIFEST.txt"
            ;;
        wheel-digest) printf 'changed\n' >>"${source_dir}/wheelhouse/example-1.0-py3-none-any.whl" ;;
        sdist) printf 'source\n' >"${source_dir}/wheelhouse/example-1.0.tar.gz" ;;
        symlink) ln -s backend "${source_dir}/backend-link" ;;
        nested-wheelhouse) mkdir -p "${source_dir}/frontend/wheelhouse" ;;
        lock-digest) printf '\n# changed\n' >>"${source_dir}/backend/requirements.lock" ;;
        package-lock-digest) printf 'changed\n' >>"${source_dir}/frontend/package-lock.json" ;;
        manifest-missing) sed -i '/^npm_version=/d' "${source_dir}/RELEASE_BUILD_MANIFEST.txt" ;;
        manifest-duplicate) printf 'git_sha=%s\n' "${release_id}" >>"${source_dir}/RELEASE_BUILD_MANIFEST.txt" ;;
        case-collision)
            printf 'one\n' >"${source_dir}/frontend/Case.txt"
            printf 'two\n' >"${source_dir}/frontend/case.txt"
            ;;
        unicode-collision)
            python3 - "${source_dir}/frontend" <<'PY'
import sys
from pathlib import Path

root = Path(sys.argv[1])
(root / "caf\u00e9.txt").write_text("one", encoding="utf-8")
(root / "cafe\u0301.txt").write_text("two", encoding="utf-8")
PY
            ;;
        backslash|duplicate-member|prefix-conflict) ;;
    esac
    archive="${test_root}/${case_name}.tar.gz"
    if [[ "${case_name}" == backslash || "${case_name}" == duplicate-member || \
          "${case_name}" == prefix-conflict ]]; then
        python3 - "${source_dir}" "${archive}" "${case_name}" <<'PY'
import io
import sys
import tarfile
from pathlib import Path

source, archive, case = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
with tarfile.open(archive, "w:gz") as bundle:
    bundle.add(source, arcname=".")
    if case == "backslash":
        info = tarfile.TarInfo("frontend\\evil.txt")
        info.size = 1
        bundle.addfile(info, io.BytesIO(b"x"))
    elif case == "duplicate-member":
        info = tarfile.TarInfo("frontend/dist/index.html")
        info.size = 1
        bundle.addfile(info, io.BytesIO(b"x"))
    else:
        info = tarfile.TarInfo("conflict")
        info.size = 1
        bundle.addfile(info, io.BytesIO(b"x"))
        child = tarfile.TarInfo("conflict/child")
        child.size = 1
        bundle.addfile(child, io.BytesIO(b"y"))
PY
    else
        tar -C "${source_dir}" -czf "${archive}" .
    fi
    checksum_archive "${archive}"
    expect_verify_failure "${archive}" "${test_root}/${case_name}-out"
done

# A failed attempt must not poison the same destination path for a safe retry.
retry_output="${test_root}/retry-output"
expect_verify_failure "${test_root}/wrong-digest.tar.gz" "${retry_output}"
verify_package "${test_root}/valid.tar.gz" "${retry_output}" >/dev/null

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
