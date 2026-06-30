from vkdl.batch import parse_csv


def test_parse_csv_semicolon(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("Name;DateStart;AlbumLink\n"
                 "Event;2024-12-25 18:00:00;https://vk.com/album-1_2\n",
                 encoding="utf-8")
    tasks = parse_csv(str(f))
    assert len(tasks) == 1
    assert tasks[0].name == "Event"
    assert tasks[0].date == "2024-12-25"
    assert tasks[0].album_url == "https://vk.com/album-1_2"


def test_parse_csv_comma_and_bom(tmp_path):
    f = tmp_path / "b.csv"
    f.write_text("﻿Name,DateStart,AlbumLink\nX,2024-07-15,https://vk.com/album-3_4\n",
                 encoding="utf-8")
    tasks = parse_csv(str(f))
    assert tasks[0].date == "2024-07-15"


def test_parse_csv_skips_incomplete_rows(tmp_path):
    f = tmp_path / "c.csv"
    f.write_text("Name;DateStart;AlbumLink\n;;https://vk.com/album-1_2\n",
                 encoding="utf-8")
    assert parse_csv(str(f)) == []


def test_parse_csv_missing_file():
    assert parse_csv("/no/such/file.csv") == []
