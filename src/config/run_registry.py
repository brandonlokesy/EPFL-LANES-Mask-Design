import json
from pathlib import Path

from src.config.paths import REGISTRY_PATH

def _load() -> dict:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text())
    return {}

def _save(data: dict):
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(data, indent=2))

def _default_mask_entry() -> dict:
    return {"run": 1, "wafers": {}}

def next_wafer(mask_type: str, run: int = None) -> tuple[int, int]:
    """
    Returns (run_number, wafer_number) for the given mask type.
    Each mask type has its own independent run and wafer counters.
    """
    data = _load()
    if mask_type not in data:
        data[mask_type] = _default_mask_entry()

    entry = data[mask_type]
    if run is None:
        run = entry["run"]
    key = str(run)
    entry["wafers"][key] = entry["wafers"].get(key, 0) + 1
    entry["run"] = run
    _save(data)
    return run, entry["wafers"][key]

def new_run(mask_type: str) -> int:
    """Starts a new run for the given mask type, returns the new run number."""
    data = _load()
    if mask_type not in data:
        data[mask_type] = _default_mask_entry()
    data[mask_type]["run"] += 1
    _save(data)
    return data[mask_type]["run"]