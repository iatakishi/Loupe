#!/usr/bin/env python3
"""
Load scraped JSONL into Postgres.

All location normalisation happens HERE, from `raw_json`, not in the spider.
That means fixing a mapping bug never requires re-scraping bina.az — just
re-run this script on the JSONL you already have.

Usage:
    python scraper/load_to_db.py data/raw/test.jsonl
    python scraper/load_to_db.py data/raw/backfill.jsonl

Safe to run repeatedly: upserts on listing_id.
"""

import json
import os
import sys

import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv

# bina_locations.py lives next to this file
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bina_locations import parse_locations, building_type_from_category  # noqa: E402

load_dotenv()

UPSERT = """
INSERT INTO listings (
    listing_id, url, deal_type, property_type,
    price_azn, currency, area_m2, rooms, floor, total_floors,
    building_type, renovation, has_kupca, has_mortgage,
    city, district, settlement, metro_station, landmark,
    latitude, longitude,
    title, description, seller_type, seller_id, seller_name,
    scrape_source, raw_json, first_seen_at, last_seen_at, is_active
) VALUES (
    %(listing_id)s, %(url)s, %(deal_type)s, %(property_type)s,
    %(price_azn)s, %(currency)s, %(area_m2)s, %(rooms)s, %(floor)s, %(total_floors)s,
    %(building_type)s, %(renovation)s, %(has_kupca)s, %(has_mortgage)s,
    %(city)s, %(district)s, %(settlement)s, %(metro_station)s, %(landmark)s,
    %(latitude)s, %(longitude)s,
    %(title)s, %(description)s, %(seller_type)s, %(seller_id)s, %(seller_name)s,
    %(scrape_source)s, %(raw_json)s, now(), now(), TRUE
)
ON CONFLICT (listing_id) DO UPDATE SET
    price_azn     = EXCLUDED.price_azn,
    -- location fields are recomputed on every load, so re-running this
    -- script is how mapping fixes get applied to existing rows
    city          = EXCLUDED.city,
    district      = EXCLUDED.district,
    settlement    = EXCLUDED.settlement,
    metro_station = EXCLUDED.metro_station,
    landmark      = EXCLUDED.landmark,
    building_type = EXCLUDED.building_type,
    description   = COALESCE(EXCLUDED.description, listings.description),
    raw_json      = EXCLUDED.raw_json,
    last_seen_at  = now(),
    is_active     = TRUE
RETURNING (xmax = 0) AS was_insert;
"""

LAST_PRICE = """
SELECT price_azn FROM listing_price_history
WHERE listing_id = %s ORDER BY observed_at DESC LIMIT 1;
"""
ADD_PRICE = "INSERT INTO listing_price_history (listing_id, price_azn) VALUES (%s, %s);"
CLEAR_IMAGES = "DELETE FROM listing_images WHERE listing_id = %s;"
ADD_IMAGE = ("INSERT INTO listing_images (listing_id, image_url, position) "
             "VALUES (%s, %s, %s);")


def to_row(rec):
    """Map a scraped record onto the listings table columns."""
    raw = rec.get("raw_json") or {}

    # Everything location-related comes from raw_json via the shared parser,
    # NOT from the spider's own (previously wrong) guesses.
    loc = parse_locations(raw)

    renovation = None
    if rec.get("has_repair") is True:
        renovation = "temirli"
    elif rec.get("has_repair") is False:
        renovation = "temirsiz"

    return {
        "listing_id":    rec["listing_id"],
        "url":           rec.get("url"),
        "deal_type":     rec.get("deal_type") or "sale",
        "property_type": rec.get("property_type"),
        "price_azn":     rec.get("price_azn"),
        "currency":      rec.get("currency") or "AZN",
        "area_m2":       rec.get("area_m2"),
        "rooms":         rec.get("rooms"),
        "floor":         rec.get("floor"),
        "total_floors":  rec.get("total_floors"),
        # buildingTypeName is null on every listing — derive from category slug
        "building_type": building_type_from_category(rec.get("property_type")),
        "renovation":    renovation,
        "has_kupca":     rec.get("has_kupca"),
        "has_mortgage":  rec.get("has_mortgage"),
        "city":          loc["city"],
        "district":      loc["district"],
        "settlement":    loc["settlement"],
        "metro_station": loc["metro_station"],
        "landmark":      loc["landmark"],
        "latitude":      rec.get("latitude"),
        "longitude":     rec.get("longitude"),
        "title":         rec.get("title"),
        "description":   rec.get("description"),
        "seller_type":   rec.get("seller_type"),
        "seller_id":     rec.get("seller_id"),
        "seller_name":   rec.get("seller_name"),
        "scrape_source": rec.get("scrape_source") or "backfill",
        "raw_json":      Json(raw),
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]

    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "bina"),
        user=os.getenv("DB_USER", "binauser"),
        password=os.getenv("DB_PASS", "binapass"),
    )
    cur = conn.cursor()

    inserted = updated = skipped = price_changes = images = 0
    bad_metro = []

    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue

            if rec.get("price_azn") is None or rec.get("area_m2") in (None, 0):
                skipped += 1
                continue

            row = to_row(rec)

            # flag anything that parsed as a metro but isn't a real station
            loc = parse_locations(rec.get("raw_json") or {})
            if loc["is_metro_valid"] is False:
                bad_metro.append((row["listing_id"], loc["metro_station"]))

            cur.execute(UPSERT, row)
            inserted += cur.fetchone()[0]

            cur.execute(LAST_PRICE, (row["listing_id"],))
            prev = cur.fetchone()
            if prev is None or float(prev[0]) != float(row["price_azn"]):
                cur.execute(ADD_PRICE, (row["listing_id"], row["price_azn"]))
                price_changes += 1

            urls = rec.get("photo_urls") or []
            if urls:
                cur.execute(CLEAR_IMAGES, (row["listing_id"],))
                for pos, url in enumerate(urls[:30]):
                    cur.execute(ADD_IMAGE, (row["listing_id"], url, pos))
                    images += 1

            if lineno % 200 == 0:
                conn.commit()
                print(f"  ...{lineno} lines")

    conn.commit()
    updated = (lineno - skipped) - inserted if 'lineno' in dir() else 0

    print("\n" + "=" * 55)
    print(f"  inserted (new):   {inserted}")
    print(f"  skipped:          {skipped}")
    print(f"  price rows added: {price_changes}")
    print(f"  images added:     {images}")
    print("=" * 55)

    if bad_metro:
        print(f"\n  WARNING: {len(bad_metro)} rows have a metro_station that is")
        print("  not a known Baku station. First few:")
        for lid, m in bad_metro[:5]:
            print(f"    listing {lid}: {m!r}")

    # ---- health check -------------------------------------------------
    cur.execute("""
        SELECT deal_type,
               count(*),
               round(avg(price_azn / NULLIF(area_m2, 0))) AS avg_per_m2
        FROM listings
        WHERE property_type LIKE 'menziller%'
        GROUP BY deal_type ORDER BY deal_type;
    """)
    print("\n  APARTMENTS ONLY (menziller/*):")
    for deal, n, avg in cur.fetchall():
        print(f"    {deal:<6} {n:>6} rows   avg {avg} AZN/m²")

    cur.execute("""
        SELECT
          count(*)                                        AS total,
          count(*) FILTER (WHERE district IS NOT NULL)    AS has_district,
          count(*) FILTER (WHERE metro_station IS NOT NULL) AS has_metro,
          count(*) FILTER (WHERE settlement IS NOT NULL)  AS has_settlement,
          count(*) FILTER (WHERE landmark IS NOT NULL)    AS has_landmark,
          count(*) FILTER (WHERE building_type IS NOT NULL) AS has_bldg
        FROM listings;
    """)
    t, d, m, s, lm, b = cur.fetchone()
    print(f"\n  FIELD COVERAGE (of {t} rows):")
    for label, n in [("district", d), ("metro_station", m), ("settlement", s),
                     ("landmark", lm), ("building_type", b)]:
        print(f"    {label:<15} {n:>6}  ({100*n//max(t,1)}%)")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
