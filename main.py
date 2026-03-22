import os
import time
import threading
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

BOT_TOKEN = os.getenv("BOT_TOKEN")

app_flask = Flask(__name__)

last_used = {}


# ✅ Dummy route (Render needs this)
@app_flask.route('/')
def home():
    return "Bot is running 🚀"


def delete_file_later(path, delay=65):
    def delete():
        if os.path.exists(path):
            os.remove(path)
    threading.Timer(delay, delete).start()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎵 *YouTube MP3 Bot*\n\n"
        "Send YouTube link to get MP3 🎧"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


def download_mp3(url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': '%(title).50s.%(ext)s',  # limit filename
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
        'quiet': True,
        'noplaylist': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename.rsplit('.', 1)[0] + ".mp3"


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    url = update.message.text.strip()

    if user_id in last_used and time.time() - last_used[user_id] < 10:
        await update.message.reply_text("Wait 10 sec ⏳")
        return

    last_used[user_id] = time.time()

    if "youtube.com" not in url and "youtu.be" not in url:
        await update.message.reply_text("Send valid YouTube link")
        return

    try:
        msg = await update.message.reply_text("Downloading... ⏳")

        file_path = download_mp3(url)

        await msg.delete()

        with open(file_path, 'rb') as f:
            await update.message.reply_document(document=f)

        delete_file_later(file_path)

    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")


def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    # run bot in thread (important for Render)
    threading.Thread(target=run_bot).start()

    # run web server (Render requirement)
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host="0.0.0.0", port=port)
