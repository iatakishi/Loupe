#!/usr/bin/env python3
"""
Bina.az reconnaissance — run this BEFORE writing the scraper.

ALREADY ANSWERED (verified — no need to re-check):
  - robots.txt disallows only /company_session/new, /reset_password/new and
    /company/new. Listing and category pages are permitted.
  - The sitemap is at https://bina.azstatic.com/uploads/attachment/sitemap_az.xml
    and contains CATEGORY urls only, not individual listings. It is useful as a
    district/metro lookup table, NOT for backfill.

WHAT THIS SCRIPT STILL ANSWERS:
  1. Can you fetch pages at all, or does bot protection block you?
  2. Is listing data server-rendered (use Scrapy) or client-rendered (Playwright)?
  3. Is there an embedded JSON blob you can parse instead of CSS selectors?

Usage:
    pip install requests
    python recon.py https://bina.az/items/XXXXXXX
    python recon.py https://bina.az/alqi-satqi/menziller

Run it on BOTH a listing page and a category page - they may differ.
"""

import json
import re
import sys
import urllib.robotparser as robotparser

import requests

BASE = "https://bina.az"
# Identify yourself honestly. Do not spoof a browser UA to evade detection.
UA = "HolbertonMLCapstone/0.1 (student research project; contact: ayyub.mammadov.2005@gmail.com)"
HEADERS = {"User-Agent": UA, "Accept-Language": "az,en;q=0.8"}


def check_robots(listing_url: str) -> None:
    print("=" * 70)
    print("1. ROBOTS.TXT")
    print("=" * 70)
    rp = robotparser.RobotFileParser()
    rp.set_url(f"{BASE}/robots.txt")
    try:
        rp.read()
    except Exception as e:
        print(f"  could not read robots.txt: {e}")
        return

    print(f"  can fetch listing page? {rp.can_fetch(UA, listing_url)}")
    print(f"  can fetch /alqi-satqi ? {rp.can_fetch(UA, BASE + '/alqi-satqi')}")
    delay = rp.crawl_delay(UA)
    print(f"  declared crawl-delay: {delay if delay else 'none (use >=2s anyway)'}")
    print(f"  sitemaps: {rp.site_maps() or 'none declared'}")
    print()
    print("  >> If can_fetch is False for the paths you need, STOP and tell")
    print("     your team. Do not scrape disallowed paths.")
    print()


def fetch(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        print(f"  HTTP {r.status_code}, {len(r.content):,} bytes, "
              f"content-type={r.headers.get('content-type', '?')}")
        if r.status_code != 200:
            print("  >> Non-200. Could be geo-blocking, Cloudflare, or a bad URL.")
            return None
        return r.text
    except Exception as e:
        print(f"  request failed: {e}")
        return None


def check_ssr(html: str) -> None:
    """Is the data in the raw HTML, or injected later by JavaScript?"""
    print("=" * 70)
    print("2. SERVER-SIDE RENDERED?")
    print("=" * 70)

    # Azerbaijani real-estate pages contain these words if content is in the HTML.
    probes = {
        "price marker (AZN)":      r"AZN|₼",
        "area (m2)":               r"m²|kv\.?m|kvadrat",
        "rooms (otaq)":            r"otaq",
        "floor (mərtəbə)":         r"mərtəbə",
        "deed (kupça)":            r"kup[çc]a",
        "mortgage (ipoteka)":      r"ipoteka",
        "renovation (təmir)":      r"t[əe]mir",
        "digits w/ thousands sep": r"\d{1,3}[ .,]\d{3}",
    }
    hits = 0
    for label, pattern in probes.items():
        found = re.search(pattern, html, re.IGNORECASE)
        print(f"  {'FOUND  ' if found else 'missing'}  {label}")
        hits += bool(found)

    print()
    if hits >= 5:
        print("  >> VERDICT: server-rendered. Use SCRAPY. Skip Playwright.")
    elif hits >= 2:
        print("  >> VERDICT: partial. Some fields may need JS. Try Scrapy first,")
        print("     fall back to Playwright only for the missing fields.")
    else:
        print("  >> VERDICT: client-rendered. You likely need Playwright,")
        print("     OR find the underlying JSON API (see section 3).")
    print()


def check_embedded_json(html: str) -> None:
    """Best case: the whole listing object is already JSON in the page."""
    print("=" * 70)
    print("3. EMBEDDED JSON  (this is the jackpot — check carefully)")
    print("=" * 70)

    patterns = {
        "__NEXT_DATA__":   r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        "__NUXT__":        r'window\.__NUXT__\s*=\s*(.*?);?\s*</script>',
        "JSON-LD":         r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
        "__INITIAL_STATE__": r'window\.__INITIAL_STATE__\s*=\s*(.*?);?\s*</script>',
    }

    found_any = False
    for name, pat in patterns.items():
        for m in re.finditer(pat, html, re.DOTALL):
            blob = m.group(1).strip()
            print(f"\n  --- {name} ({len(blob):,} chars) ---")
            found_any = True
            try:
                data = json.loads(blob)
                print(f"  parsed OK. top-level keys: {list(data)[:15]}"
                      if isinstance(data, dict) else f"  parsed OK, type={type(data).__name__}")
                print("  preview:")
                print("  " + json.dumps(data, ensure_ascii=False, indent=2)[:900]
                      .replace("\n", "\n  "))
            except json.JSONDecodeError:
                print("  not valid JSON on its own (JS object literal). Preview:")
                print("  " + blob[:400])

    # Also look for API calls referenced in the page source.
    api_hits = set(re.findall(r'["\'](/api/[^"\']{3,80})["\']', html))
    if api_hits:
        print(f"\n  API paths referenced in page source ({len(api_hits)}):")
        for p in sorted(api_hits)[:20]:
            print(f"    {p}")
        print("  >> Try these in the browser. A JSON API beats HTML parsing every time.")

    if not found_any and not api_hits:
        print("  No embedded JSON found. You'll be writing CSS/XPath selectors.")
    print()


def check_sitemap() -> None:
    """Known location. Pull it for the district/metro lookup table only."""
    print("=" * 70)
    print("4. SITEMAP  (district lookup table, NOT backfill)")
    print("=" * 70)
    index_url = "https://bina.azstatic.com/uploads/attachment/sitemap_az.xml"
    print(f"  {index_url}")
    try:
        r = requests.get(index_url, headers=HEADERS, timeout=20)
        print(f"    HTTP {r.status_code}, {len(r.content):,} bytes")
        subs = re.findall(r"<loc>(.*?)</loc>", r.text)
        print(f"    {len(subs)} sub-sitemaps:")
        for s_url in subs:
            print(f"      {s_url}")
        print()
        print("  >> These hold category URLs like")
        print("     /baki/yasamal/alqi-satqi/menziller/3-otaqli")
        print("     Parse the slugs into a district + metro lookup table for Aygul.")
        print("     They do NOT contain /items/ URLs, so backfill must paginate")
        print("     ?page=N on the category listing pages instead.")
    except Exception as e:
        print(f"    failed: {e}")
    print()


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    listing_url = sys.argv[1]

    check_robots(listing_url)   # known permissive; confirms nothing changed

    print("=" * 70)
    print(f"FETCHING {listing_url}")
    print("=" * 70)
    html = fetch(listing_url)
    print()
    if html is None:
        print("Could not fetch the page — stopping.")
        sys.exit(1)

    # Keep a copy so you can grep it by hand afterwards.
    with open("sample_listing.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("  saved raw HTML to sample_listing.html for manual inspection\n")

    check_ssr(html)
    check_embedded_json(html)
    check_sitemap()

    print("=" * 70)
    print("NEXT: paste this output to your team. The Scrapy-vs-Playwright")
    print("decision and the backfill strategy both follow from it.")
    print("=" * 70)


if __name__ == "__main__":
    main()
