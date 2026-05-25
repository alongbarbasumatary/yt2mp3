# 🎬 YouTube Downloader Bot — Render Docker Deploy

## Files
```
app.py            ← bot code (env-var config, health-check server)
Dockerfile        ← Python 3.11-slim + ffmpeg
requirements.txt  ← pinned deps
render.yaml       ← one-click deploy config
.dockerignore     ← keeps image clean
```

---

## 🚀 Deploy Steps

### 1. Push to GitHub
```bash
git init
git add .
git commit -m "yt-dlp bot"
git remote add origin https://github.com/YOU/yt-bot.git
git push -u origin main
```

### 2. Create service on Render
- Go to https://dashboard.render.com → **New → Web Service**
- Connect your GitHub repo
- Render auto-detects the `Dockerfile` ✅
- Set **Service Type** → **Web Service** (not background worker)

### 3. Set Environment Variables (in Render dashboard → Environment tab)

| Key | Value |
|-----|-------|
| `BOT_TOKEN` | Your BotFather token |
| `API_ID` | Your Telegram API ID (my.telegram.org) |
| `API_HASH` | Your Telegram API Hash |
| `MY_CHAT_ID` | Your personal chat ID (from @userinfobot) |

> 💡 `SESSION_DIR` and `DOWNLOAD_DIR` are already set in `render.yaml`.

### 4. Add Persistent Disk (important! ⚠️)
- In Render dashboard → **Disks** tab → **Add Disk**
  - Name: `bot-data`
  - Mount Path: `/app/session`
  - Size: 1 GB
- This keeps your Telethon session alive across deploys!
  Without it the bot re-authenticates on every deploy.

### 5. Deploy & Check Logs
- Click **Deploy** — build takes ~2-3 min
- Watch logs for: `✅ Telethon client ready` and `🤖 Bot is running!`

---

## ⚠️ First-time Telethon session

Since the bot uses `bot_token=BOT_TOKEN` with Telethon (not a user account),
**no phone number prompt is needed**. The `.session` file is created automatically
on first run and persists on the disk mount. ✅

---

## 🔁 Render Free-tier Note

Free web services spin down after 15 minutes of inactivity.
The health-check endpoint (`GET /`) keeps the service alive as long as
Render's own health checks ping it. For 24/7 uptime use **Starter** plan ($7/mo).
