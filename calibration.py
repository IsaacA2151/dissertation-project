"""
calibration.py — Per-user HRTF calibration profiles.

What is stored
--------------
elevation_bias_deg : float
    A constant offset added to every elevation lookup before the HRTF
    database is queried.  Corrects systematic "everything sounds too low /
    too high" errors that are common with non-individual HRTFs.
    Range: -30 to +30°.  Default: 0.

eq_gain_db : float
    Scales the elevation EQ shelf gain in SpatialEngine._apply_elevation_eq.
    The engine uses ±4 dB; setting this to 0.5 halves it, 2.0 doubles it.
    Useful for listeners who find the effect too pronounced or not strong
    enough.  Range: 0.0 to 3.0.  Default: 1.0.

itd_scale : float
    Multiplier applied to the interaural time difference by stretching /
    compressing the selected HRIR azimuth lookup.  Values > 1 exaggerate
    left/right separation; < 1 narrows it.  Implemented by biasing the
    azimuth lookup away from / toward the median plane before the database
    query.  Range: 0.5 to 2.0.  Default: 1.0.

preferred_sofa : str | None
    Filename (basename only, resolved against the ``data/`` directory) of
    the SOFA file that sounded most natural during the HRTF selection step.
    None means use the engine default.

selected_at : str
    ISO-8601 timestamp of the last save, for display only.

How calibration affects the audio path
---------------------------------------
SpatialEngine reads a CalibrationProfile at startup and whenever
apply_calibration() is called.  It stores the values under _lock so they
are safe to change while audio is running.  The callback reads them once
per block alongside the other locked state.

The elevation_bias and itd_scale are applied to the az/el values *before*
the HRTF database query — they shift which measurement is selected, which
is the correct place to intervene.  The eq_gain is applied inside
_apply_elevation_eq.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROFILE_PATH = Path("data/calibration.json")

# Calibration step definitions used by the UI wizard
CALIBRATION_STEPS: list[dict[str, Any]] = [
    {
        "id": "hrtf_select",
        "title": "HRTF Selection",
        "instruction": (
            "A source will play directly in front of you at 0° elevation. "
            "Close your eyes. Does it sound in front of you, or inside your head? "
            "We will cycle through available HRTF sets — pick the one that sounds "
            "most externalised (outside your head)."
        ),
        "az": 0.0,
        "el": 0.0,
    },
    {
        "id": "elevation_bias",
        "title": "Elevation Bias",
        "instruction": (
            "A source will play above you (80°). "
            "Use the slider to adjust until it sounds as high as possible. "
            "This corrects a systematic elevation offset in the HRTF."
        ),
        "az": 0.0,
        "el": 80.0,
    },
    {
        "id": "eq_gain",
        "title": "Elevation EQ Strength",
        "instruction": (
            "Move the source slowly between -30° and 80°. "
            "Adjust the EQ gain until the height difference feels natural — "
            "not too subtle, not too harsh."
        ),
        "az": 0.0,
        "el": 0.0,
    },
    {
        "id": "itd_scale",
        "title": "Left/Right Width",
        "instruction": (
            "A source will play at 90° (hard right). "
            "Adjust the width until it feels correctly outside your right ear — "
            "not inside your head, but not artificially wide either."
        ),
        "az": 90.0,
        "el": 0.0,
    },
]


@dataclass
class CalibrationProfile:
    elevation_bias_deg: float = 0.0
    eq_gain_db: float = 1.0          # multiplier on the ±4 dB shelf
    itd_scale: float = 1.0
    preferred_sofa: str | None = None
    selected_at: str = field(default_factory=lambda: _now_iso())

    # ------------------------------------------------------------------
    def clamp(self) -> "CalibrationProfile":
        """Clamp all numeric fields to their valid ranges and return self."""
        self.elevation_bias_deg = float(
            max(-30.0, min(30.0, self.elevation_bias_deg))
        )
        self.eq_gain_db = float(max(0.0, min(3.0, self.eq_gain_db)))
        self.itd_scale  = float(max(0.5, min(2.0, self.itd_scale)))
        return self

    # ------------------------------------------------------------------
    def save(self, path: Path = _PROFILE_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.selected_at = _now_iso()
        path.write_text(json.dumps(asdict(self), indent=2))

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: Path = _PROFILE_PATH) -> "CalibrationProfile":
        """Load from disk, returning defaults if the file does not exist."""
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text())
            profile = cls(
                elevation_bias_deg=float(data.get("elevation_bias_deg", 0.0)),
                eq_gain_db=float(data.get("eq_gain_db", 1.0)),
                itd_scale=float(data.get("itd_scale", 1.0)),
                preferred_sofa=data.get("preferred_sofa"),
                selected_at=data.get("selected_at", _now_iso()),
            )
            return profile.clamp()
        except Exception:
            return cls()

    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    # ------------------------------------------------------------------
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CalibrationProfile":
        return cls(
            elevation_bias_deg=float(d.get("elevation_bias_deg", 0.0)),
            eq_gain_db=float(d.get("eq_gain_db", 1.0)),
            itd_scale=float(d.get("itd_scale", 1.0)),
            preferred_sofa=d.get("preferred_sofa"),
        ).clamp()

    # ------------------------------------------------------------------
    def reset(self) -> "CalibrationProfile":
        self.elevation_bias_deg = 0.0
        self.eq_gain_db = 1.0
        self.itd_scale = 1.0
        self.preferred_sofa = None
        return self


def list_sofa_files(data_dir: str = "data") -> list[str]:
    """Return basenames of all .sofa files in the data directory."""
    try:
        return sorted(
            f for f in os.listdir(data_dir) if f.lower().endswith(".sofa")
        )
    except FileNotFoundError:
        return []


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")