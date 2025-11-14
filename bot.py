import os
import time
import threading
import requests
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ============================
# SETTINGS
# ============================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8573740591:AAFcvHHLyp9S9JoQMM3Em6vPsXoG_ZB4Cd0")
ADMIN_ID = int(os.getenv("ADMIN_ID", "6430768414"))
allowed_users = {ADMIN_ID}

# ============================
# FLASK KEEP-ALIVE
# ============================
app = Flask("")

@app.route("/")
def home():
    return "Ares Premium Bot is running 🥂"

@app.route("/favicon.ico")
def favicon():
    return "", 204  # Prevent 404

def keep_alive():
    t = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000))))
    t.start()

# ============================
# HELPERS
# ============================
def is_allowed(user_id):
    return user_id in allowed_users or user_id == ADMIN_ID

async def send_long_message(update: Update, text: str):
    limit = 4000
    if len(text) <= limit:
        await update.message.reply_text(text)
        return
    for i in range(0, len(text), limit):
        await update.message.reply_text(text[i:i+limit])

# ============================
# COMMANDS
# ============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 **Welcome to Ares Premium Bot 🥂**\n\n"
        "Use /commands to see all features."
    )

async def commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📜 **Ares Premium Bot Commands**\n\n"
        "/start – Welcome message\n"
        "/commands – Show commands\n"
        "/lookup <number> – Phone lookup\n"
        "/adduser <id> – Add user (Admin only)\n"
        "/removeuser <id> – Remove user (Admin only)\n"
        "/users – Show allowed users\n"
        "/test – Test bot responsiveness\n"
    )
    await update.message.reply_text(msg)

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is running and responsive!")

# ============================
# LOOKUP
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
        for idx, item in enumerate(data.get("result", []), start=1):
            text += f"🔹 Record {idx}\n"
            for k, v in item.items():
                text += f"**{k}:** `{v}`\n"
            text += "━━━━━━━━\n"
        await send_long_message(update, text)
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
# BOT RUNNER
# ============================
def main():
    keep_alive()
    while True:
        try:
            app_telegram = ApplicationBuilder().token(BOT_TOKEN).build()

            # Add handlers
            app_telegram.add_handler(CommandHandler("start", start))
            app_telegram.add_handler(CommandHandler("commands", commands))
            app_telegram.add_handler(CommandHandler("lookup", lookup))
            app_telegram.add_handler(CommandHandler("adduser", add_user))
            app_telegram.add_handler(CommandHandler("removeuser", remove_user))
            app_telegram.add_handler(CommandHandler("users", list_users))
            app_telegram.add_handler(CommandHandler("test", test))

            print("✅ Bot Running...")
            app_telegram.run_polling()
        except Exception as e:
            print(f"❌ Bot crashed: {e}")
            print("⏳ Restarting in 5 seconds...")
            time.sleep(5)

if __name__ == "__main__":
    main()
