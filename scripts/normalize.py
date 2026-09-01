#!/usr/bin/env python3
"""
Normalizuje data/all_preteky.json na konzistentné schéma:

  nazov        str   - názov pretekov
  zdroj        str   - zdrojový portál
  url          str   - URL záznamu
  datum        str   - YYYY-MM-DD (prvý deň ak rozsah); "" ak neznámy
  datum_do     str   - YYYY-MM-DD koniec rozsahu; "" ak jednodňový
  mesto        str   - mesto / miesto startu
  dlzka        str   - "10 km", "42,2 km" atď.; "" ak neznáma
  povrch       str   - "asfalt" / "terén" / ""; "" ak neznámy
  start_cas    str   - "10:00 hod." atď.; "" ak neznámy
  organizator  str   - organizátor; "" ak neznámy
  popis        str   - krátky popis (bez kontaktov)

Vstup:  data/all_preteky.json
Výstup: data/all_preteky_norm.json
"""

import json
import re
from html import unescape
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

MONTHS_SK = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "máj": 5, "maj": 5, "jún": 6, "jun": 6,
    "júl": 7, "jul": 7, "aug": 8,
    "sep": 9, "okt": 10, "nov": 11, "dec": 12,
}


# ── Dátum ────────────────────────────────────────────────────────────────────

def _parse_date(s: str) -> str | None:
    """Pokúsi sa rozpoznať dátum a vráti 'YYYY-MM-DD' alebo None."""
    if not s:
        return None
    s = s.strip()

    # YYYY-MM-DD
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        return s

    # DD.MM.YYYY
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", s)
    if m:
        return f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"

    # DD.MM.YY
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{2})$", s)
    if m:
        yr = int(m.group(3))
        yr = 2000 + yr if yr <= 50 else 1900 + yr
        return f"{yr}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"

    # "29.03.2026 - 18.10.2026" → vráti iba začiatok
    m = re.match(r"^(\d{1,2}\.\d{1,2}\.\d{4})\s*[-–]\s*\d{1,2}\.\d{1,2}\.\d{4}$", s)
    if m:
        return _parse_date(m.group(1))

    return None


def _parse_date_range(s: str) -> tuple[str, str]:
    """Vráti (datum_od, datum_do) z reťazca. datum_do = '' ak nie je rozsah."""
    if not s:
        return "", ""
    s = s.strip()

    # "DD.MM.YYYY - DD.MM.YYYY"
    m = re.match(
        r"^(\d{1,2}\.\d{1,2}\.\d{4})\s*[-–]\s*(\d{1,2}\.\d{1,2}\.\d{4})$", s
    )
    if m:
        return _parse_date(m.group(1)) or "", _parse_date(m.group(2)) or ""

    d = _parse_date(s)
    return (d or ""), ""


# ── Extrakcia vzdialenosti ───────────────────────────────────────────────────

_KM_RE = re.compile(r"\b(\d+[\.,]?\d*)\s*km\b", re.IGNORECASE)
_M_RE  = re.compile(r"\b(\d[\d\s]*\d|\d+)\s*m\b")   # metre: "10 150 m", "6000m"


def _meters_to_km(dlzka: str) -> str:
    """Prevedie metre na km: '10 150 m' → '10,15 km', '6 000 m' → '6 km'."""
    def replace(m):
        raw = m.group(1).replace(" ", "").replace(" ", "")
        meters = int(raw)
        km = meters / 1000
        if km == int(km):
            return f"{int(km)} km"
        return f"{km:.2f} km".replace(".", ",")
    return _M_RE.sub(replace, dlzka)


def _has_precise_km(dlzka: str) -> bool:
    """True ak dlzka obsahuje konkrétny km údaj (nie len časový/slovný popis)."""
    return bool(_KM_RE.search(dlzka))

_NAME_DISTANCES = [
    (r"ultra\s*maratón|ultramaraton|ultra\s*trail", "ultramaratón"),
    (r"maratón|marathon",                           "42,2 km"),
    (r"polmaratón|half\s*marathon|half\s*maratón",  "21,1 km"),
    (r"\bdesiatka\b",                                "10 km"),
    (r"\bpäťka\b",                                   "5 km"),
    (r"\b5\s*km\b",                                  "5 km"),
    (r"\b10\s*km\b",                                 "10 km"),
    (r"\b15\s*km\b",                                 "15 km"),
    (r"\b21\s*km\b",                                 "21 km"),
]

# Časové preteky — extrakt aj tag
_TIME_DISTANCES = [
    (r"(\d+)\s*-?\s*hodinovka",   lambda m: f"{m.group(1)}-hodinovka"),
    (r"\bhodinovka\b",             lambda m: "hodinovka"),
    (r"(\d+)\s*-?\s*minútovka",   lambda m: f"{m.group(1)}-minútovka"),
    (r"(\d+)\s*minút(?:ový)?\s*beh", lambda m: f"{m.group(1)}-minútovka"),
    (r"(\d+)\s*hod\.",             lambda m: f"{m.group(1)} hod."),
]


def _extract_dlzka(nazov: str, popis: str) -> str:
    """Pokúsi sa extrahovať vzdialenosť z názvu alebo popisu."""
    # 1. Časové formáty v názve
    for pat, fmt in _TIME_DISTANCES:
        m = re.search(pat, nazov, re.IGNORECASE)
        if m:
            return fmt(m)
    # 2. Explicitné "X km" v popis
    m = _KM_RE.search(popis)
    if m:
        return f"{m.group(1).replace(',', '.')} km"
    # 3. Kľúčové slová v názve
    for pat, label in _NAME_DISTANCES:
        if re.search(pat, nazov, re.IGNORECASE):
            return label
    # 4. Explicitné "X km" v názve
    m = _KM_RE.search(nazov)
    if m:
        return f"{m.group(1).replace(',', '.')} km"
    return ""


def _make_tags(nazov: str, dlzka: str, popis: str) -> list[str]:
    """Odvodí zoznam tagov z dostupných polí."""
    tags = []
    text = f"{nazov} {dlzka} {popis}".lower()

    # Neznáma presná dĺžka — prázdna alebo len časový/slovný popis bez km hodnoty
    if not _has_precise_km(dlzka):
        tags.append("neznama_dlzka")

    # Typ podľa vzdialenosti/formátu
    if re.search(r"hodinovka|\d+\s*hod\.|\d+-minút", text):
        tags.append("casova")
    elif re.search(r"ultra|trail", text):
        tags.append("ultra")
    elif re.search(r"maratón|marathon", text):
        tags.append("maraton")
    elif re.search(r"polmaratón|half.marathon", text):
        tags.append("polmaraton")
    elif re.search(r"kros|cross.country", text):
        tags.append("kros")
    else:
        tags.append("beh")

    # Povrch
    if re.search(r"terén|trail|les|hory|mountain|forest|príroda", text):
        tags.append("teren")
    elif re.search(r"asfalt|cesta|road|ulica|city|mestsk", text):
        tags.append("asfalt")

    return tags


# ── Čistenie textu ───────────────────────────────────────────────────────────

_CONTACT_RE = re.compile(
    r"(?:informácie|kontakt|organizátor|tel\.?|e-mail|@|0[689]\d{8}|párovanie platieb)[^.]*\.?",
    re.IGNORECASE,
)


def _strip_contacts(s: str) -> str:
    """Odstráni kontaktné info z popis poľa."""
    s = _CONTACT_RE.sub("", s)
    return re.sub(r"\s{2,}", " ", s).strip().rstrip(",;:")


# ── Normalizácia záznamu ─────────────────────────────────────────────────────

def normalize(r: dict) -> dict:
    zdroj = r.get("zdroj", "")
    info = r.get("info", {}) or {}

    # Dátum
    datum_raw = r.get("datum", "")
    datum_od, datum_do = _parse_date_range(datum_raw)

    # Mesto — fallback na info["Miesto"] (beh.sk)
    mesto = r.get("mesto", "").strip()
    if not mesto and isinstance(info, dict):
        mesto = info.get("Miesto", "").strip()

    # Dĺžka trate — štruktúrovaná (beh.sk) alebo extrahovaná z textu
    dlzka = ""
    if isinstance(info, dict):
        dlzka = info.get("Dĺžka trate", "").strip()
    if not dlzka:
        dlzka = _extract_dlzka(r.get("nazov", ""), r.get("popis", "") or "")
    # Metre → km
    if dlzka:
        dlzka = _meters_to_km(dlzka)

    # Povrch
    povrch = ""
    if isinstance(info, dict):
        povrch = info.get("Povrch", "").strip()

    # Čas štartu
    start_cas = ""
    if isinstance(info, dict):
        start_cas = info.get("Štart", "").strip()

    # Organizátor
    organizator = ""
    if isinstance(info, dict):
        organizator = info.get("Organizátor", "").strip()

    # Popis — vyčisti kontakty z registrujsa
    popis = r.get("popis", "") or ""
    if zdroj == "registrujsa.sk":
        popis = _strip_contacts(popis)

    # registrujsa: skús extrahovať mesto z popis ak je stále prázdne
    if not mesto and zdroj == "registrujsa.sk" and popis:
        m = re.search(r"\b(?:v\s+|vo\s+|pri\s+)?([A-ZÁÄÉÍÓÔÚŽŠČ][a-záäéíóôúžšč]+(?:\s+[A-ZÁÄÉÍÓÔÚŽŠČ][a-záäéíóôúžšč]+)?)\b", popis)
        # Nevyhodnocujeme, lebo popis nie je spoľahlivý zdroj mesta — nechajme prázdne

    tags = _make_tags(r.get("nazov", ""), dlzka, popis)

    return {
        "nazov":       unescape(r.get("nazov", "")).strip(),
        "zdroj":       zdroj,
        "url":         r.get("url", "").strip(),
        "datum":       datum_od,
        "datum_do":    datum_do,
        "mesto":       unescape(mesto),
        "dlzka":       dlzka,
        "povrch":      povrch,
        "start_cas":   start_cas,
        "organizator": organizator,
        "tagy":        tags,
        "popis":       popis[:250],
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    with open(DATA_DIR / "all_preteky.json", encoding="utf-8") as f:
        data = json.load(f)

    normalized = [normalize(r) for r in data]

    # Zoraď: najprv záznamy s dátumom, potom bez
    normalized.sort(key=lambda r: r["datum"] or "0000", reverse=True)

    out = DATA_DIR / "all_preteky_norm.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

    # Filtered — len záznamy s minimálnymi poľami
    filtered = [r for r in normalized if r["nazov"] and r["dlzka"] and r["mesto"]]
    filtered_out = DATA_DIR / "preteky_filtered.json"
    with open(filtered_out, "w", encoding="utf-8") as f:
        json.dump(filtered, f, ensure_ascii=False, indent=2)

    # Štatistiky kvality
    total = len(normalized)
    has_datum   = sum(1 for r in normalized if r["datum"])
    has_mesto   = sum(1 for r in normalized if r["mesto"])
    has_dlzka   = sum(1 for r in normalized if r["dlzka"])
    has_povrch  = sum(1 for r in normalized if r["povrch"])
    has_org     = sum(1 for r in normalized if r["organizator"])

    print(f"Záznamy:     {total}")
    print(f"datum:       {has_datum}/{total} ({has_datum*100//total} %)")
    print(f"mesto:       {has_mesto}/{total} ({has_mesto*100//total} %)")
    print(f"dlzka:       {has_dlzka}/{total} ({has_dlzka*100//total} %)")
    print(f"povrch:      {has_povrch}/{total} ({has_povrch*100//total} %)")
    print(f"organizator: {has_org}/{total} ({has_org*100//total} %)")
    print(f"\n→ {out}  (všetky záznamy)")
    print(f"→ {filtered_out}  (len záznamy s nazov+dlzka+mesto: {len(filtered)}/{total})")

    print("\nUkážka (beh.sk):")
    for r in [x for x in normalized if x["zdroj"] == "beh.sk"][:2]:
        print(json.dumps(r, ensure_ascii=False, indent=2))

    print("\nUkážka (registrujsa.sk):")
    for r in [x for x in normalized if x["zdroj"] == "registrujsa.sk"][:1]:
        print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
