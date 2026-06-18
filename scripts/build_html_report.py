"""Build a self-contained report.html FROM REPORT.md (the source of truth).

Converts the markdown to HTML, inlines every results/charts/*.png as a base64 data
URI, and wraps it in the dark theme. Run after editing REPORT.md or regenerating
charts so the HTML never drifts from the markdown again.
"""
from __future__ import annotations
import base64
import re
from pathlib import Path
import markdown

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'REPORT.md'
OUT = ROOT / 'report.html'

CSS = """
  :root {
    --bg: #0e1116; --panel: #161b22; --panel2: #1e242c; --border: #2c333d;
    --text: #d7dadf; --muted: #8a9099; --accent: #59a6ff;
    --pass: #3ec97a; --warn: #e6b455; --fail: #e25c5c;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: var(--bg); color: var(--text);
               font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, system-ui, sans-serif;
               font-size: 15px; line-height: 1.6; }
  .wrap { max-width: 980px; margin: 0 auto; padding: 36px 28px 80px; }
  h1 { font-size: 26px; margin: 0 0 10px; color: #fff; letter-spacing: -0.01em; }
  h2 { font-size: 20px; margin: 36px 0 12px; color: #fff;
       padding-top: 14px; border-top: 1px solid var(--border); }
  h3 { font-size: 16px; margin: 24px 0 8px; color: var(--accent); }
  p { margin: 10px 0; }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }
  code { background: var(--panel2); padding: 2px 6px; border-radius: 4px;
         font-family: ui-monospace, SF Mono, Menlo, monospace; font-size: 13px;
         color: #ffb37a; }
  pre { background: var(--panel); padding: 14px 16px; border-radius: 6px;
        border: 1px solid var(--border); overflow-x: auto;
        font-family: ui-monospace, SF Mono, Menlo, monospace;
        font-size: 13px; line-height: 1.55; }
  pre code { background: transparent; padding: 0; color: var(--text); }
  table { border-collapse: collapse; width: 100%; margin: 14px 0;
          background: var(--panel); border-radius: 6px; overflow: hidden;
          border: 1px solid var(--border); }
  th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border);
           font-size: 13.5px; }
  th { background: var(--panel2); color: var(--muted); font-weight: 600;
       text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px; }
  tr:last-child td { border-bottom: 0; }
  strong { color: #fff; }
  blockquote { border-left: 3px solid var(--accent); margin: 14px 0;
               padding: 8px 16px; background: var(--panel); color: var(--text); }
  img { max-width: 100%; height: auto; display: block; margin: 18px auto;
        border-radius: 6px; border: 1px solid var(--border); background: #fff; }
  ul, ol { padding-left: 22px; }
  li { margin: 4px 0; }
  hr { border: 0; border-top: 1px solid var(--border); margin: 28px 0; }
  .footer { margin-top: 40px; padding-top: 18px; border-top: 1px solid var(--border);
            color: var(--muted); font-size: 12px; text-align: center; }
"""


def inline_images(html: str) -> str:
    def repl(m: re.Match) -> str:
        src = m.group('src')
        p = (ROOT / src).resolve()
        if not p.exists():
            print(f'[warn] image missing: {src}')
            return m.group(0)
        b64 = base64.b64encode(p.read_bytes()).decode('ascii')
        return m.group(0).replace(src, f'data:image/png;base64,{b64}')
    return re.sub(r'<img[^>]*src="(?P<src>[^"]+)"', repl, html)


def main() -> None:
    body = markdown.markdown(SRC.read_text(), extensions=['tables', 'fenced_code', 'sane_lists'])
    body = inline_images(body)
    html = (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<title>Sandbox scalability comparison — E2B vs hf-sandbox vs hf-rust vs hf-pool vs MCP</title>\n'
        f'<style>{CSS}</style>\n</head>\n<body>\n<div class="wrap">\n'
        f'{body}\n'
        '<div class="footer">Generated from <code>REPORT.md</code> · charts embedded as base64 · self-contained.</div>\n'
        '</div>\n</body>\n</html>\n'
    )
    OUT.write_text(html)
    print(f'[done] wrote {OUT}  ({OUT.stat().st_size / 1024:.0f} KB, self-contained)')


if __name__ == '__main__':
    main()
