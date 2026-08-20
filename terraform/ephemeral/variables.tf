# Identical to terraform/ephemeral/variables.tf by design: one tfvars file feeds
# both modules, and Terraform warns about undeclared variables in a tfvars but
# never about declared-and-unused ones. Keep the two files in sync.

variable "project_id" {
  description = "GCP project that hosts the infrastructure. Never hardcoded."
  type        = string
}

variable "region" {
  description = "Primary region for regional resources."
  type        = string
}

variable "zone" {
  description = "Zone for zonal resources (the Memgraph VM and its disk)."
  type        = string
}

variable "workspace_user" {
  description = "Google Workspace account whose mail and calendar are read. Deliberately a different account from the project owner — see ADR-009."
  type        = string
}

variable "billing_account_id" {
  description = "Billing account the budget alert is attached to."
  type        = string
}

variable "budget_amount_usd" {
  description = "Monthly budget in USD. The alert is created in the first apply, never a later one."
  type        = number
}

variable "budget_alert_threshold_ratio" {
  description = "Fraction of the budget that triggers the first alert."
  type        = number
}

variable "cloudsql_tier" {
  description = "Cloud SQL machine tier. Ephemeral tier — destroyed between sync sessions."
  type        = string
}

variable "memgraph_machine" {
  description = "GCE machine type for Memgraph. Ephemeral tier."
  type        = string
}

variable "memgraph_disk_gb" {
  description = "Size of the Memgraph data disk in GiB."
  type        = number
}

variable "memgraph_image" {
  description = "Memgraph container image. MUST match docker-compose.local.yml or MAGE procedure availability differs between local and deployed."
  type        = string
}

variable "memgraph_restore_snapshot" {
  description = "Snapshot to restore the Memgraph data disk from. Empty string means a fresh, empty disk. scripts/sync.py resolves the latest snapshot and passes it on sync-up."
  type        = string
  default     = ""
}

variable "vertex_chat_model" {
  description = "Vertex AI chat model id. Model names are env vars, never literals — they change."
  type        = string
}

variable "vertex_embedding_model" {
  description = "Vertex AI embedding model id. Must output 768 dimensions to match the Memgraph vector indexes."
  type        = string
}

variable "vertex_location" {
  description = "Region for Vertex AI calls."
  type        = string
}

variable "name_prefix" {
  description = "Prefix for every resource name. The ephemeral module looks durable resources up by name, so this must not drift between modules."
  type        = string
  default     = "meeting-notes"
}
