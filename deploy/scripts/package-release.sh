#!/usr/bin/env bash

set -Eeuo pipefail

if [[ "$#" -ne 3 ]]; then
    echo "usage: package-release.sh <release-directory> <git-sha> <archive.tar.gz>" >&2
    exit 2
fi

release_dir="$(realpath -- "$1")"
release_id="$2"
archive="$3"
checksum="${archive}.sha256"

if [[ ! "${release_id}" =~ ^[0-9a-f]{7,40}$ ]]; then
    echo "error: Git SHA is invalid" >&2
    exit 2
fi
if [[ ! -d "${release_dir}" || -e "${archive}" || -e "${checksum}" ]]; then
    echo "error: release directory is missing or output already exists" >&2
    exit 1
fi
if [[ "$(sed -n 's/^git_sha=//p' "${release_dir}/RELEASE_BUILD_MANIFEST.txt")" != "${release_id}" ]]; then
    echo "error: release manifest Git SHA mismatch" >&2
    exit 1
fi
if find "${release_dir}" -type l -o \! -type d -a \! -type f | grep -q .; then
    echo "error: release contains a link or special file" >&2
    exit 1
fi
if find "${release_dir}" -type f \( \
    -name .env -o -name '*.db' -o -name '*.db-wal' -o -name '*.db-shm' -o \
    -name '*.pdf' -o -name '*.htpasswd' -o -name '*.pem' -o -name '*.key' -o \
    -name restic-password -o -name id_rsa -o -name id_ed25519 \
\) -print -quit | grep -q . || [[ -e "${release_dir}/data" || -L "${release_dir}/data" ]]; then
    echo "error: release contains forbidden data or secrets" >&2
    exit 1
fi

archive_parent="$(dirname -- "${archive}")"
archive_name="$(basename -- "${archive}")"
if [[ ! "${archive_name}" =~ ^[A-Za-z0-9._-]+\.tar\.gz$ ]]; then
    echo "error: archive filename must be a safe .tar.gz name" >&2
    exit 2
fi
mkdir -p -- "${archive_parent}"
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner \
    -C "${release_dir}" -czf "${archive}" .
printf '%s  %s\n' "$(sha256sum "${archive}" | cut -d' ' -f1)" "${archive_name}" \
    >"${checksum}"
chmod 0640 "${archive}" "${checksum}"
