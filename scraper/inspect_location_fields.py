#!/usr/bin/env python3
"""
Inspect the real structure of bina.az location fields.

We stored raw_json on every row precisely so we could do this without
re-scraping. This prints what the location-related fields ACTUALLY contain,
so the spider can be fixed against facts instead of guesses.

Usage:
    python scraper/inspect_location_fields.py
"""

import json
import os
from collections import Counter

import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    port=os.getenv("DB_PORT", "5432"),
    dbname=os.getenv("DB_NAME", "bina"),
    user=os.getenv("DB_USER", "binauser"),
    password=os.getenv("DB_PASS", "binapass"),
)
cur = conn.cursor()

cur.execute("""
    SELECT listing_id, city, district, metro_station, property_type, raw_json
    FROM listings
    ORDER BY listing_id
""")
rows = cur.fetchall()
print(f"Inspecting {len(rows)} listings\n")


def show(label, value, indent="    "):
    s = json.dumps(value, ensure_ascii=False)
    if len(s) > 400:
        s = s[:400] + " ...(truncated)"
    print(f"{indent}{label}: {s}")


# ======================================================================
# 1. nearestLocations — what types are actually in here?
# ======================================================================
print("=" * 72)
print("1. nearestLocations — the metro_station bug lives here")
print("=" * 72)

typename_counts = Counter()
key_counts = Counter()
samples = []

for lid, city, district, metro, ptype, raw in rows:
    for n in (raw.get("nearestLocations") or []):
        if isinstance(n, dict):
            typename_counts[n.get("__typename", "NO_TYPENAME")] += 1
            key_counts[tuple(sorted(n.keys()))] += 1
            if len(samples) < 8:
                samples.append((lid, n))
        else:
            typename_counts[f"RAW_{type(n).__name__}"] += 1

print("\n  __typename values found:")
for t, c in typename_counts.most_common():
    print(f"    {t:<25} x{c}")

print("\n  key combinations found:")
for k, c in key_counts.most_common(5):
    print(f"    {list(k)}  x{c}")

print("\n  sample objects:")
for lid, n in samples:
    print(f"    listing {lid}:")
    show("", n, indent="      ")


# ======================================================================
# 2. Where does the RAYON (district) actually live?
# ======================================================================
print("\n" + "=" * 72)
print("2. Hunting for the rayon — location / address / breadcrumbs / metaTags")
print("=" * 72)

for lid, city, district, metro, ptype, raw in rows[:6]:
    print(f"\n  --- listing {lid}  ({ptype}) ---")
    print(f"    [our columns] city={city!r} district={district!r} metro={metro!r}")
    show("location    ", raw.get("location"))
    show("address     ", raw.get("address"))
    show("city        ", raw.get("city"))
    show("breadcrumbs ", raw.get("breadcrumbs"))
    show("metaTags    ", raw.get("metaTags"))


# ======================================================================
# 3. Which top-level keys are ever non-null? (find unused fields)
# ======================================================================
print("\n" + "=" * 72)
print("3. Field fill rates — which keys are actually usable")
print("=" * 72)

filled = Counter()
present = Counter()
for _, _, _, _, _, raw in rows:
    for k, v in raw.items():
        present[k] += 1
        if v not in (None, "", [], {}):
            filled[k] += 1

print(f"\n  {'field':<24} {'non-null':>9} / {'present':>7}")
for k in sorted(present, key=lambda x: -filled[x]):
    print(f"  {k:<24} {filled[k]:>9} / {present[k]:>7}")

cur.close()
conn.close()

print("\n" + "=" * 72)
print("Paste sections 1 and 2 back to fix the extraction properly.")
print("=" * 72)
