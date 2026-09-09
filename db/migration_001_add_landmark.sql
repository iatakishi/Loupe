-- Migration 001 — add landmark column
--
-- bina.az location entries come in four flavours, distinguished by a suffix
-- on fullName:  " r." rayon, " m." metro, " q." settlement, and no suffix for
-- nişangah (landmark: Zoopark, Port Baku, Sea Breeze, shopping centres...).
--
-- We were storing only district and metro_station, and storing them wrongly.
-- Landmarks are worth keeping: "near Port Baku" is a real price signal that
-- district alone does not capture.
--
-- Run once against an existing database:
--   Get-Content db/migration_001_add_landmark.sql | docker exec -i bina-pg psql -U binauser -d bina

ALTER TABLE listings ADD COLUMN IF NOT EXISTS landmark TEXT;

CREATE INDEX IF NOT EXISTS idx_listings_district_settlement
    ON listings (district, settlement);
CREATE INDEX IF NOT EXISTS idx_listings_metro
    ON listings (metro_station);

-- buildingTypeName is null on 100% of listings; building_type is now derived
-- from category.slug in the loader. No schema change needed, just noting it.
