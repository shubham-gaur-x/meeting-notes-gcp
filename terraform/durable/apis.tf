# Every API the project needs, enabled in code rather than by hand.
#
# disable_on_destroy is false throughout: destroying the durable module should
# never turn off an API that another module or a half-torn-down resource still
# depends on. Leaving an API enabled costs nothing.
locals {
  required_apis = [
    # Needed for data.google_project lookups (budget.tf resolves the project
    # number for the budget filter). Discovered live: not obvious up front
    # because most resources don't need it directly, only this one data source.
    "cloudresourcemanager.googleapis.com",
    # Needed for the service accounts in iam.tf. Discovered live: creating a
    # service account can succeed even while this is disabled, but a later
    # read/refresh of that same resource then 403s — enable it up front.
    "iam.googleapis.com",
    "compute.googleapis.com",
    "sqladmin.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "cloudscheduler.googleapis.com",
    "aiplatform.googleapis.com",
    "billingbudgets.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "iap.googleapis.com",
    "storage.googleapis.com",
  ]
}

resource "google_project_service" "enabled" {
  for_each = toset(local.required_apis)

  project = var.project_id
  service = each.value

  disable_on_destroy = false
}
