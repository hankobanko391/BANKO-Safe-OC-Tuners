"""Generate high-resolution multi-size circular emblem icons for BANKO Tuners."""

from __future__ import annotations

import os
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ICON_SIZES = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
CANVAS = 1024


def _load_bold_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        r"C:\Windows\Fonts\segoeuib.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\calibrib.ttf",
        r"C:\Windows\Fonts\impact.ttf",
        "arialbd.ttf",
        "DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if os.path.isfile(path) or not os.path.isabs(path):
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha


def build_emblem_icon(label: str, accent_hex: str, out_path: str) -> None:
    """Create a sleek metallic & neon circular emblem .ico with centered text."""
    base = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))

    # 1. Outer ambient neon halo
    glow_layer = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    glow_draw.ellipse(
        [72, 72, CANVAS - 72, CANVAS - 72],
        outline=_hex_to_rgba(accent_hex, 210),
        width=48,
    )
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=34))
    base = Image.alpha_composite(base, glow_layer)

    draw = ImageDraw.Draw(base)

    # 2. Dark metallic outer bezel
    draw.ellipse(
        [52, 52, CANVAS - 52, CANVAS - 52],
        fill=(18, 21, 30, 255),
        outline=(54, 65, 88, 255),
        width=18,
    )

    # 3. Inner metallic chamfer ring
    draw.ellipse(
        [92, 92, CANVAS - 92, CANVAS - 92],
        fill=(24, 29, 42, 255),
        outline=(38, 45, 61, 255),
        width=10,
    )

    # 4. Crisp neon accent ring
    draw.ellipse(
        [124, 124, CANVAS - 124, CANVAS - 124],
        outline=_hex_to_rgba(accent_hex, 255),
        width=36,
    )

    # 5. Deep obsidian inner core
    draw.ellipse(
        [164, 164, CANVAS - 164, CANVAS - 164],
        fill=(13, 15, 20, 255),
        outline=_hex_to_rgba(accent_hex, 95),
        width=6,
    )

    # 6. Subtle top metallic specular arc
    draw.arc(
        [176, 176, CANVAS - 176, CANVAS - 176],
        start=210,
        end=330,
        fill=(255, 255, 255, 45),
        width=10,
    )

    # 7. Bold centered brand lettering with subtle neon drop shadow
    font_size = 370 if len(label) <= 2 else 235
    font = _load_bold_font(font_size)
    bbox = draw.textbbox((0, 0), label, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    tx = (CANVAS - text_w) / 2 - bbox[0]
    ty = (CANVAS - text_h) / 2 - bbox[1]

    text_glow = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    tg_draw = ImageDraw.Draw(text_glow)
    tg_draw.text((tx, ty), label, font=font, fill=_hex_to_rgba(accent_hex, 220))
    text_glow = text_glow.filter(ImageFilter.GaussianBlur(radius=18))
    base = Image.alpha_composite(base, text_glow)

    draw = ImageDraw.Draw(base)
    draw.text((tx, ty + 6), label, font=font, fill=_hex_to_rgba(accent_hex, 255))
    draw.text((tx, ty), label, font=font, fill=(248, 250, 252, 255))

    # Downsample crisp 256px base and export multi-resolution ICO
    icon_256 = base.resize((256, 256), Image.Resampling.LANCZOS)
    icon_256.save(out_path, format="ICO", sizes=ICON_SIZES)


def main() -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    hp_path = os.path.join(base_dir, "hp_icon.ico")
    dell_path = os.path.join(base_dir, "dell_icon.ico")

    build_emblem_icon("HP", "#00B4D8", hp_path)
    build_emblem_icon("DELL", "#00FF66", dell_path)

    print(f"Generated: {hp_path} ({os.path.getsize(hp_path)} bytes)")
    print(f"Generated: {dell_path} ({os.path.getsize(dell_path)} bytes)")


if __name__ == "__main__":
    main()
