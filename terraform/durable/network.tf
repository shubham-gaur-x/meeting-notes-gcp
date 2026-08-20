# The VPC lives in the durable tier: it costs nothing, and recreating it on every
# sync-up would churn firewall rules and subnet ranges for no benefit.
#
# An explicit VPC rather than the default network — a project's default network
# depends on how the project was created and on org policy, so relying on it is
# non-deterministic across the personal -> Onix move.

resource "google_compute_network" "vpc" {
  name                    = "${var.name_prefix}-vpc"
  auto_create_subnetworks = false

  depends_on = [google_project_service.enabled]
}

resource "google_compute_subnetwork" "subnet" {
  name          = "${var.name_prefix}-subnet"
  ip_cidr_range = "10.20.0.0/24"
  region        = var.region
  network       = google_compute_network.vpc.id

  # Lets the Memgraph VM reach Google APIs without a public route.
  private_ip_google_access = true
}

# Bolt (7687) is NEVER exposed to the internet. Access is via IAP TCP forwarding:
#   gcloud compute start-iap-tunnel memgraph 7687 --local-host-port=localhost:7687
# 35.235.240.0/20 is Google's fixed IAP forwarding range.
resource "google_compute_firewall" "allow_iap" {
  name    = "${var.name_prefix}-allow-iap"
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["22", "7687", "7444", "3000"]
  }

  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["${var.name_prefix}-memgraph"]
}

resource "google_compute_firewall" "allow_internal" {
  name    = "${var.name_prefix}-allow-internal"
  network = google_compute_network.vpc.name

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }

  source_ranges = [google_compute_subnetwork.subnet.ip_cidr_range]
}
