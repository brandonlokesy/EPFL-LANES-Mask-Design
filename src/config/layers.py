"""
layers.py
=========

Import this in every file:
    from src.config.layers import LAYERS

Layer numbering scheme
----------------------
  1 -  9   Annotation          (boundaries, notes — never fabricated)
 10 - 19   Chip-level markers  (alignment, position grid, ID text)
 20 - 29   Wafer-level markers (alignment crosses, wafer ID)
 30 - 39   Substrate / implant
 40 - 49   Photonic structures
 50 - 59   Dielectric
 60 - 69   Contacts and vias
 70 - 79   Metal
 90 - 99   Test structures
100 - 109  Do not fabricate    (keep-out, dicing streets, write fields)

datatype convention
-------------------
  datatype 0  physical geometry to be fabricated (or annotated)
  datatype 1  simulation / reference only — not sent to fab
  datatype 2  process compensation (e.g. under-etch bias)
"""

LAYERS = {

    # ── ANNOTATION ────────────────────────────────────────────────────────────
    "chip_boundary":        {"layer": 1,  "datatype": 0},
    "chip_active_area":     {"layer": 2,  "datatype": 0},
    "wafer_boundary":       {"layer": 3,  "datatype": 0},
    "notes":                {"layer": 9,  "datatype": 0},

    # ── CHIP-LEVEL MARKERS ────────────────────────────────────────────────────
    "corner_markers":       {"layer": 10, "datatype": 0},
    "pad_markers":          {"layer": 11, "datatype": 0},
    "pos_markers":          {"layer": 12, "datatype": 0},
    "chiplet_id":           {"layer": 13, "datatype": 0},

    # ── WAFER-LEVEL MARKERS ───────────────────────────────────────────────────
    "wafer_markers":        {"layer": 21, "datatype": 0},
    "dicing_crosses":       {"layer": 22, "datatype": 0},
    "wafer_id":             {"layer": 23, "datatype": 0},

    # ── SUBSTRATE / IMPLANT ───────────────────────────────────────────────────
    "mesa_etch":            {"layer": 30, "datatype": 0},
    "n_implant":            {"layer": 31, "datatype": 0},
    "p_implant":            {"layer": 32, "datatype": 0},

    # ── PHOTONIC STRUCTURES ───────────────────────────────────────────────────
    "wg_core":              {"layer": 40, "datatype": 0},
    "wg_clad":              {"layer": 40, "datatype": 1},
    "ring":                 {"layer": 41, "datatype": 0},
    "grating":              {"layer": 42, "datatype": 0},
    "photonic_crystal":     {"layer": 43, "datatype": 0},

    # ── DIELECTRIC ────────────────────────────────────────────────────────────
    "dielectric":           {"layer": 50, "datatype": 0},
    "dielectric_etch":      {"layer": 51, "datatype": 0},

    # ── CONTACTS & VIAS ───────────────────────────────────────────────────────
    "contact":              {"layer": 60, "datatype": 0},
    "via1":                 {"layer": 61, "datatype": 0},
    "via2":                 {"layer": 62, "datatype": 0},

    # ── METAL ─────────────────────────────────────────────────────────────────
    "metal1":               {"layer": 70, "datatype": 0},
    "local_gates":          {"layer": 70, "datatype": 0},   # alias for metal1
    "top_gates":            {"layer": 71, "datatype": 0},
    "metal3":               {"layer": 72, "datatype": 0},
    "bond_pads":            {"layer": 73, "datatype": 0},

    # ── TEST STRUCTURES ───────────────────────────────────────────────────────
    "tlm":                  {"layer": 90, "datatype": 0},
    "van_der_pauw":         {"layer": 91, "datatype": 0},
    "optical_test":         {"layer": 92, "datatype": 0},
    "electrical_test":      {"layer": 93, "datatype": 0},

    # ── DO NOT FABRICATE ──────────────────────────────────────────────────────
    "keepout":              {"layer": 100, "datatype": 0},
    "dicing":               {"layer": 101, "datatype": 0},
    "write_field":          {"layer": 102, "datatype": 0},
}