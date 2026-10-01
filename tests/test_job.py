"""Download jobs: the whole pipeline exercised through one interface."""
import pytest
import requests
import responses

from vkdl.job import DownloadReport, download_album
from vkdl.models import Photo

IMG_A = "https://s/a.jpg?as=10x10&cs=10x0"
IMG_B = "https://s/b.jpg?as=10x10&cs=10x0"


def _ok_source(photos, title="Job Title"):
    def source(album_url, session, cfg):
        return photos, title
    return source


@responses.activate
def test_ok_job_writes_files_and_reports(tmp_path):
    responses.add(responses.GET, "https://s/a.jpg", body=b"AAA", status=200)
    responses.add(responses.GET, "https://s/b.jpg", body=b"BBB", status=200)
    photos = [Photo(id="1_1", urls=[IMG_A]), Photo(id="1_2", urls=[IMG_B])]
    report = download_album("https://vk.com/album-1_2",
                            sources=[_ok_source(photos, "My Album")],
                            out_base=tmp_path)
    assert report.status == "ok"
    assert report.ok is True
    assert report.album_dir == tmp_path / "My Album"
    assert report.counters == {"success": 2, "skipped": 0, "duplicate": 0, "error": 0}
    assert (tmp_path / "My Album" / "001_1_1.jpg").exists()
    assert (tmp_path / "My Album" / "002_1_2.jpg").exists()
    assert report.elapsed >= 0


@responses.activate
def test_custom_title_is_sanitized_into_dir_name(tmp_path):
    responses.add(responses.GET, "https://s/a.jpg", body=b"AAA", status=200)
    photos = [Photo(id="1_1", urls=[IMG_A])]
    report = download_album("https://vk.com/album-1_2",
                            sources=[_ok_source(photos)],
                            custom_title="a/b:c", out_base=tmp_path)
    assert report.album_dir == tmp_path / "a_b_c"


def test_network_failure_is_a_report_not_a_crash():
    def boom(album_url, session, cfg):
        raise requests.RequestException("connection refused")

    report = download_album("https://vk.com/album-1_2", sources=[boom])
    assert report.status == "network_error"
    assert report.ok is False
    assert "connection refused" in report.error
    assert report.album_dir is None


def test_album_without_photos_reports_empty():
    report = download_album("https://vk.com/album-1_2",
                            sources=[lambda *a: ([], "Private")])
    assert report.status == "empty"
    assert report.ok is False


def test_unexpected_bugs_propagate_unmasked():
    def bug(album_url, session, cfg):
        raise ValueError("real bug")

    with pytest.raises(ValueError):
        download_album("https://vk.com/album-1_2", sources=[bug])
