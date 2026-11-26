"""Draw the TMD WRF Forecast brand images (icon, logo, dark variants) and the README logo.

The artwork is drawn in code: a night-blue tile with a model grid, a gold sun, a cloud and rain.
If a square .png/.jpg is placed in brand_src/, it is used instead of the drawing.
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "custom_components" / "tmd_wrf" / "brand"
DOCS = ROOT / "docs" / "images"
S = 1024  # drawing size


def draw() -> Image.Image:
    im = Image.new("RGBA", (S, S))
    px = im.load()
    for y in range(S):  # vertical gradient, night blue to deep teal
        t = y / S
        c = (int(10 + 8 * t), int(24 + 40 * t), int(52 + 40 * t), 255)
        for x in range(S):
            px[x, y] = c
    d = ImageDraw.Draw(im)
    # model grid in perspective, fading out towards the top
    for i in range(-6, 17):
        x0 = S / 2 + (i - 5) * 150
        d.line([(S / 2 + (i - 5) * 40, S * 0.56), (x0, S)], fill=(80, 170, 220, 70), width=4)
    for k in range(8):
        y = S * 0.56 + (S * 0.44) * (k / 7) ** 1.6
        d.line([(0, y), (S, y)], fill=(80, 170, 220, 40 + 8 * k), width=4)
    # sun with glow
    glow = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(glow)
    cx, cy, r = S * 0.64, S * 0.34, S * 0.17
    gd.ellipse([cx - r * 1.7, cy - r * 1.7, cx + r * 1.7, cy + r * 1.7], fill=(255, 190, 60, 120))
    glow = glow.filter(ImageFilter.GaussianBlur(60))
    im.alpha_composite(glow)
    d = ImageDraw.Draw(im)
    for a in range(0, 360, 30):  # rays
        ra = math.radians(a)
        d.line([(cx + math.cos(ra) * r * 1.25, cy + math.sin(ra) * r * 1.25), (cx + math.cos(ra) * r * 1.55, cy + math.sin(ra) * r * 1.55)],
               fill=(255, 200, 70, 255), width=22)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 196, 54, 255))
    d.ellipse([cx - r * 0.72, cy - r * 0.78, cx + r * 0.2, cy - r * 0.1], fill=(255, 226, 130, 120))
    # cloud
    cloud = Image.new("RGBA", (S, S))
    cd = ImageDraw.Draw(cloud)
    base_y = S * 0.6
    for (x, y, rr) in ((0.3, 0.5, 0.15), (0.47, 0.42, 0.19), (0.63, 0.5, 0.14), (0.44, 0.53, 0.13)):
        cd.ellipse([S * (x - rr), S * (y - rr), S * (x + rr), S * (y + rr)], fill=(236, 242, 250, 255))
    cd.rounded_rectangle([S * 0.16, S * 0.48, S * 0.77, base_y], radius=int(S * 0.06), fill=(236, 242, 250, 255))
    shadow = cloud.filter(ImageFilter.GaussianBlur(18))
    shadow = Image.eval(shadow, lambda v: v)  # keep
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sh.paste((0, 10, 30, 140), (0, 0), shadow.split()[3])
    im.alpha_composite(sh, (12, 22))
    im.alpha_composite(cloud)
    d = ImageDraw.Draw(im)
    # rain
    for i, x in enumerate((0.27, 0.38, 0.49, 0.6, 0.71)):
        y = S * (0.67 + 0.035 * (i % 2))
        d.line([(S * x, y), (S * x - 26, y + 92)], fill=(79, 195, 247, 255), width=24)
    return im


def rounded(im: Image.Image, radius_frac: float) -> Image.Image:
    w, h = im.size
    big = Image.new("L", (w * 4, h * 4), 0)
    ImageDraw.Draw(big).rounded_rectangle([0, 0, w * 4 - 1, h * 4 - 1], radius=int(min(w, h) * radius_frac * 4), fill=255)
    out = im.copy()
    out.putalpha(big.resize((w, h), Image.LANCZOS))
    return out


sources = sorted(p for p in HERE.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
if sources:
    art = Image.open(sources[0]).convert("RGBA")
    side = min(art.size)
    art = art.crop(((art.width - side) // 2, (art.height - side) // 2, (art.width + side) // 2, (art.height + side) // 2))
else:
    art = draw()

OUT.mkdir(parents=True, exist_ok=True)
DOCS.mkdir(parents=True, exist_ok=True)
for suffix, size in (("", 256), ("@2x", 512)):
    img = rounded(art.resize((size, size), Image.LANCZOS), 0.18)
    for base in ("icon", "logo", "dark_icon", "dark_logo"):
        img.save(OUT / f"{base}{suffix}.png", optimize=True)
rounded(art.resize((320, 320), Image.LANCZOS), 0.18).save(DOCS / "logo.png", optimize=True)
print("brand images written")
