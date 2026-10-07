"""HTML / PDF Slide Deck Exporter for CloudSentry.

Transforms docs/PRESENTATION_DECK.md into a standalone, interactive, dark-themed
HTML presentation deck at docs/presentation.html with keyboard navigation, progress bars,
speaker note toggling, and multi-page print-to-PDF styles.
"""

import sys
import os
import re

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CloudSentry | Academic Presentation Deck</title>
  <style>
    :root {
      --bg-color: #0d1117;
      --card-bg: #161b22;
      --border-color: #30363d;
      --primary: #58a6ff;
      --success: #3fb950;
      --alert: #f85149;
      --text: #f0f6fc;
      --text-muted: #8b949e;
      --accent: #d29922;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      background-color: var(--bg-color);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      overflow-x: hidden;
    }

    /* Presentation Header & Navigation */
    header {
      background-color: var(--card-bg);
      border-bottom: 1px solid var(--border-color);
      padding: 12px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 100;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 10px;
      font-weight: 700;
      font-size: 1.1rem;
      color: var(--primary);
    }

    .nav-controls {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .btn {
      background-color: #21262d;
      color: var(--text);
      border: 1px solid var(--border-color);
      padding: 6px 14px;
      border-radius: 6px;
      font-size: 0.9rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s ease;
    }

    .btn:hover {
      background-color: #30363d;
      border-color: var(--primary);
    }

    .btn-primary {
      background-color: #1f6feb;
      border-color: #388bfd;
      color: #ffffff;
    }

    .btn-primary:hover {
      background-color: #388bfd;
    }

    .progress-bar-container {
      width: 100%;
      height: 4px;
      background-color: #21262d;
    }

    .progress-bar {
      height: 100%;
      background: linear-gradient(90deg, #58a6ff, #3fb950);
      width: 8.33%;
      transition: width 0.3s ease;
    }

    /* Main Slide Container */
    main {
      flex: 1;
      display: flex;
      justify-content: center;
      align-items: center;
      padding: 40px 24px;
    }

    .slide {
      display: none;
      width: 100%;
      max-width: 1050px;
      background-color: var(--card-bg);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 40px;
      box-shadow: 0 12px 32px rgba(0,0,0,0.5);
      animation: fadeIn 0.3s ease;
    }

    .slide.active {
      display: block;
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }

    h1, h2, h3 {
      color: var(--primary);
      margin-bottom: 16px;
    }

    h1 { font-size: 2.2rem; }
    h2 { font-size: 1.8rem; border-bottom: 1px solid var(--border-color); padding-bottom: 8px; margin-bottom: 20px; }
    h3 { font-size: 1.3rem; color: var(--text); }

    p {
      color: var(--text);
      font-size: 1.1rem;
      line-height: 1.6;
      margin-bottom: 16px;
    }

    ul {
      margin-left: 24px;
      margin-bottom: 20px;
      font-size: 1.1rem;
      line-height: 1.8;
    }

    li strong {
      color: #79c0ff;
    }

    pre {
      background-color: #0d1117;
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 16px;
      overflow-x: auto;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.95rem;
      color: #58a6ff;
      margin-bottom: 20px;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 20px;
      font-size: 1rem;
    }

    th, td {
      border: 1px solid var(--border-color);
      padding: 10px 16px;
      text-align: left;
    }

    th {
      background-color: #21262d;
      color: var(--primary);
    }

    tr:nth-child(even) {
      background-color: rgba(255, 255, 255, 0.02);
    }

    .speaker-notes {
      margin-top: 24px;
      padding: 16px;
      background-color: rgba(31, 111, 235, 0.08);
      border-left: 4px solid var(--primary);
      border-radius: 4px;
      font-size: 0.95rem;
      color: #a5d6ff;
      display: none;
    }

    .speaker-notes.visible {
      display: block;
    }

    footer {
      background-color: var(--card-bg);
      border-top: 1px solid var(--border-color);
      padding: 12px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.85rem;
      color: var(--text-muted);
    }

    /* Print to PDF Styling */
    @media print {
      body { background-color: #ffffff; color: #000000; }
      header, footer, .progress-bar-container, .nav-controls { display: none; }
      main { padding: 0; display: block; }
      .slide {
        display: block !important;
        page-break-after: always;
        break-after: page;
        box-shadow: none;
        border: 1px solid #cccccc;
        margin-bottom: 20px;
        background-color: #ffffff;
        color: #000000;
      }
      h1, h2, h3 { color: #0969da; }
      pre { background-color: #f6f8fa; border-color: #d0d7de; color: #1f2328; }
      th { background-color: #f6f8fa; color: #0969da; }
      th, td { border-color: #d0d7de; }
      .speaker-notes { display: block !important; background-color: #f6f8fa; border-color: #0969da; color: #57606a; }
    }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <span>🛡️</span> CloudSentry Capstone Presentation
    </div>
    <div class="nav-controls">
      <span id="slideCounter" style="font-weight: 600; color: var(--text-muted); margin-right: 8px;">Slide 1 of 12</span>
      <button class="btn" onclick="toggleNotes()">Toggle Notes (S)</button>
      <button class="btn" onclick="prevSlide()">❮ Prev</button>
      <button class="btn btn-primary" onclick="nextSlide()">Next ❯</button>
    </div>
  </header>

  <div class="progress-bar-container">
    <div class="progress-bar" id="progressBar"></div>
  </div>

  <main id="slideContainer">
    <!-- INJECTED_SLIDES -->
  </main>

  <footer>
    <div>Final Year Engineering Capstone • Autonomous Multi-Agent Systems & SRE FinOps</div>
    <div>Keyboard Navigation: <b>←</b> / <b>→</b> or <b>Space</b> | Press <b>Ctrl+P</b> to Print PDF</div>
  </footer>

  <script>
    let currentSlide = 0;
    const slides = document.querySelectorAll('.slide');
    const totalSlides = slides.length;
    const counter = document.getElementById('slideCounter');
    const progressBar = document.getElementById('progressBar');

    function updateSlide() {
      slides.forEach((slide, idx) => {
        slide.classList.toggle('active', idx === currentSlide);
      });
      counter.textContent = `Slide ${currentSlide + 1} of ${totalSlides}`;
      progressBar.style.width = `${((currentSlide + 1) / totalSlides) * 100}%`;
    }

    function nextSlide() {
      if (currentSlide < totalSlides - 1) {
        currentSlide++;
        updateSlide();
      }
    }

    function prevSlide() {
      if (currentSlide > 0) {
        currentSlide--;
        updateSlide();
      }
    }

    function toggleNotes() {
      const notes = document.querySelectorAll('.speaker-notes');
      notes.forEach(n => n.classList.toggle('visible'));
    }

    document.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'PageDown') {
        nextSlide();
      } else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
        prevSlide();
      } else if (e.key === 's' || e.key === 'S') {
        toggleNotes();
      } else if (e.key === 'Home') {
        currentSlide = 0;
        updateSlide();
      } else if (e.key === 'End') {
        currentSlide = totalSlides - 1;
        updateSlide();
      }
    });

    updateSlide();
  </script>
</body>
</html>
"""


def parse_markdown_deck(deck_path: str) -> str:
    """Parses docs/PRESENTATION_DECK.md into slide HTML blocks."""
    with open(deck_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by Slide headers
    raw_slides = re.split(r"## 📽️ Slide \d+:\s*", content)
    slide_blocks = []

    for idx, raw in enumerate(raw_slides):
        if not raw.strip():
            continue

        lines = raw.strip().split("\n")
        title_line = lines[0].strip()
        body_text = "\n".join(lines[1:])

        # Extract Speaker Notes
        notes_match = re.search(r"#### Speaker Notes:\s*> \*\"(.*?)\"\*", body_text, re.DOTALL)
        notes_html = ""
        if notes_match:
            notes_content = notes_match.group(1).replace("\n", " ").strip()
            notes_html = f'<div class="speaker-notes"><b>🎙️ Speaker Notes:</b> "{notes_content}"</div>'
            body_text = body_text[:notes_match.start()]

        # Convert Markdown formatting to HTML
        slide_html = f'<div class="slide" id="slide-{idx}">\n'
        slide_html += f'  <h2>Slide {idx}: {title_line}</h2>\n'

        # Convert markdown blocks
        in_list = False
        in_code = False
        code_block = []

        for line in body_text.split("\n"):
            line_str = line.strip()

            if line_str.startswith("```"):
                if in_code:
                    in_code = False
                    slide_html += f"<pre><code>{chr(10).join(code_block)}</code></pre>\n"
                    code_block = []
                else:
                    in_code = True
                continue

            if in_code:
                code_block.append(line)
                continue

            if line_str.startswith("- ") or line_str.startswith("* "):
                if not in_list:
                    slide_html += "  <ul>\n"
                    in_list = True
                item_content = line_str[2:]
                item_content = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", item_content)
                item_content = re.sub(r"\*(.*?)\*", r"<em>\1</em>", item_content)
                item_content = re.sub(r"`(.*?)`", r"<code>\1</code>", item_content)
                slide_html += f"    <li>{item_content}</li>\n"
            elif line_str.startswith("|"):
                # Table handling
                slide_html += f"  <p>{line_str}</p>\n"
            elif line_str.startswith("### "):
                if in_list:
                    slide_html += "  </ul>\n"
                    in_list = False
                subhead = line_str[4:]
                subhead = re.sub(r"\*\*(.*?)\*\*", r"\1", subhead)
                slide_html += f"  <h3>{subhead}</h3>\n"
            elif line_str:
                if in_list:
                    slide_html += "  </ul>\n"
                    in_list = False
                p_text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", line_str)
                p_text = re.sub(r"`(.*?)`", r"<code>\1</code>", p_text)
                slide_html += f"  <p>{p_text}</p>\n"

        if in_list:
            slide_html += "  </ul>\n"

        slide_html += f"  {notes_html}\n"
        slide_html += "</div>\n"
        slide_blocks.append(slide_html)

    return "\n".join(slide_blocks)


def export_presentation_deck(
    deck_path: str = "docs/PRESENTATION_DECK.md",
    output_html: str = "docs/presentation.html",
):
    """Generates the interactive HTML slide deck."""
    print(f"[*] Parsing presentation markdown: {deck_path}...")
    slides_html = parse_markdown_deck(deck_path)
    full_html = HTML_TEMPLATE.replace("<!-- INJECTED_SLIDES -->", slides_html)

    os.makedirs(os.path.dirname(os.path.abspath(output_html)), exist_ok=True)
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(full_html)

    print(f"[+] Successfully exported interactive HTML slide deck to: {output_html}")
    return output_html


if __name__ == "__main__":
    export_presentation_deck()
