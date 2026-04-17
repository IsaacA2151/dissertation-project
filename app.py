from flask import Flask, request, jsonify, render_template_string
from spatial_engine import SpatialEngine
from calibration import (
    CalibrationProfile,
    CALIBRATION_STEPS,
    list_sofa_files,
)

engine = SpatialEngine()
engine.start()

app = Flask(__name__)

HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Spatial Audio</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@300;400;500&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --bg:      #0d0f12;
      --surface: #141720;
      --border:  #252933;
      --accent:  #4af0c4;
      --accent2: #f06a4a;
      --text:    #e8eaf0;
      --muted:   #5a6070;
      --mono:    'DM Mono', monospace;
      --sans:    'DM Sans', sans-serif;
    }

    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: var(--bg);
      color: var(--text);
      font-family: var(--sans);
      font-weight: 300;
      min-height: 100vh;
      padding: 32px 28px;
    }

    h1 {
      font-family: var(--mono);
      font-weight: 300;
      font-size: 13px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--accent);
      margin-bottom: 32px;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    h1::before {
      content: '';
      display: inline-block;
      width: 6px; height: 6px;
      background: var(--accent);
      border-radius: 50%;
      animation: pulse 2s ease-in-out infinite;
    }
    h1.paused::before { background: var(--muted); animation: none; }
    @keyframes pulse {
      0%,100% { opacity:1; transform:scale(1); }
      50%      { opacity:0.4; transform:scale(0.7); }
    }

    /* ---- Layout ---- */
    .layout {
      display: grid;
      grid-template-columns: 340px 1fr;
      gap: 16px;
      max-width: 960px;
    }
    .panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 24px;
    }
    .section { margin-bottom: 26px; }
    .section:last-child { margin-bottom: 0; }

    .label {
      font-family: var(--mono);
      font-size: 10px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 10px;
    }
    .value-row {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin-bottom: 8px;
    }
    .value-name { font-size: 14px; color: var(--text); }
    .value-num  { font-family: var(--mono); font-size: 22px; font-weight: 400; color: var(--accent); }
    .value-unit { font-family: var(--mono); font-size: 12px; color: var(--muted); margin-left: 2px; }

    /* ---- Range inputs ---- */
    input[type=range] {
      -webkit-appearance: none;
      width: 100%; height: 2px;
      background: var(--border);
      border-radius: 2px; outline: none;
      margin-bottom: 4px;
    }
    input[type=range]::-webkit-slider-thumb {
      -webkit-appearance: none;
      width: 14px; height: 14px;
      border-radius: 50%;
      background: var(--accent);
      cursor: pointer;
      transition: transform 0.15s;
    }
    input[type=range]::-webkit-slider-thumb:hover { transform: scale(1.3); }

    .hint { font-size: 11px; color: var(--muted); font-family: var(--mono); }

    /* ---- Buttons ---- */
    .play-btn {
      width: 100%; padding: 12px;
      background: transparent;
      border: 1px solid var(--accent);
      border-radius: 10px;
      color: var(--accent);
      font-family: var(--mono); font-size: 12px;
      letter-spacing: 0.12em; text-transform: uppercase;
      cursor: pointer;
      transition: background 0.15s, color 0.15s;
    }
    .play-btn:hover, .play-btn.playing { background: var(--accent); color: var(--bg); }

    .sig-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 8px; }
    .sig-btn {
      padding: 9px 4px;
      background: transparent;
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--muted);
      font-family: var(--mono); font-size: 10px;
      letter-spacing: 0.08em; text-transform: uppercase;
      cursor: pointer;
      transition: border-color 0.15s, color 0.15s;
      text-align: center;
    }
    .sig-btn:hover { border-color: var(--accent); color: var(--text); }
    .sig-btn.active { border-color: var(--accent); color: var(--accent); }

    /* ---- Toggle switches ---- */
    .toggle-row {
      display: flex; align-items: center; justify-content: space-between;
      padding: 10px 0;
      border-bottom: 1px solid var(--border);
    }
    .toggle-row:last-child { border-bottom: none; padding-bottom: 0; }
    .toggle-label { font-size: 13px; color: var(--text); }
    .toggle-desc  { font-size: 11px; color: var(--muted); margin-top: 2px; font-family: var(--mono); }
    .switch { position: relative; width: 36px; height: 20px; flex-shrink: 0; }
    .switch input { opacity: 0; width: 0; height: 0; }
    .slider-track {
      position: absolute; inset: 0;
      background: var(--border); border-radius: 20px;
      cursor: pointer; transition: background 0.2s;
    }
    .slider-track::after {
      content: '';
      position: absolute; top: 3px; left: 3px;
      width: 14px; height: 14px;
      background: var(--muted); border-radius: 50%;
      transition: transform 0.2s, background 0.2s;
    }
    .switch input:checked + .slider-track { background: #1a3530; }
    .switch input:checked + .slider-track::after { transform: translateX(16px); background: var(--accent); }

    /* ---- Calibration button ---- */
    .cal-btn {
      width: 100%; padding: 10px;
      background: transparent;
      border: 1px solid var(--border);
      border-radius: 10px;
      color: var(--muted);
      font-family: var(--mono); font-size: 11px;
      letter-spacing: 0.10em; text-transform: uppercase;
      cursor: pointer;
      transition: border-color 0.15s, color 0.15s;
    }
    .cal-btn:hover { border-color: var(--accent2); color: var(--accent2); }

    .cal-summary {
      font-family: var(--mono); font-size: 10px;
      color: var(--muted); line-height: 1.7;
      margin-top: 10px;
    }
    .cal-summary span { color: var(--text); }

    /* ---- Canvas panel ---- */
    .viz-panel { display: flex; flex-direction: column; gap: 16px; }
    .canvas-wrap {
      flex: 1; position: relative;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 12px; overflow: hidden;
      display: flex; align-items: center; justify-content: center;
    }
    canvas { display: block; }
    .canvas-label {
      position: absolute; bottom: 10px; left: 14px;
      font-family: var(--mono); font-size: 10px;
      letter-spacing: 0.12em; text-transform: uppercase;
      color: var(--muted);
    }

    /* ---- Calibration wizard overlay ---- */
    .wizard-overlay {
      display: none;
      position: fixed; inset: 0;
      background: rgba(0,0,0,0.72);
      z-index: 100;
      align-items: center; justify-content: center;
    }
    .wizard-overlay.open { display: flex; }

    .wizard {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 32px;
      width: min(560px, 94vw);
      position: relative;
    }

    .wizard-step-bar {
      display: flex; gap: 6px; margin-bottom: 24px;
    }
    .step-dot {
      flex: 1; height: 3px;
      background: var(--border); border-radius: 2px;
      transition: background 0.3s;
    }
    .step-dot.done    { background: var(--accent); }
    .step-dot.current { background: var(--accent2); }

    .wizard-title {
      font-family: var(--mono); font-size: 11px;
      letter-spacing: 0.14em; text-transform: uppercase;
      color: var(--accent2); margin-bottom: 8px;
    }
    .wizard-instruction {
      font-size: 14px; line-height: 1.7;
      color: var(--text); margin-bottom: 24px;
    }

    .wizard-control { margin-bottom: 20px; }
    .wizard-control .label { margin-bottom: 8px; }
    .wizard-control .value-num { font-size: 18px; }

    /* HRTF selector */
    .sofa-list {
      display: flex; flex-direction: column; gap: 8px;
      max-height: 180px; overflow-y: auto;
    }
    .sofa-item {
      padding: 10px 14px;
      background: transparent;
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--muted);
      font-family: var(--mono); font-size: 11px;
      cursor: pointer;
      text-align: left;
      transition: border-color 0.15s, color 0.15s;
    }
    .sofa-item:hover  { border-color: var(--accent); color: var(--text); }
    .sofa-item.active { border-color: var(--accent); color: var(--accent); }

    .wizard-footer {
      display: flex; justify-content: space-between;
      align-items: center; margin-top: 24px;
    }
    .wiz-btn {
      padding: 10px 22px;
      background: transparent;
      border-radius: 10px;
      font-family: var(--mono); font-size: 11px;
      letter-spacing: 0.10em; text-transform: uppercase;
      cursor: pointer; transition: background 0.15s, color 0.15s;
    }
    .wiz-btn-next {
      border: 1px solid var(--accent); color: var(--accent);
    }
    .wiz-btn-next:hover { background: var(--accent); color: var(--bg); }
    .wiz-btn-skip {
      border: 1px solid var(--border); color: var(--muted);
    }
    .wiz-btn-skip:hover { color: var(--text); }
    .wiz-btn-close {
      position: absolute; top: 16px; right: 18px;
      border: none; background: none;
      color: var(--muted); font-size: 18px; cursor: pointer;
      padding: 4px 8px;
    }
    .wiz-btn-close:hover { color: var(--text); }
  </style>
</head>
<body>

<h1 id="statusDot" class="paused">Spatial Audio</h1>

<div class="layout">

  <!-- Left: Controls -->
  <div class="panel">

    <div class="section">
      <div class="label">Playback</div>
      <button class="play-btn" id="btnPlayPause">&#9654; Play</button>
    </div>

    <div class="section">
      <div class="label">Azimuth</div>
      <div class="value-row">
        <span class="value-name">Horizontal</span>
        <span><span class="value-num" id="azText">0</span><span class="value-unit">°</span></span>
      </div>
      <input id="az" type="range" min="0" max="360" value="0" step="1" />
      <div class="hint">0° front &nbsp;·&nbsp; 90° right &nbsp;·&nbsp; 270° left</div>
    </div>

    <div class="section">
      <div class="label">Elevation</div>
      <div class="value-row">
        <span class="value-name">Vertical</span>
        <span><span class="value-num" id="elText">0</span><span class="value-unit">°</span></span>
      </div>
      <input id="el" type="range" min="-30" max="80" value="0" step="1" />
      <div class="hint">-30° below &nbsp;·&nbsp; 0° level &nbsp;·&nbsp; 80° above</div>
    </div>

    <div class="section">
      <div class="label">Signal</div>
      <div class="sig-grid">
        <button class="sig-btn" data-sig="noise">White</button>
        <button class="sig-btn active" data-sig="pink">Pink</button>
        <button class="sig-btn" data-sig="sweep">Sweep</button>
        <button class="sig-btn" data-sig="sine">Sine</button>
      </div>
      <div class="hint" id="sigHint" style="margin-top:8px;">Pink noise — best for hearing elevation cues</div>
    </div>

    <div class="section">
      <div class="label">Perception Aids</div>
      <div class="toggle-row">
        <div>
          <div class="toggle-label">Elevation EQ</div>
          <div class="toggle-desc">Spectral tilt ±4 dB by height</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="toggleEQ" checked />
          <span class="slider-track"></span>
        </label>
      </div>
      <div class="toggle-row">
        <div>
          <div class="toggle-label">Wobble</div>
          <div class="toggle-desc">±2° oscillation, resolves front/back</div>
        </div>
        <label class="switch">
          <input type="checkbox" id="toggleWobble" />
          <span class="slider-track"></span>
        </label>
      </div>
    </div>

    <div class="section">
      <div class="label">Calibration</div>
      <button class="cal-btn" id="btnCalibrate">&#9881; Run calibration wizard</button>
      <div class="cal-summary" id="calSummary"></div>
    </div>

  </div><!-- /left panel -->

  <!-- Right: Visuals -->
  <div class="panel viz-panel">
    <div class="canvas-wrap" style="height:260px;">
      <canvas id="azCanvas" width="500" height="240"></canvas>
      <span class="canvas-label">Azimuth</span>
    </div>
    <div class="canvas-wrap" style="height:260px;">
      <canvas id="elCanvas" width="500" height="240"></canvas>
      <span class="canvas-label">Elevation</span>
    </div>
  </div>

</div><!-- /layout -->

<!-- ===== Calibration Wizard ===== -->
<div class="wizard-overlay" id="wizardOverlay">
  <div class="wizard">
    <button class="wiz-btn-close" id="btnWizClose">&#x2715;</button>

    <div class="wizard-step-bar" id="stepBar"></div>
    <div class="wizard-title"    id="wizTitle"></div>
    <div class="wizard-instruction" id="wizInstruction"></div>

    <!-- Step-specific controls injected here -->
    <div id="wizControls"></div>

    <div class="wizard-footer">
      <button class="wiz-btn wiz-btn-skip" id="btnWizSkip">Skip</button>
      <button class="wiz-btn wiz-btn-next" id="btnWizNext">Next</button>
    </div>
  </div>
</div>

<script>
/* =====================================================================
   Constants
   ===================================================================== */
const C_ACCENT  = "#4af0c4";
const C_ACCENT2 = "#f06a4a";
const C_MUTED   = "#5a6070";
const C_TEXT    = "#e8eaf0";
const C_BORDER  = "#252933";

const sigHints = {
  noise: "White noise — flat spectrum",
  pink:  "Pink noise — best for hearing elevation cues",
  sweep: "Log sweep 200 Hz–16 kHz — makes spectral notches very audible",
  sine:  "Sine tone — useful for ITD/ILD left/right demo",
};

/* =====================================================================
   Main controls
   ===================================================================== */
const az        = document.getElementById("az");
const el        = document.getElementById("el");
const azText    = document.getElementById("azText");
const elText    = document.getElementById("elText");
const btnPP     = document.getElementById("btnPlayPause");
const statusDot = document.getElementById("statusDot");
const azCanvas  = document.getElementById("azCanvas");
const azCtx     = azCanvas.getContext("2d");
const elCanvas  = document.getElementById("elCanvas");
const elCtx     = elCanvas.getContext("2d");

let paused        = true;
let currentSignal = "pink";
let lastSent      = 0;

function updatePlayUI() {
  if (paused) {
    btnPP.textContent = "▶  Play";
    btnPP.classList.remove("playing");
    statusDot.classList.add("paused");
  } else {
    btnPP.textContent = "⏸  Pause";
    btnPP.classList.add("playing");
    statusDot.classList.remove("paused");
  }
}

btnPP.addEventListener("click", async () => {
  const res = await fetch("/api/toggle", { method: "POST" });
  const st  = await res.json();
  paused = !!st.paused;
  updatePlayUI();
});

document.querySelectorAll(".sig-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".sig-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    currentSignal = btn.dataset.sig;
    document.getElementById("sigHint").textContent = sigHints[currentSignal] || "";
    sendState();
  });
});

document.getElementById("toggleEQ").addEventListener("change", async function() {
  await fetch("/api/set", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ elevation_eq: this.checked })
  });
});
document.getElementById("toggleWobble").addEventListener("change", async function() {
  await fetch("/api/set", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ disambiguation_wobble: this.checked })
  });
});

az.addEventListener("input", () => {
  azText.textContent = Number(az.value).toFixed(0);
  drawAzimuth(Number(az.value));
  sendState();
});
el.addEventListener("input", () => {
  elText.textContent = Number(el.value).toFixed(0);
  drawElevation(Number(el.value));
  sendState();
});

async function sendState() {
  const now = performance.now();
  if (now - lastSent < 33) return;
  lastSent = now;
  await fetch("/api/state", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ azimuth: Number(az.value), elevation: Number(el.value), signal: currentSignal })
  });
}

/* =====================================================================
   Calibration summary
   ===================================================================== */
function updateCalSummary(cal) {
  if (!cal) return;
  document.getElementById("calSummary").innerHTML =
    `El bias <span>${cal.elevation_bias_deg > 0 ? "+" : ""}${cal.elevation_bias_deg.toFixed(1)}°</span>` +
    ` &nbsp;·&nbsp; EQ gain <span>×${cal.eq_gain_db.toFixed(2)}</span>` +
    ` &nbsp;·&nbsp; ITD <span>×${cal.itd_scale.toFixed(2)}</span>` +
    (cal.preferred_sofa ? ` &nbsp;·&nbsp; <span>${cal.preferred_sofa}</span>` : "");
}

/* =====================================================================
   Calibration wizard
   ===================================================================== */
const overlay  = document.getElementById("wizardOverlay");
const stepBar  = document.getElementById("stepBar");
const wizTitle = document.getElementById("wizTitle");
const wizInstr = document.getElementById("wizInstruction");
const wizCtrl  = document.getElementById("wizControls");
const btnNext  = document.getElementById("btnWizNext");
const btnSkip  = document.getElementById("btnWizSkip");
const btnClose = document.getElementById("btnWizClose");

let wizSteps      = [];
let wizStepIdx    = 0;
let sofaFiles     = [];
let draftCal      = {};   // accumulates user choices

document.getElementById("btnCalibrate").addEventListener("click", openWizard);
btnClose.addEventListener("click", closeWizard);

btnSkip.addEventListener("click", () => {
  wizStepIdx++;
  renderStep();
});

btnNext.addEventListener("click", async () => {
  await commitStep();
  wizStepIdx++;
  renderStep();
});

async function openWizard() {
  // Fetch step definitions and available SOFAs from server
  const [stepsRes, stateRes] = await Promise.all([
    fetch("/api/calibration/steps"),
    fetch("/api/state"),
  ]);
  wizSteps   = await stepsRes.json();
  const state = await stateRes.json();
  draftCal   = { ...state.calibration };
  sofaFiles  = draftCal._sofa_list || [];

  // Also fetch sofa list separately
  const sofaRes = await fetch("/api/calibration/sofas");
  sofaFiles = await sofaRes.json();

  wizStepIdx = 0;
  overlay.classList.add("open");

  // Make sure audio is playing during calibration
  if (paused) {
    const res = await fetch("/api/toggle", { method: "POST" });
    const st  = await res.json();
    paused = !!st.paused;
    updatePlayUI();
  }

  renderStep();
}

function closeWizard() {
  overlay.classList.remove("open");
}

function renderStepBar() {
  stepBar.innerHTML = "";
  wizSteps.forEach((_, i) => {
    const d = document.createElement("div");
    d.className = "step-dot" + (i < wizStepIdx ? " done" : i === wizStepIdx ? " current" : "");
    stepBar.appendChild(d);
  });
}

async function renderStep() {
  if (wizStepIdx >= wizSteps.length) {
    // Save and close
    await saveDraft();
    closeWizard();
    // Refresh summary
    const st = await fetch("/api/state").then(r => r.json());
    updateCalSummary(st.calibration);
    return;
  }

  const step = wizSteps[wizStepIdx];
  renderStepBar();
  wizTitle.textContent = step.title;
  wizInstr.textContent = step.instruction;

  // Set engine to the step's reference position
  await fetch("/api/state", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify({ azimuth: step.az, elevation: step.el })
  });
  az.value = step.az; azText.textContent = step.az;
  el.value = step.el; elText.textContent = step.el;
  drawAzimuth(step.az);
  drawElevation(step.el);

  // Render step-specific controls
  wizCtrl.innerHTML = "";
  if (step.id === "hrtf_select") renderSofaStep();
  else if (step.id === "elevation_bias") renderSliderStep("elevation_bias_deg", "Elevation bias", -30, 30, 1, "°", draftCal.elevation_bias_deg ?? 0);
  else if (step.id === "eq_gain")        renderSliderStep("eq_gain_db", "EQ gain multiplier", 0, 3, 0.05, "×", draftCal.eq_gain_db ?? 1.0);
  else if (step.id === "itd_scale")      renderSliderStep("itd_scale", "Left/right width", 0.5, 2, 0.05, "×", draftCal.itd_scale ?? 1.0);

  btnNext.textContent = wizStepIdx === wizSteps.length - 1 ? "Save" : "Next";
}

function renderSofaStep() {
  const list = document.createElement("div");
  list.className = "sofa-list";
  if (sofaFiles.length === 0) {
    list.innerHTML = '<div style="color:var(--muted);font-size:12px;font-family:var(--mono)">No additional .sofa files found in data/</div>';
  } else {
    sofaFiles.forEach(f => {
      const btn = document.createElement("button");
      btn.className = "sofa-item" + (f === draftCal.preferred_sofa ? " active" : "");
      btn.textContent = f;
      btn.addEventListener("click", async () => {
        document.querySelectorAll(".sofa-item").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        draftCal.preferred_sofa = f;
        // Preview immediately
        await fetch("/api/calibration/preview", {
          method: "POST", headers: {"Content-Type":"application/json"},
          body: JSON.stringify({ preferred_sofa: f })
        });
      });
      list.appendChild(btn);
    });
  }
  wizCtrl.appendChild(list);
}

function renderSliderStep(key, labelText, min, max, step, unit, initVal) {
  const wrap  = document.createElement("div");
  wrap.className = "wizard-control";

  const row   = document.createElement("div");
  row.className = "value-row";
  row.innerHTML = `<span class="value-name">${labelText}</span>
    <span><span class="value-num" id="wiz_${key}_val">${Number(initVal).toFixed(2)}</span><span class="value-unit">${unit}</span></span>`;

  const slider = document.createElement("input");
  slider.type  = "range";
  slider.min   = min; slider.max = max; slider.step = step;
  slider.value = initVal;

  slider.addEventListener("input", async () => {
    const v = Number(slider.value);
    document.getElementById(`wiz_${key}_val`).textContent = v.toFixed(2);
    draftCal[key] = v;
    // Live preview: send to engine immediately
    await fetch("/api/calibration/preview", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ [key]: v })
    });
  });

  wrap.appendChild(row);
  wrap.appendChild(slider);
  wizCtrl.appendChild(wrap);
}

async function commitStep() {
  // Already live-previewed; nothing extra to commit per step
}

async function saveDraft() {
  await fetch("/api/calibration/save", {
    method: "POST", headers: {"Content-Type":"application/json"},
    body: JSON.stringify(draftCal)
  });
}

/* =====================================================================
   Canvas drawing
   ===================================================================== */
function drawAzimuth(deg) {
  const w=azCanvas.width, h=azCanvas.height, cx=w/2, cy=h/2;
  const r = Math.min(w,h)*0.38;
  azCtx.clearRect(0,0,w,h);

  azCtx.beginPath(); azCtx.arc(cx,cy,r,0,Math.PI*2);
  azCtx.strokeStyle=C_BORDER; azCtx.lineWidth=1; azCtx.stroke();

  for (let a=0;a<360;a+=30) {
    const rad=(a-90)*Math.PI/180;
    const inner=r-(a%90===0?12:6);
    azCtx.beginPath();
    azCtx.moveTo(cx+inner*Math.cos(rad),cy+inner*Math.sin(rad));
    azCtx.lineTo(cx+r*Math.cos(rad),cy+r*Math.sin(rad));
    azCtx.strokeStyle=a%90===0?C_MUTED:C_BORDER;
    azCtx.lineWidth=a%90===0?1:0.5; azCtx.stroke();
  }

  azCtx.fillStyle=C_MUTED; azCtx.font="11px 'DM Mono',monospace"; azCtx.textAlign="center";
  azCtx.fillText("0°",cx,cy-r-14); azCtx.fillText("90°",cx+r+18,cy+4);
  azCtx.fillText("180°",cx,cy+r+18); azCtx.fillText("270°",cx-r-20,cy+4);

  const th=(deg-90)*Math.PI/180;
  azCtx.beginPath();
  azCtx.moveTo(cx+r*0.18*Math.cos(th),cy+r*0.18*Math.sin(th));
  azCtx.lineTo(cx+r*0.82*Math.cos(th),cy+r*0.82*Math.sin(th));
  azCtx.strokeStyle=C_ACCENT; azCtx.lineWidth=1.5; azCtx.stroke();

  azCtx.beginPath(); azCtx.arc(cx+r*Math.cos(th),cy+r*Math.sin(th),7,0,Math.PI*2);
  azCtx.fillStyle=C_ACCENT; azCtx.fill();
  azCtx.beginPath(); azCtx.arc(cx,cy,5,0,Math.PI*2);
  azCtx.fillStyle=C_TEXT; azCtx.fill();
  azCtx.fillStyle=C_ACCENT; azCtx.font="500 12px 'DM Mono',monospace";
  azCtx.fillText(deg+"°",cx,cy+r+34);
}

function drawElevation(deg) {
  const w=elCanvas.width,h=elCanvas.height,cx=w/2,cy=h*0.68;
  const r=Math.min(w,h)*0.36;
  elCtx.clearRect(0,0,w,h);

  elCtx.beginPath();
  elCtx.moveTo(cx-r-20,cy); elCtx.lineTo(cx+r+20,cy);
  elCtx.strokeStyle=C_BORDER; elCtx.lineWidth=1; elCtx.stroke();

  elCtx.beginPath(); elCtx.arc(cx,cy,r,Math.PI,0);
  elCtx.strokeStyle=C_BORDER; elCtx.lineWidth=1; elCtx.stroke();

  [-30,0,30,60,80].forEach(e=>{
    const a=-e*Math.PI/180;
    const ox=cx+r*Math.cos(a), oy=cy+r*Math.sin(a);
    const nx=cx+(r+10)*Math.cos(a), ny=cy+(r+10)*Math.sin(a);
    elCtx.beginPath(); elCtx.moveTo(ox,oy); elCtx.lineTo(nx,ny);
    elCtx.strokeStyle=C_MUTED; elCtx.lineWidth=0.75; elCtx.stroke();
    elCtx.fillStyle=C_MUTED; elCtx.font="10px 'DM Mono',monospace"; elCtx.textAlign="center";
    elCtx.fillText(e+"°",nx+12*Math.cos(a),ny+12*Math.sin(a));
  });

  const clamped=Math.max(-30,Math.min(80,deg));
  const a=-clamped*Math.PI/180;
  const sx=cx+r*Math.cos(a), sy=cy+r*Math.sin(a);

  elCtx.beginPath();
  elCtx.moveTo(cx,cy); elCtx.lineTo(sx*0.85+cx*0.15,sy*0.85+cy*0.15);
  elCtx.strokeStyle=C_ACCENT2; elCtx.lineWidth=1.5; elCtx.stroke();

  elCtx.beginPath(); elCtx.arc(sx,sy,7,0,Math.PI*2);
  elCtx.fillStyle=C_ACCENT2; elCtx.fill();
  elCtx.beginPath(); elCtx.arc(cx,cy,5,0,Math.PI*2);
  elCtx.fillStyle=C_TEXT; elCtx.fill();
  elCtx.fillStyle=C_ACCENT2; elCtx.font="500 12px 'DM Mono',monospace"; elCtx.textAlign="center";
  elCtx.fillText(deg+"°",cx,cy+r+34);
}

/* =====================================================================
   Init — sync state from server
   ===================================================================== */
drawAzimuth(0); drawElevation(0); updatePlayUI();

fetch("/api/state").then(r=>r.json()).then(st=>{
  document.getElementById("toggleEQ").checked     = !!st.elevation_eq;
  document.getElementById("toggleWobble").checked = !!st.disambiguation_wobble;
  currentSignal = st.signal || "pink";
  document.querySelectorAll(".sig-btn").forEach(b=>{
    b.classList.toggle("active", b.dataset.sig===currentSignal);
  });
  document.getElementById("sigHint").textContent = sigHints[currentSignal]||"";
  if (st.calibration) updateCalSummary(st.calibration);
});
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Routes — main
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/state", methods=["GET"])
def api_state_get():
    return jsonify(engine.get_state())


@app.route("/api/state", methods=["POST"])
def api_state_post():
    data = request.get_json(force=True, silent=True) or {}
    if "paused"    in data: engine.set_paused(data["paused"])
    if "azimuth"   in data: engine.set_azimuth(data["azimuth"])
    if "elevation" in data: engine.set_elevation(data["elevation"])
    if "signal"    in data: engine.set_signal(data["signal"])
    return jsonify(engine.get_state())


@app.route("/api/set", methods=["POST"])
def api_set():
    data = request.get_json(force=True, silent=True) or {}
    if "elevation_eq"           in data: engine.set_elevation_eq(bool(data["elevation_eq"]))
    if "disambiguation_wobble"  in data: engine.set_disambiguation_wobble(bool(data["disambiguation_wobble"]))
    return jsonify(engine.get_state())


@app.route("/api/toggle", methods=["POST"])
def api_toggle():
    engine.toggle_paused()
    return jsonify(engine.get_state())


# ---------------------------------------------------------------------------
# Routes — calibration
# ---------------------------------------------------------------------------

@app.route("/api/calibration/steps", methods=["GET"])
def api_cal_steps():
    """Return the wizard step definitions."""
    return jsonify(CALIBRATION_STEPS)


@app.route("/api/calibration/sofas", methods=["GET"])
def api_cal_sofas():
    """Return available .sofa filenames in the data/ directory."""
    return jsonify(list_sofa_files())


@app.route("/api/calibration/preview", methods=["POST"])
def api_cal_preview():
    """
    Apply one or more calibration parameters live without saving.
    The wizard calls this on every slider move so the user hears the
    effect in real time.
    """
    data = request.get_json(force=True, silent=True) or {}
    current = engine.get_calibration()
    updated = CalibrationProfile(
        elevation_bias_deg=float(data.get("elevation_bias_deg", current.elevation_bias_deg)),
        eq_gain_db=float(data.get("eq_gain_db", current.eq_gain_db)),
        itd_scale=float(data.get("itd_scale", current.itd_scale)),
        preferred_sofa=data.get("preferred_sofa", current.preferred_sofa),
    ).clamp()
    engine.apply_calibration(updated)
    return jsonify(engine.get_state())


@app.route("/api/calibration/save", methods=["POST"])
def api_cal_save():
    """
    Persist the current calibration to disk.  Called when the wizard
    reaches its final step.
    """
    data = request.get_json(force=True, silent=True) or {}
    profile = CalibrationProfile.from_dict(data)
    engine.apply_calibration(profile)
    profile.save()
    return jsonify({"ok": True, "calibration": profile.to_dict()})


@app.route("/api/calibration/reset", methods=["POST"])
def api_cal_reset():
    """Reset to factory defaults and delete the saved profile."""
    profile = CalibrationProfile()
    engine.apply_calibration(profile)
    from calibration import _PROFILE_PATH
    if _PROFILE_PATH.exists():
        _PROFILE_PATH.unlink()
    return jsonify({"ok": True, "calibration": profile.to_dict()})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)