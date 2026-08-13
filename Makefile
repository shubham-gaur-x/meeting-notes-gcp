.PHONY: help auth-spike tf-init tf-plan tf-apply tf-destroy secrets-put \
        build push deploy-api deploy-jobs run-job migrate setup-memgraph \
        test lint typecheck logs cypher psql health graphify

ENV ?= personal
TFVARS := terraform/envs/$(ENV).tfvars

# Override with `make <target> PYTHON=python3` to use something other than the
# project venv. Phase 0.6 normalises the remaining targets onto this.
PYTHON ?= .venv/bin/python

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

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
	python -m scripts.migrate

setup-memgraph:  ## Constraints, indexes, vector indexes, seeded procedures
	python scripts/setup_memgraph.py

# ─── Development ──────────────────────────────────────────────────────────────
test:  ## Full pytest suite — must pass with no live services
	python -m pytest tests/ -v

lint:
	ruff check meeting_notes jobs api scripts tests

typecheck:
	mypy meeting_notes jobs api

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
