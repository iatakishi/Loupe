#!/usr/bin/env python3
"""
Loupe — bina.az listing scraper (JSON API edition)

bina.az is a Next.js app, so every listing is available as structured JSON:
    https://bina.az/_next/data/{buildId}/az/items/{id}.json

TWO MODES
---------
mode=sitemap  (RECOMMENDED) Reads bina.az's daily-regenerated item sitemap.
              Complete coverage of every live listing. Mixed rent/sale and all
              property types — filter afterwards on deal_type / property_type.

mode=pages    Walks category pages. More targeted, but bina.az renders listing
              cards client-side, so IDs are pulled out of the embedded Apollo
              cache rather than from links.

USAGE
-----
    # smoke test — 30 listings, ~1 minute
    python -m scrapy runspider scraper/items_spider.py -a mode=sitemap -a max_items=30 -O data/raw/test.jsonl

    # real backfill — run this overnight
    python -m scrapy runspider scraper/items_spider.py -a mode=sitemap -a max_items=20000 -O data/raw/backfill.jsonl --logfile=logs/backfill.log

ARGS
----
    mode        'sitemap' (default) | 'pages'
    max_items   hard cap on listings fetched (default 500)
    max_pages   category pages to walk in pages mode
    deal        'alqi-satqi' (sale, default) | 'kiraye' (rent)
    category    'menziller' (default) | 'obyektler' | 'heyet-evleri' | ...

TIP: always pass --logfile=logs/run.log on long runs. Scrapy is verbose and
     PowerShell's scrollback will truncate it.

Politeness: 2.5s delay, 2 concurrent, autothrottle, robots.txt obeyed.
Do not lower these.
"""

import json
import re
from datetime import datetime, timezone

import scrapy


BASE = "https://bina.az"
SITEMAP_INDEX = "https://bina.azstatic.com/uploads/sitemaps/sitemap_items.xml"


# ----------------------------------------------------------------------
# Defensive helpers.
#
# bina.az's JSON is not consistently typed: `address` is a dict on some
# listings and a bare string on others, and several fields are sometimes
# null. Assuming a type is what produced 30 identical crashes, so every
# nested access goes through these.
# ----------------------------------------------------------------------
def as_dict(value):
    """Return value if it's a dict, else an empty dict."""
    return value if isinstance(value, dict) else {}


def text_of(value, *keys):
    """
    Pull a string out of a value that might be a string, a dict, or None.
        text_of("Həsənoğlu küç.")               -> "Həsənoğlu küç."
        text_of({"name": "Yasamal"}, "name")    -> "Yasamal"
        text_of(None, "name")                   -> None
    """
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for k in keys or ("name", "title", "fullAddress"):
            v = value.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None


def num_of(value, *keys):
    """Pull a number out of a scalar-or-dict field."""
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, dict):
        for k in keys or ("value", "total"):
            v = value.get(k)
            if isinstance(v, (int, float)):
                return v
    return None


def deal_type_from_breadcrumbs(breadcrumbs):
    """'Alqı-satqı' -> sale, 'Kirayə' -> rent."""
    if not breadcrumbs:
        return None
    text = json.dumps(breadcrumbs, ensure_ascii=False).lower()
    if "kirayə" in text or "kiraye" in text:
        return "rent"
    if "alqı-satqı" in text or "alqi-satqi" in text:
        return "sale"
    return None


class ItemsSpider(scrapy.Spider):
    name = "bina_items"
    allowed_domains = ["bina.az", "bina.azstatic.com"]

    custom_settings = {
        "ROBOTSTXT_OBEY": True,
        "DOWNLOAD_DELAY": 2.5,
        "CONCURRENT_REQUESTS": 2,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 2.0,
        "AUTOTHROTTLE_MAX_DELAY": 30.0,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,
        "RETRY_TIMES": 2,
        "HTTPCACHE_ENABLED": True,
        "HTTPCACHE_EXPIRATION_SECS": 86400,
        "HTTPCACHE_DIR": ".scrapy_cache",
        "LOG_LEVEL": "INFO",
        "FEED_EXPORT_ENCODING": "utf-8",
        "DEFAULT_REQUEST_HEADERS": {"Accept-Language": "az,en;q=0.8"},
        # Honest identification — put a real email here.
        "USER_AGENT": (
            "HolbertonMLCapstone/1.0 (student research project; "
            "contact: ayyub.mammadov.2005@gmail.com)"
        ),
    }

    def __init__(self, mode="sitemap", max_items=500, max_pages=3,
                 deal="alqi-satqi", category="menziller", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = mode
        self.max_items = int(max_items)
        self.max_pages = int(max_pages)
        self.deal = deal
        self.category = category

        self.build_id = None
        self.seen_ids = set()
        self.requested = 0
        self.scraped = 0
        self.failed = 0

    # ==================================================================
    # ENTRY POINT
    # Scrapy >= 2.13 calls `async def start()`; older calls start_requests().
    # Both defined so this runs on either.
    # ==================================================================
    def _initial_requests(self):
        # buildId lives in page HTML and changes on every bina.az deploy,
        # so it must be read fresh, never hardcoded.
        yield scrapy.Request(
            f"{BASE}/{self.deal}/{self.category}",
            callback=self.parse_build_id,
            dont_filter=True,
        )

    async def start(self):
        for req in self._initial_requests():
            yield req

    def start_requests(self):
        return self._initial_requests()

    # ------------------------------------------------------------------
    def parse_build_id(self, response):
        m = re.search(
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            response.text, re.DOTALL,
        )
        if not m:
            self.logger.error("No __NEXT_DATA__ on %s — site changed?",
                              response.url)
            return

        self.build_id = json.loads(m.group(1)).get("buildId")
        if not self.build_id:
            self.logger.error("buildId missing")
            return
        self.logger.info("buildId = %s   mode = %s   max_items = %d",
                         self.build_id, self.mode, self.max_items)

        if self.mode == "sitemap":
            yield scrapy.Request(SITEMAP_INDEX, callback=self.parse_sitemap_index)
        else:
            yield from self.harvest_ids(response)
            for page in range(2, self.max_pages + 1):
                yield scrapy.Request(
                    f"{BASE}/{self.deal}/{self.category}?page={page}",
                    callback=self.harvest_ids,
                    meta={"page": page},
                )

    # ------------------------------------------------------------------
    # Sitemap mode
    # ------------------------------------------------------------------
    def parse_sitemap_index(self, response):
        subs = re.findall(r"<loc>\s*(.*?)\s*</loc>", response.text)
        self.logger.info("sitemap index: %d sub-sitemaps", len(subs))
        for url in subs:
            yield scrapy.Request(url, callback=self.parse_sitemap)

    def parse_sitemap(self, response):
        ids = re.findall(r"<loc>\s*https://bina\.az/items/(\d+)\s*</loc>",
                         response.text)
        self.logger.info("sitemap %s: %d item URLs",
                         response.url.rsplit("/", 1)[-1], len(ids))
        for raw in ids:
            if self.requested >= self.max_items:
                return
            yield from self.request_item(int(raw))

    # ------------------------------------------------------------------
    # Category-page mode
    #
    # bina.az renders listing cards client-side, so there are no
    # <a href="/items/123"> links in the HTML. The IDs are in the embedded
    # Apollo cache as keys like "Item:6395784". Look for both.
    # ------------------------------------------------------------------
    def harvest_ids(self, response):
        ids = {int(i) for i in re.findall(r'"Item:(\d+)"', response.text)}
        ids |= {int(i) for i in re.findall(r"/items/(\d+)", response.text)}
        page = response.meta.get("page", 1)

        if not ids:
            self.logger.warning(
                "page %s: no item IDs found. bina.az may have changed how the "
                "listing grid is rendered — use mode=sitemap instead.", page)
            return

        new = ids - self.seen_ids
        self.logger.info("page %s: %d ids (%d new)", page, len(ids), len(new))
        for item_id in sorted(new):
            yield from self.request_item(item_id)

    # ------------------------------------------------------------------
    def request_item(self, item_id):
        if item_id in self.seen_ids or self.requested >= self.max_items:
            return
        self.seen_ids.add(item_id)
        self.requested += 1
        yield scrapy.Request(
            f"{BASE}/_next/data/{self.build_id}/az/items/{item_id}.json",
            callback=self.parse_item,
            errback=self.item_failed,
            meta={"item_id": item_id},
        )

    def item_failed(self, failure):
        self.failed += 1
        self.logger.warning("item %s failed: %s",
                            failure.request.meta.get("item_id"),
                            failure.value.__class__.__name__)

    # ------------------------------------------------------------------
    # JSON -> our schema shape
    # Whole body is wrapped: one weird listing must not abort the crawl.
    # ------------------------------------------------------------------
    def parse_item(self, response):
        item_id = response.meta["item_id"]
        try:
            yield self._build_record(item_id, response)
        except Exception as exc:                      # noqa: BLE001
            self.failed += 1
            self.logger.warning("item %s: parse failed (%s: %s)",
                                item_id, exc.__class__.__name__, exc)

    def _build_record(self, item_id, response):
        payload = json.loads(response.text)
        d = as_dict(as_dict(payload.get("pageProps")).get("currentItemData"))
        if not d:
            raise ValueError("no currentItemData")

        price = as_dict(d.get("price"))
        area = as_dict(d.get("area"))
        location = as_dict(d.get("location"))
        category = as_dict(d.get("category"))
        company = as_dict(d.get("company"))
        city = d.get("city")

        nearest = []
        for n in (d.get("nearestLocations") or []):
            name = text_of(n)
            if name:
                nearest.append(name)

        photos = []
        for p in (d.get("photos") or []):
            if isinstance(p, str):
                photos.append(p)
            elif isinstance(p, dict):
                u = p.get("full") or p.get("large") or p.get("url")
                if u:
                    photos.append(u)

        contact_type = d.get("contactTypeName") or ""
        is_agent = bool(company.get("id")) or "vasitə" in str(contact_type).lower()

        self.scraped += 1
        if self.scraped % 100 == 0:
            self.logger.info("scraped %d items", self.scraped)

        return {
            "listing_id":     item_id,
            "url":            f"{BASE}/items/{item_id}",

            # classification — always filter on these downstream
            "deal_type":      deal_type_from_breadcrumbs(d.get("breadcrumbs"))
                              or ("rent" if self.deal == "kiraye" else "sale"),
            "property_type":  category.get("slug"),
            "category_name":  category.get("name"),

            "price_azn":      num_of(price, "total"),
            "currency":       price.get("currency") or "AZN",

            "area_m2":        num_of(area, "value"),
            "area_units":     area.get("units"),
            "land_area":      num_of(d.get("landArea"), "value"),
            "rooms":          d.get("rooms"),
            "floor":          d.get("floor"),
            "total_floors":   d.get("floors"),
            "building_type":  text_of(d.get("buildingTypeName")),

            "has_repair":     d.get("hasRepair"),
            "has_kupca":      d.get("hasBillOfSale"),
            "has_mortgage":   d.get("hasMortgage"),
            "has_internal_loan": d.get("hasInternalLoan"),

            "city":           text_of(city),
            "district":       text_of(d.get("location")),
            "location_id":    location.get("id"),
            "street":         text_of(d.get("address")),
            "latitude":       d.get("latitude") or location.get("latitude"),
            "longitude":      d.get("longitude") or location.get("longitude"),
            "nearest_locations": nearest,

            "title":          text_of(d.get("metaTags"), "title"),
            "description":    d.get("description"),
            "photo_urls":     photos,
            "photo_count":    len(photos),

            "seller_type":    "agent" if is_agent else "owner",
            "seller_id":      str(company.get("id")) if company.get("id") else None,
            "seller_name":    company.get("name") or text_of(d.get("contactName")),
            "is_business":    d.get("business"),

            "views":          d.get("views"),
            "is_vipped":      d.get("isVipped"),
            "is_featured":    d.get("isFeatured"),
            "is_leased":      d.get("isLeased"),
            "updated_at_site": d.get("updatedAt"),
            "expires_at":     d.get("expiresAt"),

            "scraped_at":     datetime.now(timezone.utc).isoformat(),
            "scrape_source":  self.mode,
            "raw_json":       d,
        }

    # ------------------------------------------------------------------
    def closed(self, reason):
        self.logger.info("=" * 60)
        self.logger.info("Finished: %s", reason)
        self.logger.info("IDs discovered: %d", len(self.seen_ids))
        self.logger.info("Items scraped:  %d", self.scraped)
        self.logger.info("Failed:         %d", self.failed)
        if self.scraped == 0:
            self.logger.error(
                "ZERO ITEMS. Check: (1) did 'buildId = ...' print? "
                "(2) did the sitemap report item URLs? (3) any 403 in the log?")
        self.logger.info("=" * 60)
