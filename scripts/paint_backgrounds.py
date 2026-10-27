#!/usr/bin/env python3
"""Paint the soft watercolour botanical backgrounds, one per colour scheme.

Writes an SVG per scheme. Render each once to services/web/app/static/art/<key>.webp
(open it in a browser at 1800x1200, screenshot, save as WebP quality 80) so visitors'
phones never have to compute the watercolour filters.

    python3 scripts/paint_backgrounds.py <out_dir>
"""

import math
import random
import sys
from pathlib import Path

W, H = 1800, 1200

# scheme key: paper, leaf colours, blossom colours, wash colours
SCHEMES = {
    "forest": ("#fbfbf7", ["#9fb79a", "#b8c9a8", "#7f9c80"], ["#e9d9a6", "#f1e6c2"], ["#dfe8d6", "#eef0de"]),
    "plum": ("#fcfbfd", ["#a9b49e", "#c3c9b4", "#8e9a88"], ["#c8b6e2", "#ddd0ef", "#b7a3d6"], ["#ece6f5", "#f3eef8"]),
    "charcoal": (
        "#fdfaf6",
        ["#b2bf9f", "#c9d1b4", "#97a88c"],
        ["#f3c3ad", "#f7d8c8", "#eab39d"],
        ["#f8eae1", "#eef2f5"],
    ),
    "navy": ("#f9fbfc", ["#9fb6b4", "#b9cbc9", "#85a2a3"], ["#b9cbe3", "#d3e0ef"], ["#e3edf3", "#eaf3f0"]),
    "burgundy": (
        "#fdf9f9",
        ["#a9b39a", "#c2c8b0", "#909c86"],
        ["#e8b4c0", "#f1ccd4", "#dc9fae"],
        ["#f6e6e8", "#f6ece4"],
    ),
}

FILTERS = """
<defs>
  <filter id="wc" x="-20%" y="-20%" width="140%" height="140%">
    <feTurbulence type="fractalNoise" baseFrequency="0.022" numOctaves="3" seed="7" result="n"/>
    <feDisplacementMap in="SourceGraphic" in2="n" scale="14" xChannelSelector="R" yChannelSelector="G" result="d"/>
    <feGaussianBlur in="d" stdDeviation="1.2" result="b"/>
    <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" seed="3" result="grain"/>
    <feColorMatrix in="grain" type="saturate" values="0" result="g"/>
    <feComposite in="b" in2="g" operator="arithmetic" k1="0.25" k2="0.85" k3="0" k4="0"/>
  </filter>
  <filter id="wash" x="-30%" y="-30%" width="160%" height="160%">
    <feTurbulence type="fractalNoise" baseFrequency="0.008" numOctaves="2" seed="11" result="n"/>
    <feDisplacementMap in="SourceGraphic" in2="n" scale="80" xChannelSelector="R" yChannelSelector="G" result="d"/>
    <feGaussianBlur in="d" stdDeviation="28"/>
  </filter>
  <filter id="paper">
    <feTurbulence type="fractalNoise" baseFrequency="0.6" numOctaves="3" seed="5"/>
    <feColorMatrix type="matrix" values="0 0 0 0 0.5  0 0 0 0 0.48  0 0 0 0 0.45  0 0 0 0.06 0"/>
  </filter>
</defs>"""


def leaf(x, y, length, width, angle, color, opacity):
    # A pointed leaf: two curves meeting at the tip.
    a = math.radians(angle)
    tx, ty = x + length * math.cos(a), y + length * math.sin(a)
    nx, ny = -math.sin(a) * width, math.cos(a) * width
    mx, my = x + 0.45 * length * math.cos(a), y + 0.45 * length * math.sin(a)
    d = f"M{x:.1f},{y:.1f} Q{mx + nx:.1f},{my + ny:.1f} {tx:.1f},{ty:.1f} Q{mx - nx:.1f},{my - ny:.1f} {x:.1f},{y:.1f}Z"
    vein = f"M{x:.1f},{y:.1f} L{tx:.1f},{ty:.1f}"
    return (
        f'<path d="{d}" fill="{color}" fill-opacity="{opacity:.2f}"/>'
        f'<path d="{vein}" stroke="{color}" stroke-opacity="{min(1, opacity + 0.15):.2f}" '
        'stroke-width="1.2" fill="none"/>'
    )


def blossom(x, y, r, color, centre, opacity, rng):
    parts = []
    petals = rng.choice([5, 5, 6])
    turn = rng.uniform(0, 360)
    for i in range(petals):
        a = math.radians(turn + i * 360 / petals)
        px, py = x + r * 0.62 * math.cos(a), y + r * 0.62 * math.sin(a)
        parts.append(
            f'<ellipse cx="{px:.1f}" cy="{py:.1f}" rx="{r * 0.55:.1f}" ry="{r * 0.38:.1f}" '
            f'transform="rotate({math.degrees(a):.0f} {px:.1f} {py:.1f})" fill="{color}" fill-opacity="{opacity:.2f}"/>'
        )
    parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r * 0.18:.1f}" fill="{centre}" fill-opacity="0.55"/>')
    return "".join(parts)


def branch(x0, y0, x1, y1, bend, leaves, flowers, rng, n_leaves=14, n_flowers=4, scale=1.0):
    cx, cy = (x0 + x1) / 2 + bend[0], (y0 + y1) / 2 + bend[1]
    stem = leaves[2]
    out = [
        f'<path d="M{x0},{y0} Q{cx},{cy} {x1},{y1}" stroke="{stem}" stroke-opacity="0.55" '
        f'stroke-width="{2.4 * scale:.1f}" fill="none" stroke-linecap="round"/>'
    ]
    for i in range(n_leaves):
        t = (i + 1) / (n_leaves + 1)
        # point on the quadratic curve and its direction
        px = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t * t * x1
        py = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t * t * y1
        dx = 2 * (1 - t) * (cx - x0) + 2 * t * (x1 - cx)
        dy = 2 * (1 - t) * (cy - y0) + 2 * t * (y1 - cy)
        base = math.degrees(math.atan2(dy, dx))
        side = 1 if i % 2 else -1
        ang = base + side * rng.uniform(35, 60)
        size = rng.uniform(55, 95) * scale * (1.1 - 0.4 * t)
        out.append(leaf(px, py, size, size * 0.32, ang, rng.choice(leaves[:2]), rng.uniform(0.35, 0.6)))
    for _ in range(n_flowers):
        t = rng.uniform(0.55, 1.0)
        px = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t * t * x1 + rng.uniform(-40, 40) * scale
        py = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t * t * y1 + rng.uniform(-40, 40) * scale
        out.append(
            blossom(px, py, rng.uniform(22, 38) * scale, rng.choice(flowers), flowers[0], rng.uniform(0.45, 0.7), rng)
        )
    return "".join(out)


def paint(key: str) -> str:
    paper, leaves, flowers, washes = SCHEMES[key]
    rng = random.Random(f"martha-{key}")  # noqa: S311 - repeatable artwork, not security
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        FILTERS,
        f'<rect width="{W}" height="{H}" fill="{paper}"/>',
    ]
    # Large soft colour washes, kept away from the centre where the text sits.
    wash = []
    for cx, cy, r in [(150, 180, 380), (1650, 260, 340), (260, 1080, 420), (1580, 1000, 360), (900, 1180, 300)]:
        wash.append(
            f'<ellipse cx="{cx}" cy="{cy}" rx="{r * 1.3:.0f}" ry="{r:.0f}" '
            f'fill="{rng.choice(washes)}" fill-opacity="0.85"/>'
        )
    parts.append(f'<g filter="url(#wash)">{"".join(wash)}</g>')
    art = [
        branch(-40, 120, 420, 420, (60, -140), leaves, flowers, rng, 16, 5, 1.15),
        branch(40, 520, 300, 260, (-90, -30), leaves, flowers, rng, 9, 2, 0.8),
        branch(1840, 60, 1380, 360, (-40, -160), leaves, flowers, rng, 15, 5, 1.1),
        branch(1860, 700, 1560, 520, (40, -80), leaves, flowers, rng, 8, 3, 0.75),
        branch(-30, 1190, 380, 880, (40, 120), leaves, flowers, rng, 13, 4, 1.0),
        branch(1830, 1220, 1430, 900, (-120, 60), leaves, flowers, rng, 14, 4, 1.05),
    ]
    parts.append(f'<g filter="url(#wc)">{"".join(art)}</g>')
    # A few loose petals drifting across the page.
    loose = [
        blossom(
            rng.uniform(450, 1350),
            rng.uniform(150, 1050),
            rng.uniform(8, 14),
            rng.choice(flowers),
            flowers[0],
            rng.uniform(0.25, 0.4),
            rng,
        )
        for _ in range(7)
    ]
    parts.append(f'<g filter="url(#wc)">{"".join(loose)}</g>')
    parts.append(f'<rect width="{W}" height="{H}" filter="url(#paper)"/>')
    parts.append("</svg>")
    return "".join(parts)


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    for key in SCHEMES:
        (out / f"{key}.svg").write_text(paint(key))
        print("painted", key)
