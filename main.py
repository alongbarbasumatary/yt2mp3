import os
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

BOT_TOKEN = os.getenv("BOT_TOKEN")

last_used = {}


# ---------------- HTTP SERVER ----------------
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is running")


def run_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"🌐 Server running on port {port}")
    server.serve_forever()


# ---------------- FILE CLEANUP ----------------
def delete_file_later(path, delay=65):
    def delete():
        if os.path.exists(path):
            os.remove(path)
    threading.Timer(delay, delete).start()


# ---------------- START COMMAND ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎵 *YouTube MP3 Bot*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📥 Send any YouTube link\n"
        "⚡ Fast processing\n"
        "🎧 High-quality MP3 output\n"
        "🚀 Smooth & reliable download\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 Just paste your link below and get audio instantly!"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ---------------- DOWNLOAD ----------------
def download_mp3(url):
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'outtmpl': '%(title)s.%(ext)s',
        'ffmpeg_location': '/usr/bin/ffmpeg',
        'cookiefile': 'cookies.txt',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
        'socket_timeout': 30,
        'quiet': True,
        'noplaylist': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename.rsplit('.', 1)[0] + ".mp3"


# ---------------- MESSAGE HANDLER ----------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    url = update.message.text.strip()

    # cooldown
    if user_id in last_used and time.time() - last_used[user_id] < 10:
        await update.message.reply_text("⏳ Wait 10 sec")
        return

    last_used[user_id] = time.time()

    # validate link
    if "youtube.com" not in url and "youtu.be" not in url:
        await update.message.reply_text("❌ Invalid YouTube link")
        return

    try:
        msg = await update.message.reply_text("Downloading... ⏳")

        file_path = download_mp3(url)

        await msg.delete()

        with open(file_path, 'rb') as f:
            await update.message.reply_document(document=f)

        delete_file_later(file_path, 65)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")


# ---------------- MAIN ----------------
if __name__ == "__main__":
    # start web server for Render
    threading.Thread(target=run_server, daemon=True).start()

    # start bot
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    print("🤖 Bot running...")
    app.run_polling()
