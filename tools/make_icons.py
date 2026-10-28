import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
WEB_ICONS = ROOT / "ui" / "static" / "icons"
RES = ROOT / "android" / "app" / "src" / "main" / "res"

BG = (12, 13, 16, 255)
CARD = (18, 19, 24, 255)
GREEN = (52, 211, 153, 255)
SCALE = 4
BASE = 512


def draw_icon(rounded):
    size = BASE * SCALE
    center = size / 2
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    background = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(background).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * 0.22) if rounded else 0, fill=BG
    )
    canvas = Image.alpha_composite(canvas, background)

    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    radius = 150 * SCALE
    ImageDraw.Draw(glow).ellipse(
        [center - radius, center - radius, center + radius, center + radius],
        fill=(52, 211, 153, 120),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(46 * SCALE))
    mask = background.split()[3]
    glow.putalpha(Image.composite(glow.split()[3], Image.new("L", (size, size), 0), mask))
    canvas = Image.alpha_composite(canvas, glow)

    shape = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(shape)
    ring = 134 * SCALE
    draw.ellipse(
        [center - ring, center - ring, center + ring, center + ring],
        fill=CARD, outline=GREEN, width=12 * SCALE,
    )
    stroke = 22 * SCALE
    arc_r = 62 * SCALE
    reach = arc_r + stroke / 2
    box = [center - reach, center - reach, center + reach, center + reach]
    draw.arc(box, start=310, end=360, fill=GREEN, width=stroke)
    draw.arc(box, start=0, end=230, fill=GREEN, width=stroke)
    for angle in (310, 230):
        x = center + arc_r * math.cos(math.radians(angle))
        y = center + arc_r * math.sin(math.radians(angle))
        draw.ellipse([x - stroke / 2, y - stroke / 2, x + stroke / 2, y + stroke / 2], fill=GREEN)
    top, bottom = center - arc_r * 1.2, center - arc_r * 0.05
    draw.line([(center, top), (center, bottom)], fill=GREEN, width=stroke)
    for y in (top, bottom):
        draw.ellipse([center - stroke / 2, y - stroke / 2, center + stroke / 2, y + stroke / 2], fill=GREEN)
    return Image.alpha_composite(canvas, shape)


def save(image, path, side):
    path.parent.mkdir(parents=True, exist_ok=True)
    resample = getattr(Image, "Resampling", Image).LANCZOS
    image.resize((side, side), resample).save(path, optimize=True)
    print("wrote", path.relative_to(ROOT), side)


def main():
    square = draw_icon(rounded=False)
    rounded = draw_icon(rounded=True)
    save(square, WEB_ICONS / "icon-192.png", 192)
    save(square, WEB_ICONS / "icon-512.png", 512)
    save(square, WEB_ICONS / "apple-touch-icon.png", 180)
    for folder, side in (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)):
        save(rounded, RES / f"mipmap-{folder}" / "ic_launcher.png", side)


if __name__ == "__main__":
    main()
