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

#  condition {
#    title      = "Cancer Subscriptions"
#    expression = join(" || ", [for c in module.channels : "resource.name == '${c.subscription_id}'"])
#  }
}

resource "google_project_iam_member" "service_account_publisher" {
  project = google_service_account.service_account.project
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.service_account.email}"

#  condition {
#    title      = "Cancer Topic"
#    expression = join(" || ", [for c in module.channels : "resource.name == '${c.topic_id}'"])
#  }
}
