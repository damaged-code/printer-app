import hashlib, hmac, logging, os, re, subprocess, tempfile, time
from flask import Flask, request, session, redirect, url_for, render_template_string, abort, send_file, jsonify

PIN_HASH = os.environ.get("PRINTAPP_PIN_HASH", "")
SECRET = os.environ.get("PRINTAPP_SECRET_KEY", "")
PRINTER = os.environ.get("PRINTAPP_PRINTER", "")
MAX_FAILS = int(os.environ.get("PRINTAPP_MAX_FAILS", "5"))
LOCK_SECONDS = int(os.environ.get("PRINTAPP_LOCK_SECONDS", "900"))
TRUST_PROXY = os.environ.get("PRINTAPP_TRUST_PROXY", "false").lower() in ("1", "true", "yes")
COOKIE_SECURE = os.environ.get("PRINTAPP_COOKIE_SECURE", "true").lower() in ("1", "true", "yes")
ALLOWED = {".pdf": b"%PDF", ".png": b"\x89PNG", ".jpg": b"\xff\xd8\xff", ".jpeg": b"\xff\xd8\xff"}
IPA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "HomePrinter.ipa")

if not SECRET:
    raise RuntimeError("PRINTAPP_SECRET_KEY is required. Run install.sh or configure /etc/home-printer.env.")
if not PIN_HASH:
    raise RuntimeError("PRINTAPP_PIN_HASH is required. Run install.sh or configure /etc/home-printer.env.")
if not PRINTER:
    raise RuntimeError("PRINTAPP_PRINTER is required. Run install.sh or configure /etc/home-printer.env.")

app = Flask(__name__)
app.secret_key = SECRET
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = COOKIE_SECURE
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 7

fails = {}

def client_ip():
    if TRUST_PROXY:
        return request.headers.get("CF-Connecting-IP") or request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or request.remote_addr
    return request.remote_addr

def valid_pin(pin):
    digest = hashlib.sha256(str(pin or "").encode()).hexdigest()
    return hmac.compare_digest(digest, PIN_HASH)

def locked(ip):
    n, until = fails.get(ip, (0, 0))
    return until > time.time()

PAGE = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Home Printer</title>
<style>
body{font-family:system-ui,-apple-system,sans-serif;background:#111;color:#eee;display:flex;justify-content:center;padding:24px;margin:0}
.c{width:100%;max-width:440px}h1{font-size:22px;margin:0 0 4px 0}
.sub{color:#888;font-size:13px;margin-bottom:18px}
input,select,button{width:100%;padding:12px;margin:6px 0;border-radius:10px;border:1px solid #333;background:#1c1c1e;color:#eee;font-size:15px;box-sizing:border-box}
button{background:#facc15;color:#111;font-weight:700;border:0;cursor:pointer;margin-top:10px}
button:hover{background:#eab308}
.m{padding:12px;border-radius:10px;margin:12px 0;font-size:14px}.ok{background:#14532d;color:#86efac}.er{background:#7f1d1d;color:#fca5a5}
a{color:#facc15;text-decoration:none}
.row{display:flex;gap:10px;align-items:center}.row>*{flex:1}
.ipa{display:block;text-align:center;padding:12px;margin-top:20px;border-radius:10px;border:1px solid #333;background:#1c1c1e;color:#facc15;font-weight:600}
.card{background:#18181b;border:1px solid #27272a;border-radius:12px;padding:16px;margin-bottom:16px}
label{font-size:12px;color:#aaa;text-transform:uppercase;letter-spacing:0.5px;font-weight:600}
</style></head><body><div class=c>
<h1>{{printer}}</h1>
<div class=sub>Home Printer &middot; CUPS Server</div>
{% if msg %}<div class="m {{cls}}">{{msg}}</div>{% endif %}
{% if jobid %}<div class="m ok" id="st" data-job="{{jobid}}">Checking job status...</div>
<script>
(function(){
 var el=document.getElementById('st'),job=el.dataset.job;
 function tick(){
  fetch('/status/'+job,{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(d){
   el.textContent=d.text; el.className='m '+(d.state=='error'?'er':'ok');
   if(d.state=='done'||d.state=='error')return;
   setTimeout(tick,2000);
  }).catch(function(){setTimeout(tick,4000)});
 }
 tick();
})();
</script>{% endif %}
{% if not authed %}
<form method=post action="/login"><input name=pin type=password inputmode=numeric autocomplete=off placeholder="Enter PIN to unlock" autofocus><button>Unlock</button></form>
{% else %}
<form method=post action="/print" enctype=multipart/form-data>
<div class=card>
<label>Document or Image</label>
<input type=file name=file accept=".pdf,.png,.jpg,.jpeg" required>
<div class=row>
  <div>
    <label>Copies</label>
    <input type=number name=copies value=1 min=1 max=10>
  </div>
  <div>
    <label>Duplex</label>
    <select name=sides>
      <option value=one-sided>Single-sided</option>
      <option value=two-sided-long-edge>Double (Long)</option>
      <option value=two-sided-short-edge>Double (Short)</option>
    </select>
  </div>
</div>
<div class=row>
  <div>
    <label>Media Size</label>
    <select name=media>
      <option value=A4 selected>A4</option>
      <option value=Letter>Letter</option>
      <option value=Legal>Legal</option>
      <option value=A5>A5</option>
    </select>
  </div>
  <div>
    <label>Orientation</label>
    <select name=orientation>
      <option value=portrait selected>Portrait</option>
      <option value=landscape>Landscape</option>
    </select>
  </div>
</div>
<div class=row>
  <div>
    <label>Pages (e.g. 1-3,5)</label>
    <input type=text name=page_ranges placeholder="All pages">
  </div>
  <div>
    <label>Toner Save</label>
    <select name=toner_save>
      <option value=False selected>Normal Quality</option>
      <option value=True>Toner Save (Eco)</option>
    </select>
  </div>
</div>
</div>
<button>Print Document</button>
</form>
<p style="text-align:right"><a href="/logout">Lock / Exit</a></p>
<a class=ipa href="/HomePrinter.ipa">Download Updated iOS App (.ipa)</a>
{% endif %}
</div></body></html>"""

def render(msg=None, cls="ok", code=200, jobid=None):
    return render_template_string(PAGE, msg=msg, cls=cls, jobid=jobid, printer=PRINTER, authed=session.get("ok") is True), code

@app.get("/")
def index():
    return render()

@app.get("/HomePrinter.ipa")
def download_ipa():
    if session.get("ok") is not True:
        abort(401)
    if not os.path.exists(IPA_PATH):
        abort(404)
    return send_file(IPA_PATH, as_attachment=True, download_name="HomePrinter.ipa", mimetype="application/octet-stream")

@app.post("/login")
def login():
    ip = client_ip()
    if locked(ip):
        if request.is_json or request.headers.get("Accept") == "application/json":
            return jsonify({"status": "error", "error": "Too many attempts. Try later."}), 429
        return render("Too many attempts. Try later.", "er", 429)
    pin = request.form.get("pin") or (request.json.get("pin") if request.is_json else "")
    if valid_pin(pin):
        fails.pop(ip, None)
        session.permanent = True
        session["ok"] = True
        if request.is_json or request.headers.get("Accept") == "application/json":
            return jsonify({"status": "ok", "authenticated": True})
        return redirect(url_for("index"))
    n = fails.get(ip, (0, 0))[0] + 1
    fails[ip] = (n, time.time() + LOCK_SECONDS if n >= MAX_FAILS else 0)
    time.sleep(1)
    if request.is_json or request.headers.get("Accept") == "application/json":
        return jsonify({"status": "error", "error": "Wrong PIN."}), 401
    return render("Wrong PIN.", "er", 401)

@app.get("/logout")
def logout():
    session.clear()
    if request.is_json or request.headers.get("Accept") == "application/json":
        return jsonify({"status": "ok", "authenticated": False})
    return redirect(url_for("index"))

@app.post("/print")
def do_print():
    if session.get("ok") is not True:
        if request.is_json or request.headers.get("Accept") == "application/json":
            return jsonify({"status": "error", "error": "Unauthorized"}), 401
        abort(401)
    f = request.files.get("file")
    if not f or not f.filename:
        return render("No file.", "er", 400)
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED:
        return render("Only PDF, PNG, JPG.", "er", 400)
    data = f.read()
    if not data.startswith(ALLOWED[ext]):
        return render("File content does not match its type.", "er", 400)
    try:
        copies = max(1, min(20, int(request.form.get("copies", 1))))
    except ValueError:
        copies = 1

    sides = request.form.get("sides", "one-sided")
    if sides not in ("one-sided", "two-sided-long-edge", "two-sided-short-edge"):
        sides = "one-sided"

    media = request.form.get("media", "A4")
    if media not in ("A4", "Letter", "Legal", "A5", "A6", "B5"):
        media = "A4"

    orientation = request.form.get("orientation", "portrait")
    toner_save = request.form.get("toner_save", "False")
    page_ranges = request.form.get("page_ranges", "").strip()

    lp_args = ["lp", "-d", PRINTER, "-n", str(copies), "-o", f"media={media}", "-o", "fit-to-page"]
    if sides != "one-sided":
        lp_args.extend(["-o", f"sides={sides}"])
    if orientation == "landscape":
        lp_args.extend(["-o", "orientation-requested=4"])
    if str(toner_save).lower() in ("true", "1", "yes"):
        lp_args.extend(["-o", "brlaserEconomode=True"])
    if page_ranges and re.match(r"^[0-9,\-]+$", page_ranges):
        lp_args.extend(["-o", f"page-ranges={page_ranges}"])

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as t:
        t.write(data)
        path = t.name
    try:
        cmd = lp_args + [path]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    if r.returncode != 0:
        err = r.stderr.strip() or "unknown error"
        if request.headers.get("Accept") == "application/json":
            return jsonify({"status": "error", "error": err}), 500
        return render("Print failed: " + err, "er", 500)
    m = re.search(r"request id is \S+-(\d+) ", r.stdout)
    n = int(m.group(1)) if m else None
    if request.headers.get("Accept") == "application/json":
        return jsonify({"status": "ok", "jobid": n, "message": "Sent to printer."})
    return render("Sent to printer." + (" Job %d." % n if n else ""), "ok", jobid=n)


JOBTEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobattrs.test")
ATTR_RE = re.compile(r"^\s+(job-[a-z-]+) \(\w+\) = (.*)$", re.M)

def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0

def job_attrs(n):
    r = subprocess.run(["ipptool", "-tv", "-d", f"job={n}", f"ipp://localhost/printers/{PRINTER}", JOBTEST],
                       capture_output=True, text=True, timeout=10)
    return dict(ATTR_RE.findall(r.stdout))

def printer_problem():
    out = subprocess.run(["lpstat", "-p", PRINTER, "-l"], capture_output=True, text=True, timeout=10).stdout
    lines = out.splitlines()
    first = lines[0].lower() if lines else ""
    probs = []
    if "disabled" in first or "stopped" in first:
        probs.append("printer is stopped" + (" (" + lines[0].split(" - ", 1)[1].strip() + ")" if " - " in lines[0] else ""))
    for ln in lines:
        if ln.strip().lower().startswith("alerts:"):
            a = ln.split(":", 1)[1].strip()
            if a and a != "none":
                probs.append(a)
    return "; ".join(probs)

@app.get("/status/<int:n>")
def status(n):
    if session.get("ok") is not True:
        return jsonify({"state": "error", "text": "Unauthorized"}), 401
    try:
        a = job_attrs(n)
    except Exception:
        return jsonify({"state": "error", "text": "Could not read job status."})
    st = a.get("job-state")
    sheets_completed = _int(a.get("job-media-sheets-completed"))
    sheets_total = _int(a.get("job-media-sheets"))
    impressions_completed = _int(a.get("job-impressions-completed"))
    impressions_total = _int(a.get("job-impressions"))
    completed_pages = max(sheets_completed, impressions_completed)
    total_pages = max(sheets_total, impressions_total)

    if not st:
        return jsonify({
            "state": "done",
            "text": "Done (job finished).",
            "pages_completed": completed_pages,
            "pages_total": total_pages,
            "job_state": "completed"
        })
    reasons = a.get("job-state-reasons", "")
    pg = f" {completed_pages}/{total_pages} page(s) printed." if total_pages > 0 else (f" {completed_pages} page(s) printed." if completed_pages else "")
    if st == "completed":
        return jsonify({
            "state": "done",
            "text": "Done." + pg,
            "pages_completed": completed_pages,
            "pages_total": total_pages,
            "job_state": st
        })
    if st == "canceled":
        return jsonify({"state": "error", "text": "Job was cancelled.", "job_state": st, "pages_completed": completed_pages})
    if st == "aborted":
        return jsonify({"state": "error", "text": "Job failed. " + reasons, "job_state": st})
    try:
        prob = printer_problem()
    except Exception:
        prob = ""
    extra = " Printer: " + prob + "." if prob else ""
    if st == "pending":
        return jsonify({"state": "queued", "text": "Queued, waiting for printer." + extra, "job_state": st, "pages_completed": completed_pages, "pages_total": total_pages})
    if st == "pending-held":
        return jsonify({"state": "queued", "text": "Held in queue." + extra, "job_state": st, "pages_completed": completed_pages, "pages_total": total_pages})
    if st == "processing":
        return jsonify({"state": "printing", "text": "Printing..." + pg + extra, "job_state": st, "pages_completed": completed_pages, "pages_total": total_pages})
    if st == "processing-stopped":
        return jsonify({"state": "printing", "text": "Printing is paused." + pg + extra, "job_state": st, "pages_completed": completed_pages, "pages_total": total_pages})
    return jsonify({"state": "queued", "text": "Status: " + st + "." + extra, "job_state": st, "pages_completed": completed_pages, "pages_total": total_pages})

@app.post("/cancel/<int:n>")
def cancel_job(n):
    if session.get("ok") is not True:
        return jsonify({"status": "error", "error": "Unauthorized"}), 401
    r = subprocess.run(["cancel", str(n)], capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        return jsonify({"status": "error", "error": r.stderr.strip() or "Failed to cancel job"}), 500
    return jsonify({"status": "ok", "message": f"Job #{n} cancelled."})

@app.get("/queue")
def list_queue():
    if session.get("ok") is not True:
        return jsonify({"status": "error", "error": "Unauthorized"}), 401
    r = subprocess.run(["lpstat", "-o"], capture_output=True, text=True, timeout=10)
    jobs = []
    for line in r.stdout.splitlines():
        m = re.match(r"^(\S+)-(\d+)\s+(\S+)\s+(\d+)\s+(.*)$", line)
        if m:
            dest, jid, user, sz, dt = m.groups()
            job_info = {"id": int(jid), "dest": dest, "user": user, "bytes": int(sz), "date": dt}
            try:
                attrs = job_attrs(int(jid))
                job_info["state"] = attrs.get("job-state", "queued")
                job_info["pages_completed"] = _int(attrs.get("job-media-sheets-completed")) or _int(attrs.get("job-impressions-completed"))
                job_info["pages_total"] = _int(attrs.get("job-media-sheets")) or _int(attrs.get("job-impressions"))
            except Exception:
                pass
            jobs.append(job_info)
    return jsonify({"status": "ok", "jobs": jobs})

@app.get("/printer/status")
def printer_status():
    if session.get("ok") is not True:
        return jsonify({"status": "error", "error": "Unauthorized"}), 401
    prob = printer_problem()
    out = subprocess.run(["lpstat", "-p", PRINTER], capture_output=True, text=True, timeout=5).stdout.strip()
    return jsonify({
        "status": "ok",
        "printer": PRINTER,
        "detail": out,
        "is_idle": "idle" in out.lower(),
        "problem": prob or None
    })

@app.get("/healthz")
def healthz():
    try:
        result = subprocess.run(["lpstat", "-p", PRINTER], capture_output=True, text=True, timeout=5)
        healthy = result.returncode == 0 and "disabled" not in result.stdout.lower()
    except (OSError, subprocess.TimeoutExpired):
        healthy = False
    return jsonify({"status": "ok" if healthy else "degraded", "printer": PRINTER}), 200 if healthy else 503

@app.errorhandler(413)
def too_large(_error):
    if request.accept_mimetypes.best == "application/json":
        return jsonify({"status": "error", "error": "File is larger than 15 MB."}), 413
    return render("File is larger than 15 MB.", "er", 413)

@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Cache-Control", "no-store")
    return response
