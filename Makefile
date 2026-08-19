.PHONY: help doctor demo demo-down auth-spike tf-init tf-plan tf-apply tf-destroy \
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
SRC := scripts tests

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
auth-spike:  ## Run the OAuth spike. Do this before anything else. (ARGS=--reconsent)
	$(PYTHON) -m scripts.auth_spike $(ARGS)

# ─── Terraform ────────────────────────────────────────────────────────────────
tf-init:  ## terraform init
	cd terraform && terraform init

tf-plan:  ## terraform plan (ENV=personal|onix)
	cd terraform && terraform plan -var-file=envs/$(ENV).tfvars

tf-apply:  ## terraform apply (ENV=personal|onix)
	cd terraform && terraform apply -var-file=envs/$(ENV).tfvars

tf-destroy:  ## terraform destroy — careful
	cd terraform && terraform destroy -var-file=envs/$(ENV).tfvars

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
migrate:  ## Apply the Cloud SQL staging schema
	$(PYTHON) -m scripts.migrate

setup-memgraph:  ## Constraints, indexes, vector indexes, seeded procedures
	$(PYTHON) -m scripts.setup_memgraph

# ─── Development ──────────────────────────────────────────────────────────────
test:  ## Full pytest suite — must pass with no live services
	$(PYTHON) -m pytest tests/ -v

lint:  ## ruff over the source trees that exist
	$(PYTHON) -m ruff check $(SRC)

typecheck:  ## mypy over the source trees that exist
	$(PYTHON) -m mypy scripts

logs:  ## Tail Cloud Run logs (SERVICE=api)
	gcloud run services logs tail $(SERVICE) --region $$GCP_REGION

cypher:  ## Memgraph console on the VM
	gcloud compute ssh memgraph --command "docker exec -it memgraph mgconsole"

psql:  ## Cloud SQL console
	gcloud sql connect $$CLOUD_SQL_INSTANCE --user=$$POSTGRES_USER --database=$$POSTGRES_DB

health:  ## Hit the API health endpoint
	curl -s "$$API_URL/health" | python3 -m json.tool

graphify:  ## Refresh the code knowledge graph
	graphify . --update
