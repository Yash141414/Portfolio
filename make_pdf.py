"""Convert a Markdown report to a styled PDF.

Renders the Markdown to HTML, then prints it with headless Chrome or Edge.

    python make_pdf.py                                   # the backtest report -> .pdf next to it
    python make_pdf.py report.md -o out.pdf --image results_options_1min/equity_curves.png

Needs: pip install markdown, and Chrome or Edge installed.
"""
import argparse
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

DEFAULT_MD = "NIFTY Intraday Options Three-Strategy Backtest Report.md"
DEFAULT_IMAGE = "results/equity_curves.png"
BROWSERS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome", "chromium", "chromium-browser", "msedge",
]

CSS = """
@page { size: A4; margin: 16mm 14mm 18mm; }
body { font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif; font-size: 10pt;
       line-height: 1.45; color: #1f2328; }
h1 { font-size: 20pt; margin: 0 0 4mm; padding-bottom: 2mm; border-bottom: 2px solid #1f4e79; color: #1f4e79; }
h2 { font-size: 14pt; margin: 7mm 0 2mm; color: #1f4e79; break-after: avoid; }
h3 { font-size: 11.5pt; margin: 5mm 0 1.5mm; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
p { margin: 0 0 2.5mm; }
ul, ol { margin: 0 0 2.5mm; padding-left: 6mm; }
li { margin-bottom: 1mm; }
ul > li::marker { content: "\\2022  "; color: #1f4e79; }
p:has(+ table), p:has(+ img), p:has(+ p > img) { break-after: avoid; }
table { border-collapse: collapse; width: 99.6%; margin: 2mm 0 4mm; font-size: 8.5pt; break-inside: avoid; }
th, td { border: 1px solid #d0d7de; padding: 1.2mm 1.8mm; text-align: left; vertical-align: top; }
th { background: #eef3f8; font-weight: 600; }
tr:nth-child(even) td { background: #fafbfc; }
code { font-family: Consolas, "Courier New", monospace; font-size: 8.5pt; background: #f2f4f6;
       padding: 0.2mm 1mm; border-radius: 2px; }
pre { background: #f2f4f6; padding: 2.5mm; border-radius: 3px; white-space: pre-wrap; break-inside: avoid; }
pre code { padding: 0; background: none; }
img { max-width: 100%; display: block; margin: 3mm auto; break-inside: avoid; }
.math { text-align: center; margin: 3mm 0; font-size: 11pt; }
"""

# KaTeX renders ```latex blocks; without a network connection the raw TeX is shown instead.
KATEX = """
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script>
window.addEventListener('load', () => {
  if (!window.katex) return;
  document.querySelectorAll('.math').forEach(el => {
    try { katex.render(el.textContent, el, {displayMode: true, throwOnError: false}); } catch (e) {}
  });
});
</script>
"""


def preprocess(text: str, image: str | None) -> str:
    """Fix the parts of an exported doc that plain Markdown can't show."""
    # chart placeholders left by the doc export -> the equity-curve PNG
    placeholder = re.compile(r"^(?:&#91;|\\?\[)embedded content:.*$", re.M)
    text = placeholder.sub(lambda _: f"![Equity curves]({image})" if image else "", text)

    # ```latex blocks -> a div KaTeX can render
    def math(m):
        return f'<div class="math">{html.escape(m.group(1).strip())}</div>'
    text = re.sub(r"^```latex\n(.*?)\n```", math, text, flags=re.S | re.M)

    # task-list checkboxes
    text = re.sub(r"^(\s*)- \[ \] ", r"\1- ☐ ", text, flags=re.M)
    return re.sub(r"^(\s*)- \[x\] ", r"\1- ☑ ", text, flags=re.M | re.I)


def find_browser(explicit: str | None) -> str:
    for b in ([explicit] if explicit else BROWSERS):
        path = b if os.path.isfile(b) else shutil.which(b)
        if path:
            return path
    sys.exit("No Chrome or Edge found; pass its path with --browser")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", nargs="?", default=DEFAULT_MD)
    ap.add_argument("-o", "--output", help="PDF path (default: input with .pdf)")
    ap.add_argument("--image", default=DEFAULT_IMAGE,
                    help=f"image to show in place of embedded-chart placeholders (default {DEFAULT_IMAGE})")
    ap.add_argument("--browser", help="path to chrome.exe or msedge.exe")
    a = ap.parse_args()

    src = Path(a.input).resolve()
    out = Path(a.output).resolve() if a.output else src.with_suffix(".pdf")
    image = a.image if a.image and (src.parent / a.image).exists() else None
    if a.image and not image:
        print(f"note: {a.image} not found, chart placeholders removed")

    text = preprocess(src.read_text(encoding="utf-8"), image)
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
    title = re.search(r"^# (.+)$", text, re.M)
    page = (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{html.escape(title.group(1) if title else src.stem)}</title>"
            f"<style>{CSS}</style>{KATEX}</head><body>{body}</body></html>")

    # the HTML sits next to the .md so relative image paths resolve
    fd, tmp = tempfile.mkstemp(suffix=".html", dir=src.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(page)
        subprocess.run([find_browser(a.browser), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        "--virtual-time-budget=10000", f"--print-to-pdf={out}", Path(tmp).as_uri()],
                       check=True, capture_output=True, timeout=120)
    finally:
        os.remove(tmp)
    if not out.exists():
        sys.exit("browser exited without writing the PDF")
    print(f"PDF -> {out}")


if __name__ == "__main__":
    main()
