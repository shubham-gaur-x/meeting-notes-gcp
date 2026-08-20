# One Docker repo for both the API image and the job images (ARCHITECTURE §4).
# Durable: images survive a sync-down so the next sync-up does not rebuild.
resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = var.name_prefix
  format        = "DOCKER"
  description   = "Container images for the meeting-notes API and Cloud Run jobs"

  depends_on = [google_project_service.enabled]
}
