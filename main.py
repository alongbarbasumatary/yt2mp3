import os
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

BOT_TOKEN = os.getenv("BOT_TOKEN")

last_used = {}


# ---------------- WEB SERVER ----------------
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is running")


def run_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()


# ---------------- CLEAN FILE ----------------
def delete_file_later(path, delay=65):
    def delete():
        if os.path.exists(path):
            os.remove(path)
    threading.Timer(delay, delete).start()


# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎵 *YouTube MP3 Bot*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📥 Send any YouTube link\n"
        "⚡ Fast processing\n"
        "🎧 High-quality MP3 output\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 Paste your link below"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ---------------- DOWNLOAD ----------------
def download_mp3(url):
    # Basic options – works for all YouTube videos
    ydl_opts = {
        'format': 'bestaudio/best',               # pick the best audio regardless of container
        'outtmpl': '%(title)s.%(ext)s',
        'ffmpeg_location': '/usr/bin/ffmpeg',    # adjust if your ffmpeg is elsewhere
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
        'merge_output_format': 'mp3',
        'socket_timeout': 30,
        'quiet': True,
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']   # helps avoid age restrictions
            }
        }
    }

    # Only add cookiefile if it exists – otherwise yt-dlp may complain
    if os.path.exists('cookies.txt'):
        ydl_opts['cookiefile'] = 'cookies.txt'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename.rsplit('.', 1)[0] + ".mp3"
    except Exception:
        # Fallback: try without any extra filters (rarely needed)
        ydl_opts['format'] = 'bestaudio/best'   # already same, but keep the structure
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename.rsplit('.', 1)[0] + ".mp3"


# ---------------- HANDLER ----------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    url = update.message.text.strip()

    if user_id in last_used and time.time() - last_used[user_id] < 10:
        await update.message.reply_text("⏳ Wait 10 sec")
        return

    last_used[user_id] = time.time()

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
    threading.Thread(target=run_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    print("🤖 Bot running...")
    app.run_polling()
