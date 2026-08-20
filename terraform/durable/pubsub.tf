# Target for Google Workspace Events (Meet transcripts). Durable because the
# subscription retains undelivered messages across a sync-down — transcripts
# published while the system is torn down are still there on the next sync-up.
resource "google_pubsub_topic" "meet_transcripts" {
  name = "meet-transcripts"

  depends_on = [google_project_service.enabled]
}

# PULL, not push: no inbound endpoint needed, and it is the pattern v5 proved.
resource "google_pubsub_subscription" "meet_transcripts" {
  name  = "meet-transcripts-sub"
  topic = google_pubsub_topic.meet_transcripts.id

  # 7 days is the Pub/Sub maximum and the whole point of putting this in the
  # durable tier — a month-long gap will still lose messages older than a week,
  # which is acceptable: Meet transcripts are also retrievable from the API.
  message_retention_duration = "604800s"
  ack_deadline_seconds       = 60

  expiration_policy {
    ttl = "" # never expire
  }
}
