from cancer.message.download import DownloadMessage


def test_serialization():
    message = DownloadMessage(1, 2, ["a", "b"])
    serialized = message.serialize()
    deserialized = DownloadMessage.deserialize(serialized)
    assert deserialized == message
