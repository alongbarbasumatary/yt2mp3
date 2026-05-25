#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════╗
║   YouTube Downloader Bot - RENDER DOCKER EDITION ║
║   Telegram Bot API + Telethon MTProto            ║
║   Auto-send to personal chat after download      ║
║   No file size limit | Real-time progress        ║
╚══════════════════════════════════════════════════╝
"""

import os
import re
import asyncio
import time
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, MessageHandler,
                           CallbackQueryHandler, ContextTypes, filters)
import yt_dlp
from telethon import TelegramClient

# ─── CONFIG (from environment variables) ─────────────────────────
BOT_TOKEN     = os.environ["BOT_TOKEN"]
API_ID        = int(os.environ["API_ID"])
API_HASH      = os.environ["API_HASH"]
MY_CHAT_ID_S  = os.environ.get("MY_CHAT_ID", "")
MY_CHAT_ID    = int(MY_CHAT_ID_S) if MY_CHAT_ID_S.strip() else None

# On Render with a Disk mounted at /app/session, the session file persists.
# Fall back to /app if no separate session dir.
SESSION_DIR  = Path(os.environ.get("SESSION_DIR", "/app/session"))
SESSION_DIR.mkdir(parents=True, exist_ok=True)
SESSION      = str(SESSION_DIR / "ytdl_bot_session")

DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR", "/app/downloads"))
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

PORT = int(os.environ.get("PORT", 10000))

# ─── LOGGING ─────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler()]   # stdout only — Render captures it
)
log = logging.getLogger(__name__)

# ─── HEALTH-CHECK SERVER (required by Render web service) ────────
class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *args):
        pass   # silence access logs

def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), _HealthHandler)
    log.info(f"✅ Health-check server listening on port {PORT}")
    server.serve_forever()

# ─── TELETHON CLIENT ─────────────────────────────────────────────
tg_client = TelegramClient(SESSION, API_ID, API_HASH)

# ─── UTILS ───────────────────────────────────────────────────────
def is_youtube_url(url: str) -> bool:
    patterns = [
        r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/",
        r"(https?://)?(www\.)?youtube\.com/shorts/",
    ]
    return any(re.search(p, url) for p in patterns)

def human_size(b: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"

def human_time(s: int) -> str:
    if s < 60:   return f"{s}s"
    if s < 3600: return f"{s//60}m {s%60}s"
    return f"{s//3600}h {(s%3600)//60}m"

def progress_bar(pct: float, width=20) -> str:
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct:.1f}%"

# ─── VIDEO INFO ──────────────────────────────────────────────────
def get_video_info(url: str) -> dict:
    ydl_opts = {"quiet": True, "no_warnings": True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info

def get_formats(info: dict) -> list:
    formats = []
    seen = set()
    for f in info.get("formats", []):
        ext    = f.get("ext", "?")
        vcodec = f.get("vcodec", "none")
        height = f.get("height")
        fsize  = f.get("filesize") or f.get("filesize_approx") or 0
        fid    = f.get("format_id")

        if vcodec != "none" and height:
            label = f"🎬 {height}p {ext.upper()}"
            if height not in seen:
                seen.add(height)
                formats.append({
                    "id": fid, "label": label,
                    "type": "video", "size": fsize,
                    "height": height, "ext": ext
                })

    videos = sorted([f for f in formats if f["type"] == "video"],
                    key=lambda x: x.get("height", 0), reverse=True)

    mp3_320 = {
        "id": "bestaudio/best",
        "label": "🎵 Audio 320kbps MP3",
        "type": "audio_mp3",
        "size": 0,
        "ext": "mp3"
    }
    return videos[:5] + [mp3_320]

# ─── DOWNLOAD ────────────────────────────────────────────────────
async def download_media(url: str, fmt_id: str,
                          status_msg, chat_id: int,
                          context: ContextTypes.DEFAULT_TYPE,
                          is_mp3: bool = False) -> Path:
    last_edit = [0]
    loop = asyncio.get_event_loop()

    def progress_hook(d):
        if d["status"] != "downloading":
            return
        now = time.time()
        if now - last_edit[0] < 3:
            return
        last_edit[0] = now

        raw_pct = d.get("_percent_str", "0%").strip().replace("%", "")
        try:
            pct = float(raw_pct)
        except ValueError:
            pct = 0.0

        speed = d.get("_speed_str", "?").strip()
        eta   = d.get("_eta_str", "?").strip()
        down  = human_size(d.get("downloaded_bytes", 0))
        total = human_size(d.get("total_bytes") or
                           d.get("total_bytes_estimate") or 0)

        text = (
            f"⬇️ *Downloading...*\n"
            f"`{progress_bar(pct)}`\n"
            f"📦 {down} / {total}\n"
            f"⚡ {speed}  ⏱ ETA: {eta}"
        )

        async def _edit():
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_msg.message_id,
                    text=text,
                    parse_mode="Markdown"
                )
            except Exception:
                pass

        asyncio.run_coroutine_threadsafe(_edit(), loop)

    out_tmpl = str(DOWNLOAD_DIR / "%(title)s.%(ext)s")

    if is_mp3:
        ydl_opts = {
            "format": fmt_id,
            "outtmpl": out_tmpl,
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            }],
        }
    else:
        ydl_opts = {
            "format": fmt_id,
            "outtmpl": out_tmpl,
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
            "merge_output_format": "mp4",
            "postprocessors": [
                {
                    "key": "FFmpegVideoConvertor",
                    "preferedformat": "mp4"
                }
            ],
        }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info     = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        p = Path(filename)
        if not p.exists():
            p = p.with_suffix(".mp4")
        return p

# ─── UPLOAD VIA TELETHON (no size limit) ─────────────────────────
async def upload_via_telethon(chat_id: int, filepath: Path,
                               caption: str, status_msg,
                               context: ContextTypes.DEFAULT_TYPE,
                               is_video: bool = True):
    last_edit = [0]
    start_time = time.time()

    async def upload_progress(current, total):
        now = time.time()
        if now - last_edit[0] < 3:
            return
        last_edit[0] = now
        pct   = current / total * 100 if total else 0
        speed = current / (now - start_time + 0.001)
        eta   = int((total - current) / (speed + 0.001))
        text  = (
            f"📤 *Uploading to Telegram...*\n"
            f"`{progress_bar(pct)}`\n"
            f"📦 {human_size(current)} / {human_size(total)}\n"
            f"⚡ {human_size(int(speed))}/s  ⏱ ETA: {human_time(eta)}"
        )
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg.message_id,
                text=text,
                parse_mode="Markdown"
            )
        except Exception:
            pass

    await tg_client.send_file(
        chat_id,
        str(filepath),
        caption=caption,
        supports_streaming=is_video,
        progress_callback=upload_progress,
    )

# ─── SEND FILE HELPER ────────────────────────────────────────────
async def send_file_to_chat(chat_id: int, filepath: Path,
                             caption: str, status_msg,
                             context: ContextTypes.DEFAULT_TYPE,
                             is_video: bool = True,
                             show_progress: bool = True):
    fsize = filepath.stat().st_size

    if fsize > 45 * 1024 * 1024:
        if show_progress:
            await upload_via_telethon(
                chat_id, filepath, caption,
                status_msg, context, is_video
            )
        else:
            await tg_client.send_file(
                chat_id,
                str(filepath),
                caption=caption,
                supports_streaming=is_video,
            )
    else:
        with open(filepath, "rb") as f:
            if is_video:
                await context.bot.send_video(
                    chat_id, f,
                    caption=caption,
                    parse_mode="Markdown",
                    supports_streaming=True
                )
            else:
                await context.bot.send_audio(
                    chat_id, f,
                    caption=caption,
                    parse_mode="Markdown"
                )

# ─── BOT HANDLERS ────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎬 *YouTube Downloader Bot*\n\n"
        "Send me any YouTube link!\n\n"
        "✅ No file size limit\n"
        "✅ Video + Audio formats\n"
        "✅ Real-time progress bar\n"
        "✅ Auto-saves to your chat\n"
        "✅ Supports Shorts & Music\n\n"
        "Just paste a YouTube URL 👇"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *How to use:*\n\n"
        "1. Send a YouTube URL\n"
        "2. Choose video quality or audio\n"
        "3. Wait for download + upload\n"
        "4. File is sent to you automatically!\n\n"
        "📌 *Supported:*\n"
        "• YouTube videos\n"
        "• YouTube Shorts\n"
        "• YouTube Music\n\n"
        "💡 Large files (1GB+) supported!"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not is_youtube_url(url):
        await update.message.reply_text(
            "❌ Please send a valid YouTube URL."
        )
        return

    msg = await update.message.reply_text(
        "🔍 *Fetching video info...*", parse_mode="Markdown"
    )
    try:
        info = await asyncio.get_event_loop().run_in_executor(
            None, get_video_info, url
        )
    except Exception as e:
        await msg.edit_text(f"❌ Error:\n`{e}`", parse_mode="Markdown")
        return

    title    = info.get("title", "Unknown")
    duration = human_time(info.get("duration", 0))
    channel  = info.get("uploader", "Unknown")
    views    = f"{info.get('view_count', 0):,}"
    thumb    = info.get("thumbnail", "")

    formats = get_formats(info)
    if not formats:
        await msg.edit_text("❌ No downloadable formats found.")
        return

    context.user_data["url"]     = url
    context.user_data["formats"] = formats
    context.user_data["title"]   = title
    context.user_data["channel"] = channel

    keyboard = []
    for i, f in enumerate(formats):
        sz  = f" ({human_size(f['size'])})" if f["size"] else ""
        btn = InlineKeyboardButton(
            f"{f['label']}{sz}", callback_data=f"dl_{i}"
        )
        keyboard.append([btn])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])

    caption = (
        f"🎬 *{title}*\n"
        f"👤 {channel}  |  ⏱ {duration}  |  👁 {views} views\n\n"
        "Choose format:"
    )

    await msg.delete()
    try:
        if thumb:
            await update.message.reply_photo(
                photo=thumb,
                caption=caption,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
    except Exception:
        pass

    await update.message.reply_text(
        caption,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.message.delete()
        return

    if not query.data.startswith("dl_"):
        return

    idx     = int(query.data.split("_")[1])
    formats = context.user_data.get("formats", [])
    url     = context.user_data.get("url")
    title   = context.user_data.get("title", "video")
    channel = context.user_data.get("channel", "Unknown")
    chat_id = query.message.chat_id
    user    = query.from_user

    if idx >= len(formats):
        await query.message.reply_text("❌ Invalid format.")
        return

    chosen  = formats[idx]
    is_vid  = chosen["type"] == "video"
    is_mp3  = chosen["type"] == "audio_mp3"
    label   = chosen["label"]
    fmt_id  = f"{chosen['id']}+bestaudio/bestaudio" if is_vid else chosen["id"]

    await query.message.delete()
    status_msg = await context.bot.send_message(
        chat_id,
        f"⬇️ *Starting download...*\n🎬 {title}\n📺 Format: {label}",
        parse_mode="Markdown"
    )

    filepath = None
    try:
        filepath = await download_media(
            url, fmt_id, status_msg, chat_id, context, is_mp3=is_mp3
        )
        if is_mp3:
            mp3_path = filepath.with_suffix(".mp3")
            if mp3_path.exists():
                filepath = mp3_path
        fsize = filepath.stat().st_size

        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=(
                f"📤 *Preparing upload...*\n"
                f"📦 Size: {human_size(fsize)}\n"
                f"{'🎬 Video' if is_vid else '🎵 Audio'}: {title}"
            ),
            parse_mode="Markdown"
        )

        caption_out = (
            f"{'🎬' if is_vid else '🎵'} *{title}*\n"
            f"👤 {channel}\n"
            f"📦 {human_size(fsize)}  |  📺 {label}"
        )

        await send_file_to_chat(
            chat_id, filepath, caption_out,
            status_msg, context, is_vid and not is_mp3,
            show_progress=True
        )

        try:
            await status_msg.delete()
        except Exception:
            pass

        await context.bot.send_message(
            chat_id,
            f"✅ *Download complete!*\n"
            f"🎬 {title}\n"
            f"📦 {human_size(fsize)}",
            parse_mode="Markdown"
        )

        if MY_CHAT_ID and chat_id != MY_CHAT_ID:
            try:
                notify_caption = (
                    f"📥 *New download from bot!*\n\n"
                    f"{'🎬' if is_vid else '🎵'} *{title}*\n"
                    f"👤 Channel: {channel}\n"
                    f"📺 Format: {label}\n"
                    f"📦 Size: {human_size(fsize)}\n"
                    f"🙍 Requested by: {user.full_name} "
                    f"(`{user.id}`)"
                )
                notify_msg = await context.bot.send_message(
                    MY_CHAT_ID,
                    f"📨 *Sending file to your chat...*\n🎬 {title}",
                    parse_mode="Markdown"
                )
                await send_file_to_chat(
                    MY_CHAT_ID, filepath, notify_caption,
                    notify_msg, context, is_vid,
                    show_progress=False
                )
                try:
                    await notify_msg.delete()
                except Exception:
                    pass
                log.info(f"Auto-forwarded to MY_CHAT_ID: {MY_CHAT_ID}")
            except Exception as e:
                log.warning(f"Failed to send to MY_CHAT_ID: {e}")

        elif MY_CHAT_ID and chat_id == MY_CHAT_ID:
            log.info("Requester is MY_CHAT_ID — no duplicate send needed.")

    except Exception as e:
        log.exception("Download/upload error")
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg.message_id,
                text=f"❌ *Failed!*\n`{e}`",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    finally:
        if filepath and filepath.exists():
            try:
                filepath.unlink()
                log.info(f"Cleaned up: {filepath.name}")
            except Exception:
                pass

# ─── MAIN ────────────────────────────────────────────────────────
async def run():
    await tg_client.start(bot_token=BOT_TOKEN)
    log.info("✅ Telethon client ready")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CallbackQueryHandler(handle_callback))

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    log.info("🤖 Bot is running!")

    if MY_CHAT_ID:
        try:
            await app.bot.send_message(
                MY_CHAT_ID,
                "🟢 *YouTube Bot is now online!*\nReady to download.",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        log.info("Shutting down...")
        if MY_CHAT_ID:
            try:
                await app.bot.send_message(
                    MY_CHAT_ID,
                    "🔴 *YouTube Bot is offline.*",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await tg_client.disconnect()


if __name__ == "__main__":
    # Start health-check HTTP server in background thread
    t = threading.Thread(target=start_health_server, daemon=True)
    t.start()

    asyncio.run(run())
