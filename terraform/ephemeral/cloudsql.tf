# EPHEMERAL. Destroyed by `make sync-down`, recreated by `make sync-up`.
# ~$13/mo at db-f1-micro if left running; $0 when destroyed (ADR-016).
#
# Public IP with NO authorized networks. Access is exclusively through the Cloud
# SQL Python connector, which authenticates with IAM and encrypts with TLS — so
# there is no IP allowlist to maintain and no 0.0.0.0/0 anywhere. Private IP was
# rejected for this tier: it requires a service-networking peering connection
# that is slow to create and a frequent cause of destroy failures, which is a
# poor trade for a resource destroyed monthly.

resource "random_password" "postgres" {
  length  = 32
  special = true

  # Regenerating this on every sync-up would be fine (the instance is new), but
  # keeping it stable means .env does not change between sessions.
  keepers = {
    instance = "${var.name_prefix}-pg"
  }
}

resource "google_sql_database_instance" "postgres" {
  name             = "${var.name_prefix}-pg"
  database_version = "POSTGRES_15"
  region           = var.region

  # The instance is recreated from an export on every sync-up, so protection
  # against accidental deletion would fight the intended lifecycle.
  deletion_protection = false

  settings {
    tier              = var.cloudsql_tier
    availability_type = "ZONAL"
    disk_size         = 10
    disk_type         = "PD_HDD"
    disk_autoresize   = true

    ip_configuration {
      ipv4_enabled = true
      # Deliberately empty: the Cloud SQL connector needs no allowlist.
      ssl_mode = "ENCRYPTED_ONLY"
    }

    # No automated backups. Under ADR-016 the instance does not live long
    # enough for a backup window to fire, and sync-down takes an explicit
    # export to GCS instead — which is what actually survives the teardown.
    backup_configuration {
      enabled = false
    }

    insights_config {
      query_insights_enabled = false
    }
  }
}

resource "google_sql_database" "meeting_memory" {
  name     = "meeting_memory"
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "app" {
  name     = "meeting_notes"
  instance = google_sql_database_instance.postgres.name
  password = random_password.postgres.result
}

# `gcloud sql export` writes to GCS as the Cloud SQL INSTANCE's own service
# account, not as whatever IAM identity is running the export command. That
# identity is per-instance and re-generated every time this instance is
# recreated (every sync-up), so this grant lives here — bound to
# service_account_email_address — rather than as a static durable-tier
# binding for a service account that would not survive the next teardown.
# Discovered live: sync-down's first real run failed at the export step with
# "service account does not have the required permissions for the bucket".
resource "google_storage_bucket_iam_member" "cloudsql_export" {
  bucket = data.google_storage_bucket.backups.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_sql_database_instance.postgres.service_account_email_address}"
}
