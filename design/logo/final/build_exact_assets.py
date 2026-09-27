r"""Export the selected PNG concept without redrawing it.

Run: .\.venv\Scripts\python.exe design\logo\final\build_exact_assets.py
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "source" / "slysh-original-board-untouched.png"
EXPECTED_HASH = "4599A7B2A8DD32BD00367F16CE06B8C33E8FA0CD7B8875823C07305A3B997D48"
CROPS = {
    "primary-symbol": (100, 110, 520, 570),
    "wordmark": (660, 100, 1180, 300),
    "horizontal-lockup": (650, 390, 1280, 610),
    "app-icon-light": (30, 710, 320, 980),
    "app-icon-dark": (350, 710, 640, 980),
    "monochrome-symbol": (690, 730, 920, 950),
}


def square(image: Image.Image) -> Image.Image:
    side = max(image.size)
    result = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    result.alpha_composite(image, ((side - image.width) // 2, (side - image.height) // 2))
    return result


def png_in_svg(path: Path, title: str) -> str:
    with Image.open(path) as image:
        width, height = image.size
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%" role="img" aria-label="{title}">
  <image width="{width}" height="{height}" href="data:image/png;base64,{data}"/>
</svg>
'''


def build_preview(masters: dict[str, Image.Image], output: Path) -> None:
    page = Image.new("RGB", (1400, 900), "white")
    draw = ImageDraw.Draw(page)
    heading = ImageFont.load_default(size=24)
    label = ImageFont.load_default(size=18)
    draw.text((50, 32), "Slysh: exact selected assets", fill="#121C2C", font=heading)
    draw.text((50, 68), "Cropped from the original PNG; no redrawing or tracing", fill="#454652", font=label)
    cells = [
        ("primary-symbol", (50, 120, 520, 590)),
        ("wordmark", (550, 120, 1350, 370)),
        ("horizontal-lockup", (550, 400, 1350, 680)),
        ("app-icon-light", (50, 630, 300, 880)),
        ("app-icon-dark", (320, 630, 570, 880)),
        ("monochrome-symbol", (590, 680, 840, 880)),
    ]
    for name, box in cells:
        left, top, right, bottom = box
        draw.rounded_rectangle(box, radius=18, fill="#F9F9FF", outline="#D9E3F9")
        draw.text((left + 14, top + 10), name, fill="#121C2C", font=label)
        image = masters[name].copy()
        image.thumbnail((right - left - 28, bottom - top - 54), Image.Resampling.LANCZOS)
        x = left + (right - left - image.width) // 2
        y = top + 40 + (bottom - top - 40 - image.height) // 2
        page.paste(image, (x, y), image)
    page.save(output)


def build() -> None:
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest().upper()
    if digest != EXPECTED_HASH:
        raise RuntimeError(f"Selected source changed: {digest}")
    masters_dir = ROOT / "png" / "masters"
    sizes_dir = ROOT / "png" / "sizes"
    svg_dir = ROOT / "svg-pixel-exact"
    ico_dir = ROOT / "ico"
    preview_dir = ROOT / "preview"
    for directory in (masters_dir, sizes_dir, svg_dir, ico_dir, preview_dir):
        directory.mkdir(parents=True, exist_ok=True)

    masters = {}
    with Image.open(SOURCE).convert("RGBA") as board:
        for name, box in CROPS.items():
            crop = board.crop(box)
            crop.save(masters_dir / f"{name}.png", optimize=False)
            masters[name] = crop

    variants = {
        "symbol": square(masters["primary-symbol"]),
        "app-dark": square(masters["app-icon-dark"]),
        "app-light": square(masters["app-icon-light"]),
        "monochrome": square(masters["monochrome-symbol"]),
    }
    for name, image in variants.items():
        image.save(masters_dir / f"{name}-square.png", optimize=False)
        for size in (16, 24, 32, 40, 48, 64, 128, 256, 512, 1024):
            image.resize((size, size), Image.Resampling.LANCZOS).save(
                sizes_dir / f"slysh-{name}-{size}.png"
            )

    variants["symbol"].save(
        ico_dir / "slysh-original.ico", format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    for name in CROPS:
        png = masters_dir / f"{name}.png"
        (svg_dir / f"slysh-{name}-pixel-exact.svg").write_text(
            png_in_svg(png, f"Slysh {name}"), encoding="utf-8"
        )

    manifest = {
        "source": str(SOURCE.relative_to(ROOT)),
        "source_sha256": digest,
        "source_size": [1536, 1024],
        "crop_boxes_ltrb": CROPS,
        "method": "exact source crops; Lanczos only for resized exports",
        "vector_source_available": False,
        "svg_note": "SVG files embed exact PNG crops; they are not traced vectors.",
    }
    (ROOT / "source" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ROOT / "source" / "SOURCE_SHA256.txt").write_text(
        f"{digest}  slysh-original-board-untouched.png\n", encoding="ascii"
    )
    build_preview(masters, preview_dir / "exact-assets-preview.png")


if __name__ == "__main__":
    build()
    print(f"Exact selected-logo assets built at {ROOT}")
