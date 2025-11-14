import os
import requests
from flask import Flask, request
from telegram import Bot, Update, ParseMode
from telegram.ext import Dispatcher, CommandHandler, CallbackContext

# ==========================
#  SETTINGS
# ==========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_URL = "https://veerulookup.onrender.com/search_phone?number="

OWNER_ID = 6430768414
ADMINS = [OWNER_ID]

bot = Bot(BOT_TOKEN)

app = Flask(__name__)

# Telegram dispatcher
dispatcher = Dispatcher(bot, None, workers=0)

# ==========================
#  ADMIN CHECK
# ==========================

def is_admin(user_id):
    return user_id in ADMINS

# ==========================
#  SAFE MESSAGE SENDER
# ==========================

def send_long(update, text):
    limit = 4000
    for i in range(0, len(text), limit):
        bot.send_message(chat_id=update.message.chat_id, text=text[i:i+limit], parse_mode=ParseMode.MARKDOWN)

# ==========================
#  COMMAND: /start
# ==========================

def start(update: Update, context: CallbackContext):
    user = update.message.from_user.first_name
    bot.send_message(
        chat_id=update.message.chat_id,
        text=f"✨ *Welcome to Ares Premium Bot 🥂*\n\nHello *{user}*!\nUse */command* to see all features.",
        parse_mode=ParseMode.MARKDOWN
    )

# ==========================
#  COMMAND: /command
# ==========================

def command(update: Update, context: CallbackContext):
    text = (
        "📜 *Ares Premium Bot – Commands*\n"
        "━━━━━━━━━━━━━━\n"
        "🔍 `/lookup <number>` – Phone Lookup\n"
        "➕ `/add <user_id>` – Add admin\n"
        "➖ `/remove <user_id>` – Remove admin\n"
        "👑 `/admins` – Show admin list\n"
        "ℹ️ `/command` – Show this menu\n"
        "━━━━━━━━━━━━━━"
    )
    bot.send_message(chat_id=update.message.chat_id, text=text, parse_mode=ParseMode.MARKDOWN)

# ==========================
#  ADMIN FUNCTIONS
# ==========================

def add_admin(update: Update, context: CallbackContext):
    if update.message.from_user.id != OWNER_ID:
        bot.send_message(update.message.chat_id, "❌ Only the owner can add admins.")
        return

    if len(context.args) == 0:
        bot.send_message(update.message.chat_id, "Usage: /add <user_id>")
        return

    new_id = int(context.args[0])
    ADMINS.append(new_id)
    bot.send_message(update.message.chat_id, f"✅ Added admin: `{new_id}`", parse_mode=ParseMode.MARKDOWN)

def remove_admin(update: Update, context: CallbackContext):
    if update.message.from_user.id != OWNER_ID:
        bot.send_message(update.message.chat_id, "❌ Only owner can remove admins.")
        return

    if len(context.args) == 0:
        bot.send_message(update.message.chat_id, "Usage: /remove <user_id>")
        return

    remove_id = int(context.args[0])

    if remove_id == OWNER_ID:
        bot.send_message(update.message.chat_id, "❌ Cannot remove owner.")
        return

    if remove_id in ADMINS:
        ADMINS.remove(remove_id)
        bot.send_message(update.message.chat_id, f"🗑 Removed admin: `{remove_id}`", parse_mode=ParseMode.MARKDOWN)
    else:
        bot.send_message(update.message.chat_id, "❌ User is not admin.")

def admin_list(update: Update, context: CallbackContext):
    if not is_admin(update.message.from_user.id):
        bot.send_message(update.message.chat_id, "❌ Access denied.")
        return

    text = "👑 *Admin List:*\n━━━━━━━━━━\n"
    for a in ADMINS:
        text += f"• `{a}`\n"
    text += "━━━━━━━━━━"

    bot.send_message(update.message.chat_id, text, parse_mode=ParseMode.MARKDOWN)

# ==========================
#  LOOKUP
# ==========================

def lookup(update: Update, context: CallbackContext):
    if not is_admin(update.message.from_user.id):
        bot.send_message(update.message.chat_id, "❌ Access denied.")
        return

    if len(context.args) == 0:
        bot.send_message(update.message.chat_id, "Usage: /lookup 919876543210")
        return

    number = context.args[0]
    bot.send_message(update.message.chat_id, "⏳ Fetching premium data...")

    try:
        r = requests.get(API_URL + number)
        data = r.json()

        msg = "📱 *Ares Premium Lookup*\n━━━━━━━━━━\n"

        for idx, item in enumerate(data["result"], start=1):
            msg += f"🔷 *Record {idx}*\n"
            msg += f"👤 Name: `{item['name']}`\n"
            msg += f"📞 Mobile: `{item['mobile']}`\n"
            msg += f"📍 Circle: `{item['circle']}`\n"
            msg += f"👨 Father: `{item['father_name']}`\n"
            msg += f"🏠 Address: `{item['address']}`\n"
            msg += f"🆔 ID: `{item['id_number']}`\n"
            msg += "━━━━━━━━━━\n"

        send_long(update, msg)

    except Exception as e:
        bot.send_message(update.message.chat_id, f"❌ Error: {e}")

# ==========================
#  ADD HANDLERS
# ==========================

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("command", command))
dispatcher.add_handler(CommandHandler("lookup", lookup))
dispatcher.add_handler(CommandHandler("add", add_admin))
dispatcher.add_handler(CommandHandler("remove", remove_admin))
dispatcher.add_handler(CommandHandler("admins", admin_list))

# ==========================
#  FLASK WEBHOOK
# ==========================

@app.route("/", methods=["GET"])
def home():
    return "Ares Bot Running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.json, bot)
    dispatcher.process_update(update)
    return "ok"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
