# YT → MP3 Bot

## Fix: "Sign in to confirm you're not a bot"

The updated app.py already uses the **Android innertube client** which bypasses most bot checks automatically. If the error persists, add a cookies.txt file:

### Step 1 — Export cookies from your browser
1. Install **"Get cookies.txt LOCALLY"** Chrome/Firefox extension
2. Go to youtube.com — make sure you're **logged in**
3. Click the extension → **Export cookies for this tab**
4. Save as `cookies.txt`

### Step 2 — Add to Render (pick one)

**Option A: Secret File (recommended)**
- Render dashboard → your service → **Environment** → **Secret Files**
- Filename: `cookies.txt`
- Contents: paste your cookies.txt content
- Mount path: `/opt/render/project/src/cookies.txt`
- Redeploy ✓

**Option B: Commit to repo**
- Put `cookies.txt` in your repo root alongside `app.py`
- Add to `.gitignore` so it's not public
- Push & redeploy ✓

---

## Deploy

1. Push folder to GitHub
2. Render → New → Web Service → connect repo
3. Build Command: `./build.sh`
4. Start Command: `python app.py`
5. Deploy

## API

| Method | Path | Notes |
|---|---|---|
| POST | `/api/start` | `{"url":"..."}` → `{"job_id":"..."}` |
| GET | `/api/status/<id>` | progress polling |
| GET | `/api/download/<id>` | download MP3 |

Files auto-delete after 10 min. Personal use only.
