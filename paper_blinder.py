#!/usr/bin/env python3
"""
Paper Blinder — Local web app for blinding student submissions.
Uses Qwen2.5-VL via Ollama for handwriting recognition.

Student data NEVER leaves your computer.

Setup:
    pip install flask PyMuPDF
    ollama pull qwen2.5vl:7b

Run:
    python paper_blinder.py
"""

import base64, csv, io, json, os, re, secrets, sys, zipfile, webbrowser, threading
import urllib.request, urllib.error

missing = []
try:
    import fitz
except ImportError:
    missing.append("PyMuPDF")
try:
    from flask import Flask, request, send_file, jsonify
except ImportError:
    missing.append("flask")

if missing:
    print(f"\n  Missing packages: {', '.join(missing)}")
    print(f"  Run:  pip install {' '.join(missing)}\n")
    sys.exit(1)

# ── Check Ollama + Qwen2.5-VL availability ────────────────────
VLM_AVAILABLE = False
VLM_MODEL = "qwen2.5vl:7b"
OLLAMA_URL = "http://localhost:11434"

def check_vlm():
    global VLM_AVAILABLE
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            models = [m.get("name", "") for m in data.get("models", [])]
            for m in models:
                if "qwen2.5vl" in m:
                    global VLM_MODEL
                    VLM_MODEL = m
                    VLM_AVAILABLE = True
                    return
    except Exception:
        pass

check_vlm()

app = Flask(__name__)

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Paper Blinder</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,wght@0,400;0,500;0,700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  :root{--bg:#0f1117;--surface:#1a1d27;--border:#2a2e3f;--text:#e4e4e7;--text-dim:#8b8fa3;--accent:#6ee7b7;--accent-dim:#34d399;--accent-glow:rgba(110,231,183,0.08);--danger:#f87171;--warn:#fbbf24;--mono:'JetBrains Mono',monospace;--sans:'DM Sans',-apple-system,sans-serif}
  body{font-family:var(--sans);background:var(--bg);color:var(--text);min-height:100vh;display:flex;align-items:center;justify-content:center;padding:2rem;line-height:1.5}
  .container{width:100%;max-width:560px}
  h1{font-size:1.75rem;font-weight:700;letter-spacing:-0.02em;margin-bottom:0.25rem}
  .subtitle{color:var(--text-dim);font-size:0.9rem;margin-bottom:2rem}
  .badges{margin-bottom:1.5rem;display:flex;flex-wrap:wrap;gap:0.5rem}
  .badge{display:inline-flex;align-items:center;gap:0.4rem;font-size:0.75rem;font-weight:500;padding:0.25rem 0.6rem;border-radius:999px}
  .badge-green{background:rgba(110,231,183,0.08);border:1px solid rgba(110,231,183,0.15);color:var(--accent)}
  .badge-yellow{background:rgba(251,191,36,0.08);border:1px solid rgba(251,191,36,0.15);color:var(--warn)}
  .dropzone{border:2px dashed var(--border);border-radius:12px;padding:2.5rem 1.5rem;text-align:center;cursor:pointer;transition:all 0.2s;background:var(--surface);margin-bottom:1.5rem}
  .dropzone:hover,.dropzone.dragover{border-color:var(--accent-dim);background:var(--accent-glow)}
  .dropzone.has-file{border-color:var(--accent);border-style:solid}
  .dropzone-icon{font-size:2rem;margin-bottom:0.5rem;opacity:0.6}
  .dropzone-text{color:var(--text-dim);font-size:0.9rem}
  .dropzone-text strong{color:var(--accent)}
  .file-name{font-family:var(--mono);font-size:0.85rem;color:var(--accent);margin-top:0.5rem;word-break:break-all}
  .settings{display:flex;flex-direction:column;gap:1rem;margin-bottom:1.5rem}
  .field{display:flex;flex-direction:column;gap:0.35rem}
  label{font-size:0.8rem;font-weight:500;color:var(--text-dim);letter-spacing:0.03em;text-transform:uppercase}
  .row{display:flex;gap:0.75rem}
  .row .field{flex:1}
  .mode-toggle{display:flex;background:var(--surface);border-radius:8px;border:1px solid var(--border);overflow:hidden}
  .mode-toggle button{flex:1;padding:0.6rem 1rem;border:none;background:none;color:var(--text-dim);font-family:var(--sans);font-size:0.85rem;font-weight:500;cursor:pointer;transition:all 0.15s}
  .mode-toggle button.active{background:var(--accent-glow);color:var(--accent);box-shadow:inset 0 -2px 0 var(--accent)}
  input[type="text"],input[type="number"],select{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:0.6rem 0.75rem;color:var(--text);font-family:var(--sans);font-size:0.9rem;outline:none;transition:border-color 0.15s;width:100%}
  input:focus,select:focus{border-color:var(--accent-dim)}
  input::placeholder{color:var(--text-dim);opacity:0.6}
  select option{background:var(--surface);color:var(--text)}
  .checkbox-row{display:flex;align-items:center;gap:0.5rem;cursor:pointer;user-select:none}
  .checkbox-row input[type="checkbox"]{accent-color:var(--accent);width:16px;height:16px}
  .checkbox-row span{font-size:0.85rem;color:var(--text-dim)}
  .submit-btn{width:100%;padding:0.8rem 1.5rem;background:var(--accent);color:var(--bg);border:none;border-radius:10px;font-family:var(--sans);font-size:1rem;font-weight:700;cursor:pointer;transition:all 0.15s}
  .submit-btn:hover:not(:disabled){background:var(--accent-dim);transform:translateY(-1px);box-shadow:0 4px 20px rgba(110,231,183,0.2)}
  .submit-btn:disabled{opacity:0.4;cursor:not-allowed}
  .progress{margin-top:1.5rem;display:none}
  .progress.show{display:block}
  .progress-bar-track{height:4px;background:var(--surface);border-radius:2px;overflow:hidden;margin-bottom:0.75rem}
  .progress-bar-fill{height:100%;background:var(--accent);border-radius:2px;width:0%;transition:width 0.3s}
  .progress-bar-fill.indeterminate{width:30%;animation:slide 1.2s ease-in-out infinite}
  @keyframes slide{0%{transform:translateX(-100%)}100%{transform:translateX(400%)}}
  .progress-text{font-size:0.85rem;color:var(--text-dim)}
  .result{margin-top:1.5rem;padding:1.25rem;background:var(--surface);border:1px solid var(--accent);border-radius:10px;display:none}
  .result.show{display:block}
  .result h3{font-size:1rem;margin-bottom:0.5rem;color:var(--accent)}
  .result p{font-size:0.85rem;color:var(--text-dim);margin-bottom:1rem}
  .download-btn{display:inline-flex;align-items:center;gap:0.5rem;padding:0.6rem 1.2rem;background:var(--accent);color:var(--bg);border:none;border-radius:8px;font-family:var(--sans);font-weight:600;font-size:0.9rem;cursor:pointer;text-decoration:none}
  .download-btn:hover{background:var(--accent-dim)}
  .error{margin-top:1rem;padding:1rem;background:rgba(248,113,113,0.08);border:1px solid rgba(248,113,113,0.2);border-radius:8px;color:var(--danger);font-size:0.85rem;display:none}
  .error.show{display:block}
  .help-text{font-size:0.78rem;color:var(--text-dim);opacity:0.7;margin-top:0.2rem}
  .debug-info{margin-top:1rem;padding:0.75rem;background:rgba(255,255,255,0.03);border:1px solid var(--border);border-radius:8px;font-family:var(--mono);font-size:0.75rem;color:var(--text-dim);display:none;white-space:pre-wrap}
  .debug-info.show{display:block}
</style>
</head>
<body>
<div class="container">
  <div class="badges">
    <span class="badge badge-green">100% local</span>
    <span class="badge VLM_BADGE_CLASS" id="vlmBadge">VLM_BADGE_TEXT</span>
  </div>
  <h1>Paper Blinder</h1>
  <p class="subtitle">Redact names, split into coded PDFs, auto-detect student names for your key.</p>

  <div class="dropzone" id="dropzone">
    <div class="dropzone-icon">&#128196;</div>
    <div class="dropzone-text">Drag your scanned PDF here or <strong>click to browse</strong></div>
    <div class="file-name" id="fileName"></div>
  </div>
  <input type="file" id="fileInput" accept=".pdf" hidden>

  <div class="settings">
    <div class="field">
      <label>Split Mode</label>
      <div class="mode-toggle">
        <button class="active" id="modeFixed" onclick="setMode('fixed')">Fixed Page Count</button>
        <button id="modeLandmark" onclick="setMode('landmark')">Landmark Text</button>
      </div>
    </div>
    <div id="fixedSettings">
      <div class="field">
        <label>Pages per student</label>
        <input type="number" id="pagesPerStudent" min="1" max="50" value="2" placeholder="e.g. 2">
      </div>
    </div>
    <div id="landmarkSettings" style="display:none;">
      <div class="field">
        <label>Landmark phrase</label>
        <input type="text" id="landmarkText" placeholder='e.g. "=== START ===" or "Part 1"'>
        <div class="help-text">Text on the first page of each submission</div>
      </div>
    </div>
    <div class="row">
      <div class="field">
        <label>Redact top %</label>
        <input type="number" id="redactPct" min="1" max="50" value="15">
        <div class="help-text">How much to black out</div>
      </div>
      <div class="field">
        <label>Redact edge</label>
        <select id="redactEdge">
          <option value="top" selected>Top</option>
          <option value="left">Left</option>
          <option value="right">Right</option>
          <option value="bottom">Bottom</option>
        </select>
        <div class="help-text">Which edge has the name</div>
      </div>
    </div>
    <label class="checkbox-row">
      <input type="checkbox" id="redactAll">
      <span>Redact all pages (not just the first of each submission)</span>
    </label>
  </div>

  <button class="submit-btn" id="submitBtn" onclick="processFile()" disabled>Blind the Papers</button>
  <div class="progress" id="progress">
    <div class="progress-bar-track"><div class="progress-bar-fill indeterminate" id="progressBar"></div></div>
    <div class="progress-text" id="progressText">Processing...</div>
  </div>
  <div class="error" id="error"></div>
  <div class="debug-info" id="debugInfo"></div>
  <div class="result" id="result">
    <h3>Done!</h3>
    <p id="resultText"></p>
    <a class="download-btn" id="downloadLink" href="#">Download ZIP</a>
  </div>
</div>
<script>
  let selectedFile=null;
  const dropzone=document.getElementById('dropzone'),fileInput=document.getElementById('fileInput'),fileName=document.getElementById('fileName'),submitBtn=document.getElementById('submitBtn');
  dropzone.addEventListener('click',()=>fileInput.click());
  dropzone.addEventListener('dragover',e=>{e.preventDefault();dropzone.classList.add('dragover')});
  dropzone.addEventListener('dragleave',()=>dropzone.classList.remove('dragover'));
  dropzone.addEventListener('drop',e=>{e.preventDefault();dropzone.classList.remove('dragover');if(e.dataTransfer.files.length&&e.dataTransfer.files[0].name.endsWith('.pdf'))setFile(e.dataTransfer.files[0])});
  fileInput.addEventListener('change',()=>{if(fileInput.files.length)setFile(fileInput.files[0])});
  function setFile(f){selectedFile=f;fileName.textContent=f.name+' ('+(f.size/1024/1024).toFixed(1)+' MB)';dropzone.classList.add('has-file');submitBtn.disabled=false;document.getElementById('result').classList.remove('show');document.getElementById('error').classList.remove('show');document.getElementById('debugInfo').classList.remove('show')}
  function setMode(m){document.getElementById('modeFixed').classList.toggle('active',m==='fixed');document.getElementById('modeLandmark').classList.toggle('active',m==='landmark');document.getElementById('fixedSettings').style.display=m==='fixed'?'block':'none';document.getElementById('landmarkSettings').style.display=m==='landmark'?'block':'none'}
  async function processFile(){
    if(!selectedFile)return;
    const progress=document.getElementById('progress'),progressBar=document.getElementById('progressBar'),progressText=document.getElementById('progressText'),error=document.getElementById('error'),result=document.getElementById('result'),debugInfo=document.getElementById('debugInfo');
    progress.classList.add('show');result.classList.remove('show');error.classList.remove('show');debugInfo.classList.remove('show');submitBtn.disabled=true;progressText.textContent='Processing (vision model reading names — may take a minute)...';
    const fd=new FormData();fd.append('pdf',selectedFile);
    const mode=document.getElementById('modeFixed').classList.contains('active')?'fixed':'landmark';
    fd.append('mode',mode);
    if(mode==='fixed')fd.append('pages_per',document.getElementById('pagesPerStudent').value);
    else fd.append('landmark',document.getElementById('landmarkText').value);
    fd.append('redact_pct',document.getElementById('redactPct').value);
    fd.append('redact_edge',document.getElementById('redactEdge').value);
    fd.append('redact_all',document.getElementById('redactAll').checked?'1':'0');
    try{
      const resp=await fetch('/process',{method:'POST',body:fd});
      if(!resp.ok){const d=await resp.json();throw new Error(d.error||'Something went wrong')}
      const blob=await resp.blob(),url=URL.createObjectURL(blob),count=resp.headers.get('X-Submission-Count')||'?',debug=resp.headers.get('X-Debug-Info'),namesFound=resp.headers.get('X-Names-Found')||'0';
      progressBar.classList.remove('indeterminate');progressBar.style.width='100%';progressText.textContent='Complete!';
      let msg=count+' submissions blinded.';
      if(parseInt(namesFound)>0) msg+=' Detected '+namesFound+' name(s) — check your answer key.';
      else msg+=' No names auto-detected. Fill in _ANSWER_KEY.csv manually.';
      document.getElementById('resultText').textContent=msg;
      document.getElementById('downloadLink').href=url;document.getElementById('downloadLink').download=selectedFile.name.replace('.pdf','_blinded.zip');
      result.classList.add('show');
      if(debug){debugInfo.textContent=decodeURIComponent(debug);debugInfo.classList.add('show')}
    }catch(err){error.textContent=err.message;error.classList.add('show');progress.classList.remove('show')}
    submitBtn.disabled=false;
  }
</script>
</body>
</html>"""


# ── Vision LM name reading ────────────────────────────────────

def vlm_read_name(png_bytes):
    """
    Send an image to Qwen2.5-VL via Ollama and ask for the student name.
    Returns the name string or empty string on failure.
    """
    b64_img = base64.b64encode(png_bytes).decode("utf-8")

    payload = json.dumps({
        "model": VLM_MODEL,
        "messages": [{
            "role": "user",
            "content": (
                "This is the top section of a student's test paper. "
                "What is the student's name written on this paper? "
                "Reply with ONLY the name, nothing else. "
                "If you cannot read a name, reply with just: NONE"
            ),
            "images": [b64_img]
        }],
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 50
        }
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            raw = data.get("message", {}).get("content", "").strip()
            # Clean up common VLM response patterns
            raw = raw.strip('"\'`*')
            raw = re.sub(r'^(the student.s name is|the name is|name:)\s*', '', raw, flags=re.IGNORECASE)
            raw = raw.strip('"\'`*. ')
            if raw.upper() == "NONE" or len(raw) < 2:
                return ""
            return raw
    except Exception as e:
        print(f"  VLM error: {e}")
        return ""


def get_visual_name_rect(page, redact_pct, edge="top"):
    """Get the visual (rotation-aware) rectangle for the name zone."""
    rect = page.rect
    pct = redact_pct / 100
    rects = {
        "top":    fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + rect.height * pct),
        "bottom": fitz.Rect(rect.x0, rect.y1 - rect.height * pct, rect.x1, rect.y1),
        "left":   fitz.Rect(rect.x0, rect.y0, rect.x0 + rect.width * pct, rect.y1),
        "right":  fitz.Rect(rect.x1 - rect.width * pct, rect.y0, rect.x1, rect.y1),
    }
    return rects.get(edge, rects["top"])


def clean_name(raw_text):
    """Try to extract the student name from text-layer content."""
    if not raw_text or not raw_text.strip():
        return ""
    text = raw_text.strip()
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for line in lines:
        m = re.match(r'(?:name|nombre|student)\s*[:\-\.]\s*(.+)', line, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            name = re.split(r'\s{2,}|(?:date|period|fecha|clase|pd)\s*[:\-\.]', name, flags=re.IGNORECASE)[0]
            name = name.strip(' :-._')
            if len(name) > 1:
                return name
    for line in lines:
        cleaned = re.split(r'\s{2,}|(?:date|period|fecha|clase|pd)\s*[:\-\.]', line, flags=re.IGNORECASE)[0].strip()
        if (len(cleaned) > 1
            and not cleaned.isupper()
            and re.search(r'[a-zA-Z]', cleaned)
            and not re.match(r'^(instructions?|directions?|test|quiz|exam|checkpoint|unit|part|section|water|biology|chemistry|environmental)\b', cleaned, re.IGNORECASE)):
            return cleaned
    return ""


def extract_name_from_zone(page, redact_pct, edge="top"):
    """
    Read the student name from the redaction zone.
    Strategy:
      1. Try embedded text extraction (if scanner added a text layer)
      2. Fall back to Qwen2.5-VL vision model (reads handwriting)
    """
    clip = get_visual_name_rect(page, redact_pct, edge)

    # Attempt 1: embedded text layer
    text = page.get_text("text", clip=clip).strip()
    name = clean_name(text)
    if name:
        return name, "text-layer"

    # Attempt 2: Vision LM via Ollama
    if VLM_AVAILABLE:
        try:
            mat = fitz.Matrix(3, 3)  # 3x zoom for clear rendering
            pix = page.get_pixmap(matrix=mat, clip=clip)
            png_bytes = pix.tobytes("png")
            name = vlm_read_name(png_bytes)
            if name:
                return name, "vision-ai"
        except Exception as e:
            print(f"  VLM extraction error: {e}")

    return "", "none"


# ── PDF Processing ─────────────────────────────────────────────

def generate_code(length=6):
    return secrets.token_hex(length // 2 + 1)[:length]

def find_landmark_pages(doc, landmark_text, search_region_pct=30):
    pages = []
    low = landmark_text.lower()
    for i, page in enumerate(doc):
        r = page.rect
        clip = fitz.Rect(r.x0, r.y0, r.x1, r.y0 + r.height * (search_region_pct / 100))
        if low in page.get_text("text", clip=clip).lower():
            pages.append(i)
    return pages

def redact_name_region(page, redact_pct, edge="top"):
    """Black out a strip. Handles scanner rotation flags."""
    rot = page.rotation % 360
    visual_to_raw = {
        0:   {"top":"top","bottom":"bottom","left":"left","right":"right"},
        90:  {"top":"left","bottom":"right","left":"bottom","right":"top"},
        180: {"top":"bottom","bottom":"top","left":"right","right":"left"},
        270: {"top":"right","bottom":"left","left":"top","right":"bottom"},
    }
    raw_edge = visual_to_raw.get(rot, visual_to_raw[0]).get(edge, edge)
    mb = page.mediabox
    pct = redact_pct / 100
    rects = {
        "top":    fitz.Rect(mb.x0, mb.y0, mb.x1, mb.y0 + mb.height * pct),
        "bottom": fitz.Rect(mb.x0, mb.y1 - mb.height * pct, mb.x1, mb.y1),
        "left":   fitz.Rect(mb.x0, mb.y0, mb.x0 + mb.width * pct, mb.y1),
        "right":  fitz.Rect(mb.x1 - mb.width * pct, mb.y0, mb.x1, mb.y1),
    }
    shape = page.new_shape()
    shape.draw_rect(rects.get(raw_edge, rects["top"]))
    shape.finish(color=(0, 0, 0), fill=(0, 0, 0))
    shape.commit()

def process_pdf(pdf_bytes, mode, pages_per=None, landmark=None,
                redact_pct=15, redact_all=False, redact_edge="top"):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total = len(doc)
    warnings = []
    p0 = doc[0]
    debug = (f"Pages: {total} | Visual: {p0.rect.width:.0f}x{p0.rect.height:.0f} | "
             f"Rotation: {p0.rotation} | MediaBox: {p0.mediabox.width:.0f}x{p0.mediabox.height:.0f} | "
             f"VLM: {VLM_MODEL if VLM_AVAILABLE else 'unavailable'}")

    if mode == "landmark" and landmark:
        starts = find_landmark_pages(doc, landmark)
        if not starts:
            warnings.append(f"Landmark '{landmark}' not found. Treated as one submission.")
            starts = [0]
        elif starts[0] != 0:
            starts.insert(0, 0)
    elif mode == "fixed" and pages_per:
        starts = list(range(0, total, pages_per))
        if total % pages_per != 0:
            warnings.append(f"{total} pages / {pages_per} = uneven. Last has {total % pages_per} page(s).")
    else:
        raise ValueError("Invalid mode or missing parameters")

    ranges = []
    for i, s in enumerate(starts):
        e = starts[i+1] if i+1 < len(starts) else total
        ranges.append((s, e))

    zip_buffer = io.BytesIO()
    mapping = []
    names_found = 0

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for idx, (start, end) in enumerate(ranges, 1):
            code = generate_code()
            print(f"  [{idx}/{len(ranges)}] Reading name from page {start+1}...", end=" ", flush=True)

            # Read name BEFORE redacting
            detected_name, method = extract_name_from_zone(doc[start], redact_pct, redact_edge)
            if detected_name:
                names_found += 1
                print(f"-> {detected_name} ({method})")
            else:
                print(f"-> (none)")

            # Split and redact
            out = fitz.open()
            out.insert_pdf(doc, from_page=start, to_page=end-1)
            if redact_all:
                for pg in out:
                    redact_name_region(pg, redact_pct, redact_edge)
            else:
                redact_name_region(out[0], redact_pct, redact_edge)
            zf.writestr(f"BLINDED_{code}.pdf", out.tobytes())
            out.close()

            label = f"pp. {start+1}-{end}" if end-start > 1 else f"p. {start+1}"
            mapping.append((code, idx, label, detected_name, method))

        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["code", "submission_number", "pages", "detected_name", "detection_method", "confirmed_name"])
        for code, num, label, name, method in mapping:
            w.writerow([code, num, label, name, method, ""])
        zf.writestr("_ANSWER_KEY.csv", buf.getvalue())
        if warnings:
            zf.writestr("_WARNINGS.txt", "\n".join(warnings))

    doc.close()
    zip_buffer.seek(0)
    return zip_buffer, len(mapping), warnings, debug, names_found


# ── Flask Routes ───────────────────────────────────────────────

@app.route("/")
def index():
    page = HTML_PAGE
    if VLM_AVAILABLE:
        page = page.replace("VLM_BADGE_CLASS", "badge-green").replace("VLM_BADGE_TEXT", f"Qwen Vision active")
    else:
        page = page.replace("VLM_BADGE_CLASS", "badge-yellow").replace("VLM_BADGE_TEXT", "Vision AI not found — run: ollama pull qwen2.5vl:7b")
    return page

@app.route("/process", methods=["POST"])
def process():
    try:
        pdf_file = request.files.get("pdf")
        if not pdf_file:
            return jsonify({"error": "No PDF uploaded"}), 400
        mode = request.form.get("mode", "fixed")
        pages_per = request.form.get("pages_per")
        landmark = request.form.get("landmark", "")
        redact_pct = float(request.form.get("redact_pct", 15))
        redact_edge = request.form.get("redact_edge", "top")
        redact_all = request.form.get("redact_all") == "1"
        if mode == "fixed":
            if not pages_per: return jsonify({"error": "Specify pages per student"}), 400
            pages_per = int(pages_per)
        elif mode == "landmark":
            if not landmark.strip(): return jsonify({"error": "Enter a landmark phrase"}), 400

        zb, count, warns, debug, names_found = process_pdf(
            pdf_file.read(), mode,
            pages_per=pages_per if mode=="fixed" else None,
            landmark=landmark if mode=="landmark" else None,
            redact_pct=redact_pct, redact_all=redact_all, redact_edge=redact_edge)
        resp = send_file(zb, mimetype="application/zip", as_attachment=True, download_name="blinded_papers.zip")
        resp.headers["X-Submission-Count"] = str(count)
        resp.headers["X-Names-Found"] = str(names_found)
        resp.headers["X-Debug-Info"] = debug
        resp.headers["Access-Control-Expose-Headers"] = "X-Submission-Count, X-Names-Found, X-Debug-Info"
        return resp
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = 5757
    print(f"\n  ======================================")
    print(f"         PAPER BLINDER")
    print(f"    http://localhost:{port}")
    print(f"    Ctrl+C to quit")
    print(f"    All data stays on YOUR machine.")
    print(f"    Vision: {VLM_MODEL if VLM_AVAILABLE else 'NOT FOUND — run: ollama pull qwen2.5vl:7b'}")
    print(f"  ======================================\n")
    threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{port}")).start()
    app.run(host="127.0.0.1", port=port, debug=False)
