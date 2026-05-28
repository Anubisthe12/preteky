#!/usr/bin/env python3
"""
Multi-source scraper — bezecke preteky SK/CZ

Zdroje:
  pretekaj.sk     — HTML Bootstrap karty, ?perpage=50
  hrdosport.sk    — HTML ASP.NET tabuľka, ?SelectedYear=YYYY (roky 2014-2027)
  registrujsa.sk  — HTML SSR Bootstrap karty, ?rok=YYYY (roky 2019-2026)

Výstup: multi_preteky.json
"""

import json
import re
import sys
import time
from html import unescape
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

DELAY = 0.4

MONTH_SK = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "máj": "05", "jún": "06", "júl": "07", "aug": "08",
    "sep": "09", "okt": "10", "nov": "11", "dec": "12",
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}


def fetch(url: str) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; sk-race-scraper/1.0)"})
    with urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8")


def strip_tags(s: str) -> str:
    return unescape(re.sub(r"<[^>]+>", " ", s)).strip()


def clean(s: str) -> str:
    return re.sub(r"\s{2,}", " ", strip_tags(s)).strip()


# ── pretekaj.sk ─────────────────────────────────────────────────────────────

def scrape_pretekaj() -> list[dict]:
    """
    Zdroj: https://pretekaj.sk/sk/podujatia?perpage=50
    Stránka: Bootstrap karty, každá v .col-md-7
      h2 > a       → názov + URL
      .fa-globe    → miesto
      .fa-calendar → dátum (napr. "29.03.2026 - 18.10.2026")
      p            → popis
    """
    print("pretekaj.sk …")
    html = fetch("https://pretekaj.sk/sk/podujatia?perpage=50")

    # každý event je v bloku ohraničenom <div class="col-md-7">
    blocks = re.findall(
        r'<div class="col-md-7">(.*?)(?=<div class="col-md-7">|<div class="row"><!--Pagination-->)',
        html, re.DOTALL
    )

    races = []
    for blk in blocks:
        m = re.search(r'<h2[^>]*><a href="([^"]+)"[^>]*>([^<]+)</a>', blk)
        if not m:
            continue
        url, title = m.group(1).strip(), unescape(m.group(2).strip())

        # miesto: text vedľa fa-globe
        loc_m = re.search(r'fa-globe[^<]*</i>\s*([^<]+)', blk)
        mesto = unescape(loc_m.group(1).strip()) if loc_m else ""

        # dátum: text vedľa fa-calendar
        date_m = re.search(r'fa-calendar[^<]*</i>\s*([^<]+)', blk)
        datum = date_m.group(1).strip() if date_m else ""

        # popis: prvý <p> bez linky
        desc_m = re.search(r'<p>([^<]{10,})</p>', blk)
        popis = unescape(desc_m.group(1).strip()) if desc_m else ""

        races.append({
            "zdroj": "pretekaj.sk",
            "nazov": title,
            "url": url,
            "datum": datum,
            "mesto": mesto,
            "popis": popis,
        })

    print(f"  {len(races)} pretekov")
    return races


# ── hrdosport.sk ────────────────────────────────────────────────────────────

def _parse_hrdosport_table(html: str, year: int) -> list[dict]:
    races = []
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.DOTALL)
    if not tables:
        return races
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", tables[0], re.DOTALL)
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        if len(cells) < 4:
            continue
        datum_raw = clean(cells[1])
        nazov = clean(cells[2])
        mesto = clean(cells[3])
        if not nazov or not re.match(r"\d", datum_raw):
            continue

        # PDF linky (propozície + výsledky)
        pdfs = re.findall(r'href="(/Content/[^"]+\.pdf)"', row)

        races.append({
            "zdroj": "hrdosport.sk",
            "nazov": nazov,
            "url": f"https://www.hrdosport.sk/Events?SelectedYear={year}",
            "datum": datum_raw,
            "mesto": mesto,
            "info": {
                "propozicie": f"https://www.hrdosport.sk{pdfs[0]}" if len(pdfs) > 0 else "",
                "vysledky": f"https://www.hrdosport.sk{pdfs[1]}" if len(pdfs) > 1 else "",
            },
        })
    return races


def scrape_hrdosport() -> list[dict]:
    """
    Zdroj: https://www.hrdosport.sk/Events?SelectedYear=YYYY
    Stránka: Bootstrap + ASP.NET MVC tabuľka
      td[1] → dátum  td[2] → názov  td[3] → mesto
      PDF linky na propozície a výsledky
    Roky: 2014–2027
    """
    print("hrdosport.sk …")
    all_races: list[dict] = []
    for year in range(2014, 2028):
        time.sleep(DELAY)
        url = f"https://www.hrdosport.sk/Events?SelectedYear={year}"
        try:
            html = fetch(url)
            batch = _parse_hrdosport_table(html, year)
            if batch:
                all_races.extend(batch)
                print(f"  {year}: {len(batch)} pretekov")
        except (URLError, HTTPError) as e:
            print(f"  {year}: chyba — {e}", file=sys.stderr)
    return all_races


# ── registrujsa.sk ──────────────────────────────────────────────────────────

def _month_num(name: str) -> str:
    key = name.lower().strip()
    for k, v in MONTH_SK.items():
        if key.startswith(k):
            return v
    return "00"


def _year_from_vdn(vdn: str, fallback: int) -> int:
    """Extrahuje rok z VDN slugu: 'mich26'→2026, 'jaraba25'→2025, 'divocina2025'→2025."""
    m4 = re.search(r"(20\d{2})$", vdn)
    if m4:
        return int(m4.group(1))
    m2 = re.search(r"(\d{2})$", vdn)
    if m2:
        suffix = int(m2.group(1))
        return 2000 + suffix if suffix <= 50 else 1900 + suffix
    return fallback


def _parse_registrujsa(html: str) -> list[dict]:
    races = []
    for m in re.finditer(
        r'<div[^>]+class=[\"\']\s*cal_elm[^\"\']*[\"\']\s+'
        r'data-calid=[\"\']([\d]+)[\"\']\s+data-vdn=[\"\']([\w\-]+)[\"\']\s*>',
        html,
    ):
        cal_id, vdn = m.group(1), m.group(2)
        block_start = m.end()
        next_m = re.search(r'<div[^>]+class=[\"\']\s*cal_elm', html[block_start:])
        block = html[block_start : block_start + (next_m.start() if next_m else 3000)]

        title_m = re.search(r'class=[\"\']\s*cal_title[^\"\']*[\"\']\s*>([^<]+)<', block)
        day_m = re.search(r'class=[\"\']\s*cal_day[\"\']\s*>(\d+)<', block)
        month_m = re.search(r'class=[\"\']\s*cal_month[^\"\']*[\"\']\s*>([^<]+)<', block)
        text_m = re.search(r'class=[\"\']\s*cal_text[\"\']\s*>(.*?)</div>', block, re.DOTALL)

        if not title_m:
            continue

        year = _year_from_vdn(vdn, 0)
        day = day_m.group(1).zfill(2) if day_m else "00"
        month = _month_num(month_m.group(1)) if month_m else "00"
        datum = f"{year}-{month}-{day}" if year else f"?-{month}-{day}"
        popis = clean(text_m.group(1)) if text_m else ""

        races.append({
            "zdroj": "registrujsa.sk",
            "nazov": unescape(title_m.group(1).strip()),
            "url": f"https://www.registrujsa.sk/{vdn}",
            "datum": datum,
            "mesto": "",
            "popis": popis[:300],
            "info": {"cal_id": cal_id},
        })
    return races


def scrape_registrujsa() -> list[dict]:
    """
    Zdroj: https://www.registrujsa.sk/
    Stránka: SSR Bootstrap/Vue – ?rok= parameter nefunguje ako filter (vráti vždy rovnaké eventy).
    Fetchuje iba hlavnú stránku. Rok extrahuje z VDN slugu (mich26→2026).
      .cal_elm[data-calid, data-vdn]  → ID + URL slug
      .cal_title                       → názov
      .cal_day + .cal_month            → deň + mesiac
      .cal_text                        → popis
    """
    print("registrujsa.sk …")
    try:
        html = fetch("https://www.registrujsa.sk/")
        batch = _parse_registrujsa(html)
        print(f"  {len(batch)} pretekov")
        return batch
    except (URLError, HTTPError) as e:
        print(f"  chyba — {e}", file=sys.stderr)
        return []


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    all_races: list[dict] = []
    all_races.extend(scrape_pretekaj())
    all_races.extend(scrape_hrdosport())
    all_races.extend(scrape_registrujsa())

    # Deduplikácia: pre hrdosport (URL nie je unikátna per event) použijem nazov+datum+zdroj
    seen: set[str] = set()
    unique = []
    for r in all_races:
        key = f"{r['zdroj']}|{r['nazov']}|{r['datum']}"
        if key not in seen:
            seen.add(key)
            unique.append(r)

    by_source: dict[str, int] = {}
    for r in unique:
        by_source[r["zdroj"]] = by_source.get(r["zdroj"], 0) + 1

    out = "multi_preteky.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)

    print(f"\nCelkom {len(unique)} unikátnych záznamov → {out}")
    for src, cnt in sorted(by_source.items()):
        print(f"  {src}: {cnt}")

    print("\nUkážka (5 prvých):")
    for r in unique[:5]:
        print(f"  [{r['datum']}] {r['nazov']} ({r['zdroj']})")


if __name__ == "__main__":
    main()
