"""
inverse_tone.py

Inverse-tone exposure: expose the whole chip except the photonic pattern, split
into tiers that the EBPG writes at different beam currents. Only the sidewalls
need a fine beam; a 144 mm^2 chip at 300 uC/cm^2 takes ~24 h at 5 nA and
~15 min at 500 nA.

Terms:
  protect   union of wg_core, ring, grating, notes: the film that must survive.
  zone      one fine-beam region, given as a dict in `zones` with keys:
    name         label for the zone in the printed summary, e.g. "site".
    select       selector string, or a list of them (see below).
    margin       um added on every side of each selected bounding box.
    layer        LAYERS key the tier is written to, e.g. "inv_t1" (layer 81).
                 One zone per layer, so each can get its own beam current.
    nA           beam current for this tier, in nA. Used only for the
                 write-time estimate; the real current is set at EBPG job setup.
    merge_slack  um; gaps between boxes narrower than this are filled, so no
                 thin strip is left for the coarse beam. Optional, default 0.
    shape        "box" (default) or "collar".
    width        collar only: um the protected pattern is grown by to make the
                 frame, instead of using boxes.
  selector  string naming which placed geometry a zone covers; returns one
            bounding box per match. "site" = each device plus its label,
            "label" = labels only, "inst:<name>" = device sub-cells whose
            cell name contains <name> (e.g. "inst:grating_coupler").
  frame     a zone's area: its selector's boxes grown by `margin`, merged.
  tier      what is exposed on one layer: `frame - protect`.

Zones run in list order; where frames overlap, the earlier zone keeps the
overlap. The coarse frame is `coarse_box` (the whole chip, or the active area)
minus all zone frames, so tiers share edges exactly.

A seam is the edge where two tiers meet. The film there is etched anyway, so
a seam only matters within electron-scatter range of a waveguide sidewall.
`margin` (or collar `width`) is the seam-to-sidewall distance. Backscattered
electrons travel ~30 um, so below that the sidewall dose also depends on the
coarse tier's dose, and proximity correction is needed.

Geometry is klayout `kdb.Region` on the database-unit grid (1 nm), so tier
edges coincide exactly rather than to within a rounding tolerance.
"""

from __future__ import annotations

from collections.abc import Sequence

import gdsfactory as gf
import klayout.db as kdb

from src.config.layers import LAYERS
from src.components.photonics.technology import _l

# (x0, y0, x1, y1) in um
Box = tuple[float, float, float, float]

VALID_ZONE_KEYS = {"name", "select", "margin", "layer", "nA", "merge_slack",
                   "shape", "width"}
VALID_SHAPES = ("box", "collar")
# "all" is collar-only: it means the whole protected pattern, not a bbox.
SELECTOR_PREFIXES = ("inst:", "device", "label", "site", "all")


# =============================================================================
# READY-MADE ZONE SETS
# =============================================================================

# One zone per device site: the whole device and its label in a single tier.
ZONES_PER_SITE = [
    {"name": "site", "select": "site", "margin": 30.0,
     "layer": "inv_t1", "nA": 5.0, "merge_slack": 20.0},
]

# One zone per feature class. Covers the pattern completely -- every sub-instance
# of pulley_with_leads plus the label -- which the coverage guard enforces.
ZONES_PER_FEATURE = [
    {"name": "gc",      "select": "inst:grating_coupler", "margin": 10.0,
     "layer": "inv_t1", "nA": 5.0},
    {"name": "ring",    "select": "inst:coupler_pulley",  "margin": 10.0,
     "layer": "inv_t2", "nA": 10.0},
    {"name": "routing", "select": ["inst:bend_euler", "inst:straight"],
     "margin": 10.0, "layer": "inv_t3", "nA": 20.0},
    {"name": "text",    "select": "label",                "margin": 10.0,
     "layer": "inv_t4", "nA": 100.0},
]


# A collar hugging the whole pattern: the least fine area of any option, at the
# cost of putting the tier seam `width` from every sidewall. See the module
# docstring on seams -- at 2 um the seam is well inside the backscatter range,
# so proximity correction stops being optional.
ZONES_COLLAR = [
    {"name": "collar", "select": "all", "shape": "collar", "width": 2.0,
     "layer": "inv_t1", "nA": 5.0},
]


# =============================================================================
# BOX HELPERS
# =============================================================================

def pad_bbox(bbox, margin: float = 0.0) -> Box:
    """A klayout DBox (from ``ref.dbbox()``) as a padded ``(x0, y0, x1, y1)``."""
    return (bbox.left - margin, bbox.bottom - margin,
            bbox.right + margin, bbox.top + margin)


def union_boxes(boxes: Sequence[Box]) -> Box:
    """Smallest box containing all of *boxes*."""
    x0, y0, x1, y1 = zip(*boxes)
    return (min(x0), min(y0), max(x1), max(y1))


def site_box(refs: Sequence, margin: float = 0.0) -> Box:
    """One padded box covering every reference in *refs* -- e.g. device + label."""
    return union_boxes([pad_bbox(r.dbbox(), margin) for r in refs])


# =============================================================================
# THE PRIMITIVE
# =============================================================================

def to_kdb_box(box: Box, dbu: float) -> kdb.Box:
    """A ``(x0, y0, x1, y1)`` in um as an integer-grid ``kdb.Box``."""
    x0, y0, x1, y1 = box
    u = lambda v: int(round(v / dbu))    # noqa: E731
    return kdb.Box(u(x0), u(y0), u(x1), u(y1))


def inverse_of(pattern: kdb.Region, box: Box, dbu: float) -> kdb.Region:
    """
    The negative of *pattern* within *box*: ``box - pattern``.

    This is the whole idea. Every tier below is this operation applied to a
    different box, and the coarse tier is this operation applied to whatever is
    left over.
    """
    return kdb.Region(to_kdb_box(box, dbu)) - pattern


# =============================================================================
# SELECTORS -- placing a box around a named feature group
# =============================================================================

def resolve_selector(selector: str, sites: Sequence[dict]) -> list:
    """
    Boxes for *selector*, in chiplet coordinates, as klayout DBox objects.

    *sites* is one dict per placed device, each carrying the references the
    chiplet builder created::

        {"device": <device ref>, "label": <text ref>}

    Selectors:

    ``inst:<substring>``
        Sub-instances of each device whose cell name contains the substring.
        Mapped out of device-local coordinates with ``ref.dtrans * sub.dbbox()``,
        which carries rotation and mirroring correctly.
    ``device``
        The chiplet-level device references themselves. For a device that is a
        single primitive (a bare straight) and so has no sub-instances to match.
    ``label``
        The chiplet-level text references.
    ``site``
        Device and label together, as one box per site.
    """
    boxes = []

    if selector == "site":
        for index, site in enumerate(sites):
            refs = [r for r in (site.get("device"), site.get("label")) if r]
            if not refs:
                raise ValueError(
                    f"site {index} carries neither 'device' nor 'label'; "
                    f"selector 'site' has nothing to bound"
                )
            box = refs[0].dbbox()
            for ref in refs[1:]:
                box += ref.dbbox()
            boxes.append(box)

    elif selector == "device":
        boxes = [site["device"].dbbox() for site in sites if site.get("device")]

    elif selector == "label":
        boxes = [site["label"].dbbox() for site in sites if site.get("label")]

    elif selector.startswith("inst:"):
        needle = selector[len("inst:"):]
        if not needle:
            raise ValueError("selector 'inst:' needs a cell-name substring")
        for site in sites:
            ref = site.get("device")
            if ref is None:
                continue
            for sub in ref.cell.insts:
                if needle in sub.cell.name:
                    boxes.append(ref.dtrans * sub.dbbox())

    else:
        raise ValueError(
            f"unknown selector {selector!r}; expected one of "
            f"{', '.join(SELECTOR_PREFIXES)}"
        )

    return boxes


def validate_zones(zones: Sequence[dict]) -> None:
    """
    Reject a zone list that would silently misbehave.

    A reused output layer is the dangerous one: two zones would merge into a
    single tier and quietly get one beam current instead of two.
    """
    if not zones:
        raise ValueError("invert_zones is empty - nothing would be written fine")

    seen_layers: dict[str, str] = {}
    for zone in zones:
        unknown = set(zone) - VALID_ZONE_KEYS
        if unknown:
            raise ValueError(
                f"zone {zone.get('name', '?')!r} has unknown key(s) "
                f"{sorted(unknown)}; valid keys are {sorted(VALID_ZONE_KEYS)}"
            )
        for required in ("name", "select", "layer"):
            if required not in zone:
                raise ValueError(f"zone {zone!r} is missing {required!r}")

        shape = zone.get("shape", "box")
        if shape not in VALID_SHAPES:
            raise ValueError(
                f"zone {zone['name']!r} has shape {shape!r}; "
                f"expected one of {VALID_SHAPES}"
            )
        if shape == "collar":
            if not zone.get("width", 0) > 0:
                raise ValueError(
                    f"collar zone {zone['name']!r} needs a positive 'width' (um)"
                )
        else:
            if "width" in zone:
                raise ValueError(
                    f"zone {zone['name']!r} is a box but carries 'width'; "
                    f"boxes are sized by 'margin'. Did you mean shape='collar'?"
                )
            if "all" in ([zone["select"]] if isinstance(zone["select"], str)
                         else zone["select"]):
                raise ValueError(
                    f"zone {zone['name']!r}: selector 'all' is collar-only - a "
                    f"box needs features to bound. Use shape='collar'."
                )

        key = zone["layer"]
        if key not in LAYERS:
            raise ValueError(
                f"zone {zone['name']!r} names layer {key!r}, which is not in "
                f"src/config/layers.py"
            )
        if key in seen_layers:
            raise ValueError(
                f"zones {seen_layers[key]!r} and {zone['name']!r} both write to "
                f"layer {key!r}; they would merge into one tier and share one "
                f"beam current. Give each zone its own layer."
            )
        seen_layers[key] = zone["name"]


# =============================================================================
# WRITE-TIME ESTIMATE
# =============================================================================

def write_time_s(area_um2: float, dose_uC_cm2: float, current_nA: float) -> float:
    """
    Beam-on seconds for an area fill: t = Q / I, with Q = area x dose.

    Ignores settling, stage moves, field switching and PEC overhead, so treat it
    as a lower bound and a way to compare tiers -- not a quote.
    """
    charge_uC = area_um2 * 1e-8 * dose_uC_cm2      # 1 um^2 = 1e-8 cm^2
    return 1e3 * charge_uC / current_nA            # uC / nA -> s


def fmt_duration(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f} s"
    if seconds < 5400:
        return f"{seconds / 60:.1f} min"
    return f"{seconds / 3600:.2f} h"


# =============================================================================
# THE BOOLEAN
# =============================================================================

def add_inverse_tone_zones(
    c: gf.Component,
    *,
    zones: Sequence[dict],
    sites: Sequence[dict],
    coarse_box: Box,
    protect_layers: Sequence[str] = ("wg_core", "ring", "grating", "notes"),
    exclude_layers: Sequence[str] = (),
    exclude_margin: float = 0.0,
    bias: float = 0.0,
    max_vertices: int = 1024,
    coarse_layer: str = "inv_coarse",
    frame_layer: str | None = "inv_frame",
    allow_uncovered_pattern: bool = False,
) -> dict:
    """
    Add the inverse-tone tiers to *c* in place. Returns a per-tier summary.

    Parameters
    ----------
    zones
        Zone dicts, **finest first** -- order is precedence. See the module
        docstring and ``ZONES_PER_SITE`` / ``ZONES_PER_FEATURE``.
    sites
        One dict of references per placed device, for the selectors to resolve
        against: ``{"device": ref, "label": ref}``.
    coarse_box
        Outer extent of the exposure -- chip boundary or active area.
    protect_layers
        ``LAYERS`` keys whose geometry must survive, i.e. is subtracted from
        every tier. Include ``"notes"`` to keep device labels as readable film.
    exclude_layers
        ``LAYERS`` keys whose footprints are removed from every tier, leaving
        film islands. Intended for the MLA150 features (corner markers, pads,
        chiplet ID) that are patterned in a later step.
    exclude_margin
        Grow the excluded footprints by this much before removing them (um).
    bias
        Dilate the protected geometry by this much before subtracting (um), to
        compensate a known process bias. Positive widens the surviving line.
    max_vertices
        Split output polygons so none exceeds this vertex count. Necessary, not
        cosmetic: subtracting a few hundred curved devices from a box yields a
        single polygon with ~18000 vertices, and GDSII caps an XY record at
        8 KB, i.e. 1024 points. Writers that exceed it emit records a strict
        reader will reject and a lenient one will misparse. 0 disables.
    allow_uncovered_pattern
        Permit protected geometry that no zone covers. Off by default -- see the
        coverage guard below.

    Notes
    -----
    The positive geometry is left untouched in the component. Which layers are
    actually exposed is chosen at EBPG job setup, not here.
    """
    validate_zones(zones)
    dbu = c.kcl.dbu

    def _u(v: float) -> int:
        return int(round(v / dbu))

    # -- geometry that must survive ------------------------------------------
    protect = kdb.Region()
    for key in protect_layers:
        protect += c.get_region(_l(key))
    protect.merge()
    if bias:
        protect.size(_u(bias))
        protect.merge()

    # -- footprints that must not be exposed at all --------------------------
    exclude = kdb.Region()
    for key in exclude_layers:
        exclude += c.get_region(_l(key))
    if not exclude.is_empty():
        if exclude_margin:
            exclude.size(_u(exclude_margin))
        exclude.merge()

    outer = kdb.Region(to_kdb_box(coarse_box, dbu))

    # -- zone extents, finest first, each claiming only what is still free ---
    claimed = kdb.Region()
    frames: list[tuple[dict, kdb.Region]] = []

    for zone in zones:
        selectors = zone["select"]
        if isinstance(selectors, str):
            selectors = [selectors]

        margin = zone.get("margin", 0.0)

        def _selection() -> kdb.Region:
            """Union of the zone's selector boxes, padded by *margin*."""
            picked = kdb.Region()
            for selector in selectors:
                boxes = resolve_selector(selector, sites)
                if not boxes:
                    raise ValueError(
                        f"zone {zone['name']!r}: selector {selector!r} matched "
                        f"nothing. Check the cell-name substring against "
                        f"[i.cell.name for i in device.insts]."
                    )
                for box in boxes:
                    picked.insert(to_kdb_box(pad_bbox(box, margin), dbu))
            picked.merge()
            return picked

        if zone.get("shape", "box") == "collar":
            # A ribbon hugging the geometry. The frame is the *grown pattern*,
            # pattern included -- not `sized - pattern`. That keeps the algebra
            # identical to a box zone: the frame contains the pattern, and the
            # `frame - protect` below turns it into the outline for free. It is
            # also what lets the coverage guard stay meaningful, since a bare
            # ribbon would not contain the pattern it is protecting.
            scope = protect if selectors == ["all"] else (protect & _selection())
            if scope.is_empty():
                raise ValueError(
                    f"collar zone {zone['name']!r}: its selection contains no "
                    f"protected geometry, so there is nothing to collar."
                )
            frame = scope.sized(_u(zone["width"]))
            frame.merge()
        else:
            frame = _selection()

        slack = zone.get("merge_slack", 0.0)
        if slack:
            # Morphological close: absorb gaps narrower than this rather than
            # leave coarse slivers a large spot cannot resolve.
            s = _u(slack / 2)
            frame.size(s)
            frame.merge()
            frame.size(-s)
            frame.merge()

        frame &= outer
        frame -= claimed          # earlier, finer zones win the overlap
        claimed += frame
        frames.append((zone, frame))

    # -- COVERAGE GUARD ------------------------------------------------------
    # A protected feature that no zone covers falls into the coarse tier and has
    # its sidewall written by the largest spot. Per-site zoning could not do
    # this; per-feature zoning can, silently, by forgetting a feature class.
    uncovered = protect - claimed - exclude
    if not uncovered.is_empty() and not allow_uncovered_pattern:
        worst = max(uncovered.each(), key=lambda p: p.area())
        box = worst.bbox()
        raise ValueError(
            f"{uncovered.area() * dbu * dbu:.1f} um^2 of protected geometry in "
            f"{uncovered.count()} region(s) is covered by no zone, so the coarse "
            f"beam would write its edges. Largest at "
            f"({box.center().x * dbu:.1f}, {box.center().y * dbu:.1f}) um, "
            f"{box.width() * dbu:.2f} x {box.height() * dbu:.2f} um. "
            f"Add a zone covering it, or pass allow_uncovered_pattern=True if "
            f"that is deliberate."
        )

    # -- tier 2..n: whatever no zone claimed. Subtracting the plain claimed
    #    frames, not the zones' boolean results, is what makes tiers abut. ----
    coarse_frame = outer - claimed

    tiers = [(zone["name"], zone["layer"], zone.get("nA"),
              frame - protect - exclude, frame)
             for zone, frame in frames]
    tiers.append(("coarse", coarse_layer, None,
                  coarse_frame - protect - exclude, coarse_frame))

    # Areas are measured before fracturing: break_polygons introduces cut seams
    # that the area integral double-counts.
    um2 = dbu * dbu
    summary = {
        "tiers": [
            {"name": name, "layer": layer, "nA": nA,
             "n_regions": frame.count(), "area_um2": tier.area() * um2}
            for name, layer, nA, tier, frame in tiers
        ],
        "protect_area_um2":   protect.area() * um2,
        "excluded_area_um2":  exclude.area() * um2,
        "uncovered_area_um2": uncovered.area() * um2,
    }

    # Fracture LAST. Any boolean applied afterwards re-merges the pieces and
    # undoes it, so this has to be the final operation on each region.
    emitted = [(layer, tier) for _, layer, _, tier, _ in tiers]
    if frame_layer:
        emitted.append((frame_layer, claimed))
    if max_vertices:
        for _, region in emitted:
            region.break_polygons(max_vertices, 0)

    for layer, region in emitted:
        c.shapes(gf.get_layer(_l(layer))).insert(region)

    summary["max_vertices_out"] = max(
        (p.num_points() for _, region in emitted for p in region.each()), default=0
    )
    return summary
