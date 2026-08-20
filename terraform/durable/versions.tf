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
}
