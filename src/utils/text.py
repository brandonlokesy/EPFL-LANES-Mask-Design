"""
text.py
=======
Block-letter digit font for GDS chiplet ID labels.

Each digit is rendered as a hollow chamfered outline:
    outer boundary  MINUS  inner cutout(s)  via gdstk.boolean("not")

All coordinates are normalised to a unit grid (x,y ∈ [0,1]) and scaled
to (char_w, char_h) at draw time.

    sw  = stroke_width
    c   = outer chamfer size
    ci  = inner chamfer size  (= c * 0.5)

Public functions
----------------
chamfer_poly         — chamfered rectangle primitive
draw_digit           — single block-letter digit into a gdstk.Cell
draw_chiplet_number  — zero-padded two-digit label centred on the chip
"""

import gdstk

from src.config.layers import LAYERS


def chamfer_poly(
    x0: float, y0: float,
    x1: float, y1: float,
    c_tl: float, c_tr: float,
    c_br: float, c_bl: float,
) -> gdstk.Polygon:
    """Rectangle with independent 45° chamfers on each corner.
    Pass 0 for a sharp (unchamfered) corner."""
    pts = []
    if c_bl > 0:
        pts += [(x0 + c_bl, y0), (x0, y0 + c_bl)]
    else:
        pts += [(x0, y0)]
    if c_tl > 0:
        pts += [(x0, y1 - c_tl), (x0 + c_tl, y1)]
    else:
        pts += [(x0, y1)]
    if c_tr > 0:
        pts += [(x1 - c_tr, y1), (x1, y1 - c_tr)]
    else:
        pts += [(x1, y1)]
    if c_br > 0:
        pts += [(x1, y0 + c_br), (x1 - c_br, y0)]
    else:
        pts += [(x1, y0)]
    return gdstk.Polygon(pts)


def draw_digit(
    cell:    gdstk.Cell,
    digit:   str,
    x0:      float,
    y0:      float,
    char_w:  float,
    char_h:  float,
    stroke_w: float,
    chamfer: float,
    layer:   dict,
) -> None:
    """Draw a single block-letter digit as a hollow chamfered outline.

    Uses gdstk.boolean("not") so there is no double-exposure — correct
    for lithographic masks.
    """
    if digit not in "0123456789":
        return

    lp  = {"layer": layer["layer"], "datatype": layer["datatype"]}
    sw  = stroke_w
    c   = chamfer
    ci  = chamfer * 0.5
    W   = char_w
    H   = char_h

    def outer():
        return chamfer_poly(x0, y0, x0+W, y0+H, c, c, c, c)

    def inner_box(left=True, right=True, top=True, bottom=True):
        ix0 = x0 + sw  if left   else x0 - sw
        ix1 = x0+W-sw  if right  else x0+W+sw
        iy0 = y0 + sw  if bottom else y0 - sw
        iy1 = y0+H-sw  if top    else y0+H+sw
        c_tl = ci if (left  and top)    else 0
        c_tr = ci if (right and top)    else 0
        c_br = ci if (right and bottom) else 0
        c_bl = ci if (left  and bottom) else 0
        return chamfer_poly(ix0, iy0, ix1, iy1, c_tl, c_tr, c_br, c_bl)

    def hbar(yb, yt):
        return chamfer_poly(x0, yb, x0+W, yt, ci, ci, ci, ci)

    mid   = y0 + H * 0.5
    midy0 = mid - sw * 0.5
    midy1 = mid + sw * 0.5

    if digit == "0":
        result = gdstk.boolean([outer()], [inner_box()], "not", **lp)

    elif digit == "1":
        result = gdstk.boolean(
            [chamfer_poly(x0+W-sw, y0, x0+W, y0+H, c, c, c, c)], [], "or", **lp)

    elif digit == "2":
        top_bar = chamfer_poly(x0, y0+H-sw, x0+W, y0+H, c, c, 0, 0)
        r_upper = chamfer_poly(x0+W-sw, midy1, x0+W, y0+H-sw, 0, 0, 0, 0)
        mid_bar = chamfer_poly(x0, midy0, x0+W, midy1, c, 0, 0, 0)
        l_lower = chamfer_poly(x0, y0+sw, x0+sw, midy0, 0, 0, 0, 0)
        bot_bar = chamfer_poly(x0, y0, x0+W, y0+sw, 0, 0, c, c)
        result  = gdstk.boolean([top_bar, r_upper, mid_bar, l_lower, bot_bar], [], "or", **lp)

    elif digit == "3":
        top_bar = chamfer_poly(x0, y0+H-sw, x0+W, y0+H, ci, c, c, ci)
        r_vert  = chamfer_poly(x0+W-sw, y0, x0+W, y0+H, ci, ci, ci, ci)
        mid_bar = hbar(midy0, midy1)
        bot_bar = chamfer_poly(x0, y0, x0+W, y0+sw, c, ci, ci, c)
        result  = gdstk.boolean([top_bar, r_vert, mid_bar, bot_bar], [], "or", **lp)

    elif digit == "4":
        l_upper = chamfer_poly(x0, midy0, x0+sw, y0+H, c, ci, ci, ci)
        mid_bar = hbar(midy0, midy1)
        r_vert  = chamfer_poly(x0+W-sw, y0, x0+W, y0+H, c, c, c, c)
        result  = gdstk.boolean([l_upper, mid_bar, r_vert], [], "or", **lp)

    elif digit == "5":
        top_bar = chamfer_poly(x0, y0+H-sw, x0+W, y0+H, c, c, 0, 0)
        l_upper = chamfer_poly(x0, midy1, x0+sw, y0+H-sw, 0, 0, 0, 0)
        mid_bar = chamfer_poly(x0, midy0, x0+W, midy1, 0, 0, 0, 0)
        r_lower = chamfer_poly(x0+W-sw, y0+sw, x0+W, midy0, 0, 0, 0, 0)
        bot_bar = chamfer_poly(x0, y0, x0+W, y0+sw, 0, 0, c, c)
        result  = gdstk.boolean([top_bar, l_upper, mid_bar, r_lower, bot_bar], [], "or", **lp)

    elif digit == "6":
        top_bar = chamfer_poly(x0, y0+H-sw, x0+W, y0+H, c, c, 0, 0)
        l_vert  = chamfer_poly(x0, y0, x0+sw, y0+H, 0, 0, 0, 0)
        mid_bar = chamfer_poly(x0+sw, midy0, x0+W, midy1, 0, c, 0, 0)
        r_lower = chamfer_poly(x0+W-sw, y0+sw, x0+W, midy0, 0, 0, 0, 0)
        bot_bar = chamfer_poly(x0, y0, x0+W, y0+sw, 0, 0, c, c)
        result  = gdstk.boolean([top_bar, l_vert, mid_bar, r_lower, bot_bar], [], "or", **lp)

    elif digit == "7":
        top_bar = chamfer_poly(x0, y0+H-sw, x0+W, y0+H, c, c, ci, ci)
        r_vert  = chamfer_poly(x0+W-sw, y0, x0+W, y0+H, ci, ci, c, c)
        result  = gdstk.boolean([top_bar, r_vert], [], "or", **lp)

    elif digit == "8":
        win_h     = (H - 3*sw) / 2
        mid_y0    = y0 + sw + win_h
        mid_y1    = mid_y0 + sw
        upper_cut = chamfer_poly(x0+sw, mid_y1,  x0+W-sw, y0+H-sw, ci, ci, ci, ci)
        lower_cut = chamfer_poly(x0+sw, y0+sw,   x0+W-sw, mid_y0,  ci, ci, ci, ci)
        mid_bar   = chamfer_poly(x0,    mid_y0,  x0+W,    mid_y1,   0,  0,  0,  0)
        shell  = gdstk.boolean([outer()], [upper_cut, lower_cut], "not", **lp)
        result = gdstk.boolean(shell, [mid_bar], "or", **lp)

    elif digit == "9":
        top_half  = chamfer_poly(x0, midy0, x0+W, y0+H, c, c, ci, ci)
        inner_top = chamfer_poly(x0+sw, midy1, x0+W-sw, y0+H-sw, ci, ci, ci, ci)
        r_lower   = chamfer_poly(x0+W-sw, y0, x0+W, midy1, ci, ci, ci, ci)
        bot_bar   = chamfer_poly(x0, y0, x0+W, y0+sw, c, ci, ci, c)
        result    = gdstk.boolean([top_half, r_lower, bot_bar], [inner_top], "not", **lp)

    for poly in result:
        cell.add(poly)


def draw_chiplet_number(cell: gdstk.Cell, number: int, cfg) -> None:
    """Draw the chiplet number (0–99) as a zero-padded block-letter label.

    Horizontally centred at x=0, vertically at
    ``-cfg.chip_height/2 + cfg.chiplet_id_centre_y``.

    *cfg* is duck-typed: any object with the ``chiplet_id_*`` and
    ``chip_height`` fields (e.g. ``ChipletConfig``, ``PhotonicChipletConfig``)
    works.
    """
    label    = f"{number:02d}"
    char_h   = cfg.chiplet_id_text_size
    char_w   = char_h * cfg.chiplet_id_char_w_ratio
    stroke_w = char_h * cfg.chiplet_id_stroke_ratio
    gap      = char_h * cfg.chiplet_id_gap_ratio
    chamfer  = stroke_w * cfg.chiplet_id_chamfer_ratio

    n       = len(label)
    total_w = n * char_w + (n - 1) * gap

    cx = 0.0
    cy = -cfg.chip_height / 2 + cfg.chiplet_id_centre_y
    x0 = cx - total_w / 2
    y0 = cy - char_h  / 2

    for i, ch in enumerate(label):
        draw_digit(cell, ch,
                   x0 + i * (char_w + gap), y0,
                   char_w, char_h, stroke_w, chamfer,
                   LAYERS["chiplet_id"])
