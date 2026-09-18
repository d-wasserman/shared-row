"""Cross-section drawings: SVG for reports, ASCII for the terminal.

A parametric system needs a fast visual check -- a 0.4 m sidewalk is obvious
in a drawing and invisible in a table of numbers.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence

from . import vocab
from .model import CrossSection

#: Fill per mode group. Chosen to stay distinguishable in greyscale print.
MODE_FILL = {
    "pedestrian": "#c9b79c",
    "bicycle": "#3f7f5f",
    "transit": "#8c4a5f",
    "automobile": "#5a5f66",
    "green": "#6f9a58",
    "other": "#9aa3ad",
}
EDGE = "#2b2f33"
LABEL_DARK = "#1c1f22"
LABEL_LIGHT = "#ffffff"

#: Modes whose fill is dark enough to need light label text.
_DARK_FILL = ("automobile", "transit", "bicycle", "green")


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def to_svg(
    section: CrossSection,
    *,
    px_per_m: float = 26.0,
    height: int = 210,
    title: Optional[str] = None,
    show_dimensions: bool = True,
) -> str:
    """Render a scaled cross-section as a standalone SVG document.

    Slice heights are drawn to scale in centimetres, so kerbs and a raised
    median read as raised.
    """
    total = section.total_width
    if total <= 0:
        raise ValueError("cannot render a zero-width section")

    pad = 46
    width_px = total * px_per_m
    doc_w = int(width_px + pad * 2)
    doc_h = height
    base_y = doc_h - 58          # road surface
    max_h_cm = max([abs(s.height) for s in section.slices] + [15.24])
    h_scale = 26.0 / max_h_cm    # tallest feature is 26 px

    out = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" font-family="system-ui, sans-serif">'
        % (doc_w, doc_h, doc_w, doc_h),
        '<rect width="100%" height="100%" fill="#f7f7f5"/>',
    ]
    if title:
        out.append('<text x="%d" y="24" font-size="14" font-weight="600" '
                   'fill="%s">%s</text>' % (pad, LABEL_DARK, _esc(title)))

    x = float(pad)
    for s in section.slices:
        w = s.width * px_per_m
        rise = s.height * h_scale
        top = base_y - max(rise, 0.0)
        box_h = 30 + max(rise, 0.0) + max(-rise, 0.0)
        fill = MODE_FILL.get(s.mode, MODE_FILL["other"])
        out.append(
            '<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s" '
            'stroke="%s" stroke-width="0.8"/>'
            % (x, top, w, box_h, fill, EDGE))

        text_fill = LABEL_LIGHT if s.mode in _DARK_FILL else LABEL_DARK
        cx = x + w / 2.0
        # Only label a slice wide enough to hold text; the rest get a tick.
        if w >= 34:
            out.append(
                '<text x="%.2f" y="%.2f" font-size="9" text-anchor="middle" '
                'fill="%s">%.2f</text>'
                % (cx, base_y + 20, text_fill, s.width))
        if w >= 52:
            out.append(
                '<text x="%.2f" y="%.2f" font-size="8.5" text-anchor="middle" '
                'fill="%s" transform="rotate(-90 %.2f %.2f)">%s</text>'
                % (cx, top - 5, LABEL_DARK, cx, top - 5, _esc(s.type)))
        elif w >= 12:
            out.append('<text x="%.2f" y="%.2f" font-size="7.5" '
                       'text-anchor="middle" fill="%s">%.2f</text>'
                       % (cx, top - 5, LABEL_DARK, s.width))

        arrow = {"forward": "▸", "reverse": "◂"}.get(s.direction)
        if arrow and w >= 20:
            out.append('<text x="%.2f" y="%.2f" font-size="11" '
                       'text-anchor="middle" fill="%s">%s</text>'
                       % (cx, base_y + 8, text_fill, arrow))
        x += w

    if show_dimensions:
        y = doc_h - 18
        out.append('<line x1="%d" y1="%d" x2="%.2f" y2="%d" stroke="%s" '
                   'stroke-width="1"/>' % (pad, y, pad + width_px, y, EDGE))
        for tick in (pad, pad + width_px):
            out.append('<line x1="%.2f" y1="%d" x2="%.2f" y2="%d" stroke="%s" '
                       'stroke-width="1"/>' % (tick, y - 4, tick, y + 4, EDGE))
        out.append('<text x="%.2f" y="%d" font-size="10" text-anchor="middle" '
                   'fill="%s">%.2f m right-of-way</text>'
                   % (pad + width_px / 2.0, y - 7, LABEL_DARK, total))
    out.append("</svg>")
    return "\n".join(out)


_ASCII_GLYPH = {
    "sidewalk": "░", "path": "░",
    "planting_strip": "▒", "filter_strip": "▒", "canal": "~",
    "drive_lane": " ", "turn_lane": " ", "limitless": " ",
    "bike_lane": "b", "buffer": "/", "median": "▓",
    "parking": "p", "transit": "T", "bus_lane": "T",
}


def to_ascii(section: CrossSection, *, columns: int = 78) -> str:
    """Render a cross-section as terminal text, scaled to ``columns``.

    Every slice gets at least one column, so a narrow buffer stays visible
    even though the drawing is then not strictly to scale.
    """
    total = section.total_width
    if total <= 0:
        return "(zero-width section)"
    n = len(section.slices)
    usable = max(columns - n - 1, n)
    widths = []
    for s in section.slices:
        widths.append(max(1, int(round(s.width / total * usable))))

    bar = "|" + "|".join(
        _ASCII_GLYPH.get(s.type, "#") * w for s, w in zip(section.slices, widths)
    ) + "|"
    arrows = " "
    for s, w in zip(section.slices, widths):
        glyph = {"forward": ">", "reverse": "<"}.get(s.direction, " ")
        arrows += (glyph * w if glyph != " " else " " * w) + " "

    lines = [bar, arrows.rstrip() or ""]
    lines.append("")
    for s in section.slices:
        lines.append("  %-16s %6.2f m  %-13s %s" % (
            s.type, s.width, s.mode,
            {"forward": "->", "reverse": "<-"}.get(s.direction, "--")))
    lines.append("  %-16s %6.2f m  total" % ("", total))
    return "\n".join(lines)


def legend() -> str:
    rows = ["mode           glyph  fill"]
    for mode, fill in MODE_FILL.items():
        glyphs = sorted({_ASCII_GLYPH.get(t, "#")
                         for t in vocab.MODE_GROUPS.get(mode, ())})
        rows.append("%-14s %-6s %s" % (mode, "".join(glyphs) or "#", fill))
    return "\n".join(rows)
