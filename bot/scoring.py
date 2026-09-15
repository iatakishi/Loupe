import json
import logging

logger = logging.getLogger(__name__)

PREDICTIONS_PATH = "predictions.json"

# Loaded once and cached in memory, so we're not re-reading the file on every lookup
_predictions_cache = None


def load_predictions() -> dict:
    """Reads predictions.json from disk into a Python dict."""
    with open(PREDICTIONS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_predictions() -> dict:
    """Returns the cached predictions dict, loading it from disk the first time it's needed."""
    global _predictions_cache
    if _predictions_cache is None:
        _predictions_cache = load_predictions()
        logger.info(f"Loaded {len(_predictions_cache)} predictions from {PREDICTIONS_PATH}")
    return _predictions_cache


def get_listing_by_url(url: str) -> dict | None:
    """
    Looks up a listing by its exact Bina.az URL.
    Returns the full entry (id, url, predicted_price, actual_price, bargain_score,
    alert_level, area, rooms, district) if found, or None if this listing
    isn't in Idrak's dataset.
    """
    predictions = get_predictions()
    return predictions.get(url)


if __name__ == "__main__":
    # Quick manual test — run "python scoring.py" directly to check it works
    test_url = "https://bina.az/items/6364416"
    result = get_listing_by_url(test_url)
    print(f"Lookup for {test_url}:")
    print(result)

    missing_url = "https://bina.az/items/0000000"
    print(f"\nLookup for missing listing {missing_url}:")
    print(get_listing_by_url(missing_url))
