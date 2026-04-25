# YT → MP3 Bot

A self-hosted YouTube to MP3 downloader web service, ready to deploy on Render.

## Files

| File | Purpose |
|---|---|
| `app.py` | Flask app + frontend UI |
| `requirements.txt` | Python dependencies |
| `build.sh` | Installs ffmpeg + pip deps on Render |
| `render.yaml` | Render deploy config |

## Deploy to Render (Free Tier)

1. Push this folder to a **GitHub repo**.
2. Go to [render.com](https://render.com) → **New → Web Service**.
3. Connect your GitHub repo.
4. Set:
   - **Build Command:** `./build.sh`
   - **Start Command:** `python app.py`
   - **Environment:** Python 3
5. Click **Deploy**. Done!

> The `render.yaml` handles all config automatically if you use "New → Blueprint".

## How It Works

- User pastes a YouTube URL → hits **GRAB**
- Backend starts a background thread with `yt-dlp`
- Frontend polls `/api/status/<job_id>` every 1.5s
- When ready, **DOWNLOAD MP3** button appears
- Files auto-delete after 10 minutes

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/start` | `{"url": "..."}` → `{"job_id": "..."}` |
| GET | `/api/status/<id>` | Returns status + progress % |
| GET | `/api/download/<id>` | Streams the MP3 file |

## Notes

- Render free tier spins down after inactivity — first request may be slow (~30s).
- `/tmp/downloads` is used for temporary storage (ephemeral on Render).
- For personal use only. Respect YouTube's Terms of Service and copyright law.
