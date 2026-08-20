terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  # Bucket is supplied at init time via -backend-config, because a backend
  # block cannot interpolate variables and CLAUDE.md forbids hardcoding a
  # project-derived name. See terraform/envs/*.backend.example.hcl.
  backend "gcs" {
    prefix = "durable"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone

  # Some APIs (billingbudgets.googleapis.com among them) reject calls made
  # with user Application Default Credentials unless the provider explicitly
  # attaches a quota project via the X-Goog-User-Project header. Without
  # this, google_billing_budget fails with "requires a quota project, which
  # is not set by default" even though ADC itself has one on record.
  user_project_override = true
  billing_project       = var.project_id
}
