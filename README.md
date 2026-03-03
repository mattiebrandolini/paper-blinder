# Paper Blinder

**Blind your papers locally. Grade them however you want.**

A local web app that takes a bulk-scanned PDF of student work, redacts the name zone, splits it into individual coded submissions, and gives you a private answer key. Student data never leaves your machine.

Use it with any grading workflow — AI-assisted (Claude, ChatGPT, Gemini, whatever fits your style), human TAs, or grade them yourself with bias reduction. The blinding step is universal. What comes after is up to you.

![Python](https://img.shields.io/badge/python-3.8+-blue) ![License](https://img.shields.io/badge/license-MIT-green)

## Why?

Existing solutions couple anonymization to a specific grading engine. If that engine doesn't match your pedagogy, your students, or your standards — you're stuck.

Paper Blinder separates the two steps:
1. **Blind once** — redact names, split papers, generate codes
2. **Grade with anything** — your choice of tool, model, or human

This matters especially for:
- Teachers in high-needs districts working with handwritten papers
- Classrooms where students don't submit digitally through an LMS
- Anyone who wants to pick their own grading tool without being locked in

## Features

- **Drag-and-drop web UI** — runs locally in your browser
- **Two split modes** — fixed page count, or landmark text detection
- **Rotation-aware redaction** — handles bulk scanner orientation quirks
- **AI name detection** — uses Qwen2.5-VL (local vision model via Ollama) to read handwritten names for your answer key
- **Text layer fallback** — if your scanner embeds searchable text, it uses that first
- **Private answer key** — CSV with detected names, you verify and fill in the rest
- **100% local** — nothing touches the internet. FERPA-safe by design.

## Setup

### Required
```bash
pip install flask PyMuPDF
```

### Optional (for AI name detection)
Install [Ollama](https://ollama.com), then:
```bash
ollama pull qwen2.5vl:7b
```

This runs a local vision-language model that reads handwritten names off the scanned papers. Without it, the tool still works — you just fill in names on the answer key manually.

**Hardware:** Any machine with 8GB+ VRAM can run the 7B model. Tested on NVIDIA RTX 5080 (laptop) and RTX 5090 (desktop).

## Usage

```bash
python paper_blinder.py
```

Opens your browser to `http://localhost:5757`. Then:

1. Drag in your bulk-scanned PDF
2. Pick your split mode:
   - **Fixed page count**: "every 3 pages is one student"
   - **Landmark text**: splits wherever a phrase like `"Part 1"` appears
3. Set the redaction zone (which edge, what percentage)
4. Hit **Blind the Papers**
5. Download the ZIP

You get:
```
blinded_papers.zip
├── BLINDED_a3f7c2.pdf    # individual papers (name redacted)
├── BLINDED_9b1e04.pdf
├── BLINDED_e7c431.pdf
├── ...
└── _ANSWER_KEY.csv       # YOUR EYES ONLY
```

The answer key looks like:
| code | submission_number | pages | detected_name | detection_method | confirmed_name |
|------|------------------|-------|---------------|-----------------|----------------|
| a3f7c2 | 1 | pp. 1-3 | Maria Garcia | vision-ai | |
| 9b1e04 | 2 | pp. 4-6 | Jaime R | vision-ai | |
| e7c431 | 3 | pp. 7-9 | | none | |

Fill in `confirmed_name` where the AI got it wrong or couldn't read it. Keep this file — it's your mapping.

## Grading workflow

1. **At school**: Scan the stack on the bulk copier → one big PDF
2. **At home**: Run Paper Blinder → get coded PDFs + answer key
3. **Grade**: Upload blinded PDFs to your AI tool of choice (or grade by hand). The grader never sees student names.
4. **Map back**: Use your answer key to match grades to students

## Tips

- **Landmark phrases**: If you add something like `=== START ===` to page 1 of each test, the tool auto-detects split points — no counting pages.
- **Redact percentage**: Default is 15% from the top. Adjust if your name field is lower or your header is bigger.
- **Scanner rotation**: If the redaction hits the wrong edge, try the edge selector dropdown. Bulk scanners sometimes store pages in unexpected orientations.
- **No OCR needed**: The tool works without Ollama — you just fill in names yourself. The vision model is a convenience, not a requirement.

## Built with

- [Flask](https://flask.palletsprojects.com/) — local web server
- [PyMuPDF](https://pymupdf.readthedocs.io/) — PDF processing
- [Qwen2.5-VL](https://github.com/QwenLM/Qwen2.5-VL) via [Ollama](https://ollama.com) — local vision AI for handwriting recognition

## License

MIT — use it, share it, adapt it.

---

*Made by a first-year teacher who needed to grade 75 papers without bias and without sending student names to the cloud.*
