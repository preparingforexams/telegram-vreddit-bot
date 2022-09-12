resource "google_service_account" "service_account" {
  account_id   = "telegram-bot"
  display_name = "Telegram Bot"
}

resource "google_project_iam_custom_role" "consumer" {
  title       = "Pub/Sub Consumer"
  role_id     = "pubsubConsumer"
  permissions = [
    "pubsub.subscriptions.consume",
  ]
}

resource "google_project_iam_member" "service_account_consumer" {
  project = google_service_account.service_account.project
  role    = google_project_iam_custom_role.consumer.id
  member  = "serviceAccount:${google_service_account.service_account.email}"
}

resource "google_project_iam_member" "service_account_publisher" {
  project = google_service_account.service_account.project
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.service_account.email}"
}

locals {
  pubsub_agent_email = "service-622242716592@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "pubsub_agent_consumer" {
  project = google_service_account.service_account.project
  role    = google_project_iam_custom_role.consumer.id
  member  = "serviceAccount:${local.pubsub_agent_email}"
}

resource "google_project_iam_member" "pubsub_agent_publisher" {
  project = google_service_account.service_account.project
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${local.pubsub_agent_email}"
}
