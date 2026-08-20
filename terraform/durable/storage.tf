# Where Cloud SQL exports land on sync-down. This bucket is the ONLY thing
# bridging data across a teardown, so it is durable, versioned, and NOT
# force_destroy — an accidental `terraform destroy` here would silently discard
# every backup (ADR-016).
resource "google_storage_bucket" "backups" {
  name     = "${var.project_id}-backups"
  location = var.region

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  force_destroy = false

  versioning {
    enabled = true
  }

  # 90 days is well beyond the monthly sync cadence this project is built for,
  # while keeping storage cost in the cents.
  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }

  # Old non-current versions are pure insurance against a corrupted export;
  # two weeks is enough to notice and recover.
  lifecycle_rule {
    condition {
      days_since_noncurrent_time = 14
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.enabled]
}
