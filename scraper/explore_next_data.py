#!/usr/bin/env python3
"""
Explore bina.az's __NEXT_DATA__ blob and test for a hidden JSON API.

bina.az is a Next.js app. Two consequences:
  1. Every page embeds the full listing object as JSON in a <script> tag.
     No CSS selectors needed — just parse JSON.
  2. Next.js usually exposes /_next/data/{buildId}/{locale}/{path}.json
     which returns that same JSON directly. If that works, scraping
     becomes trivial and much lighter on their servers.

Usage:
    python scraper/explore_next_data.py https://bina.az/items/XXXXXXX

Run it on an APARTMENT (menzil) listing, not an obyekt/commercial one.
"""

import json
import re
import sys

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "az,en;q=0.8"}


def walk(obj, path=""):
    """Yield every (path, value) leaf in a nested dict/list."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(obj, list):
        # only walk the first 3 items of long lists to keep output sane
        for i, v in enumerate(obj[:3]):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield path, obj


def find_listing_object(data):
    """
    Find the dict that looks like the listing itself.
    Heuristic: a dict containing both a price-ish and an area-ish key.
    """
    candidates = []

    def rec(obj, path=""):
        if isinstance(obj, dict):
            keys = {k.lower() for k in obj}
            has_price = any("price" in k for k in keys)
            has_area  = any(k in keys for k in ("area", "field_area", "area_value")) \
                        or any("area" in k for k in keys)
            if has_price and has_area:
                candidates.append((path, obj))
            for k, v in obj.items():
                rec(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj[:5]):
                rec(v, f"{path}[{i}]")

    rec(data)
    return candidates


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    url = sys.argv[1]

    print("=" * 70)
    print("FETCHING", url)
    print("=" * 70)
    r = requests.get(url, headers=HEADERS, timeout=20)
    print(f"  HTTP {r.status_code}, {len(r.content):,} bytes\n")
    if r.status_code != 200:
        sys.exit(1)
    html = r.text

    # ---------------------------------------------------------------
    # 1. Extract and save __NEXT_DATA__
    # ---------------------------------------------------------------
    m = re.search(
        r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL
    )
    if not m:
        print("No __NEXT_DATA__ found. Falling back to JSON-LD only.")
        next_data = None
    else:
        next_data = json.loads(m.group(1))
        with open("next_data.json", "w", encoding="utf-8") as f:
            json.dump(next_data, f, ensure_ascii=False, indent=2)
        print("Saved full blob to next_data.json  <-- OPEN THIS IN VS CODE\n")

        build_id = next_data.get("buildId")
        locale = next_data.get("locale", "az")
        print(f"  buildId: {build_id}")
        print(f"  locale:  {locale}\n")

        # -----------------------------------------------------------
        # 2. Where does the listing live inside the blob?
        # -----------------------------------------------------------
        print("=" * 70)
        print("LISTING OBJECT CANDIDATES (dicts with price + area keys)")
        print("=" * 70)
        cands = find_listing_object(next_data)
        if not cands:
            print("  none found automatically — inspect next_data.json by hand")
        for path, obj in cands[:3]:
            print(f"\n  PATH: {path}")
            print(f"  KEYS: {sorted(obj.keys())[:40]}")

        # -----------------------------------------------------------
        # 3. Show every leaf that looks like a field we need
        # -----------------------------------------------------------
        print("\n" + "=" * 70)
        print("INTERESTING LEAVES")
        print("=" * 70)
        wanted = ("price", "area", "room", "floor", "lat", "lng", "long",
                  "district", "metro", "region", "repair", "mortgage",
                  "has_bill_of_sale", "category", "description", "created",
                  "updated", "views", "id")
        seen = 0
        for path, val in walk(next_data):
            low = path.lower()
            if any(w in low for w in wanted) and val not in (None, "", [], {}):
                s = str(val)
                if len(s) > 90:
                    s = s[:90] + "..."
                print(f"  {path:<70} = {s}")
                seen += 1
                if seen > 120:
                    print("  ... (truncated, see next_data.json)")
                    break

        # -----------------------------------------------------------
        # 4. Test the hidden JSON API
        # -----------------------------------------------------------
        print("\n" + "=" * 70)
        print("TESTING NEXT.JS JSON API")
        print("=" * 70)
        item_id = re.search(r"/items/(\d+)", url)
        if build_id and item_id:
            api = (f"https://bina.az/_next/data/{build_id}/{locale}"
                   f"/items/{item_id.group(1)}.json")
            print(f"  {api}")
            try:
                ar = requests.get(api, headers=HEADERS, timeout=20)
                print(f"  HTTP {ar.status_code}, {len(ar.content):,} bytes")
                if ar.status_code == 200:
                    with open("api_response.json", "w", encoding="utf-8") as f:
                        json.dump(ar.json(), f, ensure_ascii=False, indent=2)
                    print("  >>> API WORKS. Saved to api_response.json")
                    print("  >>> This is the best scraping path: pure JSON,")
                    print("      no HTML parsing, ~10x smaller responses.")
                    print("  >>> CAVEAT: buildId changes on every site deploy.")
                    print("      Re-read it from any page HTML before each run.")
                else:
                    print("  API not usable — parse __NEXT_DATA__ from HTML instead.")
            except Exception as e:
                print(f"  request failed: {e}")

    # ---------------------------------------------------------------
    # 5. JSON-LD — gives price + breadcrumb category for free
    # ---------------------------------------------------------------
    print("\n" + "=" * 70)
    print("JSON-LD")
    print("=" * 70)
    for jm in re.finditer(
        r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        html, re.DOTALL
    ):
        try:
            d = json.loads(jm.group(1))
        except json.JSONDecodeError:
            continue
        t = d.get("@type")
        print(f"\n  @type = {t}")
        if t == "Product":
            print(f"    name:     {d.get('name')}")
            print(f"    category: {d.get('category')}")
            print(f"    offers:   {json.dumps(d.get('offers'), ensure_ascii=False)}")
            print(f"    images:   {len(d.get('image', []))}")
        elif t == "BreadcrumbList":
            trail = [i.get("name") for i in d.get("itemListElement", [])]
            print(f"    trail: {' > '.join(trail)}")
            print("    >>> Use this for deal_type and property_type:")
            print("        'Alqı-satqı' -> sale     'Kirayə' -> rent")
            print("        'Mənzillər'  -> menzil   'Obyektlər' -> obyekt")

    print("\n" + "=" * 70)
    print("NEXT: open next_data.json in VS Code, Ctrl+F for the actual price")
    print("of this listing, and note the JSON path. That path is what the")
    print("spider will read. Paste the INTERESTING LEAVES section back.")
    print("=" * 70)


if __name__ == "__main__":
    main()
