"""Network seam: session factory + retrying GET/POST."""
import pytest
import requests
import responses

from vkdl.config import DownloadConfig
from vkdl.http import get, make_session, post


def test_make_session_installs_common_headers():
    s = make_session()
    assert "Mozilla" in s.headers["User-Agent"]
    assert s.headers["Accept-Language"] == "ru"


@responses.activate
def test_get_returns_response_on_success():
    responses.add(responses.GET, "https://s/ok", body=b"DATA", status=200)
    r = get(requests.Session(), "https://s/ok", DownloadConfig())
    assert r.content == b"DATA"


@responses.activate
def test_get_retries_transient_failure_then_succeeds():
    responses.add(responses.GET, "https://s/flaky",
                  body=requests.exceptions.ConnectionError("x"))
    responses.add(responses.GET, "https://s/flaky", body=b"OK", status=200)
    r = get(requests.Session(), "https://s/flaky",
            DownloadConfig(retries=2, backoff_base=0))
    assert r.content == b"OK"


@responses.activate
def test_get_retries_5xx_then_succeeds():
    responses.add(responses.GET, "https://s/5", status=500)
    responses.add(responses.GET, "https://s/5", body=b"OK", status=200)
    r = get(requests.Session(), "https://s/5",
            DownloadConfig(retries=2, backoff_base=0))
    assert r.content == b"OK"


@responses.activate
def test_get_raises_after_exhausting_retries():
    for _ in range(3):
        responses.add(responses.GET, "https://s/dead",
                      body=requests.exceptions.ConnectionError("down"))
    with pytest.raises(requests.ConnectionError):
        get(requests.Session(), "https://s/dead",
            DownloadConfig(retries=3, backoff_base=0))


@responses.activate
def test_get_404_returned_without_retry():
    responses.add(responses.GET, "https://s/gone", status=404)
    r = get(requests.Session(), "https://s/gone",
            DownloadConfig(retries=3, backoff_base=0))
    assert r.status_code == 404
    assert len(responses.calls) == 1


@responses.activate
def test_post_sends_data_and_returns_response():
    responses.add(responses.POST, "https://s/ajax", json={"payload": []},
                  status=200)
    r = post(requests.Session(), "https://s/ajax", DownloadConfig(),
             data={"al": "1"})
    assert r.json() == {"payload": []}
