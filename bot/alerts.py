# - - - - - - - - - - - - - - - - - - - - - 
# NOTIFICATION TEXT STYLE!!!
# - - - - - - - - - - - - - - - - - - - - - 
def format_alert(listing: dict, bargain_score: float) -> str:
    return (
        f"🔥 Ucuz tapıldı!\n"
        f"{listing['rooms']} otaq, {listing['district']}\n"
        f"{listing['area']}m², {listing['price']:,} AZN\n"
        f"Bazar dəyərindən {bargain_score:.1f}% aşağı\n"
        f"{listing['url']}"
    )

if __name__ == "__main__":
    test_listing = {
        "rooms": 3,
        "district": "Nəsimi",
        "area": 65,
        "price": 85000,
        "url": "https://bina.az/items/12345"
    }
    print(format_alert(test_listing, 18.4))