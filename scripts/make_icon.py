"""Draw the CNTag icon with Pillow and export PNG/ICO/ICNS.

Sibling of the DiscTag icon: same rounded-square silhouette and purple
gradient family, but the main motif is a white luggage tag carrying a
purple "中" glyph, with the teal badge kept bottom-right (music note).

Run from the repo root:
    python scripts/make_icon.py
"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SIZE = 4096            # supersampled render size; downsampled afterwards
S = SIZE / 1024        # scale factor: coordinates below are in 1024-space

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"

FONT_BOLD = Path(r"C:\Windows\Fonts\msyhbd.ttc")
FONT_REG = Path(r"C:\Windows\Fonts\msyh.ttc")


def px(v: float) -> int:
    return round(v * S)


def lerp(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def multi_stop_gradient(stops: list[tuple[float, tuple]], t: float) -> tuple:
    t = min(max(t, 0.0), 1.0)
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if t <= t1:
            return lerp(c0, c1, (t - t0) / (t1 - t0) if t1 > t0 else 0.0)
    return stops[-1][1]


def diagonal_gradient(size: int, stops: list[tuple[float, tuple]], angle_deg: float) -> Image.Image:
    """Linear gradient along an axis rotated by angle_deg from vertical.

    Built by drawing a horizontal gradient on an oversized canvas, rotating
    it and cropping the centre, so no fill colour leaks into the corners.
    """
    wide = size * 2
    grad = Image.new("RGBA", (wide, wide))
    draw = ImageDraw.Draw(grad)
    for x in range(wide):
        draw.line([(x, 0), (x, wide)], fill=multi_stop_gradient(stops, x / (wide - 1)))
    rotated = grad.rotate(angle_deg, resample=Image.Resampling.BILINEAR, center=(wide / 2, wide / 2))
    left = (rotated.width - size) // 2
    return rotated.crop((left, left, left + size, left + size))


def radial_glow(size: int, inner: tuple, outer: tuple) -> Image.Image:
    """Soft radial gradient (inner colour → transparent-ish outer) via a small
    image upscaled for smoothness."""
    small = 128
    grad = Image.new("RGBA", (small, small))
    draw = ImageDraw.Draw(grad)
    cx = (small - 1) / 2
    maxd = math.hypot(cx, cx)
    for y in range(small):
        for x in range(small):
            t = math.hypot(x - cx, y - cx) / maxd
            draw.point((x, y), fill=lerp(inner, outer, min(t, 1.0)))
    return grad.resize((size, size), Image.Resampling.BILINEAR)


def rounded_rect_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def tag_polygon(cx: float, cy: float, w: float, h: float) -> list[tuple[float, float]]:
    """Luggage-tag outline: rounded-corner polygon with an angled tip on the
    right side (the hole goes near the tip). Returns polygon points."""
    r = h * 0.18
    tip = w * 0.16  # horizontal extent of the angled tip
    x0, y0 = cx - w / 2, cy - h / 2
    x1, y1 = cx + w / 2, cy + h / 2
    tx = x1 - tip
    # clockwise from top-left
    pts = [
        (x0 + r, y0),
        (tx - r, y0),
        (tx, y0),
        (x1, cy),          # tip apex on the right edge midpoint
        (tx, y1),
        (tx - r, y1),
        (x0 + r, y1),
        (x0, y1 - r),
        (x0, y0 + r),
    ]
    return pts


def draw_tag_layer() -> tuple[Image.Image, tuple[float, float, float], tuple[float, float], float]:
    """Draw the white tag (rotated -12°) on its own layer; returns the layer,
    the glyph placement box, the hole centre, and the rotation angle."""
    layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    angle = -12.0
    cx, cy = SIZE * 0.470, SIZE * 0.462
    w, h = SIZE * 0.66, SIZE * 0.44

    tag = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    td = ImageDraw.Draw(tag)
    body = tag_polygon(cx, cy, w, h)
    td.polygon(body, fill=(255, 255, 255, 255))

    # Round the left corners with a rounded-rectangle overlay for a softer look.
    r = h * 0.18
    x0, y0 = cx - w / 2, cy - h / 2
    td.rounded_rectangle((x0, y0, x0 + w * 0.55, y0 + h), radius=r, fill=(255, 255, 255, 255))

    # String: a purple stroke anchored in the hole and leading up off the tag.
    hole_c = (cx + w * 0.335, cy)
    hole_r = h * 0.085
    sd = ImageDraw.Draw(tag)
    sd.line([(hole_c[0], hole_c[1]),
             (hole_c[0] + w * 0.02, y0 - h * 0.10),
             (hole_c[0] + w * 0.09, y0 - h * 0.24)],
            fill=(0x51, 0x40, 0xC8, 255), width=px(11), joint="curve")
    sd.ellipse((hole_c[0] + w * 0.075, y0 - h * 0.28,
                hole_c[0] + w * 0.105, y0 - h * 0.20),
               fill=(0x51, 0x40, 0xC8, 255))

    # Punch the hole near the tip: erase a circle, then draw a purple ring on
    # top of the string so it reads as threaded through the hole.
    erase = ImageDraw.Draw(tag)
    erase.ellipse((hole_c[0] - hole_r, hole_c[1] - hole_r,
                   hole_c[0] + hole_r, hole_c[1] + hole_r), fill=(0, 0, 0, 0))
    erase.ellipse((hole_c[0] - hole_r, hole_c[1] - hole_r,
                   hole_c[0] + hole_r, hole_c[1] + hole_r),
                  outline=(0x51, 0x40, 0xC8, 255), width=px(10))

    # Rotate around the tag centre.
    rotated = tag.rotate(angle, resample=Image.Resampling.BILINEAR, center=(cx, cy))

    # Drop shadow under the rotated tag.
    alpha = rotated.split()[3]
    shadow = Image.new("RGBA", (SIZE, SIZE), (23, 16, 56, 0))
    shadow.putalpha(alpha.point(lambda a: round(a * 0.35)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(px(28)))
    shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0)).alpha_composite(shadow)
    shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    sh_alpha = Image.new("L", (SIZE, SIZE), 0)
    sh_alpha.paste(alpha.point(lambda a: round(a * 0.35)), (0, px(34)))
    shadow.putalpha(sh_alpha.filter(ImageFilter.GaussianBlur(px(26))))
    tinted = Image.new("RGBA", (SIZE, SIZE), (23, 16, 56, 255))
    tinted.putalpha(shadow.split()[3])
    layer.alpha_composite(tinted)
    layer.alpha_composite(rotated)

    # Glyph box: centred in the tag body (left of the tip).
    glyph_cx = cx - w * 0.06
    glyph_box = (glyph_cx - h * 0.46, cy - h * 0.46, glyph_cx + h * 0.46, cy + h * 0.46)
    return layer, glyph_box, hole_c, angle


def draw_glyph(canvas: Image.Image, box: tuple, angle: float) -> None:
    font_path = FONT_BOLD if FONT_BOLD.is_file() else FONT_REG
    size = px(430)
    while size > 10:
        font = ImageFont.truetype(str(font_path), size)
        probe = ImageDraw.Draw(canvas)
        left, t, r, b = probe.textbbox((0, 0), "中", font=font)
        if (r - left) <= (box[2] - box[0]) and (b - t) <= (box[3] - box[1]):
            break
        size -= 10
    # Draw on a separate layer so it rotates with the tag.
    layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx = (box[0] + box[2]) / 2
    cy = (box[1] + box[3]) / 2
    left, t, r, b = d.textbbox((0, 0), "中", font=font)
    d.text((cx - (left + r) / 2, cy - (t + b) / 2), "中",
           font=font, fill=(0x51, 0x40, 0xC8, 255))
    canvas.alpha_composite(layer.rotate(angle, resample=Image.Resampling.BILINEAR,
                                        center=(SIZE * 0.470, SIZE * 0.462)))


def draw_badge(canvas: Image.Image) -> None:
    """Teal rounded badge, bottom-right, rotated -8°, white music note."""
    layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    badge = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    bd = ImageDraw.Draw(badge)
    x0, y0, y1 = px(565), px(520), px(806)
    grad = diagonal_gradient(y1 - y0, [(0.0, (0x42, 0xE8, 0xD5, 255)),
                                       (1.0, (0x08, 0xA9, 0xB5, 255))], 30)
    mask = rounded_rect_mask(y1 - y0, px(82))
    badge.paste(grad, (x0, y0), mask)

    # Top-left highlight stroke.
    bd.arc((x0 + px(30), y0 + px(24), x0 + px(260), y0 + px(150)),
           start=150, end=265, fill=(255, 255, 255, 90), width=px(12))

    # Music note: two eighth notes joined by a beam (matches DiscTag).
    w = px(29)
    # note heads
    bd.ellipse((px(627), px(684), px(713), px(752)), fill=(255, 255, 255, 255))
    bd.ellipse((px(731), px(654), px(817), px(722)), fill=(255, 255, 255, 255))
    # stems
    bd.line([(px(699), px(714)), (px(699), px(603))], fill=(255, 255, 255, 255), width=w)
    bd.line([(px(803), px(684)), (px(803), px(578))], fill=(255, 255, 255, 255), width=w)
    # beam
    bd.line([(px(699), px(618)), (px(803), px(593))], fill=(255, 255, 255, 255), width=w)

    angle = -8.0
    cx, cy = px(715), px(662)
    rotated = badge.rotate(angle, resample=Image.Resampling.BILINEAR, center=(cx, cy))
    alpha = rotated.split()[3]
    sh_alpha = Image.new("L", (SIZE, SIZE), 0)
    sh_alpha.paste(alpha.point(lambda a: round(a * 0.34)), (0, px(22)))
    shadow = Image.new("RGBA", (SIZE, SIZE), (20, 61, 98, 255))
    shadow.putalpha(sh_alpha.filter(ImageFilter.GaussianBlur(px(20))))
    layer.alpha_composite(shadow)
    layer.alpha_composite(rotated)
    canvas.alpha_composite(layer)


def render() -> Image.Image:
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    # Rounded-square purple background (same family as DiscTag).
    bg = diagonal_gradient(
        SIZE,
        [(0.0, (0x82, 0x74, 0xFA, 255)),
         (0.52, (0x62, 0x51, 0xDD, 255)),
         (1.0, (0x39, 0x28, 0x76, 255))],
        angle_deg=40,
    )
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((px(32), px(32), px(992), px(992)),
                                           radius=px(222), fill=255)
    canvas.paste(bg, (0, 0), mask)

    # Sheen shapes (match the DiscTag icon).
    deco = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    dd = ImageDraw.Draw(deco)
    dd.polygon([(px(92), px(252)), (px(356), px(74)), (px(688), px(74)),
                (px(151), px(501))], fill=(255, 255, 255, 19))
    dd.ellipse((px(716), px(102), px(924), px(310)), fill=(0xB9, 0xAE, 0xFF, 28))
    dd.ellipse((px(19), px(645), px(309), px(935)), fill=(0x24, 0x19, 0x53, 31))
    deco = deco.filter(ImageFilter.GaussianBlur(px(10)))
    canvas.alpha_composite(deco)

    # White highlight stroke, top edge.
    hl = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(hl).arc((px(180), px(60), px(560), px(320)),
                           start=195, end=330, fill=(255, 255, 255, 166), width=px(13))
    hl = hl.filter(ImageFilter.GaussianBlur(px(4)))
    canvas.alpha_composite(hl)

    tag_layer, glyph_box, _hole, angle = draw_tag_layer()
    canvas.alpha_composite(tag_layer)
    draw_glyph(canvas, glyph_box, angle)
    draw_badge(canvas)

    return canvas


def main() -> None:
    image = render()
    ASSETS.mkdir(exist_ok=True)

    png = image.resize((1024, 1024), Image.Resampling.LANCZOS)
    png.save(ASSETS / "icon.png")

    sizes = [16, 24, 32, 48, 64, 128, 256]
    png.save(ASSETS / "icon.ico", sizes=[(s, s) for s in sizes])
    png.save(ASSETS / "icon.icns")
    print(f"wrote {ASSETS / 'icon.png'}, icon.ico, icon.icns")


if __name__ == "__main__":
    main()
