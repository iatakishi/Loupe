# - - - - - - - - - - - - - - - - - - - - - 
# SCRAPED DATA WILL LIVE HEREEE!
# - - - - - - - - - - - - - - - - - - - - - 
MOCK_LISTINGS = [
    {
        "rooms": 3,
        "district": "Nəsimi",
        "area": 65,
        "price": 85000,
        "url": "https://bina.az/items/12345"
    },
    {
        "rooms": 2,
        "district": "Yasamal",
        "area": 50,
        "price": 78000,
        "url": "https://bina.az/items/23456"
    },
    {
        "rooms": 4,
        "district": "Səbail",
        "area": 110,
        "price": 195000,
        "url": "https://bina.az/items/34567"
    },
    {
        "rooms": 1,
        "district": "Xətai",
        "area": 40,
        "price": 60000,
        "url": "https://bina.az/items/45678"
    },
    {
        "rooms": 3,
        "district": "Nəsimi",
        "area": 65,
        "price": 70000,
        "url": "https://bina.az/items/56789"
    },
]

if __name__ == "__main__":
    from scoring import score_listing
    for listing in MOCK_LISTINGS:
        result = score_listing(listing)
        print(listing["district"], listing["area"], "->", result)