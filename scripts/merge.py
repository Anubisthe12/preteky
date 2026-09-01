#!/usr/bin/env python3
"""
Zlúči výstupy oboch scraperov do jedného súboru.

Vstup:  data/preteky.json (beh.sk), data/multi_preteky.json (pretekaj/hrdosport/registrujsa)
Výstup: data/all_preteky.json

Deduplikácia: normalizovaný názov + dátum. Zámerne NIE len názov —
opakujúce sa ročníky (napr. hrdosport archív 2014-2026) sú samostatné
preteky a podľa názvu by sa zliali do jedného.

Pri zhode vyhráva záznam z prioritnejšieho zdroja (beh.sk má
štruktúrované info: dĺžka trate, povrch, štart, organizátor).
"""

import json
import re
import unicodedata
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Poradie priority pri zhode — nižší index vyhráva
PRIORITA = ["beh.sk", "pretekaj.sk", "registrujsa.sk", "hrdosport.sk"]


def _norm_nazov(s: str) -> str:
    """Diakritika preč, malé písmená, len alfanumerické znaky."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", s)


def _norm_datum(s: str) -> str:
    """Rôzne formáty zdrojov → 'YYYY-MM-DD'; berie začiatok rozsahu."""
    s = (s or "").strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(0)
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})", s)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    return s


def main():
    with open(DATA_DIR / "preteky.json", encoding="utf-8") as f:
        beh = json.load(f)
    for r in beh:
        r.setdefault("zdroj", "beh.sk")
        r.setdefault("popis", "")

    with open(DATA_DIR / "multi_preteky.json", encoding="utf-8") as f:
        multi = json.load(f)

    vsetky = beh + multi
    vsetky.sort(key=lambda r: PRIORITA.index(r["zdroj"]) if r["zdroj"] in PRIORITA else 99)

    merged: dict[tuple[str, str], dict] = {}
    for r in vsetky:
        key = (_norm_nazov(r.get("nazov", "")), _norm_datum(r.get("datum", "")))
        if not key[0]:
            continue
        if key not in merged:
            merged[key] = r

    unique = list(merged.values())
    unique.sort(key=lambda r: _norm_datum(r.get("datum", "")) or "0000", reverse=True)

    with open(DATA_DIR / "all_preteky.json", "w", encoding="utf-8") as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)

    by_source: dict[str, int] = {}
    for r in unique:
        by_source[r["zdroj"]] = by_source.get(r["zdroj"], 0) + 1

    print(f"Vstup:  {len(beh)} (beh.sk) + {len(multi)} (multi) = {len(vsetky)}")
    print(f"Výstup: {len(unique)} unikátnych → data/all_preteky.json")
    for src, cnt in sorted(by_source.items()):
        print(f"  {src}: {cnt}")


if __name__ == "__main__":
    main()
