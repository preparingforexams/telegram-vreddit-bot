from cancer.message.download import DownloadMessage


def test_serialization():
    message = DownloadMessage(1, 2, ["a", "b"])
    serialized = message.serialize()
    deserialized = DownloadMessage.deserialize(serialized)
    assert deserialized == message


def test_insta():
    message = DownloadMessage(1, 2, ["a"]).instagram()
    assert b"topic" not in message.serialize()
