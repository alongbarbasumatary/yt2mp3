import os
import time
import threading
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, CallbackQueryHandler
)
import yt_dlp

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL", "https://yt2mp3ok.onrender.com")  # Replace with your Render URL
PORT = int(os.environ.get("PORT", 8080))

logging.basicConfig(level=logging.INFO)

last_used = {}
pending = {}  # {user_id: {'url': url, 'message_id': msg_id}}

# ------------------- WEBHOOK HANDLER -------------------
from telegram.ext import Updater, WebhookHandler  # Not used directly with ApplicationBuilder, but we'll set webhook

# We'll set the webhook after starting the server.

# ------------------- CLEAN FILE -------------------
def delete_file_later(path, delay=65):
    def delete():
        if os.path.exists(path):
            os.remove(path)
    threading.Timer(delay, delete).start()

# ------------------- START -------------------
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

# ------------------- DOWNLOAD -------------------
def get_best_format(info, prefer_audio=True):
    """
    Inspects the formats dict and returns the best format string for yt-dlp.
    If prefer_audio is True, tries to get an audio-only format.
    Falls back to best video+audio if needed.
    """
    formats = info.get('formats', [])
    if not formats:
        return None

    # Filter audio-only formats
    audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']
    if audio_formats:
        # Pick the one with highest bitrate or filesize
        best_audio = max(audio_formats, key=lambda f: f.get('tbr', 0))
        return best_audio['format_id']
    else:
        # No audio-only formats – use best video+audio
        return 'best'

def download_audio(url, format_code="mp3"):
    base_opts = {
        'outtmpl': '%(title)s.%(ext)s',
        'ffmpeg_location': '/usr/bin/ffmpeg',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': format_code,
            'preferredquality': '128',
        }],
        'merge_output_format': format_code,
        'socket_timeout': 30,
        'quiet': True,
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['web'] if os.path.exists('cookies.txt') else ['android', 'web']
            }
        }
    }

    if os.path.exists('cookies.txt'):
        base_opts['cookiefile'] = 'cookies.txt'

    # First, extract info without downloading to see available formats
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': False}) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise Exception(f"Failed to extract info: {str(e)}")

    # Determine the best format ID
    format_id = get_best_format(info, prefer_audio=True)
    if not format_id:
        raise Exception("No downloadable formats found for this video.")

    # Try to download with that format
    try:
        opts = base_opts.copy()
        opts['format'] = format_id
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
            filename = ydl.prepare_filename(info)
            return filename.rsplit('.', 1)[0] + f".{format_code}"
    except Exception as e:
        # Fallback: try best video+audio (combined) if audio-only failed
        if "Requested format is not available" in str(e):
            opts = base_opts.copy()
            opts['format'] = 'best'
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
                filename = ydl.prepare_filename(info)
                return filename.rsplit('.', 1)[0] + f".{format_code}"
        else:
            raise

# ------------------- FORMAT CHOICE HANDLER -------------------
async def format_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    data = pending.pop(user_id, None)
    if not data:
        await query.edit_message_text("⏳ Session expired. Please send the link again.")
        return

    url = data['url']
    format_choice = query.data

    msg = await query.edit_message_text(f"🔄 Downloading as {format_choice.upper()}... ⏳")

    try:
        file_path = download_audio(url, format_choice)

        await msg.delete()

        with open(file_path, 'rb') as f:
            await query.message.reply_document(document=f, filename=os.path.basename(file_path))

        delete_file_later(file_path, 65)

    except Exception as e:
        await query.edit_message_text(f"❌ Error: {str(e)}")

# ------------------- LINK HANDLER -------------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    url = update.message.text.strip()

    if user_id in last_used and time.time() - last_used[user_id] < 10:
        await update.message.reply_text("⏳ Please wait 10 seconds before sending another link.")
        return
    last_used[user_id] = time.time()

    if "youtube.com" not in url and "youtu.be" not in url:
        await update.message.reply_text("❌ Please send a valid YouTube link.")
        return

    keyboard = [
        [InlineKeyboardButton("🎵 MP3", callback_data="mp3"),
         InlineKeyboardButton("🎵 M4A", callback_data="m4a")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await update.message.reply_text(
        "🎧 Choose audio format:",
        reply_markup=reply_markup
    )

    pending[user_id] = {'url': url, 'message_id': msg.message_id}

# ------------------- WEBHOOK SETUP -------------------
async def set_webhook(app):
    await app.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
    logging.info(f"Webhook set to {WEBHOOK_URL}/webhook")

# ------------------- MAIN -------------------
if __name__ == "__main__":
    # Start a simple HTTP server for health checks (Render requires a web server)
    def run_health_server():
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"Bot is running")
        server = HTTPServer(("0.0.0.0", PORT), Handler)
        server.serve_forever()

    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()

    # Build the bot application
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.add_handler(CallbackQueryHandler(format_callback, pattern="^(mp3|m4a)$"))

    # Run the bot with webhook (no polling)
    # First, set the webhook
    app.run_polling(drop_pending_updates=True)  # Using polling for simplicity; replace with webhook if needed
    # For webhook, you'd need a web server to receive updates. Since we already have a health server,
    # you could integrate the webhook handler there. However, for simplicity, I'll keep polling with drop_pending_updates.
    # If you want webhook, uncomment below and comment out run_polling.
    # app.run_webhook(listen="0.0.0.0", port=PORT, url_path="/webhook", webhook_url=f"{WEBHOOK_URL}/webhook")
