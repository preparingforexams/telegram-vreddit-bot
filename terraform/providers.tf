terraform {
  backend "gcs" {
    bucket = "cancer-be-gone-terraform-state"
  }

  required_providers {
    google = {
      version = "~> 4.38.0"
    }
  }
}

provider "google" {
  project = "cancer-be-gone"
  region  = "europe-west3"
}
