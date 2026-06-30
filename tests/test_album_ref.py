from vkdl.album_ref import AlbumRef, parse, is_album_url


def test_parse_negative_owner():
    ref = parse("https://vk.com/album-18515186_240802273")
    assert ref == AlbumRef(owner_id="-18515186", album_id="240802273")


def test_parse_positive_owner():
    ref = parse("https://vk.com/album12345_67890")
    assert ref == AlbumRef(owner_id="12345", album_id="67890")


def test_parse_rejects_non_album():
    assert parse("https://vk.com/video-1_2") is None
    assert parse("not a url") is None


def test_is_album_url():
    assert is_album_url("https://vk.com/album-1_2")
    assert not is_album_url("https://vk.com/video-1_2")
    assert not is_album_url("not a url")
