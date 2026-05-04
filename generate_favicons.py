"""Generate PNG and ICO favicon files for Himaya.
Draws the logo directly with Pillow — zero system-library dependencies.
"""
import subprocess, sys

def _pip(*args):
    subprocess.check_call([sys.executable, "-m", "pip", "install", *args],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Installing Pillow...")
    _pip("Pillow")
    from PIL import Image, ImageDraw

from pathlib import Path

OUT = Path("public")

C1 = (0x5A, 0xDE, 0x7A)  # #5ADE7A  top-left
C2 = (0x0D, 0x9E, 0x6E)  # #0D9E6E  bottom-right


def _gradient(size: int) -> Image.Image:
    denom = max(1, 2 * (size - 1))
    pixels = []
    for y in range(size):
        for x in range(size):
            t = (x + y) / denom
            pixels.append((
                int(C1[0] + (C2[0] - C1[0]) * t),
                int(C1[1] + (C2[1] - C1[1]) * t),
                int(C1[2] + (C2[2] - C1[2]) * t),
                255,
            ))
    img = Image.new("RGBA", (size, size))
    img.putdata(pixels)
    return img


def _qbez(p0, p1, p2, n=40):
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        pts.append((u*u*p0[0] + 2*u*t*p1[0] + t*t*p2[0],
                     u*u*p0[1] + 2*u*t*p1[1] + t*t*p2[1]))
    return pts


def _render(size: int) -> Image.Image:
    s = size / 512.0

    # Gradient background
    bg = _gradient(size)

    # Rounded rectangle mask  (rx=114 in 512-space)
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    rx = int(114 * s)
    try:
        md.rounded_rectangle([0, 0, size - 1, size - 1], radius=rx, fill=255)
    except AttributeError:
        # Pillow < 8.2 fallback
        md.rectangle([rx, 0, size - 1 - rx, size - 1], fill=255)
        md.rectangle([0, rx, size - 1, size - 1 - rx], fill=255)
        for cx, cy in [(rx, rx), (size-1-rx, rx), (rx, size-1-rx), (size-1-rx, size-1-rx)]:
            md.ellipse([cx-rx, cy-rx, cx+rx, cy+rx], fill=255)
    bg.putalpha(mask)

    draw = ImageDraw.Draw(bg)
    W = (255, 255, 255, 255)

    # Shield outline
    # SVG: M146,172 Q256,118 366,172 L366,268 Q366,350 256,396 Q146,350 146,268 Z
    pts = []
    pts += _qbez((146, 172), (256, 118), (366, 172))
    pts.append((366, 268))
    pts += _qbez((366, 268), (366, 350), (256, 396))[1:]
    pts += _qbez((256, 396), (146, 350), (146, 268))[1:]
    pts.append((146, 172))
    pts_px = [(x * s, y * s) for x, y in pts]
    draw.line(pts_px, fill=W, width=max(1, int(26 * s)))

    # Checkmark
    ck = [(206*s, 262*s), (242*s, 298*s), (312*s, 220*s)]
    draw.line(ck, fill=W, width=max(1, int(28 * s)))

    return bg


def create_icon(size: int) -> Image.Image:
    # 2x supersampling for clean edges on larger sizes
    if size >= 48:
        return _render(size * 2).resize((size, size), Image.LANCZOS)
    return _render(size)


sizes = {
    "favicon-32.png": 32,
    "favicon-192.png": 192,
    "favicon-512.png": 512,
    "apple-touch-icon.png": 180,
}

for filename, sz in sizes.items():
    print(f"  {filename} ({sz}×{sz})…", end=" ", flush=True)
    create_icon(sz).save(str(OUT / filename))
    print("done")

print("  favicon.ico (16, 32, 48)…", end=" ", flush=True)
frames = [create_icon(sz) for sz in (16, 32, 48)]
frames[0].save(str(OUT / "favicon.ico"), format="ICO",
               sizes=[(f.width, f.height) for f in frames],
               append_images=frames[1:])
print("done")

print("\nAll favicon files written to public/")
