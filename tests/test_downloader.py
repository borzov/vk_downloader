from pathlib import Path
import responses
import requests
from vkdl.downloader import sanitize_filename, download_photo, download_all
from vkdl.dedup import file_sha256
from vkdl.models import Photo
from vkdl.config import DownloadConfig


def test_sanitize_filename():
    assert sanitize_filename('a/b:c*?.jpg') == 'a_b_c__.jpg'


def test_file_sha256(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"hello")
    assert file_sha256(p) == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )


@responses.activate
def test_download_photo_success(tmp_path):
    url = "https://s/p.jpg?as=10x10&cs=10x0"
    responses.add(responses.GET, "https://s/p.jpg", body=b"IMGDATA", status=200)
    photo = Photo(id="1_2", urls=[url])
    s = requests.Session()
    res = download_photo(photo, 1, tmp_path, s, DownloadConfig(retries=1))
    assert res["status"] == "success"
    assert (tmp_path / res["filename"]).read_bytes() == b"IMGDATA"


@responses.activate
def test_download_photo_skips_existing(tmp_path):
    url = "https://s/p.jpg?as=10x10&cs=10x0"
    photo = Photo(id="1_2", urls=[url])
    existing = tmp_path / "001_1_2.jpg"
    existing.write_bytes(b"X")
    s = requests.Session()
    res = download_photo(photo, 1, tmp_path, s, DownloadConfig())
    assert res["status"] == "skipped"


@responses.activate
def test_download_photo_falls_to_next_url_on_404(tmp_path):
    big = "https://s/p.jpg?as=99x99&cs=99x0"
    small = "https://s/p.jpg?as=10x10&cs=10x0"
    responses.add(responses.GET, "https://s/p.jpg", status=404)
    responses.add(responses.GET, "https://s/p.jpg", body=b"SMALL", status=200)
    photo = Photo(id="1_2", urls=[big, small])
    s = requests.Session()
    res = download_photo(photo, 1, tmp_path, s, DownloadConfig(retries=1))
    assert res["status"] == "success"


@responses.activate
def test_download_photo_falls_to_next_url_on_network_error(tmp_path):
    # first URL raises a connection error on every retry; second URL succeeds
    big = "https://big/p.jpg?as=99x99&cs=99x0"
    small = "https://small/p.jpg?as=10x10&cs=10x0"
    responses.add(responses.GET, "https://big/p.jpg",
                  body=requests.exceptions.ConnectionError("boom"))
    responses.add(responses.GET, "https://small/p.jpg", body=b"SMALL", status=200)
    photo = Photo(id="1_2", urls=[big, small])
    s = requests.Session()
    res = download_photo(photo, 1, tmp_path, s, DownloadConfig(retries=1, backoff_base=0))
    assert res["status"] == "success"
    assert (tmp_path / res["filename"]).read_bytes() == b"SMALL"


@responses.activate
def test_download_all_dedupes_identical_content(tmp_path):
    # two distinct photos whose bytes are identical -> one success, one duplicate
    responses.add(responses.GET, "https://s/a.jpg", body=b"SAME", status=200)
    responses.add(responses.GET, "https://s/b.jpg", body=b"SAME", status=200)
    photos = [
        Photo(id="1_1", urls=["https://s/a.jpg?as=10x10&cs=10x0"]),
        Photo(id="1_2", urls=["https://s/b.jpg?as=10x10&cs=10x0"]),
    ]
    s = requests.Session()
    counters = download_all(photos, tmp_path, s, DownloadConfig(max_workers=1, retries=1))
    assert counters["success"] == 1
    assert counters["duplicate"] == 1
