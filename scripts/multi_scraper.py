#!/usr/bin/env python3
"""
Multi-source scraper — bezecke preteky SK/CZ

Zdroje:
  pretekaj.sk       — HTML Bootstrap karty, ?perpage=50
  hrdosport.sk      — HTML ASP.NET tabuľka, ?SelectedYear=YYYY (roky 2014-2027)
  registrujsa.sk    — HTML SSR Bootstrap karty, ?rok=YYYY (roky 2019-2026)
  vsetkybehy.sk     — HTML Laravel/Tailwind karty, ?page=N (/ = nadchádzajúce, /archiv)
  bezeckyzavod.cz   — HTML tabuľka, po jednotlivých krajoch ?strana=N (CZ)

Výstup: data/multi_preteky.json
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

def _pretekaj_propozicie_url(event_url: str) -> str:
    """URL detailu z URL karty: 'https://pretekaj.sk/{slug}' → '.../sk/podujatia/{slug}/info/propozicie'."""
    slug = event_url.rstrip("/").rsplit("/", 1)[-1]
    return f"https://pretekaj.sk/sk/podujatia/{slug}/info/propozicie"


def _parse_pretekaj_propozicie(html: str) -> tuple[str, str]:
    """
    Vráti (organizator, popis) z detailu /info/propozicie.

    organizator: meno z bočného panelu (riadok s ikonou fa-info v tabuľke
    pod nadpisom "Organizátor") — ide o štruktúrované pole z profilu
    usporiadateľa, konzistentné naprieč všetkými podujatiami.
    popis: očistený text celého obsahu propozícií. Každý usporiadateľ si
    ho píše vlastným štýlom (iné značenie "Organizátor:", "Dĺžka trate" a
    pod.), preto sa z neho ďalšie polia neparsujú — slúži len ako detailný
    popis (nahrádza kusý/orezaný popis z výpisu kariet).
    Vráti ("", "") ak podujatie nemá vlastnú stránku propozícií (napr.
    skupinové výzvy typu "Tisícovky" — pretekaj.sk vráti chybovú stránku).
    """
    organizator = ""
    org_m = re.search(r'<h4>Organizátor</h4>.*?<table[^>]*>(.*?)</table>', html, re.DOTALL)
    if org_m:
        row_m = re.search(r'fa-info"[^>]*></i>\s*</td>\s*<td>(.*?)</td>', org_m.group(1), re.DOTALL)
        if row_m:
            organizator = clean(row_m.group(1))

    popis = ""
    content_m = re.search(
        r'<!--<h1>Propozície</h1>-->\s*<div>(.*?)</div>\s*</div>\s*<!--\s*Left Sidebar',
        html, re.DOTALL,
    )
    if content_m:
        popis = clean(content_m.group(1))

    return organizator, popis


def scrape_pretekaj() -> list[dict]:
    """
    Zdroj: https://pretekaj.sk/sk/podujatia?perpage=50
    Stránka: Bootstrap karty, každá v .col-md-7
      h2 > a       → názov + URL
      .fa-globe    → miesto
      .fa-calendar → dátum (napr. "29.03.2026 - 18.10.2026")
      p            → popis

    Výpis kariet má len kusý popis (často orezaný uprostred slova). Detailné
    info je na podstránke .../sk/podujatia/{slug}/info/propozicie, preto sa
    pre každý event ešte doťahuje aj tá — viď _parse_pretekaj_propozicie().
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

    print(f"  {len(races)} pretekov, doťahujem propozície…")
    doplnene = 0
    for i, race in enumerate(races, 1):
        time.sleep(DELAY)
        detail_url = _pretekaj_propozicie_url(race["url"])
        try:
            detail_html = fetch(detail_url)
        except (URLError, HTTPError) as e:
            print(f"  [{i}/{len(races)}] {race['nazov']}: propozície chyba — {e}", file=sys.stderr)
            continue

        organizator, popis_detail = _parse_pretekaj_propozicie(detail_html)
        if not organizator and not popis_detail:
            continue  # bez vlastnej stránky propozícií (napr. skupinové výzvy)

        info = {"propozicie": detail_url}
        if organizator:
            info["Organizátor"] = organizator
        race["info"] = info
        if popis_detail:
            race["popis"] = popis_detail[:2000]
        doplnene += 1

    print(f"  {doplnene}/{len(races)} doplnených z propozícií")
    return races


# ── hrdosport.sk ────────────────────────────────────────────────────────────

def _parse_hrdosport_table(html: str, year: int, month: int) -> list[dict]:
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
            "url": f"https://www.hrdosport.sk/Events?SelectedYear={year}&SelectedMonth={month}",
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
    Zdroj: https://www.hrdosport.sk/Events?SelectedYear=YYYY&SelectedMonth=M
    Stránka: Bootstrap + ASP.NET MVC tabuľka
      td[1] → dátum  td[2] → názov  td[3] → mesto
      PDF linky na propozície a výsledky
    Roky: 2014–2027. SelectedMonth je povinný — bez neho stránka
    vráti iba aktuálny mesiac, preto iterujeme rok × mesiac.
    """
    print("hrdosport.sk …")
    all_races: list[dict] = []
    for year in range(2014, 2028):
        year_count = 0
        for month in range(1, 13):
            time.sleep(DELAY)
            url = f"https://www.hrdosport.sk/Events?SelectedYear={year}&SelectedMonth={month}"
            try:
                html = fetch(url)
                batch = _parse_hrdosport_table(html, year, month)
                all_races.extend(batch)
                year_count += len(batch)
            except (URLError, HTTPError) as e:
                print(f"  {year}-{month:02d}: chyba — {e}", file=sys.stderr)
        if year_count:
            print(f"  {year}: {year_count} pretekov")
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


# ── vsetkybehy.sk ───────────────────────────────────────────────────────────

VB_BASE = "https://vsetkybehy.sk"
VB_RE = re.escape(VB_BASE)
VB_MAX_PAGES = 60


def _vb_year(slug: str) -> str:
    """Rok zo slugu: 'ms-hamburg-74-2026'→'2026', 'dojcanska-9-2026-2'→'2026'."""
    m = re.search(r"(20\d{2})(?:-\d+)?$", slug)
    return m.group(1) if m else ""


def _vb_dlzky(discipliny: list[str]) -> str:
    """Vytiahne km z názvov disciplín: 'Maratón (42.2 km)'→'42.2 km', '10 km'→'10 km'."""
    out: list[str] = []
    for d in discipliny:
        m = re.search(r"\(([\d.,]+)\s*km\)", d) or re.search(r"([\d.,]+)\s*km", d)
        if not m:
            continue
        km = f"{m.group(1).replace(',', '.')} km"
        if km not in out:
            out.append(km)
    return ", ".join(out)


def _parse_vsetkybehy(html: str) -> list[dict]:
    races = []
    starts = [m.start() for m in re.finditer(r'\sdata-event-name="', html)]

    for i, start in enumerate(starts):
        blk = html[start : starts[i + 1] if i + 1 < len(starts) else len(html)]

        name_m = re.match(r'\sdata-event-name="([^"]*)"', blk)
        slug_m = re.search(r'data-event-slug="([^"]+)"', blk)
        if not name_m or not slug_m:
            continue
        slug = slug_m.group(1)

        # Dátum: deň + skratka mesiaca z karty ("30 AUG"), rok zo slugu
        day_m = re.search(r'class="text-sm font-bold">\s*(\d{1,2})\s+([^\s<]+)\s*<', blk)
        rok = _vb_year(slug)
        datum = ""
        if day_m and rok:
            datum = f"{rok}-{_month_num(day_m.group(2))}-{day_m.group(1).zfill(2)}"

        cas_m = re.search(r'class="text-\[11px\] opacity-80">[^\d<]*(\d{1,2}:\d{2})', blk)

        # Miesto: odkaz na Google Maps nesie GPS, presné miesto (title) aj mesto (text)
        loc_m = re.search(
            r'href="https://www\.google\.com/maps/search/\?api=1&amp;query='
            r'([-\d.]+),([-\d.]+)"[^>]*title="([^"]*)"[^>]*>\s*([^<]+?)\s*</a>',
            blk,
        )
        kraj_m = re.search(rf'href="{VB_RE}/kraj/([a-z-]+)"', blk)
        seria_m = re.search(
            rf'href="{VB_RE}/seria/([a-z0-9-]+)"[^>]*>.*?</svg>\s*([^<]+?)\s*</a>', blk, re.DOTALL
        )

        # Disciplíny — odznaky (chipy) v karte. Kategorizovaná disciplína je odkaz
        # na /preteky/<typ>, nekategorizovaná (názov zhodný s podujatím, napr. keď
        # nemá vlastnú kategóriu) je obyčajný <span> bez odkazu. Obe majú triedu
        # "rounded-full", čo ich odlíši od odkazov v navigácii/pätičke stránky.
        discipliny = [
            unescape(d).strip()
            for d in re.findall(
                rf'href="{VB_RE}/preteky/[a-z0-9-]+"\s*'
                r'class="[^"]*rounded-full[^"]*"\s*>([^<]+)</a>',
                blk,
            )
            + re.findall(r'<span class="[^"]*rounded-full[^"]*">([^<]+)</span>', blk)
        ]

        # Externé odkazy (karta ich renderuje 2× — mobil + desktop, berieme prvý)
        odkazy: dict[str, str] = {}
        for href, kind in re.findall(
            r'href="([^"]+)"[^>]*data-analytics-event='
            r'"(registration|official_site|propositions|results)_click"',
            blk,
        ):
            odkazy.setdefault(kind, unescape(href))

        races.append({
            "zdroj": "vsetkybehy.sk",
            "nazov": unescape(name_m.group(1)).strip(),
            "url": f"{VB_BASE}/podujatie/{slug}",
            "datum": datum,
            "mesto": unescape(loc_m.group(4)) if loc_m else "",
            "popis": ", ".join(discipliny)[:300],
            "info": {
                "Miesto": unescape(loc_m.group(3)) if loc_m else "",
                "Dĺžka trate": _vb_dlzky(discipliny),
                "Štart": cas_m.group(1) if cas_m else "",
                "kraj": kraj_m.group(1) if kraj_m else "",
                "gps": f"{loc_m.group(1)},{loc_m.group(2)}" if loc_m else "",
                "seria": unescape(seria_m.group(2)) if seria_m else "",
                "disciplíny": discipliny,
                "registracia": odkazy.get("registration", ""),
                "web": odkazy.get("official_site", ""),
                "propozicie": odkazy.get("propositions", ""),
                "vysledky": odkazy.get("results", ""),
            },
        })

    return races


def _scrape_vb_listing(path: str, label: str) -> list[dict]:
    """Prejde stránkovaný výpis kým vracia karty (25 na stranu)."""
    races: list[dict] = []
    for page in range(1, VB_MAX_PAGES + 1):
        sep = "&" if "?" in path else "?"
        try:
            time.sleep(DELAY)
            html = fetch(f"{VB_BASE}{path}{sep}page={page}")
        except HTTPError as e:
            # za poslednou stranou vracia Laravel 404 — normálny koniec stránkovania
            if e.code != 404:
                print(f"  {label} str. {page}: chyba — {e}", file=sys.stderr)
            break
        except URLError as e:
            print(f"  {label} str. {page}: chyba — {e}", file=sys.stderr)
            break
        batch = _parse_vsetkybehy(html)
        if not batch:
            break
        races.extend(batch)
        print(f"  {label} str. {page}: {len(batch)} pretekov")
    return races


def scrape_vsetkybehy() -> list[dict]:
    """
    Zdroj: https://vsetkybehy.sk/ (nadchádzajúce) + /archiv (odbehnuté), ?page=N
    Stránka: Laravel/Livewire + Tailwind karty, 25 na stranu
      [data-event-name] + [data-event-slug]  → názov + URL slug (rok je v slugu)
      .text-sm.font-bold                     → deň + skratka mesiaca ("30 AUG")
      odkaz na Google Maps                   → GPS, presné miesto (title) + mesto
      /kraj/<slug>, /seria/<slug>            → kraj a bežecká séria
      /preteky/<typ> chipy                   → disciplíny vrátane vzdialeností
      [data-analytics-event]                 → registrácia, web, propozície, výsledky
    """
    print("vsetkybehy.sk …")
    races = _scrape_vb_listing("/", "nadchádzajúce")
    races += _scrape_vb_listing("/archiv", "archív")
    print(f"  {len(races)} pretekov")
    return races


# ── bezeckyzavod.cz (CZ) ────────────────────────────────────────────────────

BZ_BASE = "https://www.bezeckyzavod.cz"
BZ_MAX_PAGES = 15

# Kraje = výpisy /kraje/<slug>/ (+ Praha má vlastnú cestu bez prefixu /kraje/).
# Skrapuje sa po krajoch namiesto jedného spoločného /zavody/ výpisu, lebo
# výpis kraja obsahuje rovnaké karty a naviac rovno prezradí kraj (bez toho
# by bolo treba fetchovať detail každého podujatia zvlášť).
BZ_KRAJE = [
    ("/praha/", "Praha a okolí"),
    ("/kraje/stredocesky_kraj/", "Středočeský kraj"),
    ("/kraje/jihocesky_kraj/", "Jihočeský kraj"),
    ("/kraje/plzensky_kraj/", "Plzeňský kraj"),
    ("/kraje/karlovarsky_kraj/", "Karlovarský kraj"),
    ("/kraje/ustecky_kraj/", "Ústecký kraj"),
    ("/kraje/liberecky_kraj/", "Liberecký kraj"),
    ("/kraje/kralovehradecky_kraj/", "Královéhradecký kraj"),
    ("/kraje/pardubicky_kraj/", "Pardubický kraj"),
    ("/kraje/kraj_vysocina/", "Kraj Vysočina"),
    ("/kraje/jihomoravsky_kraj/", "Jihomoravský kraj"),
    ("/kraje/olomoucky_kraj/", "Olomoucký kraj"),
    ("/kraje/zlinsky_kraj/", "Zlínský kraj"),
    ("/kraje/moravskoslezsky_kraj/", "Moravskoslezský kraj"),
]


def _bz_fetch(url: str) -> str | None:
    """Vráti HTML, alebo None ak server presmeroval inam (koniec stránkovania — ?strana=N
    za poslednou stranou sa vráti na prvú stranu bez query, namiesto 404)."""
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; sk-race-scraper/1.0)"})
    with urlopen(req, timeout=15) as r:
        final_url = r.geturl()
        html = r.read().decode("utf-8")
    if "strana=" in url and "strana=" not in final_url:
        return None
    return html


def _parse_bezeckyzavod(html: str, kraj: str) -> list[dict]:
    races = []
    for blk in re.findall(r'<tr class="zavody">(.*?)</tr>', html, re.DOTALL):
        url_m = re.search(r'<a href="([^"]+)" class="badge badge-datum" title="([^"]+)"', blk)
        nazov_m = re.search(r'<strong>([^<]+)</strong>', blk)
        if not url_m or not nazov_m:
            continue
        mesto_m = re.search(r'class="sedy small">\s*<span>([^<]*)</span>', blk)
        dlzka_m = re.search(r'class="align-middle text-end zavody-vzdalenost[^"]*"[^>]*>(.*?)</td>', blk, re.DOTALL)

        races.append({
            "zdroj": "bezeckyzavod.cz",
            "nazov": unescape(nazov_m.group(1).strip()),
            "url": url_m.group(1),
            "datum": url_m.group(2).strip(),
            "mesto": unescape(mesto_m.group(1).strip()) if mesto_m else "",
            "popis": "",
            "info": {
                "Dĺžka trate": clean(dlzka_m.group(1)).replace(" ", " ") if dlzka_m else "",
                "Kraj": kraj,
            },
        })
    return races


def _scrape_bz_kraj(path: str, kraj: str) -> list[dict]:
    races: list[dict] = []
    for page in range(1, BZ_MAX_PAGES + 1):
        url = f"{BZ_BASE}{path}" if page == 1 else f"{BZ_BASE}{path}?strana={page}"
        try:
            time.sleep(DELAY)
            html = _bz_fetch(url)
        except (URLError, HTTPError) as e:
            print(f"  {kraj} str. {page}: chyba — {e}", file=sys.stderr)
            break
        if html is None:
            break
        batch = _parse_bezeckyzavod(html, kraj)
        if not batch:
            break
        races.extend(batch)
    return races


def scrape_bezeckyzavod() -> list[dict]:
    """
    Zdroj: https://www.bezeckyzavod.cz/zavody/ — výpis len nadchádzajúcich pretekov
    (?rocnik=<minulý rok> vracia 0, žiadny archív), rozdelený po krajoch:
    /praha/ a /kraje/<slug>/, stránkované ?strana=N (30 na stranu).
      badge-datum title="D.M.YYYY" → dátum, href → URL
      <strong>                     → názov
      .sedy.small > span           → mesto
      .zavody-vzdalenost           → dĺžka trate ("10 km" / "1 h" pri časovkách)
    Krajský výpis rovno prezradí kraj — netreba fetchovať detail podujatia.
    """
    print("bezeckyzavod.cz …")
    all_races: list[dict] = []
    for path, kraj in BZ_KRAJE:
        batch = _scrape_bz_kraj(path, kraj)
        all_races.extend(batch)
        print(f"  {kraj}: {len(batch)} pretekov")
    print(f"  {len(all_races)} pretekov spolu")
    return all_races


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    all_races: list[dict] = []
    all_races.extend(scrape_pretekaj())
    all_races.extend(scrape_hrdosport())
    all_races.extend(scrape_registrujsa())
    all_races.extend(scrape_vsetkybehy())
    all_races.extend(scrape_bezeckyzavod())

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

    out = DATA_DIR / "multi_preteky.json"
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
