#!/usr/bin/env python3
"""VK Album Photo Downloader — thin CLI over the vkdl package.
Usage:
  uv run vk_downloader.py <album_url> [threads]
  uv run vk_downloader.py --batch <csv> [threads]
"""
import sys
import time

from vkdl.album_ref import is_album_url
from vkdl.batch import parse_csv
from vkdl.config import MAX_WORKERS_LIMIT
from vkdl.job import download_album

_PAUSE_BETWEEN_ALBUMS_S = 2.0


def validate_url(url: str) -> bool:
    return is_album_url(url)


def _render(report) -> None:
    if report.status == "network_error":
        print(f"❌ Сетевая ошибка при загрузке альбома: {report.error}")
        return
    if report.status == "empty":
        print("❌ Фотографии не найдены (альбом закрыт или пуст).")
        return
    c = report.counters
    print(f"📁 Папка: {report.album_dir.absolute()} | "
          f"✅ {c['success']}  🔗 {c['duplicate']}  ⏭️ {c['skipped']}  "
          f"❌ {c['error']}  за {report.elapsed:.1f}с")


def _run_batch(csv_file: str, max_workers: int) -> int:
    try:
        tasks = parse_csv(csv_file)
    except OSError as e:
        print(f"❌ Не удалось прочитать CSV: {e}")
        return 1
    if not tasks:
        print("❌ Нет валидных заданий в CSV")
        return 1
    for i, t in enumerate(tasks, 1):
        print(f"\n=== {i}/{len(tasks)}: {t.name} ({t.date}) ===")
        if not validate_url(t.album_url):
            print("❌ Неверный URL, пропуск")
            continue
        report = download_album(t.album_url, max_workers=max_workers,
                                custom_title=f"{t.date} - {t.name}")
        _render(report)
        if i < len(tasks):
            time.sleep(_PAUSE_BETWEEN_ALBUMS_S)
    return 0


def _parse_workers(argv: list, pos: int) -> int:
    w = int(argv[pos]) if len(argv) > pos else 5
    if not 1 <= w <= MAX_WORKERS_LIMIT:
        raise ValueError(f"threads must be 1..{MAX_WORKERS_LIMIT}")
    return w


def main(argv: list) -> int:
    if not argv:
        print("Usage: vk_downloader.py <album_url> [threads] | --batch <csv> [threads]")
        return 1
    try:
        if argv[0] == "--batch":
            if len(argv) < 2:
                print("❌ Не указан CSV файл")
                return 1
            return _run_batch(argv[1], _parse_workers(argv, 2))
        url = argv[0]
        if not validate_url(url):
            print("❌ Неверный формат URL альбома")
            return 1
        report = download_album(url, max_workers=_parse_workers(argv, 1))
        _render(report)
        return 0 if report.ok else 1
    except ValueError as e:
        print(f"❌ {e}")
        return 1
    except KeyboardInterrupt:
        print("\n⚠️ Прервано пользователем")
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
