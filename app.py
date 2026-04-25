import os
import re
import uuid
import threading
import time
from flask import Flask, request, jsonify, send_file, render_template_string
import yt_dlp

app = Flask(__name__)

DOWNLOAD_DIR = "/tmp/downloads"
COOKIES_FILE = "/opt/render/project/src/cookies.txt"  # optional cookies.txt
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

jobs = {}

def cleanup_file(path, delay=600):
    def _delete():
        time.sleep(delay)
        try:
            os.remove(path)
        except Exception:
            pass
    threading.Thread(target=_delete, daemon=True).start()

def build_ydl_opts(output_template, progress_hook):
    opts = {
        "format": "bestaudio/bestvideo/best",
        "outtmpl": output_template,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        },
        # Use Android + web innertube clients — bypasses bot check without cookies
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
            }
        },
        "retries": 5,
        "fragment_retries": 5,
        "ignoreerrors": False,
        "allow_unplayable_formats": False,
    }
    if os.path.exists(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE
    return opts

def download_mp3(job_id, url):
    output_template = os.path.join(DOWNLOAD_DIR, f"{job_id}.%(ext)s")

    def progress_hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                pct = int(downloaded / total * 90)
                jobs[job_id]["progress"] = pct
        elif d["status"] == "finished":
            jobs[job_id]["progress"] = 95

    try:
        ydl_opts = build_ydl_opts(output_template, progress_hook)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "audio")
            safe_title = re.sub(r'[\\/*?:"<>|]', "", title)[:80]
            mp3_path = os.path.join(DOWNLOAD_DIR, f"{job_id}.mp3")
            jobs[job_id].update({
                "status": "done",
                "progress": 100,
                "filename": mp3_path,
                "title": safe_title,
            })
            cleanup_file(mp3_path)
    except Exception as e:
        err = str(e)
        if "Sign in to confirm" in err or "bot" in err.lower():
            err = "YouTube bot-check triggered. Add a cookies.txt file — see README."
        jobs[job_id].update({"status": "error", "error": err})


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>YT → MP3</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Bebas+Neue&display=swap" rel="stylesheet">
<style>
  :root { --bg:#0a0a0a;--panel:#111;--accent:#ff4d00;--accent2:#ff9500;--text:#f0f0f0;--muted:#666;--border:#222; }
  * { box-sizing:border-box;margin:0;padding:0; }
  body { background:var(--bg);color:var(--text);font-family:'Space Mono',monospace;min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:24px;overflow-x:hidden; }
  body::before { content:'';position:fixed;inset:0;background:radial-gradient(ellipse 80% 60% at 50% -10%,#ff4d0015 0%,transparent 70%);pointer-events:none; }
  .logo { font-family:'Bebas Neue',sans-serif;font-size:clamp(48px,10vw,96px);letter-spacing:4px;background:linear-gradient(135deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;line-height:1;margin-bottom:6px; }
  .tagline { color:var(--muted);font-size:11px;letter-spacing:3px;text-transform:uppercase;margin-bottom:48px; }
  .card { background:var(--panel);border:1px solid var(--border);border-radius:4px;padding:32px;width:100%;max-width:560px;position:relative; }
  .card::before { content:'';position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--accent),var(--accent2),transparent); }
  label { display:block;font-size:10px;letter-spacing:2px;color:var(--muted);text-transform:uppercase;margin-bottom:10px; }
  .input-row { display:flex;gap:8px; }
  input[type="text"] { flex:1;background:#0a0a0a;border:1px solid var(--border);border-radius:3px;color:var(--text);font-family:'Space Mono',monospace;font-size:13px;padding:12px 14px;outline:none;transition:border-color 0.2s; }
  input[type="text"]:focus { border-color:var(--accent); }
  input[type="text"]::placeholder { color:#333; }
  button { background:var(--accent);border:none;border-radius:3px;color:#fff;cursor:pointer;font-family:'Bebas Neue',sans-serif;font-size:18px;letter-spacing:2px;padding:12px 22px;transition:background 0.2s,transform 0.1s;white-space:nowrap; }
  button:hover { background:#ff6a00; }
  button:active { transform:scale(0.97); }
  button:disabled { background:#333;color:#555;cursor:not-allowed;transform:none; }
  .status-box { margin-top:28px;display:none; }
  .status-box.visible { display:block; }
  .progress-track { background:#1a1a1a;border-radius:2px;height:4px;overflow:hidden;margin-bottom:14px; }
  .progress-bar { height:100%;width:0%;background:linear-gradient(90deg,var(--accent),var(--accent2));transition:width 0.4s ease;border-radius:2px; }
  .status-text { font-size:12px;color:var(--muted);letter-spacing:1px;line-height:1.6; }
  .status-text.error { color:#ff4d4d; }
  .dl-btn { margin-top:16px;width:100%;background:#1a1a1a;border:1px solid var(--accent);color:var(--accent);font-size:16px;display:none;padding:14px;transition:background 0.2s,color 0.2s; }
  .dl-btn:hover { background:var(--accent);color:#fff; }
  .dl-btn.visible { display:block; }
  .footer { margin-top:32px;font-size:10px;color:#333;letter-spacing:1px;text-align:center; }
  @keyframes pulse { 0%,100%{opacity:.4} 50%{opacity:1} }
  .pulsing { animation:pulse 1.2s infinite; }
</style>
</head>
<body>
<div class="logo">YT→MP3</div>
<p class="tagline">YouTube Audio Extractor</p>
<div class="card">
  <label for="urlInput">YouTube URL</label>
  <div class="input-row">
    <input type="text" id="urlInput" placeholder="https://youtube.com/watch?v=..." autocomplete="off"/>
    <button id="grabBtn" onclick="startDownload()">GRAB</button>
  </div>
  <div class="status-box" id="statusBox">
    <div class="progress-track"><div class="progress-bar" id="progressBar"></div></div>
    <div class="status-text" id="statusText">Starting...</div>
    <button class="dl-btn" id="downloadBtn">⬇ DOWNLOAD MP3</button>
  </div>
</div>
<div class="footer">FOR PERSONAL USE ONLY · RESPECT COPYRIGHT</div>
<script>
let pollInterval=null,currentJobId=null;
async function startDownload(){
  const url=document.getElementById('urlInput').value.trim();
  if(!url)return;
  clearInterval(pollInterval);
  document.getElementById('grabBtn').disabled=true;
  document.getElementById('downloadBtn').classList.remove('visible');
  document.getElementById('statusBox').classList.add('visible');
  setStatus('Queuing...',0,false);
  try{
    const res=await fetch('/api/start',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
    const data=await res.json();
    if(!res.ok){setStatus(data.error||'Error',0,true);resetBtn();return;}
    currentJobId=data.job_id;
    pollStatus();
    pollInterval=setInterval(pollStatus,1500);
  }catch(e){setStatus('Network error',0,true);resetBtn();}
}
async function pollStatus(){
  if(!currentJobId)return;
  try{
    const res=await fetch(`/api/status/${currentJobId}`);
    const data=await res.json();
    if(data.status==='done'){
      clearInterval(pollInterval);
      setStatus(`✓ Ready — ${data.title||'audio'}`,100,false);
      const btn=document.getElementById('downloadBtn');
      btn.classList.add('visible');
      btn.onclick=()=>window.location.href=`/api/download/${currentJobId}`;
      resetBtn();
    }else if(data.status==='error'){
      clearInterval(pollInterval);
      setStatus('✗ '+(data.error||'Unknown error'),0,true);
      resetBtn();
    }else{
      const pct=data.progress||0;
      const msg=pct<10?'Fetching info...':pct<95?`Downloading... ${pct}%`:'Converting to MP3...';
      setStatus(msg,pct,false,true);
    }
  }catch(e){}
}
function setStatus(msg,pct,isError,pulsing=false){
  document.getElementById('progressBar').style.width=pct+'%';
  const st=document.getElementById('statusText');
  st.textContent=msg;
  st.className='status-text'+(isError?' error':'')+(pulsing?' pulsing':'');
}
function resetBtn(){document.getElementById('grabBtn').disabled=false;}
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/start", methods=["POST"])
def start():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    if not re.match(r"https?://(www\.)?(youtube\.com|youtu\.be)/", url):
        return jsonify({"error": "Not a valid YouTube URL"}), 400
    job_id = str(uuid.uuid4())[:12]
    jobs[job_id] = {"status": "running", "progress": 0}
    threading.Thread(target=download_mp3, args=(job_id, url), daemon=True).start()
    return jsonify({"job_id": job_id})

@app.route("/api/status/<job_id>")
def status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    resp = {"status": job["status"], "progress": job.get("progress", 0)}
    if job["status"] == "done":
        resp["title"] = job.get("title", "audio")
    elif job["status"] == "error":
        resp["error"] = job.get("error", "Unknown error")
    return jsonify(resp)

@app.route("/api/download/<job_id>")
def download(job_id):
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "File not ready"}), 404
    path = job.get("filename")
    if not path or not os.path.exists(path):
        return jsonify({"error": "File not found or expired"}), 404
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', job.get("title", "audio")) + ".mp3"
    return send_file(path, as_attachment=True, download_name=safe_name, mimetype="audio/mpeg")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
