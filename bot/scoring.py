# - - - - - - - - - - - - - - - - - - - - - 
# REAL MODEL WILL BE HEREEE!!
# - - - - - - - - - - - - - - - - - - - - - 
import random

DISTRICT_BASE_PRICE = {
    "Nəsimi": 1500,
    "Yasamal": 1400,
    "Xətai": 1300,
    "Səbail": 1800,
}
DEFAULT_BASE_PRICE = 1350

def score_listing(listing: dict) -> dict:
    base_price_per_sqm = DISTRICT_BASE_PRICE.get(listing["district"], DEFAULT_BASE_PRICE)

    # Seed a random generator using the listing's URL, so the "noise"
    # is always the same for this specific listing, every time it's scored.
    seeded_random = random.Random(listing["url"])
    noise = seeded_random.uniform(0.9, 1.1)

    predicted_price = base_price_per_sqm * listing["area"] * noise
    actual_price = listing["price"]
    bargain_score = (predicted_price - actual_price) / predicted_price * 100

    if bargain_score >= 15:
        alert_level = "very_cheap"
    elif bargain_score >= 10:
        alert_level = "below_market"
    else:
        alert_level = "none"

    return {
        "predicted_price": round(predicted_price, 2),
        "bargain_score": round(bargain_score, 2),
        "alert_level": alert_level
    }