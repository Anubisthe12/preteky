#!/usr/bin/env python3
"""
Scraper pre beh.sk — bezecke preteky
Scrapuje /terminy/ (stránky 1..N) + /starsie-terminy/ (archív).

Výstup: data/preteky.json
"""

import json
import re
import sys
import time
from html import unescape
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

BASE_URL = "https://beh.sk"
DELAY = 0.4  # sekundy medzi requestmi


def fetch(url: str) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; beh-scraper/1.0)"})
    with urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8")


def strip_tags(s: str) -> str:
    return unescape(re.sub(r"<[^>]+>", " ", s)).strip()


def normalize_date(raw: str) -> str:
    """'MM-DD-YYYY' → 'YYYY-MM-DD'"""
    m = re.match(r"(\d{2})-(\d{2})-(\d{4})", raw.strip())
    return f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else raw.strip()


def parse_races(html: str) -> list[dict]:
    races = []

    for entry in re.findall(
        r'class="pretek-entry">(.*?)(?=class="pretek-entry"|</ul>|</div>\s*</main>)',
        html,
        re.DOTALL,
    ):
        race = {}

        # Dátum
        m = re.search(r'<time[^>]+datetime="([^"]+)"', entry)
        race["datum"] = normalize_date(m.group(1)) if m else ""

        # Názov + URL
        m = re.search(r'class="pretek-entry__title[^"]*"\s*[^>]*href="([^"]+)"[^>]*>([^<]+)', entry)
        if not m:
            m = re.search(r'href="(https://beh\.sk/pretek/[^"]+)"[^>]*>([^<]{3,80})</a>', entry)
        if m:
            race["url"] = m.group(1).strip()
            race["nazov"] = unescape(m.group(2).strip())
        else:
            continue  # bez názvu nič neukladáme

        # Mesto
        m = re.search(r'class="pretek-entry__city[^"]*"[^>]*>([^<]+)', entry)
        race["mesto"] = unescape(m.group(1).strip()) if m else ""

        # Detailné info z hover tabuľky (Dĺžka trate, Povrch, Štart, Miesto, Organizátor …)
        info = {}
        for row in re.findall(
            r'pretek-hover__infocell--label[^>]*>(.*?)</div>\s*'
            r'<div[^>]*pretek-hover__infocell--value[^>]*>(.*?)</div>',
            entry,
            re.DOTALL,
        ):
            label = strip_tags(row[0]).rstrip(":").strip()
            value = strip_tags(row[1]).strip()
            if label:
                info[label] = value
        if info:
            race["info"] = info

        races.append(race)

    return races


def last_page(html: str) -> int:
    """Zistí číslo poslednej strany z paginátora."""
    nums = re.findall(r'/terminy/page/(\d+)/', html)
    return max((int(n) for n in nums), default=1)


def scrape_terminy() -> list[dict]:
    print("Scrapujem /terminy/ …")
    first_html = fetch(f"{BASE_URL}/terminy/")
    total = last_page(first_html)
    print(f"  Nájdených {total} strán")

    all_races = parse_races(first_html)
    print(f"  Strana 1: {len(all_races)} pretekov")

    for page in range(2, total + 1):
        time.sleep(DELAY)
        url = f"{BASE_URL}/terminy/page/{page}/"
        try:
            html = fetch(url)
            batch = parse_races(html)
            all_races.extend(batch)
            print(f"  Strana {page}: {len(batch)} pretekov")
        except (URLError, HTTPError) as e:
            print(f"  Strana {page}: chyba — {e}", file=sys.stderr)

    return all_races


def scrape_starsie() -> list[dict]:
    """Archív starších termínov — stránkované cez ?pg=N."""
    print("Scrapujem /starsie-terminy/ …")
    all_races = []
    page = 1

    while True:
        url = f"{BASE_URL}/starsie-terminy/?pg={page}"
        try:
            time.sleep(DELAY)
            html = fetch(url)
            batch = parse_races(html)
            if not batch:
                break
            all_races.extend(batch)
            print(f"  Strana {page}: {len(batch)} pretekov")

            # Koniec: ak nie je ďalšia strana v paginátore
            if f"pg={page + 1}" not in html and f"pg={page+1}" not in html:
                break
            page += 1
        except (URLError, HTTPError) as e:
            print(f"  Strana {page}: chyba — {e}", file=sys.stderr)
            break

    return all_races


def main():
    races = scrape_terminy()
    races += scrape_starsie()

    # Deduplikácia podľa URL
    seen: set[str] = set()
    unique = []
    for r in races:
        if r["url"] not in seen:
            seen.add(r["url"])
            unique.append(r)

    unique.sort(key=lambda r: r.get("datum", ""), reverse=True)

    out = DATA_DIR / "preteky.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)

    print(f"\nCelkom {len(unique)} unikátnych pretekov → {out}")

    print("\nUkážka (5 najnovších):")
    for r in unique[:5]:
        print(f"  [{r['datum']}] {r['nazov']} — {r.get('mesto', '')}")
        if "info" in r:
            for k, v in list(r["info"].items())[:2]:
                print(f"           {k}: {v}")


if __name__ == "__main__":
    main()
