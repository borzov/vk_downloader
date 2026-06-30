#!/usr/bin/env python3
"""VK Album Photo Downloader — thin CLI over the vkdl package.
Usage:
  uv run vk_downloader.py <album_url> [threads]
  uv run vk_downloader.py --batch <csv> [threads]
"""
import re
import sys
import time
from pathlib import Path
import requests
from vkdl.config import HEADERS, DownloadConfig, get_access_token, MAX_WORKERS_LIMIT
from vkdl.resolver import resolve_album
from vkdl.downloader import download_all, sanitize_filename
from vkdl.batch import parse_csv

_URL_RE = re.compile(r"https?://vk\.com/album-?\d+_\d+")


def validate_url(url: str) -> bool:
    return bool(_URL_RE.match(url))


def run_single(album_url: str, max_workers: int, custom_title: str = None) -> bool:
    session = requests.Session()
    cfg = DownloadConfig(max_workers=max_workers)
    token = get_access_token()
    try:
        photos, title = resolve_album(album_url, session, cfg, token=token)
    except requests.RequestException as e:
        print(f"❌ Сетевая ошибка при загрузке альбома: {e}")
        return False
    if not photos:
        print("❌ Фотографии не найдены (альбом закрыт или пуст).")
        return False
    title = sanitize_filename(custom_title or title)
    album_dir = Path(title)
    print(f"📁 Папка: {album_dir.absolute()} | потоков: {max_workers}")
    start = time.time()
    counters = download_all(photos, album_dir, session, cfg)
    print(f"✅ {counters['success']}  🔗 {counters['duplicate']}  "
          f"⏭️ {counters['skipped']}  ❌ {counters['error']}  "
          f"за {time.time()-start:.1f}с")
    return True


def _run_batch(csv_file: str, max_workers: int) -> None:
    tasks = parse_csv(csv_file)
    if not tasks:
        print("❌ Нет валидных заданий в CSV")
        return
    for i, t in enumerate(tasks, 1):
        print(f"\n=== {i}/{len(tasks)}: {t.name} ({t.date}) ===")
        if not validate_url(t.album_url):
            print("❌ Неверный URL, пропуск")
            continue
        run_single(t.album_url, max_workers, custom_title=f"{t.date} - {t.name}")
        if i < len(tasks):
            time.sleep(2)


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
            _run_batch(argv[1], _parse_workers(argv, 2))
            return 0
        url = argv[0]
        if not validate_url(url):
            print("❌ Неверный формат URL альбома")
            return 1
        ok = run_single(url, _parse_workers(argv, 1))
        return 0 if ok else 1
    except ValueError as e:
        print(f"❌ {e}")
        return 1
    except KeyboardInterrupt:
        print("\n⚠️ Прервано пользователем")
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
