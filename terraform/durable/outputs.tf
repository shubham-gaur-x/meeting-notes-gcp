# These are what a human needs after an apply. The ephemeral module does NOT
# consume them — it looks resources up by name with data sources, so the two
# states stay decoupled and neither can break the other.

output "vpc_name" {
  description = "VPC the Memgraph VM attaches to."
  value       = google_compute_network.vpc.name
}

output "subnet_name" {
  description = "Subnet the Memgraph VM attaches to."
  value       = google_compute_subnetwork.subnet.name
}

output "backup_bucket" {
  description = "Bucket holding Cloud SQL exports. scripts/sync.py writes here."
  value       = google_storage_bucket.backups.name
}

output "artifact_registry" {
  description = "Docker repo URL for image pushes."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "pipeline_service_account" {
  description = "Service account for Cloud Run jobs."
  value       = google_service_account.pipeline.email
}

output "api_service_account" {
  description = "Service account for the Cloud Run API service."
  value       = google_service_account.api.email
}

output "memgraph_service_account" {
  description = "Service account attached to the Memgraph VM."
  value       = google_service_account.memgraph.email
}
