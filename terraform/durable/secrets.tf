# Secret CONTAINERS only. Versions (the actual values) are added out-of-band by
# `make secrets-put`, deliberately: a secret passed through Terraform is written
# to state in plaintext, and the state bucket would then hold every credential
# in the project.
locals {
  secret_ids = [
    "google-oauth-client-secret",
    "google-refresh-token",
    "postgres-password",
    "memgraph-password",
    "jira-api-token",
    "github-webhook-secret",
  ]
}

resource "google_secret_manager_secret" "secrets" {
  for_each = toset(local.secret_ids)

  secret_id = each.value

  replication {
    auto {}
  }

  depends_on = [google_project_service.enabled]
}
