# - - - - - - - - - - - - - - - - - - - - - 
# THE FILE IN WHICH THE BOT IS RUNNING!!
# - - - - - - - - - - - - - - - - - - - - - 
import os
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from scoring import score_listing
from alerts import format_alert
from mock_listings import MOCK_LISTINGS

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

subscribed_chat_ids = set()
already_alerted_urls = set()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subscribed_chat_ids.add(update.effective_chat.id)
    await update.message.reply_text("Salam, Loupee ucuz mənzil tapmaq üçün xidmətinizdədir!🏠")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subscribed_chat_ids.discard(update.effective_chat.id)
    await update.message.reply_text("Sizi siyahıdan çıxardım. İstədiyiniz zaman /start yazıb yenidən qoşula bilərsiniz.")

async def check_for_bargains(context: ContextTypes.DEFAULT_TYPE):
    if not subscribed_chat_ids:
        return

    for listing in MOCK_LISTINGS:
        if listing["url"] in already_alerted_urls:
            continue

        result = score_listing(listing)
        if result["alert_level"] != "none":
            message = format_alert(listing, result["bargain_score"])
            for chat_id in subscribed_chat_ids.copy():
                try:
                    await context.bot.send_message(chat_id=chat_id, text=message)
                except Exception as e:
                    print(f"Failed to send to {chat_id}, removing them: {e}")
                    subscribed_chat_ids.discard(chat_id)
            already_alerted_urls.add(listing["url"])

app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("stop", stop))
app.job_queue.run_repeating(check_for_bargains, interval=30, first=5)

print("Bot is running...")
app.run_polling()