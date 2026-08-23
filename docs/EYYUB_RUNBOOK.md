# Eyyub — Data Engineer Runbook
### Bina.az ML Bargain Finder | Holberton ML Capstone

Your job: **get the data, store it correctly, keep it flowing.**
Everything else in the project depends on you finishing Week 1–2 on time.

---

## PART 0 — What we already know about bina.az

Verified, so you don't have to rediscover it:

| Question | Answer |
|---|---|
| robots.txt | Only `/company_session/new`, `/reset_password/new`, `/company/new` disallowed. Listing pages are fine. |
| Declared crawl-delay | 10s, but only for `dotbot`. Use **2–3s anyway**. |
| Sitemap | `https://bina.azstatic.com/uploads/attachment/sitemap_az.xml` → 3 sub-files. Contains **category URLs only**, not listings. Last updated Dec 2025. |
| Listing URL pattern | `https://bina.az/items/{numeric_id}` |
| Category URL pattern | `https://bina.az/alqi-satqi/menziller?page={N}` |
| District URL pattern | `https://bina.az/baki/{district}/alqi-satqi/menziller/{N}-otaqli` |
| Bot protection | **Yes.** Non-browser requests can be rejected. Plan for Playwright fallback. |

**Use the sitemap for one thing:** download all 3 sub-files, extract the URL slugs,
and you get the complete official list of Baku districts, settlements, and metro
stations. Hand that to Aygul as a lookup table — it saves her from
inventing her own district normalisation.

---

## PART 1 — Environment setup (Day 1, ~1 hour)

### 1.1 Python

```bash
# Check you have 3.10+
python3 --version

mkdir bina-bargain-finder && cd bina-bargain-finder
python3 -m venv venv

# Linux/Mac:
source venv/bin/activate
# Windows PowerShell:
venv\Scripts\Activate.ps1
```

### 1.2 Packages

```bash
pip install scrapy psycopg2-binary python-dotenv playwright parsel lxml
playwright install chromium     # only needed if you hit the bot check
```

### 1.3 PostgreSQL via Docker (easiest — no local install mess)

```bash
docker run --name bina-pg \
  -e POSTGRES_PASSWORD=binapass \
  -e POSTGRES_USER=binauser \
  -e POSTGRES_DB=bina \
  -p 5432:5432 \
  -d postgres:16

# Verify it's alive
docker exec -it bina-pg psql -U binauser -d bina -c "SELECT version();"
```

No Docker? Install PostgreSQL 16 normally and create the `bina` database by hand.

### 1.4 Load the schema

```bash
docker exec -i bina-pg psql -U binauser -d bina < schema.sql
docker exec -it bina-pg psql -U binauser -d bina -c "\dt"
# should list: listings, listing_price_history, listing_images, predictions, scrape_runs
```

### 1.5 `.env` file (never commit this)

```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=bina
DB_USER=binauser
DB_PASS=binapass
```

Add to `.gitignore`: `.env`, `venv/`, `*.html`, `data/`, `__pycache__/`

---

## PART 2 — Repo structure

Create this on Day 1 and push it. Your teammates need somewhere to commit.

```
bina-bargain-finder/
├── README.md
├── requirements.txt
├── .gitignore
├── .env.example          # same as .env but with fake values — DO commit this
├── db/
│   ├── schema.sql
│   └── data_dictionary.md    # Aygul owns this, you fill the scraper columns
├── scraper/
│   ├── scrapy.cfg
│   └── bina/
│       ├── settings.py
│       ├── items.py
│       ├── pipelines.py
│       └── spiders/
│           ├── list_spider.py      # category pages → bulk features
│           └── detail_spider.py    # item pages → description, images, GPS
├── scripts/
│   ├── recon.py              # already have this
│   ├── fetch_sample.py       # save one page for selector work
│   ├── extract_districts.py  # sitemap → district lookup table
│   └── daily_refresh.py      # mark delisted
├── notebooks/            # Aygul + Idrak work here
└── docs/
    └── architecture.md
```

```bash
git init
git remote add origin git@github.com:YOURTEAM/bina-bargain-finder.git
git add . && git commit -m "Project skeleton + DB schema"
git push -u origin main
```

---

## PART 3 — Selector discovery (Day 1–2, ~2 hours)

**You cannot write a spider until you know what the HTML looks like.**
Do not skip this and do not guess selectors.

### 3.1 Save one real page

```python
# scripts/fetch_sample.py
import sys, requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

url = sys.argv[1]
r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "az"}, timeout=20)
print(r.status_code, len(r.content))
open("sample.html", "w", encoding="utf-8").write(r.text)
```

```bash
python scripts/fetch_sample.py "https://bina.az/alqi-satqi/menziller"
```

- **HTTP 200 + big file** → plain requests/Scrapy works. Continue.
- **403 / small file / "checking your browser"** → go to §3.3 (Playwright).

### 3.2 Find the selectors

Open `sample.html` in your browser, or better: open bina.az in Chrome,
right-click a listing card → **Inspect**. Write down, for a card:

| Field | Selector | Example value |
|---|---|---|
| card container | `?` | |
| link to item | `?` | `/items/4839201` |
| price | `?` | `185 000` |
| currency | `?` | `AZN` |
| rooms | `?` | `3 otaqlı` |
| area | `?` | `89.9 m²` |
| floor | `?` | `8/12 mərtəbə` |
| location | `?` | `Zığ q.` / `Nizami m.` |
| date | `?` | `bugün 13:03` |
| agency badge | `?` | `Agentlik` |
| kupça badge | `?` | `Çıxarış var` |
| təmir badge | `?` | `Təmirli` |

Test each one before writing the spider:

```bash
scrapy shell "https://bina.az/alqi-satqi/menziller"
>>> response.css("div.items-i").get()          # try your guesses here
>>> response.css("div.items-i a::attr(href)").getall()
```

If `scrapy shell` gets blocked, load the saved file instead:

```python
from parsel import Selector
sel = Selector(open("sample.html", encoding="utf-8").read())
sel.css("YOUR_GUESS").getall()[:3]
```

### 3.3 If you're blocked — Playwright fallback

```python
# scripts/fetch_sample_pw.py
import sys
from playwright.sync_api import sync_playwright

url = sys.argv[1]
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(locale="az-AZ")
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)
    open("sample.html", "w", encoding="utf-8").write(page.content())
    print("saved", len(page.content()))
    browser.close()
```

**Important:** if Playwright *also* gets blocked, or you get rate-limited
repeatedly, stop. Do not try to work around their protection — that crosses
from "polite student scraper" into something your examiners will not defend.
Fall back to Plan B in §9.

---

## PART 4 — The list spider (Day 2–4) ← your main deliverable

This gets ~80% of the feature matrix. Priority #1.

```python
# scraper/bina/spiders/list_spider.py
import re
import scrapy


def clean_number(text):
    """'185 000' -> 185000.0 ; '89.9 m²' -> 89.9 ; None-safe."""
    if not text:
        return None
    t = text.replace("\xa0", " ").replace(",", ".")
    m = re.search(r"\d+(?:[ ]\d{3})*(?:\.\d+)?", t)
    if not m:
        return None
    return float(m.group(0).replace(" ", ""))


class ListSpider(scrapy.Spider):
    name = "bina_list"
    allowed_domains = ["bina.az"]

    custom_settings = {
        "DOWNLOAD_DELAY": 2.5,
        "CONCURRENT_REQUESTS": 2,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 1.0,
        "RETRY_TIMES": 2,
        "ROBOTSTXT_OBEY": True,
    }

    def __init__(self, max_pages=50, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_pages = int(max_pages)

    def start_requests(self):
        base = "https://bina.az/alqi-satqi/menziller"
        for page in range(1, self.max_pages + 1):
            yield scrapy.Request(f"{base}?page={page}", meta={"page": page})

    def parse(self, response):
        # >>> REPLACE ALL SELECTORS BELOW WITH WHAT YOU FOUND IN PART 3 <<<
        cards = response.css("div.items-i")

        if not cards:
            self.logger.error(
                "NO CARDS on %s — selector is wrong or we got blocked", response.url
            )
            return

        for card in cards:
            href = card.css("a::attr(href)").get()
            if not href:
                continue

            m = re.search(r"/items/(\d+)", href)
            if not m:
                continue

            raw_price = card.css(".price-val::text").get()
            raw_area  = card.css(".name::text").re_first(r"[\d.]+\s*m²")
            raw_rooms = card.css(".name::text").re_first(r"(\d+)\s*otaq")
            raw_floor = card.css(".name::text").re_first(r"(\d+)/(\d+)\s*mərtəbə")

            floor = total_floors = None
            if raw_floor:
                f = re.search(r"(\d+)/(\d+)", raw_floor)
                if f:
                    floor, total_floors = int(f.group(1)), int(f.group(2))

            badges = [b.strip() for b in card.css(".label::text").getall()]

            yield {
                "listing_id":    int(m.group(1)),
                "url":           response.urljoin(href),
                "price_azn":     clean_number(raw_price),
                "currency":      "AZN",
                "area_m2":       clean_number(raw_area),
                "rooms":         int(raw_rooms) if raw_rooms else None,
                "floor":         floor,
                "total_floors":  total_floors,
                "location_raw":  card.css(".location::text").get(),
                "posted_raw":    card.css(".city_when::text").get(),
                "seller_type":   "agent" if "Agentlik" in badges else "owner",
                "has_kupca":     any("Çıxarış" in b for b in badges),
                "renovation":    "temirli" if any("Təmirli" in b for b in badges) else None,
                "scrape_source": "backfill",
            }
```

Run it:

```bash
cd scraper
scrapy crawl bina_list -a max_pages=3 -o test.json
```

**Checkpoint:** open `test.json`. You should see ~60 rows with real prices and
areas. If prices are `null`, your selector is wrong — fix it before going further.
Do not scale up a broken spider.

Then the full backfill (run it overnight):

```bash
scrapy crawl bina_list -a max_pages=800 -s LOG_FILE=backfill.log
```

At 2.5s/page × 800 pages ≈ 35 minutes. ~20 listings/page → **~16,000 rows.**
That is a solid training set.

---

## PART 5 — Postgres pipeline (Day 3–4)

```python
# scraper/bina/pipelines.py
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

UPSERT = """
INSERT INTO listings (
    listing_id, url, price_azn, currency, area_m2, rooms,
    floor, total_floors, district, seller_type, has_kupca,
    renovation, scrape_source, first_seen_at, last_seen_at, is_active
) VALUES (
    %(listing_id)s, %(url)s, %(price_azn)s, %(currency)s, %(area_m2)s, %(rooms)s,
    %(floor)s, %(total_floors)s, %(district)s, %(seller_type)s, %(has_kupca)s,
    %(renovation)s, %(scrape_source)s, now(), now(), TRUE
)
ON CONFLICT (listing_id) DO UPDATE SET
    price_azn    = EXCLUDED.price_azn,
    last_seen_at = now(),
    is_active    = TRUE
RETURNING (xmax = 0) AS was_insert;
"""

PRICE_CHECK = """
SELECT price_azn FROM listing_price_history
WHERE listing_id = %s ORDER BY observed_at DESC LIMIT 1;
"""

PRICE_INSERT = """
INSERT INTO listing_price_history (listing_id, price_azn) VALUES (%s, %s);
"""


class PostgresPipeline:
    def open_spider(self, spider):
        self.conn = psycopg2.connect(
            host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT"),
            dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
        )
        self.cur = self.conn.cursor()
        self.new = self.updated = 0

    def process_item(self, item, spider):
        d = dict(item)
        d.setdefault("district", d.pop("location_raw", None))
        d.pop("posted_raw", None)

        self.cur.execute(UPSERT, d)
        was_insert = self.cur.fetchone()[0]
        self.new += was_insert
        self.updated += (not was_insert)

        # price history: only append when the price actually changed
        if d.get("price_azn") is not None:
            self.cur.execute(PRICE_CHECK, (d["listing_id"],))
            row = self.cur.fetchone()
            if row is None or float(row[0]) != float(d["price_azn"]):
                self.cur.execute(PRICE_INSERT, (d["listing_id"], d["price_azn"]))

        self.conn.commit()
        return item

    def close_spider(self, spider):
        spider.logger.info("NEW: %s  UPDATED: %s", self.new, self.updated)
        self.cur.close()
        self.conn.close()
```

Enable it in `settings.py`:

```python
ITEM_PIPELINES = {"bina.pipelines.PostgresPipeline": 300}

USER_AGENT = "HolbertonMLCapstone/0.1 (student project; your@email.com)"
ROBOTSTXT_OBEY = True
DOWNLOAD_DELAY = 2.5
CONCURRENT_REQUESTS = 2
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 2
AUTOTHROTTLE_MAX_DELAY = 30
HTTPCACHE_ENABLED = True          # huge: re-parse without re-downloading
HTTPCACHE_EXPIRATION_SECS = 86400
```

`HTTPCACHE_ENABLED` is the single best setting here. When your selector is wrong
(it will be, twice), you re-run the parse against cached pages instead of
hammering bina.az again.

---

## PART 6 — Detail spider (Day 5–6, lower priority)

Only for fields the card doesn't show: description text, image URLs, GPS,
ipoteka flag, seller id.

```python
# scraper/bina/spiders/detail_spider.py
import os, psycopg2, scrapy
from dotenv import load_dotenv
load_dotenv()


class DetailSpider(scrapy.Spider):
    name = "bina_detail"
    allowed_domains = ["bina.az"]
    custom_settings = {"DOWNLOAD_DELAY": 3.0, "CONCURRENT_REQUESTS": 1}

    def start_requests(self):
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"), dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"), password=os.getenv("DB_PASS"))
        cur = conn.cursor()
        # only listings we haven't enriched yet
        cur.execute("""
            SELECT listing_id, url FROM listings
            WHERE description IS NULL AND is_active = TRUE
            ORDER BY first_seen_at DESC LIMIT 3000;
        """)
        for listing_id, url in cur.fetchall():
            yield scrapy.Request(url, meta={"listing_id": listing_id})
        conn.close()

    def parse(self, response):
        yield {
            "listing_id":  response.meta["listing_id"],
            "description": " ".join(response.css(".product-description ::text").getall()).strip(),
            "images":      response.css(".product-photos img::attr(src)").getall(),
            "latitude":    response.css("#map::attr(data-lat)").get(),
            "longitude":   response.css("#map::attr(data-lng)").get(),
        }
```

3000 pages × 3s = **2.5 hours**. Run it overnight. Don't try to enrich all 16,000.
A description subset is enough for Aygul's NLP flags.

---

## PART 7 — Daily refresh & delisting (Day 6)

This is what makes Idrak's validation possible. Do not skip it.

```python
# scripts/daily_refresh.py
import os, psycopg2
from dotenv import load_dotenv
load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"), dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"), password=os.getenv("DB_PASS"))
cur = conn.cursor()

cur.execute("""
    UPDATE listings
    SET is_active = FALSE, delisted_at = now()
    WHERE is_active = TRUE
      AND last_seen_at < now() - INTERVAL '36 hours';
""")
print("marked delisted:", cur.rowcount)
conn.commit()
conn.close()
```

Run order, once a day:

```bash
scrapy crawl bina_list -a max_pages=800    # refreshes last_seen_at + prices
python scripts/daily_refresh.py            # anything not seen → delisted
```

Cron it (Linux/Mac):
```
0 3 * * * cd /path/to/project && ./venv/bin/scrapy crawl bina_list -a max_pages=800
30 4 * * * cd /path/to/project && ./venv/bin/python scripts/daily_refresh.py
```

The 36-hour window (not 24) prevents one failed run from marking your whole
database as delisted.

---

## PART 8 — Daily health check

Run this every morning. If any number looks wrong, the scraper broke silently.

```sql
SELECT count(*) AS total,
       count(*) FILTER (WHERE is_active) AS active,
       count(*) FILTER (WHERE price_azn IS NULL) AS missing_price,
       count(*) FILTER (WHERE area_m2 IS NULL)   AS missing_area,
       count(*) FILTER (WHERE first_seen_at > now() - INTERVAL '1 day') AS new_today,
       round(avg(price_azn/NULLIF(area_m2,0))) AS avg_price_per_m2
FROM listings;
```

`avg_price_per_m2` is your canary. Baku apartments are roughly 1,200–3,000
AZN/m². If that number suddenly reads 45 or 1,900,000, your parsing broke —
probably a thousands separator or a rent listing leaking into the sale set.

**Guard against rent contamination:** `/kiraye/` URLs are rentals. If a
"185 000 AZN" apartment sits next to a "450 AZN" one, you scraped the wrong
category. Filter `WHERE price_azn > 15000` as a sanity floor.

---

## PART 9 — Etiquette, and Plan B if you get blocked

**Rules you follow:**
- `DOWNLOAD_DELAY` ≥ 2.5s, `CONCURRENT_REQUESTS` ≤ 2. Never remove these.
- Honest User-Agent with a real contact email.
- Run the big backfill at night (low traffic for them).
- On 429 or 403: stop, wait, reduce rate. Do not retry in a loop.
- Public listing data only. No phone numbers or seller personal data in your
  final dataset or your GitHub repo.

**Plan B — if bina.az blocks you properly:**
1. Reduce to one district, one room-count. A few hundred listings is enough
   to demonstrate an end-to-end pipeline.
2. Collect a sample manually or semi-manually and document it honestly.
3. Pivot the demo to a public housing dataset (Kaggle has several) and present
   bina.az as the intended production source.

None of these fail the capstone. What fails the capstone is having no data in
week 5 because you spent three weeks fighting a bot wall.

---

## PART 10 — Your day-by-day

| Day | Task | Done when |
|---|---|---|
| 1 | Env, Docker Postgres, schema loaded, repo pushed | `\dt` shows 5 tables; team can clone |
| 1 | Read bina.az ToS, note it in `docs/` | one paragraph written |
| 2 | Selector discovery, `sample.html` saved | selector table filled in |
| 2–3 | List spider working on 3 pages | `test.json` has real prices |
| 3 | Postgres pipeline + upsert | run twice → row count doesn't double |
| 4 | **Full backfill overnight** | ≥10,000 rows in `listings` |
| 4 | Districts extracted from sitemap → Aygul | CSV handed over |
| 5 | Health-check SQL + fix parsing bugs it exposes | avg price/m² is plausible |
| 5–6 | Detail spider on a 3,000 subset | descriptions populated |
| 6 | Daily refresh + cron + delisting logic | `delisted_at` starts filling |
| 7+ | Monitor daily; support Aygul's cleaning questions | scrape_runs shows daily entries |

---

## The two things that matter most

1. **Get ≥10,000 rows into Postgres by end of Day 4.** Everything downstream is
   blocked on this. If you're behind, cut the detail spider entirely — nobody
   fails a capstone for missing image features, but everyone fails for having
   no data.

2. **Never `INSERT` — always `UPSERT`, and always record `first_seen_at` /
   `delisted_at`.** Those timestamps cost you nothing today and are the only
   way Idrak can prove the bargain signal is real in week 5. You cannot add
   them retroactively.
