terraform {
  required_version = ">= 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Same bucket, DIFFERENT prefix. Two independent states is the core safety
  # property of ADR-016: `terraform destroy` here cannot reach a durable
  # resource, because no durable resource is in this state file.
  backend "gcs" {
    prefix = "ephemeral"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone

  # See terraform/durable/versions.tf for why this is here: user ADC
  # credentials need an explicit quota project on some APIs, or calls fail
  # with "requires a quota project, which is not set by default".
  user_project_override = true
  billing_project       = var.project_id
}
