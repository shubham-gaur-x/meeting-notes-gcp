# EPHEMERAL. ~$40/mo at e2-medium if left running; $0 when destroyed.
#
# The DATA disk is separate from the boot disk so that sync-down snapshots only
# the graph, not a Debian install. Snapshots are incremental and small, and
# restore is a disk create rather than a VM image build.

resource "google_compute_disk" "memgraph_data" {
  name = "${var.name_prefix}-memgraph-data"
  type = "pd-balanced"
  zone = var.zone
  size = var.memgraph_disk_gb

  # Empty string means a fresh, empty disk — the first-ever sync-up. Otherwise
  # scripts/sync.py has resolved the most recent snapshot and passed it here.
  # This is a variable rather than a `most_recent` data source precisely because
  # a data source would fail on that first run, when no snapshot exists.
  snapshot = var.memgraph_restore_snapshot != "" ? var.memgraph_restore_snapshot : null

  lifecycle {
    # Changing the restore snapshot must NOT silently rebuild a live disk.
    # sync-up creates this disk fresh anyway; sync-down destroys it.
    ignore_changes = [snapshot]
  }
}

resource "google_compute_instance" "memgraph" {
  name         = "${var.name_prefix}-memgraph"
  machine_type = var.memgraph_machine
  zone         = var.zone

  tags = ["${var.name_prefix}-memgraph"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 20
      type  = "pd-balanced"
    }
  }

  attached_disk {
    source      = google_compute_disk.memgraph_data.id
    device_name = "memgraph-data"
    mode        = "READ_WRITE"
  }

  network_interface {
    network    = data.google_compute_network.vpc.id
    subnetwork = data.google_compute_subnetwork.subnet.id

    # An ephemeral external IP, purely so the VM can pull container images from
    # Docker Hub. NOTHING can reach it: the only firewall rule targeting this
    # instance allows ingress from Google's IAP range alone. Cloud NAT would be
    # the textbook alternative but costs ~$32/mo and would have to live in the
    # durable tier, defeating the point.
    access_config {}
  }

  service_account {
    email  = data.google_service_account.memgraph.email
    scopes = ["cloud-platform"]
  }

  metadata_startup_script = templatefile("${path.module}/startup.sh", {
    memgraph_image = var.memgraph_image
  })

  # Terraform reports this ready as soon as the Compute API says RUNNING —
  # about two minutes before Docker has finished pulling the images. There is
  # no Terraform-side wait for that, so scripts/sync.py polls the serial
  # console for the marker startup.sh echoes on completion, and `sync-up` does
  # not claim the tier is serving until it appears.
  allow_stopping_for_update = true
}
