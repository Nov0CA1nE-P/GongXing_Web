#!/usr/bin/env bash

set -Eeuo pipefail

apply=0
approval=0
for argument in "$@"; do
    case "${argument}" in
        --apply) apply=1 ;;
        --stage-b-approved) approval=1 ;;
        *)
            echo "error: unknown argument: ${argument}" >&2
            exit 2
            ;;
    esac
done

: "${SPACES_BUCKET:?SPACES_BUCKET is required}"
: "${SPACES_REGION:=blr1}"
endpoint="https://${SPACES_REGION}.digitaloceanspaces.com"
lifecycle_file="$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
    pwd
)/spaces/lifecycle.json"

if [[ "${apply}" -ne 1 || "${approval}" -ne 1 ]]; then
    printf '%s\n' \
        "dry run only" \
        "bucket: ${SPACES_BUCKET}" \
        "region: ${SPACES_REGION}" \
        "would enable versioning and apply ${lifecycle_file}"
    exit 0
fi

aws s3api put-bucket-versioning \
    --bucket "${SPACES_BUCKET}" \
    --endpoint-url "${endpoint}" \
    --versioning-configuration Status=Enabled

aws s3api put-bucket-lifecycle-configuration \
    --bucket "${SPACES_BUCKET}" \
    --endpoint-url "${endpoint}" \
    --lifecycle-configuration "file://${lifecycle_file}"

aws s3api get-bucket-versioning \
    --bucket "${SPACES_BUCKET}" \
    --endpoint-url "${endpoint}"
