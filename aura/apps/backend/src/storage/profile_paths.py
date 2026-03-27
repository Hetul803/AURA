from __future__ import annotations
import os
from pathlib import Path


def profile_dir() -> Path:
    override = os.getenv("PROFILE_DIR_OVERRIDE")
    if override:
        base = Path(override)
    elif os.name == "nt":
        base = Path(os.getenv("APPDATA", str(Path.home()))) / "AURA"
    else:
        base = Path.home() / ".aura"
    base.mkdir(parents=True, exist_ok=True)
    for sub in ["browser_state", "snapshots", "artifacts"]:
        (base / sub).mkdir(exist_ok=True)
    return base
