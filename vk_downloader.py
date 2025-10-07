#!/usr/bin/env python3
"""
VK Album Photo Downloader
Скачивает фотографии из альбома ВКонтакте в максимальном качестве
Использование: 
  uv run vk_downloader.py <URL_альбома> [количество_потоков]
  uv run vk_downloader.py --batch <CSV_файл> [количество_потоков]
"""

import re
import sys
import time
import json
import hashlib
import csv
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from datetime import datetime
import requests
from bs4 import BeautifulSoup


def calculate_file_hash(filepath: Path) -> str:
    """Вычисляет SHA256 хеш файла"""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def get_all_quality_urls(style_url: str) -> list:
    """Извлекает все доступные URL в порядке убывания качества"""
    match = re.search(r'url\((https://[^)]+)\)', style_url)
    if not match:
        return []
    
    url = match.group(1)
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    
    urls = []
    
    # Сначала пробуем оригинал без параметров
    base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    urls.append(base_url)
    
    if 'as' in params:
        sizes = params['as'][0].split(',')
        # Сортируем размеры от большего к меньшему
        sizes_sorted = sorted(sizes, key=lambda x: int(x.split('x')[0]), reverse=True)
        
        # Получаем текущий cs параметр
        current_cs = params.get('cs', [''])[0]
        
        for size in sizes_sorted:
            # Создаем новые параметры
            new_params = params.copy()
            
            # Определяем новый cs параметр
            # Если в оригинале cs заканчивается на x0, сохраняем этот формат
            if current_cs.endswith('x0'):
                width = size.split('x')[0]
                new_cs = f"{width}x0"
            else:
                new_cs = size
            
            new_params['cs'] = [new_cs]
            
            # Собираем URL обратно
            new_query = urlencode(new_params, doseq=True)
            new_url = urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                new_query,
                parsed.fragment
            ))
            urls.append(new_url)
    
    # Добавляем оригинальный URL как fallback
    if url not in urls:
        urls.append(url)
    
    return urls


def sanitize_filename(filename: str) -> str:
    """Очищает имя файла от недопустимых символов"""
    return re.sub(r'[<>:"/\\|?*]', '_', filename)


def parse_photos_from_html(html_content: str) -> list:
    """Извлекает фотографии из HTML"""
    soup = BeautifulSoup(html_content, 'html.parser')
    photos = []
    
    photo_rows = soup.select('.photos_row')
    for photo_row in photo_rows:
        photo_id = photo_row.get('data-id', '')
        style = photo_row.get('style', '')
        photo_urls = get_all_quality_urls(style)
        if photo_urls and photo_id:
            photos.append({'id': photo_id, 'urls': photo_urls})
    
    return photos


def check_album_accessible(album_url: str, headers: dict, session: requests.Session) -> tuple:
    """
    Проверяет доступность альбома
    Возвращает (доступен: bool, сообщение: str)
    """
    try:
        response = session.get(album_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Проверяем наличие фотографий
        photo_rows = soup.select('.photos_row')
        if not photo_rows:
            # Проверяем, не закрыт ли альбом
            if 'Access denied' in response.text or 'Доступ запрещён' in response.text:
                return False, "Доступ запрещён"
            if 'Album not found' in response.text or 'Альбом не найден' in response.text:
                return False, "Альбом не найден"
            return False, "Фотографии не найдены"
        
        return True, "OK"
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return False, "404 Not Found"
        elif e.response.status_code == 403:
            return False, "403 Forbidden"
        else:
            return False, f"HTTP {e.response.status_code}"
    except requests.exceptions.Timeout:
        return False, "Timeout"
    except Exception as e:
        return False, f"Error: {str(e)[:50]}"


def load_all_photos_ajax(album_url: str, headers: dict, session: requests.Session, silent: bool = False) -> tuple:
    """Загружает все фотографии через AJAX запросы"""
    
    if not silent:
        print(f"📡 Загружаю информацию об альбоме...\n")
    
    all_photos = []
    
    # Загружаем начальную страницу
    response = session.get(album_url, headers=headers)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Извлекаем название альбома
    album_title_elem = soup.select_one('.photos_album_intro h1')
    album_title = album_title_elem.text.strip() if album_title_elem else 'VK_Album'
    
    # Извлекаем общее количество фото
    count_elem = soup.select_one('.ui_crumb_count')
    total_count = int(count_elem.text.strip()) if count_elem else 0
    
    # Собираем фото с первой страницы
    photos = parse_photos_from_html(response.text)
    all_photos.extend(photos)
    
    if not silent:
        print(f"📸 Альбом: {album_title}")
        print(f"📊 Всего фотографий: {total_count}")
        print(f"✓ Загружено с первой страницы: {len(photos)}\n")
    
    offset = len(all_photos)
    
    # Загружаем остальные фото через AJAX
    while offset < total_count:
        if not silent:
            print(f"📡 Загружаю метаданные фото {offset + 1}-{min(offset + 40, total_count)}...", end=' ')
        
        ajax_data = {
            'al': '1',
            'offset': str(offset),
            'part': '1',
            'rev': ''
        }
        
        ajax_headers = headers.copy()
        ajax_headers.update({
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': '*/*',
            'Origin': 'https://vk.com',
            'Referer': album_url,
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin'
        })
        
        try:
            ajax_response = session.post(album_url, data=ajax_data, headers=ajax_headers)
            ajax_response.raise_for_status()
            
            response_text = ajax_response.text
            
            try:
                json_data = json.loads(response_text)
                
                if 'payload' in json_data and isinstance(json_data['payload'], list):
                    payload = json_data['payload']
                    
                    html_content = None
                    for item in payload:
                        if isinstance(item, list) and len(item) >= 2:
                            if isinstance(item[1], str) and '<div' in item[1]:
                                html_content = item[1]
                                break
                    
                    if html_content:
                        photos = parse_photos_from_html(html_content)
                        
                        if not photos:
                            if not silent:
                                print("❌ Фото не найдены в ответе")
                            break
                        
                        all_photos.extend(photos)
                        offset = len(all_photos)
                        if not silent:
                            print(f"✓ ({len(photos)} шт.)")
                        
                        time.sleep(0.5)
                    else:
                        if not silent:
                            print("❌ HTML не найден в payload")
                        break
                else:
                    if not silent:
                        print("❌ Неверная структура JSON")
                    break
                    
            except json.JSONDecodeError as e:
                if not silent:
                    print(f"❌ Не удалось распарсить JSON: {e}")
                break
                
        except Exception as e:
            if not silent:
                print(f"❌ Ошибка: {e}")
            break
    
    if not silent:
        print(f"\n✅ Всего загружено метаданных: {len(all_photos)}/{total_count}\n")
    
    return all_photos, album_title


def find_duplicate_by_hash(album_dir: Path, file_hash: str, current_filename: str) -> Path:
    """Ищет файл с таким же хешем в директории"""
    for filepath in album_dir.glob('*.*'):
        if filepath.name == current_filename:
            continue
        if filepath.is_file() and filepath.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']:
            if calculate_file_hash(filepath) == file_hash:
                return filepath
    return None


def download_single_photo(args: tuple) -> dict:
    """Скачивает одну фотографию (для параллельного выполнения)"""
    idx, photo, album_dir, headers, session, total_photos = args
    
    photo_id = photo['id']
    photo_urls = photo['urls']
    
    # Определяем расширение файла (из первого URL)
    ext = '.jpg'
    if photo_urls and '.png' in photo_urls[0]:
        ext = '.png'
    elif photo_urls and '.webp' in photo_urls[0]:
        ext = '.webp'
    
    # Формируем имя файла
    filename = f"{idx:03d}_{photo_id.replace('-', '_')}{ext}"
    filepath = album_dir / filename
    
    # Проверяем, не скачан ли уже файл
    if filepath.exists():
        file_size = filepath.stat().st_size / 1024
        return {
            'status': 'skipped',
            'idx': idx,
            'filename': filename,
            'size': file_size,
            'message': 'пропущено'
        }
    
    # Пробуем скачать, начиная с максимального качества
    for url_idx, photo_url in enumerate(photo_urls):
        try:
            img_response = session.get(photo_url, headers=headers, stream=True, timeout=30)
            img_response.raise_for_status()
            
            # Сохраняем во временный файл
            temp_filepath = filepath.with_suffix(filepath.suffix + '.tmp')
            with open(temp_filepath, 'wb') as f:
                for chunk in img_response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            # Вычисляем хеш
            file_hash = calculate_file_hash(temp_filepath)
            
            # Проверяем на дубликаты
            duplicate = find_duplicate_by_hash(album_dir, file_hash, filename)
            if duplicate:
                temp_filepath.unlink()  # Удаляем временный файл
                file_size = duplicate.stat().st_size / 1024
                return {
                    'status': 'duplicate',
                    'idx': idx,
                    'filename': filename,
                    'size': file_size,
                    'duplicate_name': duplicate.name
                }
            
            # Переименовываем временный файл в финальный
            temp_filepath.rename(filepath)
            
            file_size = filepath.stat().st_size / 1024
            quality_note = f" (качество {url_idx + 1}/{len(photo_urls)})" if url_idx > 0 else ""
            
            return {
                'status': 'success',
                'idx': idx,
                'filename': filename,
                'size': file_size,
                'quality_note': quality_note,
                'is_original': url_idx == 0
            }
            
        except requests.exceptions.HTTPError as e:
            # Если 404, пробуем следующий размер
            if e.response.status_code == 404:
                continue
            else:
                return {
                    'status': 'error',
                    'idx': idx,
                    'filename': filename,
                    'error': str(e)
                }
        except Exception as e:
            return {
                'status': 'error',
                'idx': idx,
                'filename': filename,
                'error': str(e)
            }
    
    return {
        'status': 'error',
        'idx': idx,
        'filename': filename,
        'error': 'Все URL недоступны'
    }


def download_vk_album(album_url: str, max_workers: int = 5, custom_title: str = None):
    """Скачивает все фотографии из альбома ВКонтакте"""
    
    print(f"🔍 Анализирую альбом: {album_url}\n")
    
    # Создаем сессию для сохранения cookies
    session = requests.Session()
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0.1 Safari/605.1.15',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive'
    }
    
    # Загружаем все фото (включая AJAX)
    all_photos, album_title = load_all_photos_ajax(album_url, headers, session)
    
    if not all_photos:
        print("\n❌ Фотографии не найдены. Возможно, альбом закрыт или требуется авторизация.")
        return False
    
    # Используем custom_title если передан, иначе оригинальное название
    if custom_title:
        album_title = custom_title
    
    # Создаем папку для альбома
    album_title = sanitize_filename(album_title)
    album_dir = Path(album_title)
    album_dir.mkdir(exist_ok=True)
    
    print(f"📁 Папка: {album_dir.absolute()}")
    print(f"🚀 Параллельных потоков: {max_workers}")
    print(f"{'='*70}\n")
    
    # Счетчики
    downloaded = 0
    skipped = 0
    duplicates = 0
    errors = 0
    originals = 0
    
    # Блокировка для потокобезопасного вывода
    print_lock = Lock()
    
    # Подготавливаем аргументы для загрузки
    download_args = [
        (idx, photo, album_dir, headers, session, len(all_photos))
        for idx, photo in enumerate(all_photos, 1)
    ]
    
    start_time = time.time()
    
    # Параллельная загрузка
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Запускаем все задачи
        future_to_args = {executor.submit(download_single_photo, args): args for args in download_args}
        
        # Обрабатываем результаты по мере завершения
        for future in as_completed(future_to_args):
            result = future.result()
            
            with print_lock:
                idx = result['idx']
                filename = result['filename']
                
                if result['status'] == 'success':
                    downloaded += 1
                    if result.get('is_original', False):
                        originals += 1
                    size = result['size']
                    quality_note = result.get('quality_note', '')
                    print(f"[{idx:3d}/{len(all_photos)}] ✅ {filename:<45} ({size:>7.1f} KB){quality_note}")
                
                elif result['status'] == 'skipped':
                    skipped += 1
                    size = result['size']
                    print(f"[{idx:3d}/{len(all_photos)}] ⏭️  {filename:<45} ({size:>7.1f} KB) - {result['message']}")
                
                elif result['status'] == 'duplicate':
                    duplicates += 1
                    size = result['size']
                    duplicate_name = result['duplicate_name']
                    print(f"[{idx:3d}/{len(all_photos)}] 🔗 {filename:<45} ({size:>7.1f} KB) - дубликат {duplicate_name}")
                
                elif result['status'] == 'error':
                    errors += 1
                    error = result['error']
                    print(f"[{idx:3d}/{len(all_photos)}] ❌ {filename:<45} - {error}")
    
    elapsed_time = time.time() - start_time
    
    # Итоговая статистика
    print(f"\n{'='*70}")
    print(f"🎉 Скачивание завершено!")
    print(f"{'='*70}")
    print(f"✅ Скачано:      {downloaded:>4} (оригиналов: {originals})")
    print(f"🔗 Дубликатов:   {duplicates:>4}")
    print(f"⏭️  Пропущено:    {skipped:>4}")
    print(f"❌ Ошибок:       {errors:>4}")
    print(f"📊 Всего:        {len(all_photos):>4}")
    print(f"⏱️  Время:        {elapsed_time:.1f} сек")
    print(f"⚡ Скорость:     {len(all_photos)/elapsed_time:.2f} фото/сек")
    print(f"📁 Папка:        {album_dir.absolute()}")
    print(f"{'='*70}")
    
    return True


def parse_csv_file(csv_file: str) -> list:
    """
    Парсит CSV файл с заданиями
    Возвращает список словарей с полями: name, date, album_url
    """
    tasks = []
    
    try:
        with open(csv_file, 'r', encoding='utf-8-sig') as f:  # utf-8-sig автоматически удаляет BOM
            # Определяем разделитель (может быть ; или ,)
            first_line = f.readline()
            f.seek(0)
            delimiter = ';' if ';' in first_line else ','
            
            reader = csv.DictReader(f, delimiter=delimiter)
            
            for row_num, row in enumerate(reader, 2):  # Начинаем с 2, т.к. 1 - заголовок
                # Ищем нужные колонки (регистронезависимо)
                name = None
                date_str = None
                album_url = None
                
                # Выводим отладочную информацию для первой строки
                if row_num == 2:
                    print(f"🔍 Найденные колонки: {list(row.keys())}\n")
                
                for key, value in row.items():
                    key_lower = key.lower().strip()
                    if key_lower == 'name':
                        name = value.strip()
                    elif key_lower == 'datestart':
                        date_str = value.strip()
                    elif key_lower == 'albumlink':
                        album_url = value.strip()
                
                if not name or not date_str or not album_url:
                    print(f"⚠️  Строка {row_num}: пропущена (отсутствуют обязательные поля)")
                    print(f"    Name: {name}")
                    print(f"    DateStart: {date_str}")
                    print(f"    AlbumLink: {album_url}\n")
                    continue
                
                # Парсим дату
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                    date_formatted = date_obj.strftime('%Y-%m-%d')
                except ValueError:
                    try:
                        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                        date_formatted = date_str
                    except ValueError:
                        print(f"⚠️  Предупреждение: не удалось распарсить дату '{date_str}', используется как есть")
                        date_formatted = date_str
                
                tasks.append({
                    'name': name,
                    'date': date_formatted,
                    'album_url': album_url
                })
        
        return tasks
        
    except FileNotFoundError:
        print(f"❌ Ошибка: файл '{csv_file}' не найден")
        return []
    except Exception as e:
        print(f"❌ Ошибка при чтении CSV файла: {e}")
        import traceback
        traceback.print_exc()
        return []


def process_batch(csv_file: str, max_workers: int = 5):
    """Обрабатывает пакет альбомов из CSV файла"""
    
    print(f"📋 Загружаю задания из файла: {csv_file}\n")
    
    tasks = parse_csv_file(csv_file)
    
    if not tasks:
        print("❌ Не найдено ни одного задания в файле")
        return
    
    print(f"✅ Загружено заданий: {len(tasks)}\n")
    print(f"{'='*80}\n")
    
    # Создаем сессию для проверки доступности
    session = requests.Session()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0.1 Safari/605.1.15',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive'
    }
    
    # Статистика
    total_tasks = len(tasks)
    successful_tasks = 0
    failed_tasks = 0
    skipped_tasks = 0
    
    # Обрабатываем каждое задание
    for idx, task in enumerate(tasks, 1):
        name = task['name']
        date = task['date']
        album_url = task['album_url']
        
        print(f"{'='*80}")
        print(f"📌 Задание {idx}/{total_tasks}")
        print(f"{'='*80}")
        print(f"📅 Дата:    {date}")
        print(f"📝 Название: {name}")
        print(f"🔗 URL:     {album_url}")
        print()
        
        # Проверяем формат URL
        if not re.match(r'https?://vk\.com/album-?\d+_\d+', album_url):
            print(f"❌ Неверный формат URL альбома, пропускаю...\n")
            failed_tasks += 1
            continue
        
        # Проверяем доступность альбома
        print("🔍 Проверяю доступность альбома...", end=' ')
        accessible, message = check_album_accessible(album_url, headers, session)
        
        if not accessible:
            print(f"❌ {message}")
            print(f"⏭️  Пропускаю альбом\n")
            skipped_tasks += 1
            continue
        
        print(f"✅ {message}\n")
        
        # Формируем название папки с датой
        custom_title = f"{date} - {name}"
        
        # Скачиваем альбом
        try:
            success = download_vk_album(album_url, max_workers, custom_title)
            if success:
                successful_tasks += 1
            else:
                failed_tasks += 1
        except Exception as e:
            print(f"\n❌ Ошибка при скачивании альбома: {e}")
            failed_tasks += 1
        
        print()
        
        # Небольшая пауза между альбомами
        if idx < total_tasks:
            time.sleep(2)
    
    # Итоговая статистика по всем заданиям
    print(f"\n{'='*80}")
    print(f"🏁 ИТОГОВАЯ СТАТИСТИКА")
    print(f"{'='*80}")
    print(f"✅ Успешно обработано: {successful_tasks}/{total_tasks}")
    print(f"⏭️  Пропущено:          {skipped_tasks}/{total_tasks}")
    print(f"❌ Ошибок:             {failed_tasks}/{total_tasks}")
    print(f"{'='*80}")


def main():
    """Главная функция"""
    if len(sys.argv) < 2:
        print("❌ Ошибка: не указаны параметры")
        print("\n📖 Использование:")
        print(f"   # Одиночный альбом:")
        print(f"   uv run {sys.argv[0]} <URL_альбома> [количество_потоков]")
        print(f"\n   # Пакетная обработка:")
        print(f"   uv run {sys.argv[0]} --batch <CSV_файл> [количество_потоков]")
        print("\n💡 Примеры:")
        print(f"   uv run {sys.argv[0]} https://vk.com/album-18515186_240802273")
        print(f"   uv run {sys.argv[0]} https://vk.com/album-18515186_240802273 10")
        print(f"   uv run {sys.argv[0]} --batch albums.csv")
        print(f"   uv run {sys.argv[0]} --batch albums.csv 10")
        print("\n📋 Формат CSV файла:")
        print("   Name;DateStart;AlbumLink")
        print('   "Название события";2019-05-01 00:00:00;https://vk.com/album-123_456')
        sys.exit(1)
    
    # Проверяем режим работы
    if sys.argv[1] == '--batch':
        # Пакетный режим
        if len(sys.argv) < 3:
            print("❌ Ошибка: не указан CSV файл")
            print(f"💡 Использование: uv run {sys.argv[0]} --batch <CSV_файл> [количество_потоков]")
            sys.exit(1)
        
        csv_file = sys.argv[2]
        max_workers = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        
        # Проверяем количество потоков
        if max_workers < 1 or max_workers > 20:
            print("❌ Ошибка: количество потоков должно быть от 1 до 20")
            sys.exit(1)
        
        try:
            process_batch(csv_file, max_workers)
        except KeyboardInterrupt:
            print("\n\n⚠️  Обработка прервана пользователем")
            sys.exit(0)
        except Exception as e:
            print(f"\n❌ Критическая ошибка: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    else:
        # Одиночный режим
        album_url = sys.argv[1]
        max_workers = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        
        # Проверяем формат URL
        if not re.match(r'https?://vk\.com/album-?\d+_\d+', album_url):
            print("❌ Ошибка: неверный формат URL альбома")
            print("💡 URL должен быть в формате: https://vk.com/album{owner_id}_{album_id}")
            sys.exit(1)
        
        # Проверяем количество потоков
        if max_workers < 1 or max_workers > 20:
            print("❌ Ошибка: количество потоков должно быть от 1 до 20")
            sys.exit(1)
        
        try:
            download_vk_album(album_url, max_workers)
        except KeyboardInterrupt:
            print("\n\n⚠️  Скачивание прервано пользователем")
            sys.exit(0)
        except Exception as e:
            print(f"\n❌ Критическая ошибка: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    main()
