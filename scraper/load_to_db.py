#!/usr/bin/env python3
"""
Load scraped JSONL into Postgres.

Kept separate from the spider on purpose: scraping and loading are different
failure modes. If the DB is down you still keep the data; if the load has a
bug you re-run it without re-scraping bina.az.

Usage:
    python scraper/load_to_db.py data/raw/test.jsonl
    python scraper/load_to_db.py data/raw/backfill.jsonl

Safe to run repeatedly — it upserts on listing_id.
"""

import json
import os
import sys

import psycopg2
from psycopg2.extras import Json
from dotenv import load_dotenv

load_dotenv()

UPSERT = """
INSERT INTO listings (
    listing_id, url, deal_type, property_type,
    price_azn, currency, area_m2, rooms, floor, total_floors,
    building_type, renovation, has_kupca, has_mortgage,
    city, district, latitude, longitude, metro_station,
    title, description, seller_type, seller_id, seller_name,
    scrape_source, raw_json, first_seen_at, last_seen_at, is_active
) VALUES (
    %(listing_id)s, %(url)s, %(deal_type)s, %(property_type)s,
    %(price_azn)s, %(currency)s, %(area_m2)s, %(rooms)s, %(floor)s, %(total_floors)s,
    %(building_type)s, %(renovation)s, %(has_kupca)s, %(has_mortgage)s,
    %(city)s, %(district)s, %(latitude)s, %(longitude)s, %(metro_station)s,
    %(title)s, %(description)s, %(seller_type)s, %(seller_id)s, %(seller_name)s,
    %(scrape_source)s, %(raw_json)s, now(), now(), TRUE
)
ON CONFLICT (listing_id) DO UPDATE SET
    price_azn    = EXCLUDED.price_azn,
    description  = COALESCE(EXCLUDED.description, listings.description),
    latitude     = COALESCE(EXCLUDED.latitude,  listings.latitude),
    longitude    = COALESCE(EXCLUDED.longitude, listings.longitude),
    raw_json     = EXCLUDED.raw_json,
    last_seen_at = now(),
    is_active    = TRUE
RETURNING (xmax = 0) AS was_insert;
"""

LAST_PRICE = """
SELECT price_azn FROM listing_price_history
WHERE listing_id = %s ORDER BY observed_at DESC LIMIT 1;
"""

ADD_PRICE = """
INSERT INTO listing_price_history (listing_id, price_azn) VALUES (%s, %s);
"""

ADD_IMAGE = """
INSERT INTO listing_images (listing_id, image_url, position)
VALUES (%s, %s, %s);
"""

CLEAR_IMAGES = "DELETE FROM listing_images WHERE listing_id = %s;"


def to_row(rec):
    """Map a scraped record onto the listings table columns."""
    renovation = None
    if rec.get("has_repair") is True:
        renovation = "temirli"
    elif rec.get("has_repair") is False:
        renovation = "temirsiz"

    nearest = rec.get("nearest_locations") or []

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
        "building_type": rec.get("building_type"),
        "renovation":    renovation,
        "has_kupca":     rec.get("has_kupca"),
        "has_mortgage":  rec.get("has_mortgage"),
        "city":          rec.get("city"),
        "district":      rec.get("district"),
        "latitude":      rec.get("latitude"),
        "longitude":     rec.get("longitude"),
        "metro_station": nearest[0] if nearest else None,
        "title":         rec.get("title"),
        "description":   rec.get("description"),
        "seller_type":   rec.get("seller_type"),
        "seller_id":     rec.get("seller_id"),
        "seller_name":   rec.get("seller_name"),
        "scrape_source": rec.get("scrape_source") or "backfill",
        "raw_json":      Json(rec.get("raw_json") or {}),
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

    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                print(f"  line {lineno}: bad JSON, skipped")
                skipped += 1
                continue

            # Sanity gate. Rows without price or area are useless to the model.
            if rec.get("price_azn") is None or rec.get("area_m2") in (None, 0):
                skipped += 1
                continue

            row = to_row(rec)
            cur.execute(UPSERT, row)
            was_insert = cur.fetchone()[0]
            inserted += was_insert
            updated += (not was_insert)

            # price history — append only when it actually changed
            cur.execute(LAST_PRICE, (row["listing_id"],))
            prev = cur.fetchone()
            if prev is None or float(prev[0]) != float(row["price_azn"]):
                cur.execute(ADD_PRICE, (row["listing_id"], row["price_azn"]))
                price_changes += 1

            # images — replace the set each time
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

    print("\n" + "=" * 50)
    print(f"  inserted (new):   {inserted}")
    print(f"  updated:          {updated}")
    print(f"  skipped:          {skipped}")
    print(f"  price rows added: {price_changes}")
    print(f"  images added:     {images}")
    print("=" * 50)

    # Health check — read this every time
    cur.execute("""
        SELECT count(*)                                            AS total,
               count(*) FILTER (WHERE deal_type = 'sale')          AS sale,
               count(*) FILTER (WHERE deal_type = 'rent')          AS rent,
               round(avg(price_azn / NULLIF(area_m2, 0)))          AS avg_per_m2,
               min(price_azn), max(price_azn)
        FROM listings;
    """)
    total, sale, rent, avg_m2, mn, mx = cur.fetchone()
    print(f"\n  DB now: {total} rows ({sale} sale / {rent} rent)")
    print(f"  avg price/m²: {avg_m2} AZN   range: {mn} - {mx}")
    if avg_m2 and not (800 <= float(avg_m2) <= 6000):
        print("  *** WARNING: avg price/m² is outside 800-6000 AZN.")
        print("      Likely rent contamination or a parsing bug. Investigate.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
