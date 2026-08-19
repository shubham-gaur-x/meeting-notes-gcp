# Template for terraform/envs/onix.tfvars — the Onix-owned GCP project.
#
#   cp terraform/envs/onix.example.tfvars terraform/envs/onix.tfvars
#
# Phase 10. Moving to Onix must be: new .tfvars, terraform apply, re-consent
# OAuth, restore data — nothing else (CLAUDE.md, "Deployment Context").
#
# The real .tfvars is gitignored. Nothing secret belongs in either file.

# ─── Identity ─────────────────────────────────────────────────────────────────
project_id = "onix-project-id-here"
region     = "us-central1"
zone       = "us-central1-a"

# Unchanged from the personal environment — the data source was always the Onix
# Workspace account. Only the hosting project moves.
workspace_user = "shubham.gaur@onixnet.com"

# ─── Cost control ─────────────────────────────────────────────────────────────
billing_account_id = "000000-000000-000000"

# Onix billing, not personal — but keep the alert. A budget alert costs nothing
# and an unwatched always-on VM is how cloud bills surprise people.
budget_amount_usd            = 200
budget_alert_threshold_ratio = 0.5

# ─── Compute sizing ───────────────────────────────────────────────────────────
# Sized up from personal: no longer paying out of pocket.
cloudsql_tier    = "db-g1-small"
memgraph_machine = "e2-standard-2"
memgraph_disk_gb = 100

memgraph_image = "memgraph/memgraph-mage:3.11.0"

# ─── LLM ──────────────────────────────────────────────────────────────────────
vertex_chat_model      = "gemini-2.5-flash"
vertex_embedding_model = "text-embedding-005"
vertex_location        = "us-central1"

# ─── Note on OAuth ────────────────────────────────────────────────────────────
# In the Onix project the OAuth client should be user type INTERNAL, which
# removes both the 7-day refresh token expiry and the verification requirement
# entirely (GOOGLE_AUTH.md §8). That is the permanent fix for the weekly
# re-consent chore, and it is not expressible in Terraform — it is a console
# step, same as the personal project's client.
