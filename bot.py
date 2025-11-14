import os
import time
import threading
import requests
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ============================
# BOT SETTINGS
# ============================
BOT_TOKEN = os.getenv("BOT_TOKEN")  # From Render environment
ADMIN_ID = int(os.getenv("ADMIN_ID"))  # Your Telegram ID
allowed_users = {ADMIN_ID}

# ============================
# FLASK KEEP-ALIVE
# ============================
app = Flask("")

@app.route("/")
def home():
    return "Ares Premium Bot is running 🥂"

def keep_alive():
    t = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000))))
    t.start()

# ============================
# ACCESS CHECK
# ============================
def is_allowed(user_id):
    return user_id in allowed_users or user_id == ADMIN_ID

# ============================
# START COMMAND
# ============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **Welcome to Ares Premium Bot 🥂**\n\n"
        "Use /commands to see all features."
    )

# ============================
# COMMAND LIST
# ============================
async def commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📜 **Ares Premium Bot Commands**\n\n"
        "/start – Welcome message\n"
        "/commands – Show command list\n"
        "/lookup <number> – Phone lookup\n"
        "/adduser <id> – Add user (Admin only)\n"
        "/removeuser <id> – Remove user (Admin only)\n"
        "/users – Show allowed users\n"
    )
    await update.message.reply_text(msg)

# ============================
# LOOKUP COMMAND
# ============================
async def lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not is_allowed(user_id):
        return await update.message.reply_text("⛔ You are not authorized.")

    if len(context.args) == 0:
        return await update.message.reply_text("❗ Usage: `/lookup 9876543210`")

    number = context.args[0]
    url = f"https://veerulookup.onrender.com/search_phone?number={number}"

    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        text = "📞 **Lookup Result**\n\n"
        for item in data.get("result", []):
            for key, value in item.items():
                text += f"**{key}:** `{value}`\n"
        if len(text) > 4000:
            text = text[:3990] + "\n\n⚠️ Result trimmed."
        await update.message.reply_text(text)
    except Exception as e:
        await update.message.reply_text(f"❌ Lookup failed:\n`{e}`")

# ============================
# USER MANAGEMENT
# ============================
async def add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Only admin can add users.")
    if len(context.args) == 0:
        return await update.message.reply_text("❗ Usage: `/adduser 123456789`")
    try:
        uid = int(context.args[0])
        allowed_users.add(uid)
        await update.message.reply_text(f"✅ User `{uid}` added.")
    except:
        await update.message.reply_text("❌ Invalid user ID.")

async def remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Only admin can remove users.")
    if len(context.args) == 0:
        return await update.message.reply_text("❗ Usage: `/removeuser 123456789`")
    try:
        uid = int(context.args[0])
        allowed_users.discard(uid)
        await update.message.reply_text(f"🗑 User `{uid}` removed.")
    except:
        await update.message.reply_text("❌ Invalid user ID.")

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ Only admin allowed.")
    text = "👤 **Allowed Users:**\n\n"
    for u in allowed_users:
        text += f"- `{u}`\n"
    await update.message.reply_text(text)

# ============================
# BOT RUNNER WITH AUTO-RECONNECT
# ============================
def main():
    keep_alive()  # Start Flask server for Render free Web Service
    while True:
        try:
            app_telegram = ApplicationBuilder().token(BOT_TOKEN).build()

            app_telegram.add_handler(CommandHandler("start", start))
            app_telegram.add_handler(CommandHandler("commands", commands))
            app_telegram.add_handler(CommandHandler("lookup", lookup))
            app_telegram.add_handler(CommandHandler("adduser", add_user))
            app_telegram.add_handler(CommandHandler("removeuser", remove_user))
            app_telegram.add_handler(CommandHandler("users", list_users))

            print("✅ Bot Running...")
            app_telegram.run_polling()
        except Exception as e:
            print(f"❌ Bot crashed: {e}")
            print("⏳ Restarting in 5 seconds...")
            time.sleep(5)

if __name__ == "__main__":
    main()
