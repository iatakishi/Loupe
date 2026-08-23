-- =====================================================================
-- Bina.az ML Bargain Finder — database schema v1
-- Holberton ML Capstone
--
-- This file is the CONTRACT between the four of us:
--   Eyyub  writes into `listings`, `listing_price_history`, `listing_images`
--   Aygul  reads `listings` for EDA and builds the feature matrix
--   Idrak  trains on the feature matrix, writes into `predictions`
--   Madina reads `predictions` where alert_class IS NOT NULL
--
-- RULE: nobody changes a column name without telling the others.
-- Change it here first, then in code.
-- =====================================================================

-- ---------------------------------------------------------------------
-- listings — current state of each listing, one row per listing
-- ---------------------------------------------------------------------
CREATE TABLE listings (
    -- identity ---------------------------------------------------------
    listing_id       BIGINT PRIMARY KEY,   -- Bina.az's own numeric ID from the URL.
                                           -- NEVER invent your own. Their ID is what
                                           -- makes re-scraping idempotent.
    url              TEXT NOT NULL,

    -- what kind of listing this is -----------------------------------------
    -- CRITICAL: bina.az has /alqi-satqi/ (sale) and /kiraye/ (rent) under the
    -- same card markup. A 450 AZN monthly rent and a 185,000 AZN sale look
    -- identical to a parser. If rentals leak into the training set the model
    -- is destroyed. Set this from the URL path, and always filter on it.
    deal_type        TEXT NOT NULL DEFAULT 'sale',  -- 'sale' (alqi-satqi) | 'rent' (kiraye)
    property_type    TEXT,                 -- 'menzil' | 'yeni-tikili' | 'heyet-evi' | ...
                                           -- keep only apartments for the model

    -- price ------------------------------------------------------------
    price_azn        NUMERIC(12,2),        -- total price in AZN. NULL if "razılaşma ilə".
                                           -- Store the NUMBER only, never "185 000 AZN".
    currency         TEXT DEFAULT 'AZN',   -- some listings are USD/EUR — do not silently
                                           -- treat them as AZN, it will poison the model.
    is_negotiable    BOOLEAN,              -- "razılaşma ilə" / price on request

    -- core physical attributes ------------------------------------------
    area_m2          NUMERIC(8,2),         -- total area. Watch for "sahə" vs "faktiki sahə".
    rooms            SMALLINT,             -- otaq sayı
    floor            SMALLINT,             -- mərtəbə (the unit's floor)
    total_floors     SMALLINT,             -- binanın mərtəbə sayı
    building_type    TEXT,                 -- 'yeni tikili' | 'kohne tikili' | NULL
                                           -- normalise to lowercase ASCII slugs, not raw text
    renovation       TEXT,                 -- 'temirli' | 'temirsiz' | NULL
    has_kupca        BOOLEAN,              -- çıxarış / kupça mövcuddur
    has_mortgage     BOOLEAN,              -- ipoteka mümkündür

    -- location -----------------------------------------------------------
    city             TEXT,                 -- 'Baku' for almost everything
    district         TEXT,                 -- rayon: 'Yasamal', 'Nasimi', ...
    settlement       TEXT,                 -- qəsəbə / mikrorayon, often NULL
    metro_station    TEXT,                 -- nearest metro as stated in the listing
    latitude         DOUBLE PRECISION,     -- often NULL. Do not fabricate.
    longitude        DOUBLE PRECISION,

    -- free text ------------------------------------------------------------
    title            TEXT,
    description      TEXT,                 -- raw, unmodified. Aygul's NLP flags come from this.

    -- seller ---------------------------------------------------------------
    seller_type      TEXT,                 -- 'owner' (mülkiyyətçi) | 'agent' (vasitəçi)
    seller_name      TEXT,
    seller_id        TEXT,                 -- if the site exposes one — needed for the
                                           -- realtor risk index later

    -- lifecycle — THIS IS THE PART THAT MAKES VALIDATION POSSIBLE ----------
    posted_at        TIMESTAMPTZ,          -- listing's own publish date if shown
    first_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),  -- when WE first scraped it
    last_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),  -- last daily scan that saw it alive
    delisted_at      TIMESTAMPTZ,          -- set when a daily scan no longer finds it
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,

    -- provenance -------------------------------------------------------------
    scrape_source    TEXT,                 -- 'backfill' | 'incremental'
    raw_json         JSONB                 -- the untouched parsed blob. Storage is cheap;
                                           -- re-scraping because you dropped a field is not.
);

-- NOTE ON price_per_m2: deliberately NOT a column here.
-- It is the model TARGET. If it lives in the table next to the features,
-- someone will eventually feed it to CatBoost and get 0.2% MAPE and think
-- they succeeded. Compute it at feature-build time, in Aygul's code, and
-- keep it out of the feature matrix.

CREATE INDEX idx_listings_deal_type   ON listings (deal_type, property_type, is_active);
CREATE INDEX idx_listings_active      ON listings (is_active, last_seen_at);
CREATE INDEX idx_listings_district    ON listings (district);
CREATE INDEX idx_listings_first_seen  ON listings (first_seen_at);
CREATE INDEX idx_listings_seller      ON listings (seller_id);

-- ---------------------------------------------------------------------
-- listing_price_history — append-only. One row per observed price change.
-- Sellers cutting price repeatedly is a strong signal, and this table is
-- also how you measure "did our flagged bargains sell faster?"
-- ---------------------------------------------------------------------
CREATE TABLE listing_price_history (
    id           BIGSERIAL PRIMARY KEY,
    listing_id   BIGINT NOT NULL REFERENCES listings(listing_id) ON DELETE CASCADE,
    price_azn    NUMERIC(12,2) NOT NULL,
    observed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_price_hist_listing ON listing_price_history (listing_id, observed_at);

-- ---------------------------------------------------------------------
-- listing_images — for duplicate detection
-- Store the perceptual hash, not the image bytes. phash is 64 bits and
-- gets you ~90% of duplicate detection for 5% of the ResNet effort.
-- ---------------------------------------------------------------------
CREATE TABLE listing_images (
    id            BIGSERIAL PRIMARY KEY,
    listing_id    BIGINT NOT NULL REFERENCES listings(listing_id) ON DELETE CASCADE,
    image_url     TEXT NOT NULL,
    position      SMALLINT,               -- order in the gallery; image 0 is the cover
    phash         BIT(64),                -- imagehash.phash() -> store as bitstring
    downloaded_at TIMESTAMPTZ
);

CREATE INDEX idx_images_listing ON listing_images (listing_id);
CREATE INDEX idx_images_phash   ON listing_images (phash);

-- ---------------------------------------------------------------------
-- predictions — Idrak writes, Madina reads
-- ---------------------------------------------------------------------
CREATE TABLE predictions (
    id                BIGSERIAL PRIMARY KEY,
    listing_id        BIGINT NOT NULL REFERENCES listings(listing_id) ON DELETE CASCADE,
    model_version     TEXT NOT NULL,      -- 'catboost_v3_2026_08_20'. Always version.
    y_pred_price_azn  NUMERIC(12,2) NOT NULL,
    y_actual_price_azn NUMERIC(12,2) NOT NULL,
    bargain_score     NUMERIC(6,2),       -- (y_pred - y_actual) / y_pred * 100
    alert_class       TEXT,               -- 'A' (>=15%) | 'B' (10-15%) | NULL
    fraud_status      TEXT,               -- 'clean' | 'quarantine' | 'duplicate'
    predicted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    alert_sent_at     TIMESTAMPTZ         -- Madina sets this. Prevents double-notifying.
);

CREATE INDEX idx_pred_pending ON predictions (alert_class, alert_sent_at)
    WHERE alert_class IS NOT NULL AND alert_sent_at IS NULL;

-- ---------------------------------------------------------------------
-- scrape_runs — monitoring. When the scraper silently breaks because
-- Bina.az changed their HTML, this table is how you find out.
-- ---------------------------------------------------------------------
CREATE TABLE scrape_runs (
    id                BIGSERIAL PRIMARY KEY,
    run_type          TEXT NOT NULL,      -- 'backfill' | 'incremental' | 'daily_refresh'
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at       TIMESTAMPTZ,
    pages_fetched     INTEGER DEFAULT 0,
    listings_new      INTEGER DEFAULT 0,
    listings_updated  INTEGER DEFAULT 0,
    errors            INTEGER DEFAULT 0,
    notes             TEXT
);

-- =====================================================================
-- UPSERT PATTERN — use this, not INSERT.
-- Re-scraping the same listing must be safe and must not duplicate rows.
-- =====================================================================
-- INSERT INTO listings (listing_id, url, price_azn, area_m2, ...)
-- VALUES (%s, %s, %s, %s, ...)
-- ON CONFLICT (listing_id) DO UPDATE SET
--     price_azn    = EXCLUDED.price_azn,
--     last_seen_at = now(),
--     is_active    = TRUE,
--     raw_json     = EXCLUDED.raw_json;

-- Then, only when the price actually changed:
-- INSERT INTO listing_price_history (listing_id, price_azn)
-- SELECT %s, %s
-- WHERE NOT EXISTS (
--     SELECT 1 FROM listing_price_history
--     WHERE listing_id = %s
--     ORDER BY observed_at DESC LIMIT 1
--     -- compare price here
-- );

-- After each daily full scan, mark everything you did not see as delisted:
-- UPDATE listings
-- SET is_active = FALSE, delisted_at = now()
-- WHERE is_active = TRUE AND last_seen_at < now() - INTERVAL '36 hours';
