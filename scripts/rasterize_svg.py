"""Rasterize the viral photo SVG from firebreak-ui.html into data/viral.png.

Strips the dashed evidence boxes and number tags first, so Gemini sees a clean image.
Writes data/viral.svg, then renders it with resvg (Node) instead of cairosvg,
which needs native Cairo DLLs on Windows. The PNG is committed, so this only
needs rerunning if the SVG changes.

Run: npm install --prefix scripts/.node @resvg/resvg-js@2.6.2
     python scripts/rasterize_svg.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "firebreak-ui.html"
OUT = ROOT / "data" / "viral.png"
W, H = 1080, 660  # SVG viewBox is 360x220

RENDER_JS = """
const {Resvg} = require('@resvg/resvg-js');
const fs = require('fs');
const svg = fs.readFileSync(process.argv[2], 'utf8');
const png = new Resvg(svg, {fitTo: {mode: 'width', value: %d}, font: {loadSystemFonts: true}}).render().asPng();
fs.writeFileSync(process.argv[3], png);
""" % W


def clean_svg(html: str) -> str:
    m = re.search(r'<div class="photo">\s*(<svg.*?</svg>)', html, re.S)
    if not m:
        sys.exit("Could not find the <svg> inside .photo")
    svg = m.group(1)
    # dashed boxes group and number tags group
    svg = re.sub(r'<g fill="none" stroke="#5cc8ff".*?</g>', "", svg, flags=re.S)
    svg = re.sub(r'<g font-family="IBM Plex Mono.*?</g>', "", svg, flags=re.S)
    svg = re.sub(r'\s(role|aria-label)="[^"]*"', "", svg)
    return svg.replace("<svg ", f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" ', 1)


def main():
    svg = clean_svg(SRC.read_text(encoding="utf-8"))
    svg_path = OUT.with_suffix(".svg")
    svg_path.write_text(svg, encoding="utf-8")
    node_dir = Path(__file__).parent / ".node"
    if not (node_dir / "node_modules" / "@resvg").exists():
        sys.exit(f"Wrote {svg_path}. To make the PNG: npm install --prefix scripts/.node @resvg/resvg-js@2.6.2")
    js = node_dir / "render.js"
    js.write_text(RENDER_JS, encoding="utf-8")
    subprocess.run(["node", str(js), str(svg_path), str(OUT)], check=True, cwd=node_dir)
    print(f"Wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
