import os
import re
import threading
import tempfile
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set!")

YOUTUBE_REGEX = re.compile(
    r"(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[\w\-]+"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 *YouTube MP3 Bot*\n\n"
        "Send me any YouTube link and I'll send you the MP3!\n\n"
        "Just paste the URL and I'll handle the rest.",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *How to use:*\n\n"
        "1. Copy a YouTube video URL\n"
        "2. Paste it here\n"
        "3. Wait for your MP3 file\n\n"
        "Supports: youtube.com and youtu.be links",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if not YOUTUBE_REGEX.search(text):
        await update.message.reply_text(
            "❌ That doesn't look like a YouTube link.\n\nSend me a YouTube URL like:\n`https://youtube.com/watch?v=...`",
            parse_mode="Markdown"
        )
        return

    status_msg = await update.message.reply_text("⏳ Downloading... please wait.")

    def do_download():
        with tempfile.TemporaryDirectory() as tmpdir:
            output_template = os.path.join(tmpdir, "%(title)s.%(ext)s")
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": output_template,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(text, download=True)
                    title = info.get("title", "audio")
                    duration = info.get("duration", 0)

                    # Telegram bots can only send files up to 50MB
                    if duration and duration > 3600:
                        context.application.create_task(
                            status_msg.edit_text("❌ Video is too long (max 1 hour).")
                        )
                        return

                    # Find the downloaded mp3
                    mp3_file = None
                    for f in os.listdir(tmpdir):
                        if f.endswith(".mp3"):
                            mp3_file = os.path.join(tmpdir, f)
                            break

                    if not mp3_file:
                        context.application.create_task(
                            status_msg.edit_text("❌ Conversion failed. Try another video.")
                        )
                        return

                    file_size = os.path.getsize(mp3_file)
                    if file_size > 50 * 1024 * 1024:
                        context.application.create_task(
                            status_msg.edit_text("❌ File too large for Telegram (max 50MB).")
                        )
                        return

                    context.application.create_task(
                        status_msg.edit_text("📤 Uploading to Telegram...")
                    )

                    safe_title = re.sub(r'[\\/*?:"<>|]', "", title)[:60]

                    async def send_audio():
                        with open(mp3_file, "rb") as f:
                            await update.message.reply_audio(
                                audio=f,
                                title=safe_title,
                                filename=f"{safe_title}.mp3",
                            )
                        await status_msg.delete()

                    context.application.create_task(send_audio())

            except Exception as e:
                logger.error(f"Download error: {e}")
                error_msg = str(e)
                if "Video unavailable" in error_msg:
                    msg = "❌ Video is unavailable or private."
                elif "age" in error_msg.lower():
                    msg = "❌ Age-restricted video — cannot download."
                else:
                    msg = f"❌ Error: {error_msg[:200]}"
                context.application.create_task(status_msg.edit_text(msg))

    thread = threading.Thread(target=do_download, daemon=True)
    thread.start()


def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
