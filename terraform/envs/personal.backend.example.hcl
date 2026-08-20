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
