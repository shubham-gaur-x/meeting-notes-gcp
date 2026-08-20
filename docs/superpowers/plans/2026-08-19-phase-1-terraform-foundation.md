# Phase 1 Terraform Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up every GCP resource in Terraform, split into a durable tier that lives permanently and an ephemeral tier that exists only while syncing, with `make sync-up` / `make sync-down` as the lifecycle and proven data survival across the gap.

**Architecture:** Two independent Terraform root modules. `terraform/durable/` holds everything cheap-to-free when idle — VPC, Artifact Registry, Secret Manager, service accounts, Pub/Sub, the backup bucket, the budget alert. `terraform/ephemeral/` holds only the two resources that bill 24/7 — the Cloud SQL instance and the Memgraph GCE VM — and is destroyed between sessions. The ephemeral module reads durable resources through **data sources looked up by name**, not `terraform_remote_state`, so the two states stay fully decoupled and `terraform destroy` in `ephemeral/` is physically incapable of touching a durable resource. `scripts/sync.py` orchestrates the lifecycle and is the only piece with real test coverage, because it is the only piece that can destroy data.

**Tech Stack:** Terraform ≥1.9 · `hashicorp/google` provider ≥6.0 · Python 3.11+ · `pytest` · gcloud CLI

## Global Constraints

Copied verbatim from `CLAUDE.md`, `ARCHITECTURE.md`, and ADR-016.

- **DO NOT create GCP resources by hand. Everything is Terraform.**
- **DO NOT hardcode a project ID, region, bucket name, or account email anywhere.** All of it comes from `terraform/envs/*.tfvars` and, at runtime, from environment variables.
- **DO NOT hardcode any secret or API key.** Secret Manager, injected as env. Terraform creates secret *containers*; values are added out-of-band by `make secrets-put` so no secret ever enters Terraform state.
- **DO NOT commit `.env`, a token file, a service-account key, or a `.tfvars` containing secrets.**
- Type hints on **all** Python function signatures (`mypy --disallow-untyped-defs` runs over `scripts/`).
- `ruff` line-length is **110**, target `py311`.
- Tests are mocked — the suite must run with no live GCP, no database, no LLM. A test requiring live credentials is a broken test.
- Structured logging with `structlog`. **Never pass `event=` as a kwarg.**
- Do not read `os.environ` outside `config.py` — `scripts/sync.py` is a Phase 1 script predating `config.py`, the same documented exception as `auth_spike.py` and `doctor.py`; it takes `env` as a parameter.
- The Memgraph image tag in Terraform **must** equal the tag in `docker-compose.local.yml` (`memgraph/memgraph-mage:3.11.0`), or MAGE procedure availability differs between local and deployed.
- Every `make doctor` FAIL carries a runnable remediation.

## Cost basis

Verified against the live Cloud Billing Catalog API on 2026-08-19, not estimated (ADR-016):

| Resource | Rate | If left running |
|---|---|---|
| `e2-medium` | $0.021812/vCPU-hr + $0.002924/GiB-hr | ~$40/mo |
| Cloud SQL `db-f1-micro` (zonal, PG) | $0.018/hr | ~$13/mo |
| Balanced PD | $0.10/GiB-mo | $5/mo at 50GiB |
| Artifact Registry | $0.10/GiB-mo | ~$0 |
| Cloud Scheduler | 3 jobs free, then $0.10/job-mo | $0 |
| Snapshot storage (`us-central1`) | $0.04/GiB-mo standard | cents |
| GCS standard storage | ~$0.02/GiB-mo | cents |

The ephemeral tier is ~$58/mo if left up and **$0 when destroyed**. The durable tier is cents per month. This asymmetry is the entire justification for ADR-016.

## Scope note

This plan builds Phase 1 of `docs/PHASE_PLAN.md` only. **No Cloud Run services or jobs are created here** — there is no application to deploy until Phases 5–8, and an empty Cloud Run job is not worth the Terraform. The service accounts those workloads will use *are* created now, because IAM propagation is slow and getting it wrong is discovered late.

Cloud Scheduler jobs are likewise deferred to Phase 5: a schedule that fires against a nonexistent job is worse than no schedule, and under ADR-016 the system is not up on a schedule anyway.

---

## File Structure

| File | Responsibility |
|---|---|
| `terraform/durable/versions.tf` | Provider + Terraform version pins, GCS backend. |
| `terraform/durable/variables.tf` | Full variable set (identical to ephemeral's, so one tfvars serves both). |
| `terraform/durable/apis.tf` | `google_project_service` for every API the project needs. |
| `terraform/durable/network.tf` | VPC, subnet, IAP-only firewall rules. |
| `terraform/durable/registry.tf` | Artifact Registry Docker repo. |
| `terraform/durable/storage.tf` | Backup bucket for SQL exports. |
| `terraform/durable/secrets.tf` | Secret Manager secret containers (no versions). |
| `terraform/durable/iam.tf` | Service accounts + least-privilege role bindings. |
| `terraform/durable/pubsub.tf` | Meet transcripts topic + pull subscription. |
| `terraform/durable/budget.tf` | Email notification channel + billing budget. |
| `terraform/durable/outputs.tf` | Names the ephemeral module looks up. |
| `terraform/ephemeral/versions.tf` | Provider pins, separate GCS state prefix. |
| `terraform/ephemeral/variables.tf` | Identical to durable's. |
| `terraform/ephemeral/data.tf` | Data-source lookups of durable resources by name. |
| `terraform/ephemeral/cloudsql.tf` | Cloud SQL instance, database, user. |
| `terraform/ephemeral/memgraph.tf` | Data disk, VM, startup script. |
| `terraform/ephemeral/outputs.tf` | Connection details for `sync.py` and `.env`. |
| `terraform/ephemeral/startup.sh` | VM bootstrap — Docker + compose stack. |
| `terraform/envs/personal.backend.example.hcl` | Committed backend template. |
| `terraform/envs/onix.backend.example.hcl` | Committed backend template. |
| `scripts/tf_bootstrap.sh` | Idempotent GCS state-bucket creation. Solves the chicken-and-egg. |
| `scripts/sync.py` | `sync-up` / `sync-down` orchestration. All the dangerous logic. |
| `tests/test_phase01_sync.py` | One test file for the phase, per `CLAUDE.md` convention. |
| `scripts/doctor.py` | Modify: tier-2 ephemeral-tier cost check. |
| `tests/test_phase06_doctor.py` | Modify: tests for the new check. |
| `Makefile` | Modify: `sync-up`, `sync-down`, per-module tf targets. |
| `.gitignore` | Modify: backend config files. |
| `.env.example` | Modify: `GCS_BACKUP_BUCKET`, `MEMGRAPH_HOST` guidance. |
| `docs/SETUP.md` | Modify: tier 2 becomes the sync-session runbook. |
| `docs/ARCHITECTURE.md` | Modify: §4 gains the durable/ephemeral column, §7 rewritten. |
| `README.md` | Modify: tier 2 row reflects sync lifecycle. |

---

### Task 0: Billing gate — BLOCKING, manual, do this first

Phase 0.5 gated everything on a real OAuth token being held in hand. This is the same shape: **no GCP resource in this phase can be created until billing works**, and discovering that during a failed `terraform apply` wastes the whole apply cycle.

**Verified state as of 2026-08-19:**

```
gcloud billing accounts list
  01485E-D2C464-2A6DE4  My Billing Account  OPEN: False

gcloud billing projects describe meeting-notes-gcp-personal
  billingAccountName: ''
  billingEnabled: false
```

The only billing account on `shubham.gaur.x@gmail.com` is **closed**, and the project is **not linked** to any billing account.

- [ ] **Step 1: Confirm the blocker still stands**

```bash
gcloud billing accounts list
```
Expected if still blocked: `OPEN` column reads `False`.

- [ ] **Step 2: Resolve it in the console — this cannot be automated**

Either reopen the closed account or create a new one at
**https://console.cloud.google.com/billing**. A payment method is required. New
Google Cloud customers get $300 in credits valid for 90 days; if this account was
a previously-expired trial, a new account with a real payment method is needed.

- [ ] **Step 3: Link the project to the open billing account**

```bash
gcloud billing projects link meeting-notes-gcp-personal \
  --billing-account=<OPEN_ACCOUNT_ID>
```

- [ ] **Step 4: Verify the gate is passed**

```bash
gcloud billing projects describe meeting-notes-gcp-personal \
  --format='value(billingEnabled)'
```
Expected: `True`. **Do not proceed past Task 1 until this prints `True`.**

- [ ] **Step 5: Record the billing account id**

Put it in `terraform/envs/personal.tfvars` as `billing_account_id`. It is not a
secret — it is an identifier — but the file is gitignored regardless because it
also carries the project id.

**Tasks 1 through 10 can be written and unit-tested with billing still off.** Only
Task 11 (live validation) genuinely requires it. If billing is not resolved today,
build through Task 10, then stop.

---

### Task 1: Terraform tooling and the state bucket

Terraform is not installed on this machine (`terraform version` → `command not found`), and the GCS backend needs a bucket that Terraform itself cannot create — the classic chicken-and-egg. A tiny idempotent shell script owns the bootstrap.

**Files:**
- Create: `scripts/tf_bootstrap.sh`
- Create: `terraform/envs/personal.backend.example.hcl`
- Create: `terraform/envs/onix.backend.example.hcl`
- Modify: `.gitignore`

- [ ] **Step 1: Install Terraform**

HashiCorp moved Terraform to the BUSL license and Homebrew dropped it from
`homebrew-core`; a plain `brew install terraform` returns a fuzzy-match list of
unrelated `terraform-*` tools instead of installing anything. Use HashiCorp's
own tap:

```bash
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
```

- [ ] **Step 2: Verify the install**

```bash
terraform version
```
Expected: `Terraform v1.9.x` or newer on `darwin_arm64`.

- [ ] **Step 3: Write the bootstrap script**

Create `scripts/tf_bootstrap.sh`:

```bash
#!/usr/bin/env bash
# Create the GCS bucket that holds Terraform state.
#
# Terraform cannot create its own backend bucket, so this one resource is
# created with gcloud. It is the ONLY resource in the project not managed by
# Terraform, and it is deliberately outside both module lifecycles: destroying
# the state bucket would strand every other resource.
#
# Idempotent — safe to re-run. Takes the project id as its only argument so
# nothing is hardcoded (CLAUDE.md, "Deployment Context").
set -euo pipefail

PROJECT_ID="${1:?usage: tf_bootstrap.sh <project-id> [region]}"
REGION="${2:-us-central1}"
BUCKET="${PROJECT_ID}-tfstate"

if gcloud storage buckets describe "gs://${BUCKET}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "State bucket gs://${BUCKET} already exists."
  exit 0
fi

echo "Creating state bucket gs://${BUCKET} in ${REGION}..."
gcloud storage buckets create "gs://${BUCKET}" \
  --project="${PROJECT_ID}" \
  --location="${REGION}" \
  --uniform-bucket-level-access \
  --public-access-prevention

# Versioning is not optional. A corrupted or truncated state file with no
# previous version is an unrecoverable loss of the ability to destroy.
gcloud storage buckets update "gs://${BUCKET}" --versioning

echo "Done. Put this in terraform/envs/<env>.backend.hcl:"
echo "  bucket = \"${BUCKET}\""
```

- [ ] **Step 4: Make it executable**

```bash
chmod +x scripts/tf_bootstrap.sh
```

- [ ] **Step 5: Write the backend config templates**

A Terraform `backend` block cannot interpolate variables, so the bucket name has
to arrive via `-backend-config`. Same committed-template pattern as the tfvars.

Create `terraform/envs/personal.backend.example.hcl`:

```hcl
# Template for terraform/envs/personal.backend.hcl.
#
#   cp terraform/envs/personal.backend.example.hcl terraform/envs/personal.backend.hcl
#
# A Terraform backend block cannot use variables, so the bucket name is passed
# with -backend-config at init time. `make tf-init` does this for you.
#
# The bucket is created by scripts/tf_bootstrap.sh, not by Terraform — Terraform
# cannot create its own state backend. The real .backend.hcl is gitignored
# because the bucket name embeds the project id.

bucket = "your-project-id-tfstate"
```

Create `terraform/envs/onix.backend.example.hcl`:

```hcl
# Template for terraform/envs/onix.backend.hcl — the Onix-owned GCP project.
#
#   cp terraform/envs/onix.backend.example.hcl terraform/envs/onix.backend.hcl
#
# Phase 10. See terraform/envs/personal.backend.example.hcl for the reasoning.

bucket = "onix-project-id-tfstate"
```

- [ ] **Step 6: Keep real backend configs out of git**

In `.gitignore`, extend the Terraform block. Replace:

```
override.tf
override.tf.json
```

with:

```
override.tf
override.tf.json
# Backend configs embed the project-derived bucket name, same reasoning as
# *.tfvars above: the example is committed, the real file is not.
*.backend.hcl
!terraform/envs/*.backend.example.hcl
```

- [ ] **Step 7: Verify the ignore rules do what they claim**

```bash
git check-ignore -v terraform/envs/personal.backend.hcl
git check-ignore terraform/envs/personal.backend.example.hcl; echo "exit=$? (1 = committable)"
```
Expected: the first prints a matching rule; the second prints `exit=1`.

- [ ] **Step 8: Commit**

```bash
git add scripts/tf_bootstrap.sh terraform/envs/*.backend.example.hcl .gitignore
git commit -m "Phase 1: terraform state bucket bootstrap and backend templates"
```

---

### Task 2: Durable module — skeleton, APIs, network

**Files:**
- Create: `terraform/durable/versions.tf`, `terraform/durable/variables.tf`, `terraform/durable/apis.tf`, `terraform/durable/network.tf`

**Interfaces:**
- Produces: VPC named `${var.name_prefix}-vpc`, subnet `${var.name_prefix}-subnet`, firewall rules `${var.name_prefix}-allow-iap` and `${var.name_prefix}-allow-internal`. Task 6 looks these up by name.

- [ ] **Step 1: Provider and backend pins**

Create `terraform/durable/versions.tf`:

```hcl
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
```

- [ ] **Step 2: Variables**

Create `terraform/durable/variables.tf`. This file is **byte-identical** to
`terraform/ephemeral/variables.tf` in Task 5 — that is deliberate, so a single
`envs/<env>.tfvars` serves both modules without "value for undeclared variable"
warnings. Terraform does not warn about declared-but-unused variables.

```hcl
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
```

- [ ] **Step 3: Enable the APIs**

Create `terraform/durable/apis.tf`:

```hcl
# Every API the project needs, enabled in code rather than by hand.
#
# disable_on_destroy is false throughout: destroying the durable module should
# never turn off an API that another module or a half-torn-down resource still
# depends on. Leaving an API enabled costs nothing.
locals {
  required_apis = [
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
```

- [ ] **Step 4: Network**

Create `terraform/durable/network.tf`:

```hcl
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
```

- [ ] **Step 5: Validate**

```bash
cd terraform/durable && terraform init -backend=false && terraform validate && terraform fmt -check
```
Expected: `Success! The configuration is valid.` and `fmt -check` prints nothing.

`-backend=false` lets validation run with no GCS bucket and no billing — this is
the gate that keeps Tasks 2–6 workable while Task 0 is outstanding.

- [ ] **Step 6: Commit**

```bash
git add terraform/durable/
git commit -m "Phase 1: durable module skeleton, APIs, VPC with IAP-only ingress"
```

---

### Task 3: Durable module — registry, backup bucket, secrets, IAM, Pub/Sub

**Files:**
- Create: `terraform/durable/registry.tf`, `terraform/durable/storage.tf`, `terraform/durable/secrets.tf`, `terraform/durable/iam.tf`, `terraform/durable/pubsub.tf`, `terraform/durable/outputs.tf`

**Interfaces:**
- Produces: Artifact Registry repo `${var.name_prefix}`, bucket `${var.project_id}-backups`, service accounts `${var.name_prefix}-pipeline` / `-api` / `-memgraph`, Pub/Sub topic `meet-transcripts`. Task 6 and `scripts/sync.py` look these up by name.

- [ ] **Step 1: Artifact Registry**

Create `terraform/durable/registry.tf`:

```hcl
# One Docker repo for both the API image and the job images (ARCHITECTURE §4).
# Durable: images survive a sync-down so the next sync-up does not rebuild.
resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = var.name_prefix
  format        = "DOCKER"
  description   = "Container images for the meeting-notes API and Cloud Run jobs"

  depends_on = [google_project_service.enabled]
}
```

- [ ] **Step 2: Backup bucket**

Create `terraform/durable/storage.tf`:

```hcl
# Where Cloud SQL exports land on sync-down. This bucket is the ONLY thing
# bridging data across a teardown, so it is durable, versioned, and NOT
# force_destroy — an accidental `terraform destroy` here would silently discard
# every backup (ADR-016).
resource "google_storage_bucket" "backups" {
  name     = "${var.project_id}-backups"
  location = var.region

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  force_destroy = false

  versioning {
    enabled = true
  }

  # 90 days is well beyond the monthly sync cadence this project is built for,
  # while keeping storage cost in the cents.
  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }

  # Old non-current versions are pure insurance against a corrupted export;
  # two weeks is enough to notice and recover.
  lifecycle_rule {
    condition {
      days_since_noncurrent_time = 14
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.enabled]
}
```

- [ ] **Step 3: Secret containers**

Create `terraform/durable/secrets.tf`:

```hcl
# Secret CONTAINERS only. Versions (the actual values) are added out-of-band by
# `make secrets-put`, deliberately: a secret passed through Terraform is written
# to state in plaintext, and the state bucket would then hold every credential
# in the project.
locals {
  secret_ids = [
    "google-oauth-client-secret",
    "google-refresh-token",
    "postgres-password",
    "memgraph-password",
    "jira-api-token",
    "github-webhook-secret",
  ]
}

resource "google_secret_manager_secret" "secrets" {
  for_each = toset(local.secret_ids)

  secret_id = each.value

  replication {
    auto {}
  }

  depends_on = [google_project_service.enabled]
}
```

- [ ] **Step 4: Service accounts and least-privilege IAM**

Create `terraform/durable/iam.tf`:

```hcl
# One service account per workload, no shared default SA (ARCHITECTURE §4).
# Created in Phase 1 even though the workloads land in Phases 5-8: IAM
# propagation is slow and a missing binding is discovered late and painfully.

resource "google_service_account" "pipeline" {
  account_id   = "${var.name_prefix}-pipeline"
  display_name = "Cloud Run jobs: connectors and pipeline_drain"

  depends_on = [google_project_service.enabled]
}

resource "google_service_account" "api" {
  account_id   = "${var.name_prefix}-api"
  display_name = "Cloud Run service: FastAPI query layer"

  depends_on = [google_project_service.enabled]
}

resource "google_service_account" "memgraph" {
  account_id   = "${var.name_prefix}-memgraph"
  display_name = "Memgraph GCE VM"

  depends_on = [google_project_service.enabled]
}

# ─── pipeline: reads secrets, talks to Cloud SQL, pulls Pub/Sub, calls Vertex ──
locals {
  pipeline_roles = [
    "roles/cloudsql.client",
    "roles/secretmanager.secretAccessor",
    "roles/pubsub.subscriber",
    "roles/aiplatform.user",
    "roles/logging.logWriter",
  ]

  api_roles = [
    "roles/cloudsql.client",
    "roles/secretmanager.secretAccessor",
    "roles/aiplatform.user",
    "roles/logging.logWriter",
  ]

  # The VM writes logs and reads its own secrets. It does NOT get
  # cloudsql.client: Memgraph never talks to Postgres.
  memgraph_roles = [
    "roles/secretmanager.secretAccessor",
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
  ]
}

resource "google_project_iam_member" "pipeline" {
  for_each = toset(local.pipeline_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.pipeline.email}"
}

resource "google_project_iam_member" "api" {
  for_each = toset(local.api_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "memgraph" {
  for_each = toset(local.memgraph_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.memgraph.email}"
}

# The pipeline SA writes Cloud SQL exports into the backup bucket on sync-down.
# Bucket-scoped rather than project-scoped: it has no business in any other bucket.
resource "google_storage_bucket_iam_member" "pipeline_backups" {
  bucket = google_storage_bucket.backups.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.pipeline.email}"
}
```

- [ ] **Step 5: Pub/Sub**

Create `terraform/durable/pubsub.tf`:

```hcl
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
```

- [ ] **Step 6: Outputs**

Create `terraform/durable/outputs.tf`:

```hcl
# These are what a human needs after an apply. The ephemeral module does NOT
# consume them — it looks resources up by name with data sources, so the two
# states stay decoupled and neither can break the other.

output "vpc_name" {
  description = "VPC the Memgraph VM attaches to."
  value       = google_compute_network.vpc.name
}

output "subnet_name" {
  description = "Subnet the Memgraph VM attaches to."
  value       = google_compute_subnetwork.subnet.name
}

output "backup_bucket" {
  description = "Bucket holding Cloud SQL exports. scripts/sync.py writes here."
  value       = google_storage_bucket.backups.name
}

output "artifact_registry" {
  description = "Docker repo URL for image pushes."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "pipeline_service_account" {
  description = "Service account for Cloud Run jobs."
  value       = google_service_account.pipeline.email
}

output "api_service_account" {
  description = "Service account for the Cloud Run API service."
  value       = google_service_account.api.email
}

output "memgraph_service_account" {
  description = "Service account attached to the Memgraph VM."
  value       = google_service_account.memgraph.email
}
```

- [ ] **Step 7: Validate**

```bash
cd terraform/durable && terraform validate && terraform fmt -check
```
Expected: `Success! The configuration is valid.`

- [ ] **Step 8: Commit**

```bash
git add terraform/durable/
git commit -m "Phase 1: durable registry, backup bucket, secrets, service accounts, pubsub"
```

---

### Task 4: Durable module — budget alert

`ARCHITECTURE.md` §4 says "**Set this in Phase 1.**" It is the cheapest insurance in the project and the one resource whose absence is only noticed via a bill.

**Files:**
- Create: `terraform/durable/budget.tf`

**Interfaces:**
- Consumes: `var.billing_account_id`, `var.budget_amount_usd`, `var.budget_alert_threshold_ratio`, `var.workspace_user` (Task 2's variables).

- [ ] **Step 1: Notification channel and budget**

Create `terraform/durable/budget.tf`:

```hcl
# A budget alert that emails on threshold breach. Created in the FIRST apply,
# not a later one — the whole point is to catch a surprise before it is a bill.
#
# Under ADR-016 the ephemeral tier should be down most of the month, so a breach
# here usually means one thing: a sync-down was skipped or failed and Cloud SQL
# plus the Memgraph VM have been running unattended.

resource "google_monitoring_notification_channel" "budget_email" {
  display_name = "meeting-notes budget alert"
  type         = "email"

  labels = {
    email_address = var.workspace_user
  }

  depends_on = [google_project_service.enabled]
}

resource "google_billing_budget" "monthly" {
  billing_account = var.billing_account_id
  display_name    = "${var.name_prefix} monthly budget"

  # Scope the budget to THIS project. The billing account may pay for others,
  # and an alert that fires on someone else's spend is an alert you learn to
  # ignore.
  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.budget_amount_usd)
    }
  }

  # Early warning, then at-budget, then over. The first is the one that matters:
  # it is the "you left the stack up" signal.
  threshold_rules {
    threshold_percent = var.budget_alert_threshold_ratio
  }

  threshold_rules {
    threshold_percent = 1.0
  }

  threshold_rules {
    threshold_percent = 1.2
  }

  all_updates_rule {
    monitoring_notification_channels = [
      google_monitoring_notification_channel.budget_email.id,
    ]
    disable_default_iam_recipients = false
  }

  depends_on = [google_project_service.enabled]
}

# budget_filter.projects wants the project NUMBER, not the id.
data "google_project" "this" {
  project_id = var.project_id
}
```

- [ ] **Step 2: Validate**

```bash
cd terraform/durable && terraform validate && terraform fmt -check
```
Expected: `Success! The configuration is valid.`

- [ ] **Step 3: Commit**

```bash
git add terraform/durable/budget.tf
git commit -m "Phase 1: budget alert with email notification channel"
```

---

### Task 5: Ephemeral module — skeleton and Cloud SQL

**Files:**
- Create: `terraform/ephemeral/versions.tf`, `terraform/ephemeral/variables.tf`, `terraform/ephemeral/data.tf`, `terraform/ephemeral/cloudsql.tf`

**Interfaces:**
- Consumes: durable resources by name — VPC `${var.name_prefix}-vpc`, subnet `${var.name_prefix}-subnet`, service account `${var.name_prefix}-memgraph@...`.
- Produces: Cloud SQL instance named `${var.name_prefix}-pg`, database `meeting_memory`, user `meeting_notes`.

- [ ] **Step 1: Provider pins with a separate state prefix**

Create `terraform/ephemeral/versions.tf`:

```hcl
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
}
```

- [ ] **Step 2: Variables**

Copy `terraform/durable/variables.tf` to `terraform/ephemeral/variables.tf` verbatim.

```bash
cp terraform/durable/variables.tf terraform/ephemeral/variables.tf
```

- [ ] **Step 3: Look durable resources up by name**

Create `terraform/ephemeral/data.tf`:

```hcl
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
```

- [ ] **Step 4: Cloud SQL**

Create `terraform/ephemeral/cloudsql.tf`:

```hcl
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
```

- [ ] **Step 5: Validate**

```bash
cd terraform/ephemeral && terraform init -backend=false && terraform validate && terraform fmt -check
```
Expected: `Success! The configuration is valid.`

- [ ] **Step 6: Commit**

```bash
git add terraform/ephemeral/
git commit -m "Phase 1: ephemeral module skeleton and Cloud SQL instance"
```

---

### Task 6: Ephemeral module — Memgraph disk, VM, bootstrap

**Files:**
- Create: `terraform/ephemeral/memgraph.tf`, `terraform/ephemeral/startup.sh`, `terraform/ephemeral/outputs.tf`

**Interfaces:**
- Consumes: `data.google_compute_network.vpc`, `data.google_compute_subnetwork.subnet`, `data.google_service_account.memgraph` (Task 5), `var.memgraph_restore_snapshot` (Task 2).
- Produces: outputs `cloudsql_connection_name`, `memgraph_internal_ip`, `memgraph_disk_name`, `postgres_password` (sensitive) — consumed by `scripts/sync.py` and by the developer's `.env`.

- [ ] **Step 1: Disk and VM**

Create `terraform/ephemeral/memgraph.tf`:

```hcl
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

  # Terraform reports the VM ready as soon as the API says RUNNING, which is
  # well before Docker has pulled the images. scripts/sync.py polls Bolt.
  allow_stopping_for_update = true
}
```

- [ ] **Step 2: The bootstrap script**

Create `terraform/ephemeral/startup.sh`:

```bash
#!/usr/bin/env bash
# Memgraph VM bootstrap. Runs on every boot; idempotent throughout.
#
# Mirrors docker-compose.local.yml so local and deployed behave identically —
# the image tag is passed in from Terraform, which takes it from the same
# variable the local compose file pins (CLAUDE.md: MAGE procedure availability
# must not differ between environments).
set -euo pipefail

DATA_DEVICE="/dev/disk/by-id/google-memgraph-data"
MOUNT_POINT="/var/lib/memgraph"

# ─── Format the data disk on first boot only ─────────────────────────────────
# blkid returns non-zero on an unformatted device. Formatting an already-
# formatted disk would destroy a restored snapshot, so this check is critical.
if ! blkid "$${DATA_DEVICE}" >/dev/null 2>&1; then
  echo "Data disk is blank — formatting ext4."
  mkfs.ext4 -m 0 -F -E lazy_itable_init=0,lazy_journal_init=0,discard "$${DATA_DEVICE}"
else
  echo "Data disk already has a filesystem — leaving it alone."
fi

mkdir -p "$${MOUNT_POINT}"
if ! mountpoint -q "$${MOUNT_POINT}"; then
  mount -o discard,defaults "$${DATA_DEVICE}" "$${MOUNT_POINT}"
fi
grep -q "$${DATA_DEVICE}" /etc/fstab || \
  echo "$${DATA_DEVICE} $${MOUNT_POINT} ext4 discard,defaults,nofail 0 2" >> /etc/fstab

# Memgraph runs as uid 101 in the official image.
chown -R 101:101 "$${MOUNT_POINT}"

# ─── Docker ───────────────────────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
  apt-get update
  apt-get install -y ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg | \
    gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/debian $(. /etc/os-release && echo "$${VERSION_CODENAME}") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

systemctl enable --now docker

# ─── The stack ────────────────────────────────────────────────────────────────
mkdir -p /opt/memgraph
cat > /opt/memgraph/docker-compose.yml <<'COMPOSE'
services:
  memgraph:
    image: ${memgraph_image}
    container_name: memgraph
    restart: unless-stopped
    ports:
      - "7687:7687"
      - "7444:7444"
    volumes:
      - /var/lib/memgraph:/var/lib/memgraph
    command: ["--log-level=WARNING"]

  lab:
    image: memgraph/lab:3.11.0
    container_name: memgraph-lab
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      QUICK_CONNECT_MG_HOST: memgraph
      QUICK_CONNECT_MG_PORT: "7687"
    depends_on:
      - memgraph
COMPOSE

cd /opt/memgraph
docker compose up -d

echo "Memgraph bootstrap complete."
```

Note the `$${VAR}` escaping: this file is rendered through `templatefile()`, so a
literal `$` in shell must be doubled. Only `${memgraph_image}` is interpolated by
Terraform.

- [ ] **Step 3: Outputs**

Create `terraform/ephemeral/outputs.tf`:

```hcl
output "cloudsql_connection_name" {
  description = "project:region:instance — goes in .env as CLOUD_SQL_CONNECTION_NAME."
  value       = google_sql_database_instance.postgres.connection_name
}

output "cloudsql_public_ip" {
  description = "Public IP of the instance. Only reachable via the Cloud SQL connector — there is no authorized network."
  value       = google_sql_database_instance.postgres.public_ip_address
}

output "postgres_password" {
  description = "Generated app-user password. Put it in Secret Manager with `make secrets-put`."
  value       = random_password.postgres.result
  sensitive   = true
}

output "memgraph_internal_ip" {
  description = "Bolt endpoint, reachable through an IAP tunnel only."
  value       = google_compute_instance.memgraph.network_interface[0].network_ip
}

output "memgraph_instance_name" {
  description = "VM name — scripts/sync.py uses this for IAP tunnels."
  value       = google_compute_instance.memgraph.name
}

output "memgraph_disk_name" {
  description = "Data disk name — scripts/sync.py snapshots this on sync-down."
  value       = google_compute_disk.memgraph_data.name
}
```

- [ ] **Step 4: Validate**

```bash
cd terraform/ephemeral && terraform validate && terraform fmt -check
```
Expected: `Success! The configuration is valid.`

- [ ] **Step 5: Commit**

```bash
git add terraform/ephemeral/
git commit -m "Phase 1: Memgraph VM, data disk with snapshot restore, bootstrap script"
```

---

### Task 7: `scripts/sync.py` — pure logic, TDD

The dangerous part of this phase. `sync-down` destroys billable resources, and the only thing standing between a teardown and permanent data loss is a verification step that must run first. That logic gets real tests; the Terraform does not, because `terraform plan` is its own test.

**Files:**
- Create: `scripts/sync.py`
- Test: `tests/test_phase01_sync.py`

**Interfaces:**
- Produces: `SyncError` (Exception), `export_object_name(now: datetime) -> str`, `snapshot_name(now: datetime) -> str`, `select_latest(items: list[dict[str, str]], key: str, name_field: str) -> str | None`, `backup_uri(bucket: str, obj: str) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_phase01_sync.py`:

```python
"""Phase 1 — sync lifecycle. See docs/DECISIONS.md ADR-016.

Every test runs with no gcloud, no terraform, and no network. Commands are
injected as a callable so the destructive paths are exercised without
destroying anything.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from scripts.sync import (
    SyncError,
    backup_uri,
    export_object_name,
    select_latest,
    snapshot_name,
)

FIXED = datetime(2026, 8, 19, 12, 45, 0, tzinfo=UTC)


def test_export_object_name_is_timestamped_and_sorts_chronologically() -> None:
    earlier = export_object_name(datetime(2026, 8, 19, 1, 0, 0, tzinfo=UTC))
    later = export_object_name(FIXED)
    assert earlier < later, "lexical sort must match chronological order"
    assert later.endswith(".sql.gz")
    assert later.startswith("cloudsql/")


def test_snapshot_name_is_a_legal_gce_resource_name() -> None:
    """GCE names must match [a-z]([-a-z0-9]*[a-z0-9])? and be <= 63 chars."""
    import re

    name = snapshot_name(FIXED)
    assert re.fullmatch(r"[a-z]([-a-z0-9]*[a-z0-9])?", name), name
    assert len(name) <= 63


def test_snapshot_names_sort_chronologically() -> None:
    earlier = snapshot_name(datetime(2026, 8, 19, 1, 0, 0, tzinfo=UTC))
    assert earlier < snapshot_name(FIXED)


def test_select_latest_picks_the_most_recent() -> None:
    items = [
        {"name": "old", "creationTimestamp": "2026-08-01T00:00:00Z"},
        {"name": "newest", "creationTimestamp": "2026-08-19T00:00:00Z"},
        {"name": "middle", "creationTimestamp": "2026-08-10T00:00:00Z"},
    ]
    assert select_latest(items, "creationTimestamp", "name") == "newest"


def test_select_latest_returns_none_on_empty() -> None:
    """The first-ever sync-up has no snapshot and no export. Not an error."""
    assert select_latest([], "creationTimestamp", "name") is None


def test_select_latest_raises_on_a_malformed_record() -> None:
    """A missing timestamp means gcloud changed its output shape. Fail loudly
    rather than silently restoring the wrong backup."""
    with pytest.raises(SyncError):
        select_latest([{"name": "x"}], "creationTimestamp", "name")


def test_backup_uri_builds_a_gs_url() -> None:
    assert backup_uri("proj-backups", "cloudsql/x.sql.gz") == "gs://proj-backups/cloudsql/x.sql.gz"
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/test_phase01_sync.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.sync'`

- [ ] **Step 3: Implement the pure layer**

Create `scripts/sync.py`:

```python
#!/usr/bin/env python3
"""Phase 1 — bring the ephemeral tier up for a sync session, then tear it down.

Under ADR-016 the Cloud SQL instance and the Memgraph VM exist only while
actively syncing. Everything else is durable and cheap. This script owns the
transition in both directions.

    make sync-up     apply the ephemeral tier, restoring the last backup
    make sync-down   back up, VERIFY the backup, then destroy

The verification between "back up" and "destroy" is the whole point. A failed
export that still proceeds to destroy is permanent data loss, so every path to
`terraform destroy` runs through a check that raises rather than returns.

Like scripts/auth_spike.py and scripts/doctor.py, this predates
meeting_notes/config.py and takes its environment as a parameter.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence
from datetime import datetime

# A command runner, injected so tests never invoke gcloud or terraform.
Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]

EXPORT_PREFIX = "cloudsql"
SNAPSHOT_PREFIX = "memgraph-data"


class SyncError(RuntimeError):
    """A sync step failed. Raised rather than returned so no caller can
    accidentally continue to a destructive step after a failure."""


def _stamp(now: datetime) -> str:
    """Compact UTC timestamp. Lowercase so it is legal in a GCE resource name,
    and fixed-width so lexical sort equals chronological sort."""
    return now.strftime("%Y%m%dt%H%M%Sz")


def export_object_name(now: datetime) -> str:
    """GCS object path for a Cloud SQL export."""
    return f"{EXPORT_PREFIX}/meeting-memory-{_stamp(now)}.sql.gz"


def snapshot_name(now: datetime) -> str:
    """GCE snapshot name for the Memgraph data disk.

    Must match [a-z]([-a-z0-9]*[a-z0-9])? and be at most 63 characters.
    """
    return f"{SNAPSHOT_PREFIX}-{_stamp(now)}"


def backup_uri(bucket: str, obj: str) -> str:
    return f"gs://{bucket}/{obj}"


def select_latest(
    items: list[dict[str, str]], key: str, name_field: str
) -> str | None:
    """Name of the most recent item, or None if there are none.

    None is a legitimate answer — the first-ever sync-up has no backup to
    restore. A record missing its timestamp is NOT legitimate: it means the
    gcloud output shape changed, and guessing would restore the wrong backup.
    """
    if not items:
        return None

    try:
        newest = max(items, key=lambda item: item[key])
    except KeyError as exc:
        raise SyncError(
            f"Record is missing {key!r} — gcloud output shape may have changed. "
            f"Refusing to guess which backup is newest."
        ) from exc

    return newest[name_field]
```

- [ ] **Step 4: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/test_phase01_sync.py -v
```
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/sync.py tests/test_phase01_sync.py
git commit -m "Phase 1: sync naming and selection logic"
```

---

### Task 8: `scripts/sync.py` — orchestration and CLI, TDD

**Files:**
- Modify: `scripts/sync.py`
- Test: `tests/test_phase01_sync.py`

**Interfaces:**
- Consumes: everything from Task 7.
- Produces: `run(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]`, `terraform_output(module: str, name: str, *, runner: Runner) -> str`, `sync_down(env_name: str, project_id: str, bucket: str, *, now: datetime, runner: Runner) -> list[str]`, `sync_up(env_name: str, project_id: str, bucket: str, *, runner: Runner) -> list[str]`, `build_parser() -> argparse.ArgumentParser`, `main(argv: list[str] | None = None) -> int`

Each of `sync_down` / `sync_up` returns the list of step descriptions it completed, which is what the tests assert against.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_phase01_sync.py`:

```python
import subprocess

from scripts.sync import sync_down, sync_up


def _ok(stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def _fail(stderr: str = "boom") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=stderr)


class RecordingRunner:
    """Records every command and replays scripted responses."""

    def __init__(self, responses: dict[str, subprocess.CompletedProcess[str]]) -> None:
        self.responses = responses
        self.calls: list[list[str]] = []

    def __call__(self, cmd) -> subprocess.CompletedProcess[str]:  # type: ignore[no-untyped-def]
        self.calls.append(list(cmd))
        for fragment, response in self.responses.items():
            if fragment in " ".join(cmd):
                return response
        return _ok()

    def ran(self, fragment: str) -> bool:
        return any(fragment in " ".join(c) for c in self.calls)


def test_sync_down_exports_before_it_destroys() -> None:
    # `snapshots describe` must report READY, or the status gate raises before
    # destroy is ever reached — which is the behaviour the next tests assert.
    runner = RecordingRunner(
        {"sql export": _ok(), "disks snapshot": _ok(), "snapshots describe": _ok("READY")}
    )
    sync_down("personal", "proj", "proj-backups", now=FIXED, runner=runner)

    export_at = next(i for i, c in enumerate(runner.calls) if "export" in " ".join(c))
    destroy_at = next(i for i, c in enumerate(runner.calls) if "destroy" in " ".join(c))
    assert export_at < destroy_at, "export must complete before destroy is issued"


def test_sync_down_never_destroys_when_the_sql_export_fails() -> None:
    """The single most important test in this file. A failed export followed by
    a destroy is permanent, unrecoverable data loss."""
    runner = RecordingRunner({"sql export": _fail("quota exceeded")})

    with pytest.raises(SyncError, match="export"):
        sync_down("personal", "proj", "proj-backups", now=FIXED, runner=runner)

    assert not runner.ran("destroy"), "destroy must not run after a failed export"


def test_sync_down_never_destroys_when_the_snapshot_fails() -> None:
    runner = RecordingRunner({"disks snapshot": _fail("disk busy")})

    with pytest.raises(SyncError, match="snapshot"):
        sync_down("personal", "proj", "proj-backups", now=FIXED, runner=runner)

    assert not runner.ran("destroy"), "destroy must not run after a failed snapshot"


def test_sync_down_verifies_the_export_object_actually_exists() -> None:
    """gcloud sql export can exit 0 having written nothing usable. Verify the
    object, do not trust the exit code."""
    runner = RecordingRunner({"storage objects describe": _fail("not found")})

    with pytest.raises(SyncError):
        sync_down("personal", "proj", "proj-backups", now=FIXED, runner=runner)

    assert not runner.ran("destroy")


def test_sync_down_never_destroys_when_the_snapshot_is_not_ready() -> None:
    """`gcloud compute disks snapshot` exits 0 as soon as the snapshot is
    created, which is before it holds usable data. FAILED is not a state we may
    destroy on top of."""
    runner = RecordingRunner({"snapshots describe": _ok("FAILED")})

    with pytest.raises(SyncError, match="READY"):
        sync_down("personal", "proj", "proj-backups", now=FIXED, runner=runner)

    assert not runner.ran("destroy")


def test_sync_up_passes_the_latest_snapshot_to_terraform() -> None:
    snapshots = json.dumps(
        [{"name": "memgraph-data-20260801t000000z", "creationTimestamp": "2026-08-01T00:00:00Z"}]
    )
    runner = RecordingRunner({"snapshots list": _ok(snapshots)})
    sync_up("personal", "proj", "proj-backups", runner=runner)

    apply_cmd = next(c for c in runner.calls if "apply" in " ".join(c))
    assert "memgraph_restore_snapshot=memgraph-data-20260801t000000z" in " ".join(apply_cmd)


def test_sync_up_on_a_virgin_project_requests_an_empty_snapshot() -> None:
    """First ever run: no snapshots, no exports. Must still succeed."""
    runner = RecordingRunner({"snapshots list": _ok("[]"), "storage ls": _ok("")})
    sync_up("personal", "proj", "proj-backups", runner=runner)

    apply_cmd = next(c for c in runner.calls if "apply" in " ".join(c))
    assert "memgraph_restore_snapshot=" in " ".join(apply_cmd)
    assert not runner.ran("sql import"), "nothing to import on a virgin project"
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/test_phase01_sync.py -v
```
Expected: FAIL — `ImportError: cannot import name 'sync_down' from 'scripts.sync'`

- [ ] **Step 3: Implement the orchestration**

Append to `scripts/sync.py`:

```python
def run(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Default runner. Captures output so failures can be reported with context."""
    return subprocess.run(list(cmd), capture_output=True, text=True, check=False)


def _require(
    result: subprocess.CompletedProcess[str], what: str
) -> subprocess.CompletedProcess[str]:
    """Raise unless the command succeeded.

    Every destructive step in sync_down is preceded by one of these. Returning a
    status instead of raising would let a caller forget to check it, which is
    exactly the mistake that loses a month of graph data.
    """
    if result.returncode != 0:
        raise SyncError(f"{what} failed (exit {result.returncode}): {result.stderr.strip()}")
    return result


def _tf(module: str, *args: str, env_name: str) -> list[str]:
    return [
        "terraform",
        f"-chdir=terraform/{module}",
        *args,
        f"-var-file=../envs/{env_name}.tfvars",
    ]


def terraform_output(module: str, name: str, *, runner: Runner = run) -> str:
    result = _require(
        runner(["terraform", f"-chdir=terraform/{module}", "output", "-raw", name]),
        f"reading terraform output {name!r}",
    )
    return result.stdout.strip()


def sync_down(
    env_name: str,
    project_id: str,
    bucket: str,
    *,
    now: datetime,
    runner: Runner = run,
) -> list[str]:
    """Back up, verify the backup, then destroy the ephemeral tier.

    Ordering is a safety property, not a preference. Each step raises on
    failure, so `terraform destroy` at the end is only ever reached when every
    preceding verification passed.
    """
    steps: list[str] = []

    instance = terraform_output("ephemeral", "cloudsql_connection_name", runner=runner)
    instance_name = instance.split(":")[-1]
    disk = terraform_output("ephemeral", "memgraph_disk_name", runner=runner)

    # 1. Export Cloud SQL to the durable bucket.
    obj = export_object_name(now)
    uri = backup_uri(bucket, obj)
    _require(
        runner(
            [
                "gcloud", "sql", "export", "sql", instance_name, uri,
                "--database=meeting_memory", f"--project={project_id}",
            ]
        ),
        "Cloud SQL export",
    )
    steps.append(f"exported Cloud SQL to {uri}")

    # 2. Verify the object exists. `gcloud sql export` has been known to exit 0
    #    while producing nothing usable; the exit code alone is not evidence.
    _require(
        runner(["gcloud", "storage", "objects", "describe", uri, f"--project={project_id}"]),
        f"verifying the export object at {uri}",
    )
    steps.append("verified the export object exists")

    # 3. Snapshot the Memgraph data disk.
    snap = snapshot_name(now)
    _require(
        runner(
            [
                "gcloud", "compute", "disks", "snapshot", disk,
                f"--snapshot-names={snap}", f"--project={project_id}",
            ]
        ),
        "Memgraph disk snapshot",
    )
    steps.append(f"snapshotted the Memgraph disk as {snap}")

    # 4. Verify the snapshot is READY, not merely created.
    result = _require(
        runner(
            [
                "gcloud", "compute", "snapshots", "describe", snap,
                "--format=value(status)", f"--project={project_id}",
            ]
        ),
        f"verifying snapshot {snap}",
    )
    if result.stdout.strip() not in ("READY", "UPLOADING"):
        raise SyncError(f"snapshot {snap} is {result.stdout.strip()!r}, not READY")
    steps.append("verified the snapshot")

    # 5. Only now: tear down. Everything above raised on failure, so reaching
    #    this line means both backups are on durable storage.
    _require(
        runner(_tf("ephemeral", "destroy", "-auto-approve", env_name=env_name)),
        "terraform destroy of the ephemeral tier",
    )
    steps.append("destroyed the ephemeral tier — billing for it is now $0")

    return steps


def sync_up(
    env_name: str,
    project_id: str,
    bucket: str,
    *,
    runner: Runner = run,
) -> list[str]:
    """Recreate the ephemeral tier, restoring the most recent backup."""
    steps: list[str] = []

    # 1. Find the newest Memgraph snapshot. None on a virgin project.
    result = _require(
        runner(
            [
                "gcloud", "compute", "snapshots", "list",
                f"--filter=name~^{SNAPSHOT_PREFIX}-", "--format=json",
                f"--project={project_id}",
            ]
        ),
        "listing Memgraph snapshots",
    )
    snapshots = json.loads(result.stdout or "[]")
    latest_snapshot = select_latest(snapshots, "creationTimestamp", "name") or ""
    steps.append(
        f"restoring Memgraph from {latest_snapshot}"
        if latest_snapshot
        else "no Memgraph snapshot found — starting from an empty graph"
    )

    # 2. Apply, handing Terraform the snapshot to restore from.
    _require(
        runner(
            _tf(
                "ephemeral",
                "apply",
                "-auto-approve",
                f"-var=memgraph_restore_snapshot={latest_snapshot}",
                env_name=env_name,
            )
        ),
        "terraform apply of the ephemeral tier",
    )
    steps.append("ephemeral tier is up")

    # 3. Find the newest Cloud SQL export and import it.
    result = _require(
        runner(
            [
                "gcloud", "storage", "ls", f"gs://{bucket}/{EXPORT_PREFIX}/",
                f"--project={project_id}",
            ]
        ),
        "listing Cloud SQL exports",
    )
    exports = sorted(line for line in result.stdout.splitlines() if line.endswith(".sql.gz"))
    if exports:
        instance = terraform_output("ephemeral", "cloudsql_connection_name", runner=runner)
        _require(
            runner(
                [
                    "gcloud", "sql", "import", "sql", instance.split(":")[-1], exports[-1],
                    "--database=meeting_memory", f"--project={project_id}", "--quiet",
                ]
            ),
            "Cloud SQL import",
        )
        steps.append(f"restored Cloud SQL from {exports[-1]}")
    else:
        steps.append("no Cloud SQL export found — starting from an empty database")

    return steps
```

- [ ] **Step 4: Add the CLI**

Append to `scripts/sync.py`:

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sync",
        description="Bring the ephemeral tier up for a session, or tear it down. See ADR-016.",
    )
    parser.add_argument(
        "direction",
        choices=("up", "down"),
        help="up: apply and restore. down: back up, verify, destroy.",
    )
    parser.add_argument("--env", default="personal", help="which terraform env to act on")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    from scripts.auth_spike import load_env_file

    load_env_file()
    import os

    project_id = os.environ.get("GCP_PROJECT_ID", "").strip()
    if not project_id:
        print("GCP_PROJECT_ID is unset. Put it in .env — see .env.example.")
        return 1

    bucket = f"{project_id}-backups"

    try:
        steps = (
            sync_up(args.env, project_id, bucket)
            if args.direction == "up"
            else sync_down(args.env, project_id, bucket, now=datetime.now(UTC))
        )
    except SyncError as exc:
        print(f"\n  sync {args.direction} FAILED: {exc}\n")
        if args.direction == "down":
            print("  The ephemeral tier is still UP and still billing.")
            print("  Fix the cause and re-run `make sync-down` — nothing was destroyed.\n")
        return 1

    print(f"\n  sync {args.direction} complete:")
    for step in steps:
        print(f"    - {step}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Two import changes at the top of the file. Add `import argparse` alongside
`import json`, and **replace** the existing `from datetime import datetime` with:

```python
from datetime import UTC, datetime
```

Do not add a second `datetime` import line — `ruff` (rule `F811`) fails on the
redefinition.

- [ ] **Step 5: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/test_phase01_sync.py -v
```
Expected: 14 passed

- [ ] **Step 6: Lint and typecheck**

```bash
.venv/bin/python -m ruff check scripts tests && .venv/bin/python -m mypy scripts
```
Expected: both clean.

- [ ] **Step 7: Commit**

```bash
git add scripts/sync.py tests/test_phase01_sync.py
git commit -m "Phase 1: sync-up and sync-down orchestration, backup verified before destroy"
```

---

### Task 9: `doctor` learns about the ephemeral tier

ADR-016 names the specific failure mode: a `sync-down` skipped or interrupted leaves ~$58/mo running unattended, and nothing surfaces it until the bill. The doctor already runs at tier 2; it should report cost state.

**Files:**
- Modify: `scripts/doctor.py`
- Test: `tests/test_phase06_doctor.py`

**Interfaces:**
- Produces: `check_ephemeral_tier(probe: Callable[[], bool]) -> CheckResult`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_phase06_doctor.py`:

```python
from scripts.doctor import check_ephemeral_tier


def test_ephemeral_tier_down_is_a_pass() -> None:
    """Torn down is the correct resting state under ADR-016."""
    result = check_ephemeral_tier(probe=lambda: False)
    assert result.status is Status.PASS
    assert "$0" in result.detail


def test_ephemeral_tier_up_warns_with_the_burn_rate() -> None:
    """Up is normal DURING a session, so this is a WARN, never a FAIL — but it
    must name the cost, because the failure mode is forgetting to tear down."""
    result = check_ephemeral_tier(probe=lambda: True)
    assert result.status is Status.WARN
    assert "sync-down" in (result.remediation or "")
```

- [ ] **Step 2: Run to verify failure**

```bash
.venv/bin/python -m pytest tests/test_phase06_doctor.py -k ephemeral -v
```
Expected: FAIL — `ImportError: cannot import name 'check_ephemeral_tier'`

- [ ] **Step 3: Implement**

In `scripts/doctor.py`, add after `check_tfvars`:

```python
def _ephemeral_tier_is_up() -> bool:
    """True if the Cloud SQL instance or the Memgraph VM currently exists.

    Reads Terraform state rather than calling gcloud: state is the authority on
    what this project created, and it answers without network round-trips to
    two separate APIs.
    """
    try:
        completed = subprocess.run(
            ["terraform", "-chdir=terraform/ephemeral", "state", "list"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0 and bool(completed.stdout.strip())


def check_ephemeral_tier(
    probe: Callable[[], bool] = _ephemeral_tier_is_up,
) -> CheckResult:
    """Report whether the billable tier is currently running (ADR-016).

    Both answers are legitimate — up is correct during a sync session, down is
    correct the rest of the month — so this is never a FAIL. It exists because
    the expensive mistake is a sync-down that was skipped or failed, and
    nothing else in the system would tell you.
    """
    name = "ephemeral tier (Cloud SQL + Memgraph VM)"
    if not probe():
        return CheckResult(name, Status.PASS, "down — costing $0")
    return CheckResult(
        name,
        Status.WARN,
        "UP — roughly $58/month while it stays up",
        "Expected during a sync session. When you are done: make sync-down",
    )
```

- [ ] **Step 4: Wire it into tier 2**

In `run_checks`, inside the `if tier >= 2:` block, add `check_ephemeral_tier(),`
immediately after `check_tfvars(env_name),`:

```python
            check_tfvars(env_name),
            check_ephemeral_tier(),
        ]
```

- [ ] **Step 5: Run to verify pass**

```bash
.venv/bin/python -m pytest tests/test_phase06_doctor.py -v
```
Expected: all tests pass, including the two new ones.

- [ ] **Step 6: Commit**

```bash
git add scripts/doctor.py tests/test_phase06_doctor.py
git commit -m "Phase 1: doctor reports whether the billable tier is up"
```

---

### Task 10: Makefile and documentation sync

The docs must describe what was actually built. `SETUP.md`'s tier 2 currently describes a one-shot deploy; under ADR-016 it is a repeatable session.

**Files:**
- Modify: `Makefile`, `docs/SETUP.md`, `docs/ARCHITECTURE.md`, `README.md`, `.env.example`

- [ ] **Step 1: Makefile — replace the Terraform block**

Replace the entire `# ─── Terraform ───` section with:

```makefile
# ─── Terraform ────────────────────────────────────────────────────────────────
# Two root modules, two states (ADR-016). MODULE selects which one; the default
# is `ephemeral` because that is the one touched every session.
MODULE ?= ephemeral
TF := terraform -chdir=terraform/$(MODULE)

tf-bootstrap:  ## Create the GCS state bucket. Run once per project.
	./scripts/tf_bootstrap.sh $$GCP_PROJECT_ID $${GCP_REGION:-us-central1}

tf-init:  ## terraform init (MODULE=durable|ephemeral)
	$(TF) init -backend-config=../envs/$(ENV).backend.hcl

tf-plan:  ## terraform plan (MODULE=durable|ephemeral, ENV=personal|onix)
	$(TF) plan -var-file=../envs/$(ENV).tfvars

tf-apply:  ## terraform apply (MODULE=durable|ephemeral)
	$(TF) apply -var-file=../envs/$(ENV).tfvars

tf-destroy:  ## terraform destroy — prefer `make sync-down` for the ephemeral tier
	$(TF) destroy -var-file=../envs/$(ENV).tfvars

tf-validate:  ## Validate both modules without touching a backend
	terraform -chdir=terraform/durable init -backend=false >/dev/null && \
	  terraform -chdir=terraform/durable validate
	terraform -chdir=terraform/ephemeral init -backend=false >/dev/null && \
	  terraform -chdir=terraform/ephemeral validate

# ─── Sync sessions (ADR-016) ──────────────────────────────────────────────────
# The system is up only while syncing. Everything else is durable and near-free.
sync-up:  ## Bring the billable tier up and restore the last backup
	$(PYTHON) -m scripts.sync up --env $(ENV)
	@$(MAKE) doctor TIER=2 ENV=$(ENV)

sync-down:  ## Back up, VERIFY, then destroy the billable tier
	$(PYTHON) -m scripts.sync down --env $(ENV)
```

- [ ] **Step 2: Makefile — declare the new targets**

Update the `.PHONY` line at the top to include the new targets:

```makefile
.PHONY: help doctor demo demo-up demo-down auth-spike tf-bootstrap tf-init tf-plan \
        tf-apply tf-destroy tf-validate sync-up sync-down \
        secrets-put build push deploy-api deploy-jobs run-job migrate setup-memgraph \
        test lint typecheck logs cypher psql health graphify
```

- [ ] **Step 3: Makefile — fix the Memgraph console target**

Bolt is not publicly reachable, so the existing `cypher` target cannot work.
Replace it:

```makefile
cypher:  ## Memgraph console on the VM (via IAP — no public Bolt port)
	gcloud compute ssh $${MEMGRAPH_VM:-meeting-notes-memgraph} \
	  --tunnel-through-iap --command "docker exec -it memgraph mgconsole"
```

- [ ] **Step 4: Verify the Makefile parses and the help text renders**

```bash
make help
```
Expected: `sync-up`, `sync-down`, `tf-bootstrap`, and `tf-validate` all appear with
their descriptions.

- [ ] **Step 5: `.env.example` — document what an apply produces**

Under the `# Cloud SQL` block, add:

```env
# Populated from `terraform -chdir=terraform/ephemeral output` after `make sync-up`.
# These change on every sync-up because the instance is recreated (ADR-016).
GCS_BACKUP_BUCKET=              # <project-id>-backups, created by the durable tier
```

Under the `# Memgraph` block, add:

```env
# Bolt is NOT publicly reachable. Open a tunnel first:
#   gcloud compute start-iap-tunnel meeting-notes-memgraph 7687 \
#     --local-host-port=localhost:7687 --zone=$GCP_ZONE
# then leave MEMGRAPH_HOST as localhost.
```

- [ ] **Step 6: `docs/SETUP.md` — rewrite the tier 2 infrastructure section**

Replace the `### Infrastructure` block with:

````markdown
### Infrastructure

```bash
cp terraform/envs/personal.example.tfvars terraform/envs/personal.tfvars
cp terraform/envs/personal.backend.example.hcl terraform/envs/personal.backend.hcl
$EDITOR terraform/envs/personal.tfvars     # project id, region, billing account

make tf-bootstrap                          # create the state bucket, once
make doctor TIER=2                         # verify before spending money

make tf-init  MODULE=durable
make tf-apply MODULE=durable               # once. Cheap, and stays up.
```

The durable tier — VPC, Artifact Registry, Secret Manager, service accounts,
Pub/Sub, the backup bucket, the budget alert — costs cents per month and is
applied once. Real `.tfvars` and `.backend.hcl` files are gitignored because they
carry project ids; the `*.example.*` alongside them are committed so the required
variables are discoverable.

### Sync sessions — the part that costs money

**The system is not meant to be up all the time.** Cloud SQL and the Memgraph VM
are the only always-on-priced resources, and together they run about **$58/month
if you leave them up**. So they exist only while you are actually syncing:

```bash
make sync-up      # create them, restore the last backup, run doctor
#   ... sync meetings, query the graph, do the work ...
make sync-down    # back up, verify the backup, then destroy them
```

Between sessions the billable tier costs **$0**. Your data lives in the durable
backup bucket (Cloud SQL export) and in a disk snapshot (the graph), and
`sync-up` restores both.

`sync-down` will not destroy anything until it has confirmed both backups
exist — a failed export leaves the tier up and tells you so, rather than
silently discarding a month of work.

> **Expect to re-consent every session.** The OAuth refresh token dies after 7
> days (`docs/GOOGLE_AUTH.md`), so any gap longer than a week means `sync-up`'s
> doctor run reports the token as expired. That is normal at this cadence, not a
> fault:
>
> ```bash
> make auth-spike ARGS=--reconsent
> ```

> **If you forget `sync-down`,** the budget alert emails you at
> `budget_alert_threshold_ratio` of `budget_amount_usd`. `make doctor TIER=2`
> also reports the tier as UP with its burn rate.
````

- [ ] **Step 7: `docs/ARCHITECTURE.md` — rewrite §7**

Replace the entire `## 7. Cost posture` section with:

````markdown
## 7. Cost posture

**The system is up only while syncing (ADR-016).** This is a trial touched a few
hours a month, so the design target is $0 when idle rather than "cheap when
running".

Every resource is in one of two tiers:

| Tier | Resources | Idle cost |
|---|---|---|
| **Durable** — applied once | VPC · Artifact Registry · Secret Manager · service accounts · Pub/Sub · backup bucket · budget alert | cents/month |
| **Ephemeral** — `sync-up` / `sync-down` | Cloud SQL instance · Memgraph GCE VM + data disk | **$0 when destroyed** |

Verified against the Cloud Billing Catalog API on 2026-08-19:

| Resource | Rate | Monthly if left up |
|---|---|---|
| `e2-medium` | $0.021812/vCPU-hr + $0.002924/GiB-hr | ~$40 |
| Cloud SQL `db-f1-micro` | $0.018/hr | ~$13 |
| Balanced PD, 50GiB | $0.10/GiB-month | $5 |
| Gemini 2.5 Flash | $0.30/M input, $2.50/M output tokens | pennies at this volume |

Data crosses the gap between sessions as a Cloud SQL export in the durable
bucket and a snapshot of the Memgraph data disk. `sync-down` verifies both
before it destroys anything.

Levers, if a session's cost ever matters:

1. Smallest viable Cloud SQL tier — already `db-f1-micro`.
2. `e2-small` instead of `e2-medium` for Memgraph; resize when the graph grows.
3. `min-instances=0` on the API service, always.
4. A Flash-tier Gemini model for extraction. Pro is not needed to fill a JSON schema.
5. Scheduler frequencies are config, not architecture — and under this lifecycle
   nothing is scheduled while the system is down anyway.

**Stopping instead of destroying does not work**, and was rejected: Cloud SQL
auto-restarts a stopped instance after ~7 days for maintenance, silently
resuming the bill partway through a month of inactivity.
````

- [ ] **Step 8: `docs/ARCHITECTURE.md` — mark the tiers in §4**

In the `### Compute` table, change the `memgraph` row's Notes cell to end with
`**Ephemeral — destroyed between sync sessions (ADR-016).**`

In the `### Data` table, change the Cloud SQL row's Notes cell to end with
`**Ephemeral — destroyed between sync sessions (ADR-016).**`, and add a row:

```
| GCS backup bucket | Durable. Cloud SQL exports land here on sync-down; sync-up restores from the newest. |
```

- [ ] **Step 9: `README.md` — correct the tier 2 row**

In the three-tier table, replace the tier 2 row with:

```
| 2 | `make sync-up` … `make sync-down` | GCP + Workspace + Jira | the deployed product |
```

And replace the sentence beginning "Tier 0 runs entirely on local Docker" with:

```markdown
Tier 0 runs entirely on local Docker with replayed LLM fixtures, so a fresh clone
works offline with no account anywhere. Tiers 0 and 1 cost nothing. Tier 2 splits
its resources into a durable tier that costs cents a month and a billable tier
that exists **only while you are syncing** — `make sync-up` creates it and
restores your data, `make sync-down` backs it up and destroys it. Idle cost
between sessions is $0. A budget alert ships from the first apply either way.
```

- [ ] **Step 10: Verify the docs claim nothing untrue**

```bash
grep -rn "always-on" README.md docs/SETUP.md docs/ARCHITECTURE.md
```
Expected: no hit that describes *this* system as always-on. The phrase survives
only where it describes the cost model being avoided.

- [ ] **Step 11: Commit**

```bash
git add Makefile .env.example docs/SETUP.md docs/ARCHITECTURE.md README.md
git commit -m "Phase 1: sync lifecycle in the Makefile and every doc that described a deploy"
```

---

### Task 11: Live validation — GATED ON TASK 0

Everything above is written and unit-tested without billing. This task is the
first that spends money, and it is the one that proves the phase.

**Prerequisite:** `gcloud billing projects describe meeting-notes-gcp-personal --format='value(billingEnabled)'` prints `True`.

- [ ] **Step 1: Bootstrap and apply the durable tier**

```bash
make tf-bootstrap
make tf-init  MODULE=durable
make tf-apply MODULE=durable
```
Expected: apply completes. Note the outputs — especially `backup_bucket`.

- [ ] **Step 2: Confirm the budget alert exists before going further**

```bash
gcloud billing budgets list --billing-account=$(grep billing_account_id terraform/envs/personal.tfvars | cut -d'"' -f2)
```
Expected: one budget named `meeting-notes monthly budget`. **If this is missing,
stop and fix it — it is the only thing standing between a mistake and a bill.**

- [ ] **Step 3: First sync-up**

```bash
make tf-init MODULE=ephemeral
make sync-up
```
Expected: reports "no Memgraph snapshot found — starting from an empty graph" and
"no Cloud SQL export found — starting from an empty database", then brings the
tier up. The doctor run afterwards is expected to report the OAuth token as
expired if more than 7 days have passed since the last consent.

- [ ] **Step 4: Verify Memgraph is actually serving Bolt**

The VM reports RUNNING well before Docker has pulled the images, so give it a
minute, then:

```bash
gcloud compute start-iap-tunnel meeting-notes-memgraph 7687 \
  --local-host-port=localhost:7687 --zone=us-central1-a &
sleep 5
.venv/bin/python -c "
from neo4j import GraphDatabase
with GraphDatabase.driver('bolt://localhost:7687') as d:
    print(d.execute_query('RETURN 1 AS ok').records[0]['ok'])
"
```
Expected: `1`

- [ ] **Step 5: Write a marker record into both stores**

This is what proves data survives the gap. Without it, "destroy then apply
worked" only proves Terraform is deterministic — it says nothing about the data.

```bash
.venv/bin/python -c "
from neo4j import GraphDatabase
with GraphDatabase.driver('bolt://localhost:7687') as d:
    d.execute_query(\"MERGE (m:SyncMarker {id: 'phase1'}) SET m.written_at = datetime()\")
    print('marker written')
"
```

```bash
gcloud sql connect meeting-notes-pg --user=meeting_notes --database=meeting_memory \
  --quiet <<'SQL'
CREATE TABLE IF NOT EXISTS sync_marker (id text primary key, written_at timestamptz default now());
INSERT INTO sync_marker (id) VALUES ('phase1') ON CONFLICT DO NOTHING;
SELECT * FROM sync_marker;
SQL
```

- [ ] **Step 6: Tear down**

```bash
make sync-down
```
Expected output names each step: exported, verified the export object,
snapshotted, verified the snapshot, destroyed.

- [ ] **Step 7: Confirm the billable tier is really gone**

```bash
gcloud sql instances list
gcloud compute instances list
make doctor TIER=2
```
Expected: no `meeting-notes-pg`, no `meeting-notes-memgraph`, and the doctor
reports the ephemeral tier as `PASS — down, costing $0`.

- [ ] **Step 8: Bring it back and check the marker survived**

```bash
make sync-up
```
Expected: reports restoring from a named snapshot and a named export.

```bash
gcloud compute start-iap-tunnel meeting-notes-memgraph 7687 \
  --local-host-port=localhost:7687 --zone=us-central1-a &
sleep 5
.venv/bin/python -c "
from neo4j import GraphDatabase
with GraphDatabase.driver('bolt://localhost:7687') as d:
    r = d.execute_query(\"MATCH (m:SyncMarker {id:'phase1'}) RETURN m.written_at AS t\")
    assert r.records, 'MARKER LOST — the snapshot restore did not work'
    print('graph marker survived:', r.records[0]['t'])
"
```
Expected: prints the original timestamp. **If the marker is missing, the phase is
not done** — the restore path is broken and Task 6's disk/snapshot wiring or
Task 8's `sync_up` is at fault.

```bash
gcloud sql connect meeting-notes-pg --user=meeting_notes --database=meeting_memory \
  --quiet <<'SQL'
SELECT * FROM sync_marker;
SQL
```
Expected: one row, with the original `written_at`.

- [ ] **Step 9: Tear down again and leave it down**

```bash
make sync-down
```

- [ ] **Step 10: Record the outcome**

Append an ADR to `docs/DECISIONS.md` recording what the live run proved — in
particular the real bring-up time for `sync-up`, since that is the number that
decides whether this lifecycle is pleasant or annoying to live with. Follow the
template at the bottom of that file.

---

### Task 12: Refresh the knowledge graph and close the phase

- [ ] **Step 1: Update the phase plan**

In `docs/PHASE_PLAN.md`, change the Phase 1 heading to
`## Phase 1 — Terraform foundation ✅ DONE (2026-08-DD, ADR-016 / ADR-017)` and
add a one-paragraph outcome summary in the same style as Phase 0.5's, including
the measured `sync-up` duration.

- [ ] **Step 2: Re-run extraction**

```bash
graphify . --update
```

- [ ] **Step 3: Compare the health check against the previous run**

The dangling-edge count must not regress. If it does, say so plainly rather than
committing a quietly-worse graph.

- [ ] **Step 4: Commit**

```bash
git add graphify-out/GRAPH_REPORT.md graphify-out/graph.json graphify-out/graph.html \
        graphify-out/manifest.json docs/PHASE_PLAN.md docs/DECISIONS.md
git commit -m "graphify: rebuild for Phase 1"
```

**Never** commit `graphify-out/cache/` or `.graphify_root`.

---

## Self-review notes

- **Phase plan coverage:** `PHASE_PLAN.md` Phase 1 task 1 → Tasks 1–2. Task 2 (tfvars + examples) → already done in Phase 0.6, extended by Task 1's backend templates. Task 3 (durable resources) → Tasks 2–4. Task 4 (ephemeral resources) → Tasks 5–6. Task 5 (VM bootstrap) → Task 6. Task 6 (Makefile incl. `sync-up`/`sync-down`) → Task 10. Exit criteria → Task 11, with the data-survival criterion proven by the marker record in Steps 5 and 8.
- **Deliberately not built:** Cloud Run services and jobs, and Cloud Scheduler jobs. There is no application to deploy until Phases 5–8, and under ADR-016 nothing is scheduled while the system is down. The service accounts those workloads need *are* created (Task 3), because IAM propagation delays are discovered late.
- **Type consistency:** `Runner` is the single injected-command type across Tasks 7–8. `SyncError` is raised by every failure path in both. `CheckResult` / `Status` in Task 9 match the existing `scripts/doctor.py` definitions exactly. `var.name_prefix` is the one naming contract between the two Terraform modules and is declared identically in both `variables.tf` files.
- **Known-blocking by design:** Task 0 is a hard gate. Tasks 1–10 are fully buildable with billing off — every Terraform validation step uses `-backend=false`, and every Python test injects its runner. Only Task 11 spends money.
- **The one test that matters:** `test_sync_down_never_destroys_when_the_sql_export_fails`. Everything else in this phase is recoverable.
