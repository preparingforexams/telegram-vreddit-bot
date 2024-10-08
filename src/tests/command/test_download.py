import pytest

from cancer.command import download


@pytest.mark.skip(reason="The YouTube API lies")
def test_check_size():
    url = "https://www.youtube.com/watch?v=eomhW5MLGWA"
    info = download._get_info(url)
    assert 4_000_000 < info.size < 6_000_000
