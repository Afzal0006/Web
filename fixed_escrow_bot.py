
# CLEANED & FIXED VERSION

import os
import re
import random
import pytz
import io
from datetime import datetime, timedelta
from dotenv import load_dotenv
from pymongo import MongoClient

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputFile, ChatPermissions
)
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    CallbackQueryHandler, MessageHandler, filters
)

# ==== ENV ====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
OWNER_IDS = [int(x) for x in os.getenv("OWNER_IDS", "").split(",") if x.strip().isdigit()]

if not BOT_TOKEN or not MONGO_URI or not LOG_CHANNEL_ID or not OWNER_IDS:
    raise ValueError("❌ Missing config in .env")

print("✅ Config Loaded")

# ==== DB ====
client = MongoClient(MONGO_URI)
db = client["escrow_bot"]
groups_col = db["groups"]
admins_col = db["admins"]

# ==== TIMEZONE ====
IST = pytz.timezone("Asia/Kolkata")

# ==== HELPERS ====
async def is_admin(update: Update) -> bool:
    user_id = update.effective_user.id
    if user_id in OWNER_IDS:
        return True
    return admins_col.find_one({"user_id": user_id}) is not None

def init_group(chat_id):
    if not groups_col.find_one({"_id": chat_id}):
        groups_col.insert_one({
            "_id": chat_id,
            "deals": {},
            "total_fee": 0
        })

def extract_username(user):
    return f"@{user.username}" if user.username else user.full_name

# ==== START ====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is alive")

# ==== ADD DEAL ====
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    if not update.message.reply_to_message:
        return await update.message.reply_text("Reply to deal msg")

    if not context.args:
        return await update.message.reply_text("/add 50")

    amount = float(context.args[0])
    chat_id = str(update.effective_chat.id)
    reply_id = str(update.message.reply_to_message.message_id)

    init_group(chat_id)

    g = groups_col.find_one({"_id": chat_id}) or {}
    deals = g.get("deals", {})

    trade_id = f"TID{random.randint(100000,999999)}"

    deals[reply_id] = {
        "trade_id": trade_id,
        "amount": amount,
        "completed": False
    }

    groups_col.update_one({"_id": chat_id}, {"$set": {"deals": deals}})

    await update.message.reply_text(f"✅ Deal Added #{trade_id}")

# ==== RELEASE ====
async def release(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update):
        return

    if not update.message.reply_to_message:
        return

    chat_id = str(update.effective_chat.id)
    reply_id = str(update.message.reply_to_message.message_id)

    g = groups_col.find_one({"_id": chat_id})
    if not g or "deals" not in g:
        return await update.message.reply_text("No deals")

    deal = g["deals"].get(reply_id)
    if not deal:
        return await update.message.reply_text("Deal not found")

    deal["completed"] = True
    g["deals"][reply_id] = deal

    groups_col.update_one({"_id": chat_id}, {"$set": {"deals": g["deals"]}})

    await update.message.reply_text(f"✅ Completed #{deal['trade_id']}")

# ==== STATUS ====
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("/status TID123")

    tid = context.args[0]

    for g in groups_col.find({}):
        for d in g.get("deals", {}).values():
            if d.get("trade_id") == tid:
                return await update.message.reply_text(f"Status: {'Done' if d['completed'] else 'Pending'}")

    await update.message.reply_text("Not found")

# ==== MAIN ====
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("release", release))
    app.add_handler(CommandHandler("status", status))

    print("🚀 Bot Running")
    app.run_polling()

if __name__ == "__main__":
    main()
