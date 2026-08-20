# One service account per workload, no shared default SA (ARCHITECTURE §4).
# Created in Phase 1 even though the workloads land in Phases 5-8: IAM
# propagation is slow and a missing binding is discovered late and painfully.

resource "google_service_account" "pipeline" {
  account_id   = "${var.name_prefix}-pipeline"
  display_name = "Cloud Run jobs: connectors and pipeline_drain"

  depends_on = [google_project_service.enabled]
}

resource "google_service_account" "api" {
  account_id   = "${var.name_prefix}-api"
  display_name = "Cloud Run service: FastAPI query layer"

  depends_on = [google_project_service.enabled]
}

resource "google_service_account" "memgraph" {
  account_id   = "${var.name_prefix}-memgraph"
  display_name = "Memgraph GCE VM"

  depends_on = [google_project_service.enabled]
}

# ─── pipeline: reads secrets, talks to Cloud SQL, pulls Pub/Sub, calls Vertex ──
locals {
  pipeline_roles = [
    "roles/cloudsql.client",
    "roles/secretmanager.secretAccessor",
    "roles/pubsub.subscriber",
    "roles/aiplatform.user",
    "roles/logging.logWriter",
  ]

  api_roles = [
    "roles/cloudsql.client",
    "roles/secretmanager.secretAccessor",
    "roles/aiplatform.user",
    "roles/logging.logWriter",
  ]

  # The VM writes logs and reads its own secrets. It does NOT get
  # cloudsql.client: Memgraph never talks to Postgres.
  memgraph_roles = [
    "roles/secretmanager.secretAccessor",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
  ]
}

resource "google_project_iam_member" "pipeline" {
  for_each = toset(local.pipeline_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_project_iam_member" "api" {
  for_each = toset(local.api_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "memgraph" {
  for_each = toset(local.memgraph_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.memgraph.email}"
}

# The pipeline SA writes Cloud SQL exports into the backup bucket on sync-down.
# Bucket-scoped rather than project-scoped: it has no business in any other bucket.
resource "google_storage_bucket_iam_member" "pipeline_backups" {
  bucket = google_storage_bucket.backups.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.pipeline.email}"
}
