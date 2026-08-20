#!/usr/bin/env bash
# Create the GCS bucket that holds Terraform state.
#
# Terraform cannot create its own backend bucket, so this one resource is
# created with gcloud. It is the ONLY resource in the project not managed by
# Terraform, and it is deliberately outside both module lifecycles: destroying
# the state bucket would strand every other resource.
#
# Idempotent — safe to re-run. Takes the project id as its only argument so
# nothing is hardcoded (CLAUDE.md, "Deployment Context").
set -euo pipefail

PROJECT_ID="${1:?usage: tf_bootstrap.sh <project-id> [region]}"
REGION="${2:-us-central1}"
BUCKET="${PROJECT_ID}-tfstate"

if gcloud storage buckets describe "gs://${BUCKET}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "State bucket gs://${BUCKET} already exists."
  exit 0
fi

echo "Creating state bucket gs://${BUCKET} in ${REGION}..."
gcloud storage buckets create "gs://${BUCKET}" \
  --project="${PROJECT_ID}" \
  --location="${REGION}" \
  --uniform-bucket-level-access \
  --public-access-prevention

# Versioning is not optional. A corrupted or truncated state file with no
# previous version is an unrecoverable loss of the ability to destroy.
gcloud storage buckets update "gs://${BUCKET}" --versioning

echo "Done. Put this in terraform/envs/<env>.backend.hcl:"
echo "  bucket = \"${BUCKET}\""
