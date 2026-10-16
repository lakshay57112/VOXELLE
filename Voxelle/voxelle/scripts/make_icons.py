"""Generate the app icons (green circle with a white pill). Run once, output goes to static/."""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "static"
GREEN = (47, 107, 63)
CREAM = (251, 246, 233)
AMBER = (232, 163, 61)


def draw(size: int) -> Image.Image:
    s = size * 4  # draw large, then downsample for smooth edges
    img = Image.new("RGBA", (s, s), GREEN)
    d = ImageDraw.Draw(img)
    # pill, tilted 40 degrees
    pill = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    pd = ImageDraw.Draw(pill)
    w, h = int(s * 0.62), int(s * 0.26)
    x0, y0 = (s - w) // 2, (s - h) // 2
    r = h // 2
    pd.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=r, fill=CREAM)
    pd.rounded_rectangle([x0 + w // 2, y0, x0 + w, y0 + h], radius=r, fill=AMBER)
    pd.rectangle([x0 + w // 2 - r, y0, x0 + w // 2 + 2, y0 + h], fill=CREAM)
    pd.rounded_rectangle([x0 + w // 2, y0, x0 + w, y0 + h], radius=r, fill=AMBER)
    pd.rectangle([x0 + w // 2, y0, x0 + w // 2 + r, y0 + h], fill=AMBER)
    pill = pill.rotate(40, resample=Image.BICUBIC)
    img.alpha_composite(pill)
    return img.resize((size, size), Image.LANCZOS).convert("RGB")


for px in (192, 512):
    draw(px).save(OUT / f"icon-{px}.png")
    print("wrote", OUT / f"icon-{px}.png")
