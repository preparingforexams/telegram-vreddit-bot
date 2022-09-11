module "channels" {
  for_each = toset([
    "download",
    "instaDownload",
    "tiktokDownload",
    "twitterDownload",
    "youtubeDownload",
    "youtubeUrlConvert",
  ])

  source               = "./modules/pubsub_channel"
  name                 = each.value
}
