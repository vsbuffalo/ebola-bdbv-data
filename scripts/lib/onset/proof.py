"""Proof overlays: the reader's conclusions drawn onto the pixels it read.

One PNG per distinct decoded image, the human check the build ships with.
Everything the pipeline concluded is drawn where a glance can falsify it:
the fitted alive and total heights as outlines on every bar, the date grid
as month rules, flagged bars marked, and the reconciliation verdict in the
footer. A one-day date misregistration -- invisible in any CSV -- shows as
every outline sitting beside its bar.
"""

from __future__ import annotations

import datetime as dt

from PIL import Image, ImageDraw

from .assemble import Vintage

INK_TOTAL = (20, 20, 20)
INK_ALIVE = (0, 120, 60)
INK_FLAG = (230, 60, 0)
INK_GRID = (60, 110, 220)


def draw_proof(img: Image.Image, v: Vintage, status: str,
               reasons: tuple[str, ...]) -> Image.Image:
    out = img.convert("RGB").copy()
    d = ImageDraw.Draw(out)
    cal = v.calibration
    p = cal.panel
    c = cal.px_per_case
    d.rectangle([p.left, p.top, p.right, p.bottom],
                outline=INK_GRID, width=1)
    for bar, date in zip(v.bars, v.dates):
        x0 = cal.x_phase + bar.slot * cal.day_px - 0.45 * cal.day_px
        x1 = x0 + 0.9 * cal.day_px
        top_total = p.bottom - (bar.alive + bar.dead) * c
        top_alive = p.bottom - bar.alive * c
        if bar.alive + bar.dead > 0:
            d.rectangle([x0, top_total, x1, p.bottom],
                        outline=INK_TOTAL, width=1)
            if bar.dead > 0:
                d.line([x0, top_alive, x1, top_alive],
                       fill=INK_ALIVE, width=1)
        if not bar.reader_agreement:
            d.line([x0, p.top + 2, x1, p.top + 2], fill=INK_FLAG, width=2)
        if date.day == 1:
            d.line([x0, p.top, x0, p.bottom], fill=INK_GRID, width=1)
            d.text((x0 + 2, p.top + 4), date.strftime("%b"), fill=INK_GRID)
    footer = (f"{v.image_file}  sitreps {','.join(map(str, v.sitreps))}  "
              f"read {v.total}"
              + (f"  printed {v.printed_n}  "
                 f"deficit {v.total - v.printed_n:+d}"
                 if v.printed_n is not None else "  printed —")
              + f"  {status}")
    d.rectangle([0, out.height - 30, out.width, out.height],
                fill=(255, 255, 255))
    d.text((6, out.height - 26), footer, fill=INK_TOTAL)
    if reasons:
        d.text((6, out.height - 14), "; ".join(reasons)[:180], fill=INK_FLAG)
    return out
