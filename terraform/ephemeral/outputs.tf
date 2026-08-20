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
