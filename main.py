import os
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)
import yt_dlp

BOT_TOKEN = os.getenv("BOT_TOKEN")

last_used = {}
pending = {}  # {user_id: {'url': url, 'message_id': msg_id}}


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
        "🎵 *YouTube Audio Bot*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📥 Send any YouTube link\n"
        "⚡ Fast processing\n"
        "🎧 Choose your preferred format\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 Paste your link below"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ---------------- DOWNLOAD ----------------
def download_audio(url, format_code="mp3"):
    """
    Download audio from YouTube.
    format_code: 'mp3' or 'm4a'
    """
    base_opts = {
        'outtmpl': '%(title)s.%(ext)s',
        'ffmpeg_location': '/usr/bin/ffmpeg',   # adjust if needed
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': format_code,      # 'mp3' or 'm4a'
            'preferredquality': '128',
        }],
        'merge_output_format': format_code,
        'socket_timeout': 30,
        'quiet': True,
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web']
            }
        }
    }

    if os.path.exists('cookies.txt'):
        base_opts['cookiefile'] = 'cookies.txt'

    # First try: audio-only (fast)
    try:
        opts = base_opts.copy()
        opts['format'] = 'bestaudio/best'
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename.rsplit('.', 1)[0] + f".{format_code}"
    except Exception as e:
        # If audio-only fails, fall back to video+audio then extract
        if "Requested format is not available" in str(e):
            opts = base_opts.copy()
            opts['format'] = 'best'   # video+audio combined
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                return filename.rsplit('.', 1)[0] + f".{format_code}"
        else:
            raise


# ---------------- FORMAT CHOICE HANDLER ----------------
async def format_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()  # remove the "loading" state

    # Retrieve pending data
    data = pending.pop(user_id, None)
    if not data:
        await query.edit_message_text("⏳ Session expired. Please send the link again.")
        return

    url = data['url']
    format_choice = query.data  # 'mp3' or 'm4a'

    # Send a temporary "downloading" message
    msg = await query.edit_message_text(f"🔄 Downloading as {format_choice.upper()}... ⏳")

    try:
        file_path = download_audio(url, format_choice)

        await msg.delete()

        with open(file_path, 'rb') as f:
            await query.message.reply_document(document=f, filename=os.path.basename(file_path))

        delete_file_later(file_path, 65)

    except Exception as e:
        await query.edit_message_text(f"❌ Error: {str(e)}")


# ---------------- LINK HANDLER ----------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    url = update.message.text.strip()

    # Rate limit
    if user_id in last_used and time.time() - last_used[user_id] < 10:
        await update.message.reply_text("⏳ Please wait 10 seconds before sending another link.")
        return
    last_used[user_id] = time.time()

    if "youtube.com" not in url and "youtu.be" not in url:
        await update.message.reply_text("❌ Please send a valid YouTube link.")
        return

    # Show format choice buttons
    keyboard = [
        [InlineKeyboardButton("🎵 MP3", callback_data="mp3"),
         InlineKeyboardButton("🎵 M4A", callback_data="m4a")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await update.message.reply_text(
        "🎧 Choose audio format:",
        reply_markup=reply_markup
    )

    # Store pending for this user
    pending[user_id] = {'url': url, 'message_id': msg.message_id}


# ---------------- MAIN ----------------
if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.add_handler(CallbackQueryHandler(format_callback, pattern="^(mp3|m4a)$"))

    print("🤖 Bot running...")
    app.run_polling()
