#!/usr/bin/env python3
"""Render a Markdown document to a print-quality PDF.

    python3 tools/md2pdf.py ARCHITECTURE.md ARCHITECTURE.pdf

Markdown -> HTML (python-markdown) -> PDF (headless Chromium via Playwright).
A committed binary that cannot be regenerated is worse than no binary, so this
script is the recipe for the PDF in the repository root.

Requires: pip install markdown playwright, and a Chromium that Playwright can
find. Set LEDGER_CHROME to point at a specific binary; otherwise Playwright's
own bundled Chromium is used.
"""
import html as _html
import pathlib
import sys

import markdown

SRC = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "ARCHITECTURE.md")
OUT = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "ARCHITECTURE.pdf")
import os
import tempfile

SCRATCH = pathlib.Path(tempfile.mkdtemp(prefix="md2pdf-"))
CHROME = os.environ.get("LEDGER_CHROME") or None  # None -> Playwright default

text = SRC.read_text(encoding="utf-8")

# The file opens with "# ARCHITECTURE" and a lead paragraph; promote those into
# a proper title block and drop the first horizontal rule so the cover reads as
# a cover rather than as section zero.
lines = text.split("\n")
assert lines[0].startswith("# "), "expected a level-1 heading on line 1"
title = lines[0][2:].strip()
rest = "\n".join(lines[1:]).lstrip("\n")
lead, _, body_md = rest.partition("\n---\n")

md = markdown.Markdown(
    extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
    output_format="html5",
)
lead_html = md.convert(lead.strip())
md.reset()
body_html = md.convert(body_md.strip())

# The "---" separators in the source are section dividers. In print they are
# redundant with a page break, so they are hidden and the break is driven off
# the <h2> itself -- a zero-height <hr> is not a reliable break anchor.

CSS = """
/* Tuned for a 3-4 page document. The content is dense and mostly tables, so
   the layout is compressed rather than the text cut: tighter leading, smaller
   table type, no per-section page breaks. */
@page { size: A4; margin: 12mm 12mm 14mm 12mm; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  font-family: "Bitstream Charter", "DejaVu Serif", serif;
  font-size: 8.5pt;
  line-height: 1.33;
  color: #1a1a1a;
  margin: 0;
  hyphens: none;
}

/* ---- masthead ---- */
.cover { margin: 0 0 3mm 0; }
.cover h1 {
  font-family: "DejaVu Sans", sans-serif;
  font-size: 17pt; font-weight: 700; letter-spacing: -0.3pt;
  margin: 0; color: #111; display: inline;
}
.cover .sub {
  font-family: "DejaVu Sans", sans-serif;
  font-size: 7.5pt; color: #777; letter-spacing: 1.1pt;
  text-transform: uppercase; display: inline; margin-left: 3mm;
}
.cover .lead p { font-size: 8.5pt; color: #333; margin: 1.5mm 0 0 0; }
.rule { border: 0; border-top: 1.5px solid #111; margin: 2.5mm 0 0 0; }

/* ---- headings: no page breaks, tight spacing ---- */
body > hr { display: none; }
h2 {
  font-family: "DejaVu Sans", sans-serif;
  font-size: 11pt; font-weight: 700; color: #111;
  margin: 5mm 0 2mm 0; padding-bottom: 1.2mm;
  border-bottom: 1px solid #c8c8c8;
  break-after: avoid; break-inside: avoid;
}
body > h2:first-of-type { margin-top: 3mm; }
h3 {
  font-family: "DejaVu Sans", sans-serif;
  font-size: 9pt; font-weight: 700; color: #222;
  margin: 3.2mm 0 1.4mm 0;
  break-after: avoid; break-inside: avoid;
}
p { margin: 0 0 1.7mm 0; orphans: 2; widows: 2; }

ul, ol { margin: 0 0 1.8mm 0; padding-left: 4.5mm; }
li { margin-bottom: 0.8mm; orphans: 2; widows: 2; }
li > p { margin-bottom: 0.7mm; }

code {
  font-family: "DejaVu Sans Mono", monospace;
  font-size: 7.2pt; background: #f2f3f5;
  padding: 0.2mm 0.7mm; border-radius: 2px; color: #23303d;
}
pre {
  background: #f7f8fa; border: 1px solid #e0e3e8; border-left: 2.5px solid #8b97a8;
  border-radius: 2px; padding: 1.8mm 2.5mm; margin: 0 0 2mm 0;
  break-inside: avoid; white-space: pre-wrap; word-wrap: break-word;
}
pre code { background: none; padding: 0; font-size: 7.2pt; line-height: 1.35; }

table {
  width: 100%; border-collapse: collapse; margin: 0 0 2.4mm 0;
  font-family: "DejaVu Sans", sans-serif;
  font-size: 6.9pt; line-height: 1.28; break-inside: auto;
}
thead { display: table-header-group; }
tr { break-inside: avoid; }
th {
  background: #ebedf0; text-align: left; font-weight: 700; color: #111;
  padding: 1mm 1.4mm; border: 1px solid #ccd0d6;
}
td { padding: 1mm 1.4mm; border: 1px solid #dde0e5; vertical-align: top; }
tbody tr:nth-child(even) td { background: #fafbfc; }
td code, th code { font-size: 6.4pt; background: #e9ebef; padding: 0 0.5mm; }

strong { font-weight: 700; color: #000; }
a { color: #1a4d8f; text-decoration: none; }
"""

doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{_html.escape(title)}</title>
<style>{CSS}</style></head>
<body>
<div class="cover">
  <h1>{_html.escape(title)}</h1>
  <div class="sub">In-memory account ledger core</div>
  <div class="lead">{lead_html}</div>
  <hr class="rule">
</div>
{body_html}
</body></html>
"""

tmp_html = SCRATCH / "architecture.html"
tmp_html.write_text(doc, encoding="utf-8")

# Chromium's CLI --print-to-pdf cannot set a custom footer, and its default
# footer prints the file:// URL. Driving it through Playwright's printToPDF
# gives a real page-number footer instead.
from playwright.sync_api import sync_playwright

FOOTER = """
<div style="width:100%;font-family:'DejaVu Sans',sans-serif;font-size:7.5pt;
            color:#8a8a8a;padding:0 17mm;display:flex;
            justify-content:space-between;">
  <span>ARCHITECTURE &middot; in-memory account ledger core</span>
  <span><span class="pageNumber"></span> / <span class="totalPages"></span></span>
</div>"""

with sync_playwright() as pw:
    launch_kwargs = {"executable_path": CHROME} if CHROME else {}
    browser = pw.chromium.launch(**launch_kwargs)
    page = browser.new_page()
    page.goto(tmp_html.resolve().as_uri(), wait_until="networkidle")
    page.pdf(
        path=str(OUT.resolve()),
        format="A4",
        print_background=True,
        display_header_footer=True,
        header_template="<div></div>",
        footer_template=FOOTER,
        margin={"top": "20mm", "bottom": "20mm", "left": "17mm", "right": "17mm"},
    )
    browser.close()

if not OUT.exists():
    sys.exit("PDF was not produced")
print(f"wrote {OUT} ({OUT.stat().st_size/1024:.0f} KB)")
