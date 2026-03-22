import os
import time
import threading
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN")

last_used = {}

# ================== WEB SERVER (for Render) ==================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

# ================== FILE DELETE ==================
def delete_file_later(path, delay=65):
    def delete():
        if os.path.exists(path):
            try:
                os.remove(path)
            except:
                pass
    threading.Timer(delay, delete).start()

# ================== START COMMAND ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎵 *YouTube MP3 Bot*\n\n"
        "Convert YouTube videos to MP3 instantly.\n\n"
        "📌 Send any YouTube link\n"
        "⚡ Fast download\n"
        "🎧 High quality audio\n\n"
        "Just paste link and enjoy 🚀"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# ================== DOWNLOAD ==================
def download_mp3(url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': '%(id)s.%(ext)s',  # SAFE filename
        'ffmpeg_location': '/usr/bin/ffmpeg',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
        'socket_timeout': 120,
        'quiet': True,
        'noplaylist': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename.rsplit('.', 1)[0] + ".mp3"

# ================== HANDLE MESSAGE ==================
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    url = update.message.text.strip()

    # Rate limit
    if user_id in last_used and time.time() - last_used[user_id] < 10:
        await update.message.reply_text("Wait 10 sec ⏳")
        return

    last_used[user_id] = time.time()

    # Validate URL
    if "youtube.com" not in url and "youtu.be" not in url:
        await update.message.reply_text("Send valid YouTube link")
        return

    try:
        msg = await update.message.reply_text("Downloading... ⏳")

        file_path = download_mp3(url)

        await msg.delete()

        with open(file_path, 'rb') as f:
            await update.message.reply_document(document=f)

        delete_file_later(file_path, 65)

    except Exception:
        await update.message.reply_text("Failed to download. Try another link.")

# ================== MAIN BOT ==================
def main():
    app = ApplicationBuilder()\
        .token(BOT_TOKEN)\
        .read_timeout(120)\
        .write_timeout(120)\
        .build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    print("Bot running...")
    app.run_polling()

# ================== START EVERYTHING ==================
if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    main()
