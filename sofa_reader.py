import math
import numpy as np
from pysofaconventions import SOFAFile


class HRTFDatabase:
    """
    Loads an HRTF SOFA file and provides fast nearest-HRIR lookup
    using 3D unit-vector distance rather than raw Euclidean angle
    distance, which is more accurate near the poles.
    """

    def __init__(self, sofa_path: str):
        self.sofa_path = sofa_path
        self._sofa: SOFAFile | None = None

        sofa = SOFAFile(sofa_path, "r")
        try:
            ir = sofa.getDataIR()
            positions = sofa.getVariableValue("SourcePosition")
            fs = int(sofa.getSamplingRate())
        except Exception:
            sofa.close()
            raise

        if ir.ndim != 3 or ir.shape[1] < 2:
            sofa.close()
            raise ValueError(
                f"Unexpected IR array shape {ir.shape}; expected (N, >=2, L)"
            )
        if positions.ndim != 2 or positions.shape[1] < 2:
            sofa.close()
            raise ValueError(
                f"Unexpected SourcePosition shape {positions.shape}; expected (N, >=2)"
            )

        self._sofa = sofa
        self.fs = fs

        self.ir = ir.astype(np.float32)        # (N, 2, L)
        az_deg = positions[:, 0]
        el_deg = positions[:, 1]

        self._az_wrapped = np.mod(az_deg, 360.0)
        self._el = el_deg.copy()

        az_r = np.deg2rad(az_deg)
        el_r = np.deg2rad(el_deg)
        cos_el = np.cos(el_r)
        self._unit_vecs = np.column_stack([
            cos_el * np.sin(az_r),
            cos_el * np.cos(az_r),
            np.sin(el_r),
        ]).astype(np.float32)

    # ------------------------------------------------------------------
    def get_nearest_hrir(
        self, target_azimuth: float, target_elevation: float
    ) -> tuple[np.ndarray, np.ndarray, int, float, float]:
        """
        Return (hL, hR, idx, used_az_deg, used_el_deg) for the measurement
        whose direction is closest to (target_azimuth, target_elevation).

        ``idx`` is the row index into self.ir, returned so callers can
        directly index into pre-computed FFT tables without a secondary
        search.
        """
        az_r = math.radians(float(target_azimuth) % 360.0)
        el_r = math.radians(float(target_elevation))
        cos_el = math.cos(el_r)

        q = np.array([
            cos_el * math.sin(az_r),
            cos_el * math.cos(az_r),
            math.sin(el_r),
        ], dtype=np.float32)

        dots = self._unit_vecs @ q
        idx = int(np.argmax(dots))

        hL = self.ir[idx, 0, :]
        hR = self.ir[idx, 1, :]
        return hL, hR, idx, float(self._az_wrapped[idx]), float(self._el[idx])

    # ------------------------------------------------------------------
    def close(self) -> None:
        if self._sofa is not None:
            self._sofa.close()
            self._sofa = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()