"""CLI: argv -> download job -> rendered report. No importlib hacks."""
from pathlib import Path

import vk_downloader as cli
from vkdl.job import DownloadReport


def _report(status="ok", **extra):
    base = dict(status=status, title="My Album",
                album_dir=Path("My Album") if status == "ok" else None,
                counters={"success": 1, "skipped": 0, "duplicate": 0, "error": 0},
                elapsed=1.5)
    base.update(extra)
    return DownloadReport(**base)


def test_validate_url_accepts_album():
    assert cli.validate_url("https://vk.com/album-18515186_240802273")
    assert cli.validate_url("https://vk.com/album12345_67890")


def test_validate_url_rejects_garbage():
    assert not cli.validate_url("https://vk.com/video-1_2")
    assert not cli.validate_url("not a url")


def test_main_no_args_returns_error_code():
    assert cli.main([]) == 1


def test_main_bad_url_returns_error_code():
    assert cli.main(["https://vk.com/video-1_2"]) == 1


def test_main_ok_album_renders_report_and_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(cli, "download_album", lambda *a, **k: _report())
    assert cli.main(["https://vk.com/album-1_2"]) == 0
    out = capsys.readouterr().out
    assert "📁" in out
    assert "✅ 1" in out


def test_main_network_error_exits_one(monkeypatch, capsys):
    monkeypatch.setattr(cli, "download_album",
                        lambda *a, **k: _report("network_error", error="down"))
    assert cli.main(["https://vk.com/album-1_2"]) == 1
    assert "down" in capsys.readouterr().out


def test_main_empty_album_exits_one(monkeypatch, capsys):
    monkeypatch.setattr(cli, "download_album",
                        lambda *a, **k: _report("empty"))
    assert cli.main(["https://vk.com/album-1_2"]) == 1
    assert "закрыт или пуст" in capsys.readouterr().out


def test_batch_runs_each_task_as_a_job(monkeypatch, tmp_path, capsys):
    f = tmp_path / "batch.csv"
    f.write_text("Name;DateStart;AlbumLink\n"
                 "Event;2024-12-25 18:00:00;https://vk.com/album-1_2\n"
                 "Other;2024-07-15;https://vk.com/album-3_4\n",
                 encoding="utf-8")
    calls = []

    def fake_download(url, **kwargs):
        calls.append((url, kwargs))
        return _report()

    monkeypatch.setattr(cli, "download_album", fake_download)
    monkeypatch.setattr(cli.time, "sleep", lambda s: None)
    assert cli.main(["--batch", str(f)]) == 0
    assert [c[0] for c in calls] == ["https://vk.com/album-1_2",
                                     "https://vk.com/album-3_4"]
    assert calls[0][1]["custom_title"] == "2024-12-25 - Event"
    assert "1/2" in capsys.readouterr().out


def test_batch_missing_csv_is_an_error(monkeypatch, capsys):
    assert cli.main(["--batch", "/no/such/file.csv"]) == 1
    assert "CSV" in capsys.readouterr().out


def test_batch_bad_url_row_is_skipped(monkeypatch, tmp_path, capsys):
    f = tmp_path / "b.csv"
    f.write_text("Name;DateStart;AlbumLink\n"
                 "X;2024-01-01;https://vk.com/video-1_2\n",
                 encoding="utf-8")
    monkeypatch.setattr(cli, "download_album", lambda *a, **k: _report())
    assert cli.main(["--batch", str(f)]) == 0
    assert "Неверный URL" in capsys.readouterr().out
