from vkdl.api_client import parse_owner_album, photos_to_models

def test_parse_owner_album_negative_owner():
    owner, album = parse_owner_album("https://vk.com/album-18515186_240802273")
    assert owner == "-18515186"
    assert album == "240802273"

def test_parse_owner_album_positive_owner():
    owner, album = parse_owner_album("https://vk.com/album12345_67890")
    assert owner == "12345"
    assert album == "67890"

def test_photos_to_models_picks_largest():
    api = {"response": {"items": [
        {"id": 1, "owner_id": -5, "sizes": [
            {"type": "m", "url": "u_m", "width": 130, "height": 100},
            {"type": "w", "url": "u_w", "width": 2560, "height": 1920},
            {"type": "x", "url": "u_x", "width": 604, "height": 453},
        ]},
    ]}}
    photos = photos_to_models(api)
    assert len(photos) == 1
    assert photos[0].urls[0] == "u_w"  # largest by width first
    assert photos[0].id == "-5_1"

def test_photos_to_models_empty():
    assert photos_to_models({"response": {"items": []}}) == []
