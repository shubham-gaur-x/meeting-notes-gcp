# Template for terraform/envs/personal.tfvars — the personal GCP project.
#
#   cp terraform/envs/personal.example.tfvars terraform/envs/personal.tfvars
#
# The real .tfvars is gitignored because it carries a project id; this example
# is committed so the required variables are discoverable (PHASE_PLAN Phase 1).
# Nothing secret belongs in either file — secrets live in Secret Manager.

# ─── Identity ─────────────────────────────────────────────────────────────────
# Never hardcoded in any .tf file. See CLAUDE.md, "Deployment Context".
project_id = "your-project-id-here"
region     = "us-central1"
zone       = "us-central1-a"

# The Workspace account whose mail and calendar are read. Deliberately a
# different account from the one owning the project above — see ADR-009.
workspace_user = "you@your-company.com"

# ─── Cost control ─────────────────────────────────────────────────────────────
# Billing account this project bills to (gcloud billing accounts list).
billing_account_id = "000000-000000-000000"

# The budget alert is created in the FIRST apply, not a later one (ARCHITECTURE
# §4). Cloud SQL and the Memgraph VM are always-on and dominate the bill.
budget_amount_usd            = 50
budget_alert_threshold_ratio = 0.5

# ─── Compute sizing ───────────────────────────────────────────────────────────
# Smallest viable while on personal billing (ARCHITECTURE §7 lever 1 and 2).
cloudsql_tier    = "db-f1-micro"
memgraph_machine = "e2-medium"
memgraph_disk_gb = 50

# Must match the tag in docker-compose.local.yml, or MAGE procedure
# availability differs between local and deployed.
memgraph_image = "memgraph/memgraph-mage:3.11.0"

# ─── LLM ──────────────────────────────────────────────────────────────────────
# Confirm the current model name at build time — they change (PHASE_PLAN Phase 4).
vertex_chat_model      = "gemini-2.5-flash"
vertex_embedding_model = "text-embedding-005"
vertex_location        = "us-central1"
