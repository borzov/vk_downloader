"""CSV batch task parsing. Tolerant of delimiter, BOM, header case, date formats."""
import csv
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BatchTask:
    name: str
    date: str
    album_url: str


def _norm_date(raw: str) -> str:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return raw


def parse_csv(path: str) -> list:
    tasks = []
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            first = f.readline()
            f.seek(0)
            delim = ";" if ";" in first else ","
            reader = csv.DictReader(f, delimiter=delim)
            for row in reader:
                low = {k.lower().strip(): (v or "").strip() for k, v in row.items()}
                name = low.get("name", "")
                date = low.get("datestart", "")
                url = low.get("albumlink", "")
                if not (name and date and url):
                    continue
                tasks.append(BatchTask(name=name, date=_norm_date(date), album_url=url))
        return tasks
    except FileNotFoundError:
        return []
    except Exception:
        return []
