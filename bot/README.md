# Loupee Bot — Telegram Alert System

Part of the **Bina.az Real-Time Bargain Finder** capstone project (Holberton School ML).
This repository covers the **MLOps / Backend (Alert & Demo)** role: the Telegram bot that notifies users when a cheaper-than-market-value apartment listing is found.

## What this bot does

The bot periodically checks a list of apartment listings, estimates whether each one is priced significantly below its expected market value, and automatically pushes a Telegram alert to every subscribed user when a bargain is found — with no user action required beyond subscribing once.

**Current status:** this is a fully working end-to-end demo running on **mock data and a mock scoring model**. It is built so that the mock pieces (listings + scoring) can be swapped for the real scraper and the real ML model without changing the bot logic itself.

## How it works (pipeline)

```
mock_listings.py  --->  scoring.py  --->  alerts.py  --->  bot.py (Telegram)
   (fake data)        (fake model)      (message text)     (sends + schedules)
```

1. **`mock_listings.py`** provides a static list of apartment listings, standing in for Eyyub's real scraper output.
2. **`scoring.py`** estimates a "predicted market price" for each listing and computes a **Bargain Score**, standing in for Idrak's real CatBoost model.
3. **`alerts.py`** formats a listing + score into a readable Telegram message.
4. **`bot.py`** ties it together: runs the Telegram bot, tracks subscribers, and automatically checks listings on a timer, sending alerts to everyone subscribed.

## Bargain Score logic

```
bargain_score = (predicted_price - actual_price) / predicted_price * 100
```

| Score          | Alert level      |
|----------------|------------------|
| >= 15%         | `very_cheap`     |
| 10% – 15%      | `below_market`   |
| < 10%          | `none` (no alert)|

## Files

| File | Purpose | Replaced by (later) |
|---|---|---|
| `bot.py` | Telegram bot: commands, subscriber tracking, scheduled alert loop | — (stays as-is) |
| `scoring.py` | Mock model: fakes a predicted price per listing | Idrak's real CatBoost model |
| `mock_listings.py` | Static fake listings | Eyyub's real scraped data feed |
| `alerts.py` | Formats alert messages | — (stays as-is) |
| `.env` | Stores the Telegram bot token (not committed to git) | — |
| `requirements.txt` | Python dependencies | — |

## Setup

1. **Get a bot token** from [@BotFather](https://t.me/BotFather) on Telegram (`/newbot`).
2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   ```
3. **Activate it:**
   - Windows: `venv\Scripts\activate.bat`
   - Mac/Linux: `source venv/bin/activate`
4. **Install dependencies:**
   ```bash
   pip install "python-telegram-bot[job-queue]" python-dotenv
   ```
5. **Create a `.env` file** in the project root:
   ```
   TELEGRAM_BOT_TOKEN=your_token_here
   ```

## Running the bot

```bash
python bot.py
```

You should see `Bot is running...` in the terminal. In Telegram:
- Send `/start` to subscribe to alerts.
- Send `/stop` to unsubscribe.
- Wait — the bot automatically checks listings every 30 seconds and pushes an alert whenever a bargain is found. No command is needed to receive alerts.

## Integration contract (for the rest of the team)

### `score_listing(listing: dict) -> dict`

**Input** — a listing must be a dict with these keys:
```python
{
    "rooms": int,
    "district": str,
    "area": float,       # square meters
    "price": float,      # AZN
    "url": str           # unique identifier for the listing
}
```

**Output** — must return a dict with these keys:
```python
{
    "predicted_price": float,
    "bargain_score": float,
    "alert_level": str   # one of: "very_cheap", "below_market", "none"
}
```

Idrak's real model can replace the entire body of `score_listing()` in `scoring.py` as long as this input/output shape is preserved — `bot.py` requires no changes.

### Listings feed

`bot.py` currently imports a static `MOCK_LISTINGS` list from `mock_listings.py`. Once Eyyub's scraper is ready, `check_for_bargains()` in `bot.py` should instead read from wherever the scraper writes data (database table, API, or file) — as long as each listing follows the schema above.

## Known limitations (mock-data stage)

- **In-memory state:** `subscribed_chat_ids` and `already_alerted_urls` reset every time the bot restarts. In production this should be persisted (e.g. a database) so the bot doesn't lose subscribers or re-send old alerts after a restart.
- **Static listings:** `MOCK_LISTINGS` never changes, so after all bargains in the list have been alerted once, no further alerts will fire until the bot restarts or new listings are added.
- **Deterministic mock scoring:** `scoring.py` seeds its randomness by listing URL so results are consistent across checks (not re-randomized every 30 seconds) — this mimics real model behavior but is not an actual prediction.

## Next steps

- Swap `scoring.py`'s internals for Idrak's trained CatBoost model.
- Swap `mock_listings.py` for Eyyub's live scraper output.
- Persist subscriber list and alerted-listings history to a database.
