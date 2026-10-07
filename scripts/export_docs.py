"""Publication-Grade Document & Synopsis HTML/PDF Exporter for CloudSentry.

Transforms docs/PROJECT_REPORT.md and docs/PROJECT_SYNOPSIS.md into clean,
publication-standard HTML documents with comprehensive print stylesheets
for instant, flawless Ctrl+P PDF generation.
"""

import sys
import os
import re

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


DOC_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{TITLE}} | CloudSentry</title>
  <style>
    :root {
      --font-main: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      --font-mono: ui-monospace, SFMono-Regular, "Cascadia Code", "Courier New", monospace;
      --text-color: #1f2328;
      --heading-color: #0969da;
      --border-color: #d0d7de;
      --bg-light: #f6f8fa;
      --code-bg: #f6f8fa;
      --primary: #0969da;
      --accent: #1a7f37;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      font-family: var(--font-main);
      color: var(--text-color);
      line-height: 1.65;
      font-size: 15px;
      background-color: #ffffff;
      padding: 40px 20px;
    }

    .container {
      max-width: 920px;
      margin: 0 auto;
      background: #ffffff;
    }

    /* Header & Document Title */
    .doc-header {
      border-bottom: 2px solid var(--border-color);
      padding-bottom: 24px;
      margin-bottom: 32px;
    }

    .doc-badge {
      display: inline-block;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      padding: 4px 10px;
      background-color: #ddf4ff;
      color: #0969da;
      border: 1px solid #54aeff;
      border-radius: 20px;
      margin-bottom: 12px;
    }

    h1 {
      font-size: 2.2rem;
      color: #1f2328;
      line-height: 1.25;
      margin-bottom: 12px;
    }

    h2 {
      font-size: 1.5rem;
      color: var(--heading-color);
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 6px;
      margin-top: 36px;
      margin-bottom: 16px;
      page-break-after: avoid;
    }

    h3 {
      font-size: 1.2rem;
      color: #24292f;
      margin-top: 24px;
      margin-bottom: 10px;
      page-break-after: avoid;
    }

    h4 {
      font-size: 1.05rem;
      color: #57606a;
      margin-top: 18px;
      margin-bottom: 8px;
    }

    p {
      margin-bottom: 14px;
      text-align: justify;
    }

    strong {
      color: #1f2328;
      font-weight: 600;
    }

    em {
      font-style: italic;
    }

    ul, ol {
      margin-left: 24px;
      margin-bottom: 16px;
    }

    li {
      margin-bottom: 6px;
    }

    /* Math and Code Blocks */
    code {
      font-family: var(--font-mono);
      font-size: 0.9em;
      background-color: var(--code-bg);
      border: 1px solid var(--border-color);
      border-radius: 4px;
      padding: 2px 6px;
      color: #0969da;
    }

    pre {
      background-color: var(--code-bg);
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 14px 16px;
      font-family: var(--font-mono);
      font-size: 13px;
      line-height: 1.5;
      overflow-x: auto;
      margin-bottom: 18px;
      page-break-inside: avoid;
    }

    pre code {
      background: none;
      border: none;
      padding: 0;
      color: #1f2328;
    }

    /* Tables */
    table {
      width: 100%;
      border-collapse: collapse;
      margin: 20px 0;
      font-size: 14px;
      page-break-inside: avoid;
    }

    th, td {
      border: 1px solid var(--border-color);
      padding: 8px 12px;
      text-align: left;
    }

    th {
      background-color: var(--bg-light);
      font-weight: 600;
      color: #24292f;
    }

    tr:nth-child(even) {
      background-color: #fafbfc;
    }

    /* Blockquotes & Callouts */
    blockquote {
      border-left: 4px solid var(--primary);
      background-color: #f6f8fa;
      padding: 12px 18px;
      margin-bottom: 16px;
      border-radius: 0 6px 6px 0;
      color: #57606a;
      font-style: italic;
    }

    hr {
      border: 0;
      height: 1px;
      background: var(--border-color);
      margin: 28px 0;
    }

    /* Action bar on top for browser view */
    .print-bar {
      position: sticky;
      top: 0;
      background: #ffffff;
      padding: 10px 0;
      border-bottom: 1px solid var(--border-color);
      margin-bottom: 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      z-index: 100;
    }

    .btn-print {
      background-color: #0969da;
      color: #ffffff;
      border: none;
      padding: 8px 16px;
      border-radius: 6px;
      font-weight: 600;
      cursor: pointer;
      font-size: 14px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: background-color 0.2s ease;
    }

    .btn-print:hover {
      background-color: #0854ad;
    }

    /* Print Styles */
    @media print {
      @page {
        size: A4;
        margin: 1.8cm 1.5cm;
      }

      body {
        padding: 0;
        font-size: 13px;
        line-height: 1.55;
        color: #000000;
      }

      .print-bar {
        display: none !important;
      }

      .container {
        max-width: 100%;
        margin: 0;
      }

      h1 { font-size: 1.8rem; }
      h2 { font-size: 1.3rem; margin-top: 24px; page-break-after: avoid; }
      h3 { font-size: 1.1rem; margin-top: 18px; page-break-after: avoid; }

      pre, table, blockquote {
        page-break-inside: avoid;
      }

      th {
        background-color: #f0f0f0 !important;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }

      tr:nth-child(even) {
        background-color: #fcfcfc !important;
      }

      a {
        text-decoration: none;
        color: #000000;
      }
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="print-bar">
      <div>
        <strong>CloudSentry Documentation</strong> • {{DOC_TYPE}}
      </div>
      <div>
        <button class="btn-print" onclick="window.print()">🖨️ Print / Save as PDF (Ctrl+P)</button>
      </div>
    </div>

    <div class="doc-header">
      <div class="doc-badge">{{DOC_BADGE}}</div>
      {{BODY_CONTENT}}
    </div>
  </div>
</body>
</html>
"""


def markdown_to_html_body(md_content: str) -> str:
    """Converts a standard Markdown document into semantic HTML elements."""
    lines = md_content.split("\n")
    html_lines = []
    
    in_code = False
    code_block = []
    in_list = False
    in_table = False
    table_rows = []

    def flush_table():
        nonlocal in_table, table_rows
        if not table_rows:
            in_table = False
            return ""
        
        t_html = "<table>\n"
        # First row is header
        header_cols = [c.strip() for c in table_rows[0].strip("|").split("|")]
        t_html += "  <thead>\n    <tr>\n"
        for col in header_cols:
            col_text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", col)
            col_text = re.sub(r"`(.*?)`", r"<code>\1</code>", col_text)
            t_html += f"      <th>{col_text}</th>\n"
        t_html += "    </tr>\n  </thead>\n  <tbody>\n"

        # Remaining rows (skip separator row at index 1)
        start_idx = 2 if len(table_rows) > 1 and "---" in table_rows[1] else 1
        for row_str in table_rows[start_idx:]:
            if not row_str.strip():
                continue
            cols = [c.strip() for c in row_str.strip("|").split("|")]
            t_html += "    <tr>\n"
            for col in cols:
                col_text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", col)
                col_text = re.sub(r"`(.*?)`", r"<code>\1</code>", col_text)
                t_html += f"      <td>{col_text}</td>\n"
            t_html += "    </tr>\n"
        t_html += "  </tbody>\n</table>\n"
        
        table_rows = []
        in_table = False
        return t_html

    for line in lines:
        line_str = line.rstrip()

        # Code Blocks
        if line_str.startswith("```"):
            if in_code:
                in_code = False
                escaped_code = (
                    "\n".join(code_block)
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                html_lines.append(f"<pre><code>{escaped_code}</code></pre>")
                code_block = []
            else:
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                if in_table:
                    html_lines.append(flush_table())
                in_code = True
            continue

        if in_code:
            code_block.append(line)
            continue

        # Tables
        if line_str.startswith("|") and line_str.endswith("|"):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            in_table = True
            table_rows.append(line_str)
            continue
        elif in_table:
            html_lines.append(flush_table())

        # Headers
        if line_str.startswith("# "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            h_text = line_str[2:].strip()
            html_lines.append(f"<h1>{h_text}</h1>")
        elif line_str.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            h_text = line_str[3:].strip()
            html_lines.append(f"<h2>{h_text}</h2>")
        elif line_str.startswith("### "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            h_text = line_str[4:].strip()
            html_lines.append(f"<h3>{h_text}</h3>")
        elif line_str.startswith("#### "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            h_text = line_str[5:].strip()
            html_lines.append(f"<h4>{h_text}</h4>")
        elif line_str.startswith("---"):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<hr>")
        elif line_str.startswith("> "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            b_text = line_str[2:].strip()
            b_text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", b_text)
            b_text = re.sub(r"`(.*?)`", r"<code>\1</code>", b_text)
            html_lines.append(f"<blockquote>{b_text}</blockquote>")
        elif line_str.startswith("- ") or line_str.startswith("* "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            item_text = line_str[2:].strip()
            item_text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", item_text)
            item_text = re.sub(r"\*(.*?)\*", r"<em>\1</em>", item_text)
            item_text = re.sub(r"`(.*?)`", r"<code>\1</code>", item_text)
            html_lines.append(f"  <li>{item_text}</li>")
        elif line_str:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            p_text = line_str
            p_text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", p_text)
            p_text = re.sub(r"\*(.*?)\*", r"<em>\1</em>", p_text)
            p_text = re.sub(r"`(.*?)`", r"<code>\1</code>", p_text)
            # LaTeX math delimiters
            p_text = re.sub(r"\$\$(.*?)\$\$", r"<div style='text-align: center; margin: 12px 0;'><code>\1</code></div>", p_text)
            p_text = re.sub(r"\$(.*?)\$", r"<code>\1</code>", p_text)
            html_lines.append(f"<p>{p_text}</p>")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False

    if in_list:
        html_lines.append("</ul>")
    if in_table:
        html_lines.append(flush_table())

    return "\n".join(html_lines)


def export_document(
    input_md: str,
    output_html: str,
    title: str,
    doc_type: str,
    doc_badge: str,
):
    """Compiles a markdown file to a printable publication-ready HTML file."""
    print(f"[*] Compiling document: {input_md} -> {output_html}...")
    if not os.path.exists(input_md):
        print(f"[!] Error: File not found: {input_md}")
        return False

    with open(input_md, "r", encoding="utf-8") as f:
        md_text = f.read()

    body_html = markdown_to_html_body(md_text)

    full_html = (
        DOC_HTML_TEMPLATE.replace("{{TITLE}}", title)
        .replace("{{DOC_TYPE}}", doc_type)
        .replace("{{DOC_BADGE}}", doc_badge)
        .replace("{{BODY_CONTENT}}", body_html)
    )

    os.makedirs(os.path.dirname(os.path.abspath(output_html)), exist_ok=True)
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(full_html)

    print(f"[+] Successfully exported printable HTML to: {output_html}")
    return True


def main():
    print("=" * 72)
    print(" [CLOUDSENTRY] ACADEMIC DOCUMENT & SYNOPSIS HTML EXPORTER")
    print("=" * 72)

    # 1. Export Project Synopsis
    export_document(
        input_md="docs/PROJECT_SYNOPSIS.md",
        output_html="docs/synopsis.html",
        title="Capstone Project Synopsis",
        doc_type="Executive Academic Synopsis",
        doc_badge="Academic Submission • Synopsis",
    )

    # 2. Export Project Report
    export_document(
        input_md="docs/PROJECT_REPORT.md",
        output_html="docs/report.html",
        title="Comprehensive Capstone Project Report",
        doc_type="Final Capstone Technical Report",
        doc_badge="Official Academic Capstone Report",
    )

    print("=" * 72)
    print("[+] All academic documentation compiled into printable HTML deliverables.")


if __name__ == "__main__":
    main()
