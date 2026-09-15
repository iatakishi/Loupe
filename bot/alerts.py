def format_alert(listing: dict) -> str:
    """
    Takes a listing dict (as returned by scoring.get_listing_by_url) and
    formats it into the analysis message the user sees.
    """
    bargain_score = listing["bargain_score"]

    if bargain_score >= 15:
        verdict = f"🔥 Nəticə: Bu mənzil bazar dəyərindən {bargain_score:.1f}% aşağıdır! (Ucuz tapıldı, diqqət yetirin)"
    elif bargain_score >= 10:
        verdict = f"⚡ Nəticə: Bu mənzil bazar dəyərindən {bargain_score:.1f}% aşağıdır."
    elif bargain_score > 0:
        verdict = f"ℹ️ Nəticə: Bu mənzil bazar dəyərinə yaxındır ({bargain_score:.1f}% aşağı)."
    else:
        verdict = f"ℹ️ Nəticə: Bu mənzil bazar dəyərindən {abs(bargain_score):.1f}% yuxarıdır."

    return (
        f"🏠 Mənzil Təhlili Nəticəsi\n"
        f"📍 Rayon: {listing['district']}\n"
        f"📐 Sahə: {listing['area']}m², {listing['rooms']} otaq\n"
        f"💰 Elan qiyməti: {listing['actual_price']:,} AZN\n"
        f"🤖 Model proqnozu: {listing['predicted_price']:,.0f} AZN\n\n"
        f"{verdict}"
    )


if __name__ == "__main__":
    test_listing = {
        "id": 6364416,
        "url": "https://bina.az/items/6364416",
        "predicted_price": 417841,
        "actual_price": 390000,
        "bargain_score": 6.7,
        "alert_level": "none",
        "area": 135.0,
        "rooms": 3,
        "district": "nizami-metrosu"
    }
    print(format_alert(test_listing))
