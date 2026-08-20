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

  depends_on = [google_project_service.enabled]
}
