import os
import time
import threading
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

BOT_TOKEN = os.getenv("BOT_TOKEN")

last_used = {}


def delete_file_later(path, delay=65):
    def delete():
        if os.path.exists(path):
            os.remove(path)
    threading.Timer(delay, delete).start()


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


def download_mp3(url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': '%(title)s.%(ext)s',
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


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    url = update.message.text.strip()

    # ✅ 3 sec cooldown
    if user_id in last_used and time.time() - last_used[user_id] < 3:
        await update.message.reply_text("Wait 3 sec ⏳")
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

        delete_file_later(file_path, 65)

    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")


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


if __name__ == "__main__":
    main()
