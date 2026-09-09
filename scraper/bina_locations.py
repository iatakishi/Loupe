#!/usr/bin/env python3
"""
bina.az location parsing — single source of truth.

WHY THIS EXISTS
---------------
bina.az returns all location entries as the same `Location` shape, and encodes
the TYPE in a suffix on `fullName`:

    "Nəsimi r."      -> rayon / district
    "Gənclik m."     -> metro station
    "Şüvəlan q."     -> qəsəbə / settlement
    "Zoopark"        -> nişangah / landmark   (no suffix)
    {__typename: City, name: "Xırdalan"}      -> city

The `location` field is NOT the district — it is whichever location the seller
picked as primary, which is often the metro. Taking nearestLocations[0] and
calling it "metro" is how "Xırdalan" (a city) ended up in metro_station.

`path` also encodes hierarchy, which lets us recover the rayon when no " r."
entry is present:
    /baki/nesimi            -> 2 parts: city + rayon-or-metro
    /baki/xezer/suvelan     -> 3 parts: city + rayon + settlement
"""

# The 12 administrative rayons of Baku, by URL slug.
# Used to recover the district from a path when no " r." entry exists,
# and to validate what we parsed.
BAKU_DISTRICT_SLUGS = {
    "abseron":   "Abşeron",
    "bineqedi":  "Binəqədi",
    "qaradag":   "Qaradağ",
    "xetai":     "Xətai",
    "xezer":     "Xəzər",
    "nerimanov": "Nərimanov",
    "nesimi":    "Nəsimi",
    "nizami":    "Nizami",
    "pirallahi": "Pirallahı",
    "sabuncu":   "Sabunçu",
    "sebail":    "Səbail",
    "suraxani":  "Suraxanı",
    "yasamal":   "Yasamal",
}

# Baku metro stations, for validating the " m." parse.
# If something parses as a metro but isn't in here, it's suspicious.
BAKU_METRO_STATIONS = {
    "20 Yanvar", "28 May", "8 Noyabr", "Avtovağzal", "Azadlıq Prospekti",
    "Bakmil", "Dərnəgül", "Elmlər Akademiyası", "Əhmədli", "Gənclik",
    "Həzi Aslanov", "Xalqlar Dostluğu", "Xocəsən", "İçəri Şəhər",
    "İnşaatçılar", "Koroğlu", "Qara Qarayev", "Memar Əcəmi", "Neftçilər",
    "Nəriman Nərimanov", "Nəsimi", "Nizami", "Sahil", "Şah İsmayıl Xətai",
    "Ulduz",
}

SUFFIX_MAP = {
    " r.": "district",
    " m.": "metro_station",
    " q.": "settlement",
}


def _classify(full_name):
    """
    'Nəsimi r.' -> ('district', 'Nəsimi')
    'Zoopark'   -> ('landmark', 'Zoopark')
    """
    name = (full_name or "").strip()
    if not name:
        return None, None
    for suffix, kind in SUFFIX_MAP.items():
        if name.endswith(suffix):
            return kind, name[: -len(suffix)].strip()
    return "landmark", name


def _district_from_path(path):
    """'/baki/xezer/suvelan' -> 'Xəzər'  (3+ segments means middle is the rayon)"""
    parts = [p for p in (path or "").split("/") if p]
    if len(parts) >= 3 and parts[1] in BAKU_DISTRICT_SLUGS:
        return BAKU_DISTRICT_SLUGS[parts[1]]
    return None


def parse_locations(raw):
    """
    Take a raw currentItemData dict, return normalised location fields.

    Returns:
        {city, district, settlement, metro_station, landmark,
         metro_count, is_metro_valid}
    """
    out = {
        "city": None,
        "district": None,
        "settlement": None,
        "metro_station": None,
        "landmark": None,
        "metro_count": 0,
        "is_metro_valid": None,
    }
    if not isinstance(raw, dict):
        return out

    # --- city -------------------------------------------------------
    city = raw.get("city")
    if isinstance(city, dict):
        out["city"] = city.get("name")
    elif isinstance(city, str):
        out["city"] = city

    # --- gather every location-ish entry ----------------------------
    entries = []
    loc = raw.get("location")
    if isinstance(loc, dict):
        entries.append(loc)
    for n in (raw.get("nearestLocations") or []):
        if isinstance(n, dict):
            entries.append(n)

    landmarks = []
    metros = []

    for e in entries:
        if e.get("__typename") == "City":
            out["city"] = out["city"] or e.get("name")
            continue

        kind, clean = _classify(e.get("fullName") or e.get("name"))
        if not clean:
            continue

        if kind == "metro_station":
            metros.append(clean)
        elif kind == "landmark":
            if clean not in landmarks:
                landmarks.append(clean)
        elif out[kind] is None:
            out[kind] = clean

    # --- district fallback via path hierarchy ------------------------
    if out["district"] is None:
        for e in entries:
            d = _district_from_path(e.get("path"))
            if d:
                out["district"] = d
                break

    # --- metro: keep the first, but record how many were nearby ------
    out["metro_count"] = len(metros)
    if metros:
        out["metro_station"] = metros[0]
        out["is_metro_valid"] = metros[0] in BAKU_METRO_STATIONS

    out["landmark"] = landmarks[0] if landmarks else None
    return out


def building_type_from_category(category_slug):
    """
    buildingTypeName is null on every listing, but category.slug carries it:
        'menziller/yeni-tikili'  -> 'yeni tikili'
        'menziller/kohne-tikili' -> 'kohne tikili'
    """
    slug = (category_slug or "").lower()
    if "yeni-tikili" in slug:
        return "yeni tikili"
    if "kohne-tikili" in slug:
        return "kohne tikili"
    return None
