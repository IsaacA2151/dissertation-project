import atexit
import logging
import math
import threading
import numpy as np
import sounddevice as sd
from numpy.fft import rfft, irfft
from sofa_reader import HRTFDatabase
from calibration import CalibrationProfile, list_sofa_files

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pink noise — Paul Kellett's method
# ---------------------------------------------------------------------------

def _make_pink_block(white: np.ndarray, state: np.ndarray) -> np.ndarray:
    out = np.empty(len(white), dtype=np.float64)
    b = state
    for i, w in enumerate(white):
        b[0] = 0.99886 * b[0] + w * 0.0555179
        b[1] = 0.99332 * b[1] + w * 0.0750759
        b[2] = 0.96900 * b[2] + w * 0.1538520
        b[3] = 0.86650 * b[3] + w * 0.3104856
        b[4] = 0.55000 * b[4] + w * 0.5329522
        b[5] = -0.7616 * b[5] - w * 0.0168980
        out[i] = (b[0]+b[1]+b[2]+b[3]+b[4]+b[5]+b[6] + w*0.5362) * 0.11
        b[6] = w * 0.115926
    return out.astype(np.float32)


class SpatialEngine:
    """
    Real-time stereo spatial audio engine using HRTF convolution.

    Calibration
    -----------
    A CalibrationProfile is loaded from disk at startup (or uses defaults).
    Three parameters are applied per audio block:

    elevation_bias_deg
        Added to the elevation value before the HRTF lookup.  Corrects a
        common perceptual offset where non-individual HRTFs make sources
        sound systematically too low or too high.

    eq_gain_db (multiplier, not dB despite the name)
        Scales the ±4 dB high-shelf applied by _apply_elevation_eq.
        A value of 0 disables EQ entirely; 2.0 doubles the shelf depth.

    itd_scale
        Biases the azimuth lookup to exaggerate or narrow left/right
        separation.  Applied by moving the lookup azimuth away from (>1) or
        toward (<1) the median plane before the database query.
        Implementation: az_eff = median + (az - median) * itd_scale.

    Calling apply_calibration(profile) replaces the active profile under
    the audio lock and is safe to call while the stream is running.

    Thread model
    ------------
    All shared user-facing state, including calibration values, is copied
    into plain floats under _lock at the start of _callback.  The callback
    itself never holds the lock during convolution.
    """

    SIGNALS = frozenset({"sine", "noise", "pink", "sweep"})

    def __init__(
        self,
        fs: int = 48000,
        tone_hz: float = 220.0,
        blocksize: int = 256,
        sofa_path: str = "hrtf_demo/data/hrtf_nh2.sofa",
        elevation_eq: bool = True,
        disambiguation_wobble: bool = False,
        calibration: CalibrationProfile | None = None,
    ):
        self.fs = int(fs)
        self.blocksize = int(blocksize)
        self.tone_hz = float(tone_hz)
        self._default_sofa_path = sofa_path

        # Calibration — loaded from disk if not provided
        cal = calibration or CalibrationProfile.load()
        self._cal_elevation_bias: float = cal.elevation_bias_deg
        self._cal_eq_gain: float = cal.eq_gain_db
        self._cal_itd_scale: float = cal.itd_scale

        # User-controlled features
        self._elevation_eq = bool(elevation_eq)
        self._disambiguation_wobble = bool(disambiguation_wobble)

        # Protected shared state
        self._lock = threading.Lock()
        self._paused = True
        self._azimuth = 0.0
        self._elevation = 0.0
        self._signal: str = "pink"

        # Callback-only state (no lock needed)
        self._phase = 0.0
        self._phase_inc = 2.0 * math.pi * self.tone_hz / self.fs
        self._rng = np.random.default_rng(0)
        self._pink_state = np.zeros(7, dtype=np.float64)
        self._sweep_pos: int = 0
        self._eq_state: float = 0.0
        self._callback_count: int = 0

        # HRTF database — use preferred_sofa from calibration if present
        sofa_to_load = sofa_path
        if cal.preferred_sofa:
            candidate = f"data/{cal.preferred_sofa}"
            import os
            if os.path.exists(candidate):
                sofa_to_load = candidate

        self.hrtf_db = self._load_db(sofa_to_load)
        self._build_fft_table()

        self.stream: sd.OutputStream | None = None
        atexit.register(self.stop)

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _load_db(self, sofa_path: str) -> HRTFDatabase:
        db = HRTFDatabase(sofa_path)
        if db.fs != self.fs:
            db.close()
            raise ValueError(
                f"HRTF fs={db.fs} does not match engine fs={self.fs}"
            )
        return db

    def _build_fft_table(self) -> None:
        """Pre-compute rfft of every HRIR pair in the current database."""
        hrir_len = self.hrtf_db.ir.shape[2]
        raw = self.blocksize + hrir_len - 1
        self._fft_len = 1 << (raw - 1).bit_length()

        n_pos = self.hrtf_db.ir.shape[0]
        self._hrir_ffts: list[tuple[np.ndarray, np.ndarray]] = []
        for i in range(n_pos):
            hL = self.hrtf_db.ir[i, 0, :].astype(np.float32)
            hR = self.hrtf_db.ir[i, 1, :].astype(np.float32)
            self._hrir_ffts.append((rfft(hL, n=self._fft_len),
                                    rfft(hR, n=self._fft_len)))

        tail = hrir_len - 1
        self._overlap_L = np.zeros(tail, dtype=np.float32)
        self._overlap_R = np.zeros(tail, dtype=np.float32)
        self._tail = tail

    # -----------------------------------------------------------------------
    # Calibration API
    # -----------------------------------------------------------------------

    def apply_calibration(self, profile: CalibrationProfile) -> None:
        """
        Apply a new calibration profile.  Safe to call while audio is
        running — values are swapped under the lock.

        If preferred_sofa has changed and the file exists, the HRTF database
        is reloaded.  The stream is briefly paused during the reload to
        avoid a glitch from changed overlap-add buffer sizes.
        """
        import os
        new_sofa: str | None = None
        if profile.preferred_sofa:
            candidate = f"data/{profile.preferred_sofa}"
            current_basename = os.path.basename(self.hrtf_db.sofa_path)
            if (os.path.exists(candidate)
                    and profile.preferred_sofa != current_basename):
                new_sofa = candidate

        if new_sofa:
            # Pause audio, swap database, rebuild FFT table, resume
            was_paused: bool
            with self._lock:
                was_paused = self._paused
                self._paused = True

            old_db = self.hrtf_db
            try:
                self.hrtf_db = self._load_db(new_sofa)
                self._build_fft_table()
                old_db.close()
                log.info("Loaded HRTF: %s", new_sofa)
            except Exception as exc:
                log.error("Failed to load HRTF %s: %s", new_sofa, exc)
                self.hrtf_db = old_db   # roll back

            with self._lock:
                self._paused = was_paused

        with self._lock:
            self._cal_elevation_bias = profile.elevation_bias_deg
            self._cal_eq_gain = profile.eq_gain_db
            self._cal_itd_scale = profile.itd_scale

    def get_calibration(self) -> CalibrationProfile:
        with self._lock:
            import os
            return CalibrationProfile(
                elevation_bias_deg=self._cal_elevation_bias,
                eq_gain_db=self._cal_eq_gain,
                itd_scale=self._cal_itd_scale,
                preferred_sofa=os.path.basename(self.hrtf_db.sofa_path),
            )

    # -----------------------------------------------------------------------
    # State setters
    # -----------------------------------------------------------------------

    def set_azimuth(self, az_deg: float) -> None:
        with self._lock:
            self._azimuth = float(az_deg) % 360.0

    def set_elevation(self, el_deg: float) -> None:
        with self._lock:
            self._elevation = float(el_deg)

    def set_signal(self, sig: str) -> None:
        sig = sig.lower().strip()
        if sig not in self.SIGNALS:
            sig = "pink"
        with self._lock:
            self._signal = sig

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            self._paused = bool(paused)

    def toggle_paused(self) -> bool:
        with self._lock:
            self._paused = not self._paused
            return self._paused

    def set_elevation_eq(self, enabled: bool) -> None:
        with self._lock:
            self._elevation_eq = bool(enabled)

    def set_disambiguation_wobble(self, enabled: bool) -> None:
        with self._lock:
            self._disambiguation_wobble = bool(enabled)

    def get_state(self) -> dict:
        with self._lock:
            import os
            return {
                "azimuth": self._azimuth,
                "elevation": self._elevation,
                "signal": self._signal,
                "paused": self._paused,
                "elevation_eq": self._elevation_eq,
                "disambiguation_wobble": self._disambiguation_wobble,
                "calibration": {
                    "elevation_bias_deg": self._cal_elevation_bias,
                    "eq_gain_db": self._cal_eq_gain,
                    "itd_scale": self._cal_itd_scale,
                    "preferred_sofa": os.path.basename(self.hrtf_db.sofa_path),
                },
            }

    # -----------------------------------------------------------------------
    # Signal generators (callback-only)
    # -----------------------------------------------------------------------

    def _gen_sine(self, frames: int) -> np.ndarray:
        t = np.arange(frames, dtype=np.float64)
        block = np.sin(self._phase + t * self._phase_inc).astype(np.float32)
        self._phase = (self._phase + frames * self._phase_inc) % (2.0 * math.pi)
        return block

    def _gen_noise(self, frames: int) -> np.ndarray:
        return (self._rng.standard_normal(frames) * 0.12).astype(np.float32)

    def _gen_pink(self, frames: int) -> np.ndarray:
        return _make_pink_block(self._rng.standard_normal(frames), self._pink_state)

    def _gen_sweep(self, frames: int) -> np.ndarray:
        period = self.fs
        f_lo, f_hi = 200.0, 16000.0
        idx = (self._sweep_pos + np.arange(frames)) % period
        self._sweep_pos = int((self._sweep_pos + frames) % period)
        f = f_lo * (f_hi / f_lo) ** (idx / period)
        block = np.sin(np.cumsum(2.0 * math.pi * f / self.fs)).astype(np.float32) * 0.25
        return block

    # -----------------------------------------------------------------------
    # Elevation EQ (callback-only)
    # -----------------------------------------------------------------------

    def _apply_elevation_eq(
        self, block: np.ndarray, el_deg: float, gain_multiplier: float
    ) -> np.ndarray:
        """
        One-pole high-shelf scaled by gain_multiplier (from calibration).
        gain_multiplier=0 → flat; 1.0 → default ±4 dB; 2.0 → ±8 dB.
        """
        if gain_multiplier == 0.0:
            return block
        t = float(np.clip(el_deg / 80.0, -1.0, 1.0))
        fc = 3000.0 * (1.0 - 0.3 * t)
        gain_db = 4.0 * t * gain_multiplier
        gain = 10.0 ** (gain_db / 20.0)
        wc = 2.0 * math.pi * fc / self.fs
        alpha = wc / (wc + 1.0)
        out = np.empty_like(block)
        s = self._eq_state
        for i, x in enumerate(block):
            s += alpha * (float(x) - s)
            out[i] = x + (gain - 1.0) * s
        self._eq_state = s
        return out

    # -----------------------------------------------------------------------
    # Audio callback
    # -----------------------------------------------------------------------

    def _callback(self, outdata, frames, time_info, status):
        if status:
            log.warning("sounddevice status: %s", status)

        with self._lock:
            az            = self._azimuth
            el            = self._elevation
            sig           = self._signal
            paused        = self._paused
            eq_on         = self._elevation_eq
            wobble_on     = self._disambiguation_wobble
            el_bias       = self._cal_elevation_bias
            eq_gain       = self._cal_eq_gain
            itd_scale     = self._cal_itd_scale

        if paused:
            outdata[:] = 0
            return

        # Wobble
        if wobble_on:
            t_sec = self._callback_count * self.blocksize / self.fs
            az = (az + 2.0 * math.sin(2.0 * math.pi * 0.3 * t_sec)) % 360.0
        self._callback_count += 1

        # Apply calibration to az/el before HRTF lookup
        el_cal = el + el_bias

        # ITD scale: move az away from / toward the median plane
        # az=0 and az=180 are the median plane; we scale the deviation from 0
        # (treating the range as signed -180..180 for the scaling).
        az_signed = az if az <= 180.0 else az - 360.0
        az_cal_signed = az_signed * itd_scale
        # Reclamp to 0..360
        lookup_az = ((-az_cal_signed) % 360.0)   # negate for dataset convention
        lookup_el = el_cal

        # Generate mono block
        if sig == "sine":
            mono = self._gen_sine(frames)
        elif sig == "pink":
            mono = self._gen_pink(frames)
        elif sig == "sweep":
            mono = self._gen_sweep(frames)
        else:
            mono = self._gen_noise(frames)

        # Elevation EQ (calibrated gain)
        if eq_on:
            mono = self._apply_elevation_eq(mono, el_cal, eq_gain)

        # HRTF lookup
        _, _, idx, _, _ = self.hrtf_db.get_nearest_hrir(lookup_az, lookup_el)
        hL_fft, hR_fft = self._hrir_ffts[idx]

        # Overlap-add convolution
        mono_fft = rfft(mono, n=self._fft_len)
        conv_L = irfft(mono_fft * hL_fft)[:frames + self._tail].astype(np.float32)
        conv_R = irfft(mono_fft * hR_fft)[:frames + self._tail].astype(np.float32)

        if self._tail > 0:
            conv_L[:self._tail] += self._overlap_L
            conv_R[:self._tail] += self._overlap_R
            self._overlap_L = conv_L[frames:frames + self._tail].copy()
            self._overlap_R = conv_R[frames:frames + self._tail].copy()

        out = np.stack([conv_L[:frames], conv_R[:frames]], axis=1)
        outdata[:] = np.clip(out, -0.9, 0.9)

    # -----------------------------------------------------------------------
    # Stream lifecycle
    # -----------------------------------------------------------------------

    def start(self) -> None:
        if self.stream is not None:
            return
        self.stream = sd.OutputStream(
            samplerate=self.fs,
            channels=2,
            blocksize=self.blocksize,
            dtype="float32",
            callback=self._callback,
        )
        self.stream.start()

    def stop(self) -> None:
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        if self.hrtf_db is not None:
            self.hrtf_db.close()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *_):
        self.stop()