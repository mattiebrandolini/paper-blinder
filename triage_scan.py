#!/usr/bin/env python3
"""
Triage Scanner — Quick scan of a bulk PDF to see who filled out what.

Reads names via Qwen2.5-VL, estimates page completion via ink density.
Auto-calibrates: compares each page against the lightest page in the
document to distinguish "just printed questions" from "student wrote on it."

Usage:
    python triage_scan.py scan.pdf --pages-per 7

    Optional:
      --pages-per N     Pages per student (default: 2)
      --skip-names      Skip VLM name detection (faster, just numbers)
"""

import argparse, base64, io, json, os, re, sys, urllib.request
try:
    import fitz
except ImportError:
    print("Need PyMuPDF:  pip install PyMuPDF")
    sys.exit(1)

OLLAMA_URL = "http://localhost:11434"
VLM_MODEL = "qwen2.5vl:7b"

def check_vlm():
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            for m in data.get("models", []):
                if "qwen2.5vl" in m.get("name", ""):
                    global VLM_MODEL
                    VLM_MODEL = m["name"]
                    return True
    except Exception:
        pass
    return False

def vlm_read_name(png_bytes):
    b64 = base64.b64encode(png_bytes).decode()
    payload = json.dumps({
        "model": VLM_MODEL,
        "messages": [{"role": "user",
            "content": "This is the top of a student's test paper. What is the student's name? Reply with ONLY the name. If unreadable: NONE",
            "images": [b64]}],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 50}
    }).encode()
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = json.loads(resp.read()).get("message", {}).get("content", "").strip()
            raw = raw.strip('"\'`*')
            raw = re.sub(r'^(the student.s name is|the name is|name:)\s*', '', raw, flags=re.IGNORECASE)
            raw = raw.strip('"\'`*. ')
            return "" if raw.upper() == "NONE" or len(raw) < 2 else raw
    except:
        return ""

def get_name_from_page(page, pct=15):
    rect = page.rect
    clip = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + rect.height * (pct / 100))
    text = page.get_text("text", clip=clip).strip()
    if text:
        for line in text.split('\n'):
            m = re.match(r'(?:name|nombre|student)\s*[:\-\.]\s*(.+)', line.strip(), re.IGNORECASE)
            if m:
                name = re.split(r'\s{2,}|(?:date|period|fecha|clase|pd)\s*[:\-\.]', m.group(1), flags=re.IGNORECASE)[0].strip(' :-._')
                if len(name) > 1:
                    return name
    # VLM fallback
    mat = fitz.Matrix(3, 3)
    pix = page.get_pixmap(matrix=mat, clip=clip)
    return vlm_read_name(pix.tobytes("png"))

def page_ink_density(page, skip_top_pct=18):
    """How much ink is on this page (below the header)."""
    rect = page.rect
    clip = fitz.Rect(rect.x0, rect.y0 + rect.height * (skip_top_pct / 100),
                     rect.x1, rect.y1)
    pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), clip=clip)
    samples = pix.samples
    total = pix.width * pix.height
    if total == 0:
        return 0.0
    dark = 0
    n = pix.n
    for i in range(0, len(samples), n):
        if samples[i] < 140 and samples[i+1] < 140 and samples[i+2] < 140:
            dark += 1
    return dark / total

def main():
    parser = argparse.ArgumentParser(description="Triage scan — who filled out what?")
    parser.add_argument("pdf", help="Path to the scanned PDF")
    parser.add_argument("--pages-per", type=int, default=2, help="Pages per student")
    parser.add_argument("--skip-names", action="store_true", help="Skip name detection")
    args = parser.parse_args()

    if not os.path.exists(args.pdf):
        print(f"File not found: {args.pdf}")
        sys.exit(1)

    vlm_ok = False
    if not args.skip_names:
        print("Checking vision model...", end=" ", flush=True)
        vlm_ok = check_vlm()
        print(f"{'OK (' + VLM_MODEL + ')' if vlm_ok else 'not found (names will be blank)'}")

    doc = fitz.open(args.pdf)
    total = len(doc)
    pp = args.pages_per
    n_students = (total + pp - 1) // pp

    # First pass: measure ink density on every page for auto-calibration
    print(f"Scanning {total} pages...", flush=True)
    densities = []
    for i in range(total):
        densities.append(page_ink_density(doc[i]))

    # Baseline = density of a "blank" page (just printed questions, no handwriting)
    # Use the 10th percentile as baseline to be robust against outliers
    sorted_d = sorted(densities)
    baseline_idx = max(0, len(sorted_d) // 10)
    baseline = sorted_d[baseline_idx]

    # A page counts as "filled" if its density is meaningfully above baseline
    # Use 1.5x baseline or baseline + 0.003, whichever is larger
    fill_threshold = max(baseline * 1.5, baseline + 0.003)

    print(f"\n{total} pages / {pp} per student = {n_students} submissions")
    print(f"Baseline ink density: {baseline:.4f}  |  Fill threshold: {fill_threshold:.4f}\n")
    print(f"{'#':<4} {'Name':<30} {'Pages':>6}  {'Completion'}")
    print("-" * 75)

    results = []
    for i in range(n_students):
        start = i * pp
        end = min(start + pp, total)

        # Read name
        name = ""
        if not args.skip_names and vlm_ok:
            print(f"  Reading name from p.{start+1}...          ", end="\r", flush=True)
            name = get_name_from_page(doc[start])

        # Check each page
        page_results = []
        for p_idx in range(start, end):
            d = densities[p_idx]
            if d > fill_threshold:
                label = "FILLED"
            elif d > baseline + 0.001:
                label = "partial"
            else:
                label = "blank"
            page_results.append((p_idx + 1, d, label))

        filled_count = sum(1 for _, _, l in page_results if l == "FILLED")
        partial_count = sum(1 for _, _, l in page_results if l == "partial")
        total_pages = len(page_results)

        if filled_count == total_pages:
            summary = "ALL FILLED"
        elif filled_count + partial_count == 0:
            summary = "BLANK"
        else:
            parts = []
            for p, d, l in page_results:
                if l == "FILLED":
                    parts.append(f"p{p}:YES")
                elif l == "partial":
                    parts.append(f"p{p}:some")
                else:
                    parts.append(f"p{p}:blank")
            summary = f"{filled_count}/{total_pages} filled — {' '.join(parts)}"

        display_name = name if name else f"(student #{i+1})"
        print(f"{i+1:<4} {display_name:<30} {f'{start+1}-{end}':>6}  {summary}")
        results.append((i+1, name, filled_count, total_pages))

    # Summary
    all_filled = sum(1 for r in results if r[2] == r[3])
    some = sum(1 for r in results if 0 < r[2] < r[3])
    blank = sum(1 for r in results if r[2] == 0)

    print(f"\n{'='*75}")
    print(f"  Complete: {all_filled}  |  Partial: {some}  |  Blank: {blank}  |  Total: {len(results)}")
    print(f"{'='*75}")

    doc.close()

if __name__ == "__main__":
    main()
