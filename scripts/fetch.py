"""Скачивает расписание групп колледжа ПВГУС с lk.tolgas.ru и сохраняет в data/*.json.

Запуск:
  python scripts/fetch.py                 # все группы колледжа (СП...)
  python scripts/fetch.py СПКС24 СПИС241  # только указанные
  python scripts/fetch.py --parse page.html  # разобрать сохранённую страницу (для проверки)

Только стандартная библиотека Python 3.9+.
"""
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://lk.tolgas.ru/public-schedule"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
UA = "Mozilla/5.0 (raspisanie-pwa; +https://github.com/qDoza/raspisanie)"
WEEKS_BACK, WEEKS_AHEAD = 1, 6
COLLEGE_PREFIX = "СП"

TYPE_MAP = [
    ("лек", "lec"),
    ("лаб", "lab"),
    ("практ", "prac"),
    ("семинар", "prac"),
    ("консульт", "cons"),
    ("экзам", "exam"),
    ("зач", "exam"),
]


def get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ru"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise last


def text(s):
    return html.unescape(re.sub(r"<[^>]+>", " ", s)).strip()


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def lesson_type(label):
    low = label.lower()
    for key, code in TYPE_MAP:
        if key in low:
            return code
    return "other"


def parse_group_page(page):
    """HTML страницы /public-schedule/group -> {"YYYY-MM-DD": [пары]}, "обновлено" с сайта."""
    days = {}
    parts = re.split(r'<div class="date-bar">', page)
    for part in parts[1:]:
        m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", part)
        if not m:
            continue
        date = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        lessons = []
        for item in re.split(r'<div class="lesson-item">', part)[1:]:
            num = re.search(r'lesson-number">\s*(\d+)', item)
            tm = re.search(r'lesson-time">\s*(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})', item)
            title = re.search(r'lesson-title">(.*?)</div>', item, re.S)
            details = re.search(r'lesson-details">(.*?)</div>', item, re.S)
            badge = re.search(r'class="badge[^"]*">(.*?)</span>', item, re.S)
            room = re.search(r'lesson-auditorium">(.*?)</span>', item, re.S)
            teacher = None
            notes = []
            if details:
                for line in re.split(r"<br\s*/?>", details.group(1)):
                    line = norm(text(re.sub(r'<span class="lesson-auditorium">.*?</span>', "", line, flags=re.S)))
                    if not line:
                        continue
                    if line.lower().startswith("преподаватель"):
                        teacher = norm(line.split(":", 1)[-1])
                    else:
                        notes.append(line)
            label = norm(text(badge.group(1))) if badge else ""
            lessons.append({
                "n": int(num.group(1)) if num else None,
                "start": tm.group(1).zfill(5) if tm else "",
                "end": tm.group(2).zfill(5) if tm else "",
                "title": norm(text(title.group(1))) if title else "",
                "type": lesson_type(label),
                "typeLabel": label,
                "room": norm(text(room.group(1))) if room else "",
                "teacher": teacher or "",
                **({"note": "; ".join(notes)} if notes else {}),
            })
        if lessons:
            days.setdefault(date, []).extend(lessons)
    upd = re.search(r"Обновлено:\s*([\d.]+\s+[\d:]+)", page)
    return days, (upd.group(1) if upd else None)


def college_groups():
    page = get(f"{BASE}/search/")
    m = re.search(r"\nconst groups = (\[.*?\]);", page)
    groups = json.loads(m.group(1)) if m else []
    return sorted(g for g in groups if g.startswith(COLLEGE_PREFIX))


def date_range():
    today = dt.date.today()
    monday = today - dt.timedelta(days=today.weekday())
    start = monday - dt.timedelta(weeks=WEEKS_BACK)
    end = monday + dt.timedelta(weeks=WEEKS_AHEAD, days=6)
    return start, end


def fetch_group(group, start, end):
    q = urllib.parse.urlencode({"id": group, "dateFrom": start.isoformat(), "dateTo": end.isoformat()})
    return parse_group_page(get(f"{BASE}/group?{q}"))


def save(group, days, site_updated, start, end):
    os.makedirs(DATA, exist_ok=True)
    out = {
        "group": group,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "siteUpdated": site_updated,
        "fetched": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "days": dict(sorted(days.items())),
    }
    with open(os.path.join(DATA, f"{group}.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))


def main(argv):
    if argv[:1] == ["--parse"]:
        page = open(argv[1], encoding="utf-8").read()
        days, upd = parse_group_page(page)
        g = re.search(r"Расписание группы\s+([^\s<]+)", page)
        p = re.search(r"Период:</strong>\s*([\d.]+)\s*—\s*([\d.]+)", page)
        to_iso = lambda s: dt.datetime.strptime(s, "%d.%m.%Y").date()  # noqa: E731
        save(g.group(1), days, upd, to_iso(p.group(1)), to_iso(p.group(2)))
        print(g.group(1), sum(len(v) for v in days.values()), "пар,", len(days), "дней")
        return 0

    groups = argv or college_groups()
    if not groups:
        print("Не удалось получить список групп", file=sys.stderr)
        return 1
    start, end = date_range()
    ok, failed = [], []
    for g in groups:
        try:
            days, upd = fetch_group(g, start, end)
            save(g, days, upd, start, end)
            ok.append(g)
            print(f"{g}: {sum(len(v) for v in days.values())} пар")
        except Exception as e:  # noqa: BLE001
            failed.append(g)
            print(f"{g}: ошибка {e}", file=sys.stderr)
        time.sleep(0.7)

    os.makedirs(DATA, exist_ok=True)
    index_path = os.path.join(DATA, "index.json")
    prev = {}
    if os.path.exists(index_path):
        prev = json.load(open(index_path, encoding="utf-8"))
    all_groups = sorted(set(prev.get("groups", [])) | set(ok))
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({
            "groups": all_groups,
            "fetched": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "failed": failed,
        }, f, ensure_ascii=False, indent=1)
    print(f"Готово: {len(ok)} групп, ошибок: {len(failed)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
