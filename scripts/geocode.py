#!/usr/bin/env python3
"""
Doplní polia "lat"/"lon" (float alebo None) do každého záznamu v
data/all_preteky_norm.json podľa poľa "mesto" + "krajina".

Namiesto dopytovania externého geokódovacieho API (pomalé, rate-limited,
potrebuje sieť pri každom behu) sa súradnice hľadajú offline v dátovej sade
GeoNames (https://www.geonames.org/, licencia CC-BY 4.0) — voľne stiahnuteľný
zoznam sídiel SK a ČR so súradnicami (feature class "P" = mestá/obce), ktorý
už obsahuje presne to, čo tento skript potreboval: mesto → súradnice.
Sťahuje sa priamo do pamäte (žiadny súbor na disku), spracovanie ~2 500
záznamov trvá rádovo sekundy.

Zhoda mena je heuristická (skús celý reťazec, potom časti pri pomlčke/čiarke,
skratky "n./nad", odsek okresu "okr. ...", číslo mestskej časti "Praha 4")
— viď `candidate_keys()`. Nezhodnutým záznamom (typicky konkrétne športoviská
alebo preklepy v "mesto", nie názvy sídiel — napr. "Fotbalové hřiště ul.
Luční", "AGAMA footgolf klub") ostáva lat/lon None; mapa na frontende v tom
prípade zobrazí len krajskú bublinu, nie bod pretekov.

Vstup:  data/all_preteky_norm.json (musí už existovať — pozri normalize.py)
Výstup: data/all_preteky_norm.json (prepísaný, s lat/lon poľami)

Poradie v pipeline: spúšťaj až PO scripts/normalize.py.
"""

import csv
import io
import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path
from urllib.request import urlopen

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
NORM_FILE = DATA_DIR / "all_preteky_norm.json"

GEONAMES_URL = "https://download.geonames.org/export/dump/{}.zip"
COUNTRY_FILES = {
    "Slovensko": "SK",
    "Česká republika": "CZ",
}


def normalize_text(s: str) -> str:
    s = s.lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def fetch_places(country_code: str) -> dict:
    """Stiahne GeoNames dump pre danú krajinu a vráti {normalizovaný_kľúč: [lat, lon]}
    len pre sídla (feature class "P"), vrátane alternatívnych názvov. Pri kolízii
    kľúčov vyhráva ľudnatejšie miesto."""
    url = GEONAMES_URL.format(country_code)
    with urlopen(url, timeout=30) as resp:
        raw = resp.read()

    places: dict[str, tuple[float, float, int]] = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        with zf.open(f"{country_code}.txt") as f:
            reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8"), delimiter="\t")
            for row in reader:
                if row[6] != "P":  # feature class: len sídla (mestá/obce)
                    continue
                lat, lon = float(row[4]), float(row[5])
                population = int(row[14]) if row[14] else 0
                names = {row[1], row[2]}
                if row[3]:
                    names.update(row[3].split(","))
                for name in names:
                    key = normalize_text(name)
                    if not key:
                        continue
                    if key not in places or population > places[key][2]:
                        places[key] = (lat, lon, population)

    return {k: [v[0], v[1]] for k, v in places.items()}


def candidate_keys(raw: str) -> list[str]:
    """Odvodí viacero možných kľúčov z voľného textu 'mesto' v poradí istoty."""
    text = raw.strip()
    text = re.sub(r"\bn\.\s*", "nad ", text, flags=re.IGNORECASE)

    segments = [text]
    segments += re.split(r"\s*[-–]\s*", text)
    segments += [text.split(",")[0]]
    segments += [re.sub(r"\bokr\.?.*$", "", text, flags=re.IGNORECASE)]
    segments += [re.sub(r"\d+\s*$", "", text)]  # "Praha 4" -> "Praha "

    keys = []
    for seg in segments:
        key = normalize_text(seg.split("(")[0])
        if key and key not in keys:
            keys.append(key)
    return keys


def lookup(mesto: str, krajina: str, places_by_country: dict) -> list | None:
    own = places_by_country.get(krajina) or {}
    other_krajina = next((k for k in places_by_country if k != krajina), None)
    other = places_by_country.get(other_krajina) or {}

    for key in candidate_keys(mesto):
        if key in own:
            return own[key]
    for key in candidate_keys(mesto):
        if key in other:
            return other[key]
    return None


def main():
    with open(NORM_FILE, encoding="utf-8") as f:
        races = json.load(f)

    places_by_country = {}
    for krajina, code in COUNTRY_FILES.items():
        print(f"Sťahujem GeoNames {code}…")
        places_by_country[krajina] = fetch_places(code)
        print(f"  {len(places_by_country[krajina])} unikátnych názvov sídiel")

    found = 0
    unmatched_sample = []
    for r in races:
        mesto = (r.get("mesto") or "").strip()
        krajina = (r.get("krajina") or "Slovensko").strip()
        coords = lookup(mesto, krajina, places_by_country) if mesto else None
        if coords:
            r["lat"], r["lon"] = coords
            found += 1
        else:
            r["lat"], r["lon"] = None, None
            if mesto and len(unmatched_sample) < 20:
                unmatched_sample.append(f"{mesto} ({krajina})")

    with open(NORM_FILE, "w", encoding="utf-8") as f:
        json.dump(races, f, ensure_ascii=False, indent=2)

    print(f"\nZáznamy so súradnicami: {found}/{len(races)}")
    if unmatched_sample:
        print("Ukážka nenájdených miest:")
        for s in unmatched_sample:
            print(f"  - {s}")
    print(f"\n→ {NORM_FILE}")


if __name__ == "__main__":
    main()
