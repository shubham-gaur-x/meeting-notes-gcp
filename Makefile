.PHONY: help doctor demo demo-up demo-down auth-spike tf-bootstrap tf-init tf-plan \
        tf-apply tf-destroy tf-validate sync-up sync-down \
        secrets-put build push deploy-api deploy-jobs run-job migrate setup-memgraph \
        test lint typecheck logs cypher psql health graphify

ENV ?= personal
TFVARS := terraform/envs/$(ENV).tfvars

# Override with `make <target> PYTHON=python3` to use something other than the
# project venv.
PYTHON ?= .venv/bin/python

COMPOSE := docker compose -f docker-compose.local.yml

# Which source trees actually exist yet. Phases 2-8 add to this; naming a
# directory before it exists makes lint/typecheck fail on a clean clone.
SRC := meeting_notes scripts tests

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ─── Preflight ────────────────────────────────────────────────────────────────
# Tier 0 by default. `make doctor TIER=1` adds the LLM check; `make doctor TIER=2
# ENV=personal` adds GCP, Workspace and Jira. Start here on a fresh clone.
TIER ?= 0

# Exit 2 means warnings only — not a failure, so don't let make report one.
# Exit 1 (a real FAIL) still propagates and stops the build.
doctor:  ## Preflight: what's missing? (TIER=0|1|2, ENV=personal|onix)
	@$(PYTHON) -m scripts.doctor --tier $(TIER) --env $(ENV) || [ $$? -eq 2 ]

# ─── Local stack ──────────────────────────────────────────────────────────────
demo:  ## Tier 0: run the whole pipeline locally, no credentials (Phase 6)
	@echo "Not ready yet — the pipeline lands in Phase 6, the dashboard in Phase 8."
	@echo "See docs/SETUP.md. Today you can start the stack with: make demo-up"
	@exit 1

demo-up:  ## Start the local Postgres + Memgraph stack
	$(COMPOSE) up -d

demo-down:  ## Stop the local stack (add ARGS=-v to delete its data)
	$(COMPOSE) down $(ARGS)

# ─── Phase 0.5 ────────────────────────────────────────────────────────────────
record-fixtures:  ## Re-record tier-0 LLM fixtures against a real backend (ADR-014)
	$(PYTHON) -m scripts.record_fixtures $(ARGS)

auth-spike:  ## Run the OAuth spike. Do this before anything else. (ARGS=--reconsent)
	$(PYTHON) -m scripts.auth_spike $(ARGS)

# ─── Terraform ────────────────────────────────────────────────────────────────
# Two root modules, two states (ADR-016). MODULE selects which one; the default
# is `ephemeral` because that is the one touched every session.
MODULE ?= ephemeral
TF := terraform -chdir=terraform/$(MODULE)

# Pinned to the ephemeral module regardless of MODULE, for targets that read
# deployed connection details out of Terraform state.
TF_EPHEMERAL := terraform -chdir=terraform/ephemeral

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

secrets-put:  ## Interactively write a secret to Secret Manager
	@read -p "Secret id: " id; \
	 read -s -p "Value: " val; echo; \
	 printf '%s' "$$val" | gcloud secrets versions add "$$id" --data-file=-

# ─── Build and deploy ─────────────────────────────────────────────────────────
build:  ## Build api + jobs images
	@echo "TODO Phase 1 — see docs/PHASE_PLAN.md"

push:  ## Push images to Artifact Registry
	@echo "TODO Phase 1"

deploy-api:  ## Deploy the Cloud Run service
	@echo "TODO Phase 8"

deploy-jobs:  ## Deploy all Cloud Run Jobs
	@echo "TODO Phase 5"

run-job:  ## Execute a Cloud Run Job now (JOB=pipeline-drain)
	gcloud run jobs execute $(JOB) --region $$GCP_REGION --wait

# ─── Data layer ───────────────────────────────────────────────────────────────
migrate:  ## Apply the Cloud SQL staging schema (idempotent)
	$(PYTHON) -m meeting_notes.db

setup-memgraph:  ## Constraints, indexes, vector indexes, seeded procedures
	$(PYTHON) -m scripts.setup_memgraph

# ─── Development ──────────────────────────────────────────────────────────────
test:  ## Full pytest suite — must pass with no live services
	$(PYTHON) -m pytest tests/ -v

lint:  ## ruff over the source trees that exist
	$(PYTHON) -m ruff check $(SRC)

typecheck:  ## mypy over the source trees that exist
	$(PYTHON) -m mypy meeting_notes scripts

logs:  ## Tail Cloud Run logs (SERVICE=api)
	gcloud run services logs tail $(SERVICE) --region $$GCP_REGION

# Both of these read the instance name from Terraform state rather than from an
# env var, so they cannot drift from what is actually deployed. They only work
# while the ephemeral tier is up (`make sync-up`).
cypher:  ## Memgraph console on the VM (via IAP — no public Bolt port)
	@name=$$($(TF_EPHEMERAL) output -raw memgraph_instance_name) && \
	  gcloud compute ssh "$$name" --zone "$$GCP_ZONE" --tunnel-through-iap \
	    --command "docker exec -it memgraph mgconsole"

# Needs the cloud-sql-proxy component:
#   gcloud components install cloud-sql-proxy
# Connecting to the public IP directly will hang — there are no authorized
# networks, by design (docs/SETUP.md).
psql:  ## Cloud SQL console
	@conn=$$($(TF_EPHEMERAL) output -raw cloudsql_connection_name) && \
	  gcloud sql connect "$${conn##*:}" --user=meeting_notes --database=meeting_memory

health:  ## Hit the API health endpoint
	curl -s "$$API_URL/health" | python3 -m json.tool

graphify:  ## Refresh the code knowledge graph
	graphify . --update
