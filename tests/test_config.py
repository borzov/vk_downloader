import os
from vkdl import config

def test_headers_have_browser_ua():
    assert "User-Agent" in config.HEADERS
    assert "Mozilla/5.0" in config.HEADERS["User-Agent"]

def test_default_download_config():
    c = config.DownloadConfig()
    assert c.max_workers == 5
    assert c.retries == 3
    assert c.ajax_page_size == 40

def test_get_access_token_absent(monkeypatch):
    monkeypatch.delenv("VK_ACCESS_TOKEN", raising=False)
    assert config.get_access_token() is None

def test_get_access_token_present(monkeypatch):
    monkeypatch.setenv("VK_ACCESS_TOKEN", "tok123")
    assert config.get_access_token() == "tok123"

def test_get_access_token_empty_is_none(monkeypatch):
    monkeypatch.setenv("VK_ACCESS_TOKEN", "")
    assert config.get_access_token() is None
