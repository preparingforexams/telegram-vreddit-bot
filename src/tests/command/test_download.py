import pytest

from cancer.command import download


@pytest.mark.skip(reason="The YouTube API lies")
def test_check_size():
    url = "https://www.youtube.com/watch?v=eomhW5MLGWA"
    info = download._get_info(url)
    size = info.size
    assert size
    assert 4_000_000 < size < 6_000_000
