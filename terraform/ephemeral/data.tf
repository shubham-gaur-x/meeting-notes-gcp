# Durable resources are read by NAME, not through terraform_remote_state.
#
# This is deliberate. Remote state would couple the two modules: a durable
# refactor could break an ephemeral plan, and the ephemeral module would need
# read access to the durable state. Name lookups keep the coupling to a naming
# convention (var.name_prefix), which is already the thing both modules agree on.
#
# If any of these lookups fails, the durable module has not been applied yet.
# That is the correct failure and the error message says so plainly.

data "google_compute_network" "vpc" {
  name = "${var.name_prefix}-vpc"
}

data "google_compute_subnetwork" "subnet" {
  name   = "${var.name_prefix}-subnet"
  region = var.region
}

data "google_service_account" "memgraph" {
  account_id = "${var.name_prefix}-memgraph"
}

data "google_storage_bucket" "backups" {
  name = "${var.project_id}-backups"
}
