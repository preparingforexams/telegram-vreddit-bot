from cancer.command import download


def test_check_size():
    url = "https://www.youtube.com/watch?v=eomhW5MLGWA"
    size = download._check_size(url)
    assert 4_000_000 < size < 6_000_000
