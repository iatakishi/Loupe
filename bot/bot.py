import os
import re
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

from scoring import get_listing_by_url
from alerts import format_alert
from storage import init_db, add_subscriber, get_all_subscribers

# Configure logging: what gets recorded, and where
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Silence noisy third-party libraries that log full request URLs (including your token)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Make sure the database file and tables exist before the bot starts handling anything
init_db()

# Matches a Bina.az listing URL and captures the numeric id, e.g.
# "https://bina.az/items/6364416" -> "6364416"
BINA_URL_PATTERN = re.compile(r"bina\.az/items/(\d+)")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    add_subscriber(update.effective_chat.id)
    logger.info(f"New/returning user: {update.effective_chat.id}")
    await update.message.reply_text(
        "Salam! Mənə bəyəndiyin Bina.az elanının linkini göndər, "
        "mən süni intellekt ilə onun real bazar dəyərini hesablayıb deyim. 🏠"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users = len(get_all_subscribers())
    await update.message.reply_text(f"📊 Botdan istifadə edən ümumi istifadəçi sayı: {total_users}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    # Count this user even if they never sent /start — any real interaction counts
    add_subscriber(chat_id)

    try:
        match = BINA_URL_PATTERN.search(text)
        if not match:
            await update.message.reply_text(
                "Zəhmət olmasa düzgün Bina.az elan linki göndərin.\n"
                "Məsələn: https://bina.az/items/6364416"
            )
            return

        listing_id = match.group(1)
        url = f"https://bina.az/items/{listing_id}"

        await update.message.reply_text("⏳ Təhlil edilir...")

        listing = get_listing_by_url(url)

        if listing is None:
            logger.info(f"Lookup miss for {url} (user {chat_id})")
            await update.message.reply_text(
                "Bu elan hazırkı bazamızda tapılmadı. "
                "Hazırda yalnız mövcud dataset-dəki elanları yoxlaya bilirik."
            )
            return

        message = format_alert(listing)
        await update.message.reply_text(message)
        logger.info(f"Lookup success for {url} (user {chat_id}), bargain_score={listing['bargain_score']}")

    except Exception as e:
        # Covers network hiccups, Telegram API errors, or a blocked/deleted chat —
        # this one user's request fails gracefully instead of failing silently,
        # and every other user is completely unaffected.
        logger.warning(f"Failed to handle message from {chat_id}: {e}")


app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

logger.info("Bot is running...")
app.run_polling()