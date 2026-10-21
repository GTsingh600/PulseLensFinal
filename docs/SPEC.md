# PulseLens prototype: technical spec (camera-first, two sites)

This is the contract for the build. `BUILD_PLAN.md` gives the order of work. `EXPLAINERS.md` holds the on-screen text. If code and this spec disagree, fix one of them in the same commit.

---

## 1. Scope

**Built in the 48 hours**
- **One shared engine.** Browser capture (Android Chrome first, iPhone Safari, desktop Chrome and Edge), the six-stage pipeline, checks in five families plus a continuity guard, a per-device planner, family-level fusion, an event stream, and an evidence pack.
- **Lab site (experiments).** Device check, labelled recording on any phone or laptop, session reports with every raw measurement explained, and an experimental results dashboard (separation, calibration, gates, fixed-vs-adaptive results).
- **Demo site (judges).** A customer view on a phone or laptop, plus a big-screen presenter view. The presenter view explains each stage live: camera details, the plan and why, every test result in plain words, live echo charts, continuity and the decision. It also has agent controls, step-through mode, five scenarios, and replay of recorded sessions.

**Out of scope (say so if asked):**
- the final customer-facing product site
- native Android and iOS SDKs with attestation
- lens pulse beyond browsers that expose controls
- vendor integrations
- linking sessions across customers

---

## 2. Architecture

```
 packages/capture (browser)                    server (FastAPI)                               apps
 ---------------------------                   ----------------                               ----
 camera start + CameraDetails  ─ REST ───────►  sessions + store (SQLite + files)              Lab: record, sessions, results
 stage-1 mode-switch probe     ─ probe.jsonl ►  orchestrator (stages, planner, pulses JIT)     Demo: customer, presenter, replay
 frame grabber + fingerprint   ─ frames ─────►  analysis workers (checks → CheckResult)
 pulses (light suite, tilt,    ◄ WS pulse ────  fusion + continuity guard + decision
   hand, lens) + sensors       ─ WS acks ────►  event bus ── events.jsonl ── WS /ws/session ─► both sites render events
```

Everything both sites show comes from one ordered **event stream** per session (section 5). The same events are saved, so any session can be replayed through the presenter view.

---

## 3. Repo layout

```
CLAUDE.md  Makefile  config.yaml  .env.example  package.json (npm workspaces)  playwright.config.ts  eslint.config.js
docs/ SPEC.md  EXPLAINERS.md  BUILD_PLAN.md  STATUS.md  consent_form.md
e2e/          Playwright specs (Chromium fake camera)
packages/
  types/      TS mirror of server models and events: src/models.gen.ts is generated from models.py (`make types`)
  capture/    framework-free: camera, details, probe, grabber, pulses, sensors, ws client, isoluminant colours
  explain/    explainer registry built from docs/EXPLAINERS.md (scripts/build_explainers.ts), lookup by key
  ui/         React components shared by both apps: CameraCard, PlanCard, CoverageMatrix, CheckCard, EchoPlot,
              SplitBars, TiltPlot, NoisePlot, ContinuityStrip, DecisionBanner, ExplainPanel, HonestyLabel
apps/
  lab/        React + Vite: Home, DeviceCheck, Record, Sessions, SessionReport, Results
  demo/       React + Vite: PresenterHome, Customer, Stage (presenter), DesktopCombined, Replay
server/
  pulselens/
    api/ main.py sessions.py ws.py lab.py demo.py
    models.py events.py hub.py pulses.py store.py config.py cli.py analyze.py plots.py orchestrator.py pairing.py fusion.py reasons.py evidence.py
    vision/ models.py frames.py linearize.py face.py hand.py flow.py arcface.py clip.py prnu.py noise.py
    checks/ base.py echo.py camera_modes.py camera_noise.py camera_fingerprint.py camera_timing.py camera_rules.py
            optical_light.py optical_face_neck.py optical_split.py optical_noise_pulse.py optical_lens.py
            motion_tilt.py content_hand.py content_hole.py content_clip.py physiology_pos.py continuity.py
    planner/ registry.py planner.py policy.yaml
    calibration/ profiles.py thresholds.py bootstrap.yaml
    train/ clip_probe.py
  tests/ fixtures/synth.py  test_*.py
eval/ people.csv labels.csv split.py freeze.py run.py report.py separation.py gates.py
scripts/ dev.py (task runner behind the Makefile, incl. tunnel) gen_types.py fetch_models.py build_explainers.ts purge_volunteers.py verify_evidence.py
data/ (gitignored)   models/ (gitignored)
```

---

## 4. Data model

### 4.1 Session bundle: `data/sessions/<session_id>/`

| File | Content |
|---|---|
| `meta.json` | mode, scenario, product, CameraDetails, profiles, plan, label |
| `frames/000123.jpg` | working frames (640x480 desktop, 480x360 phones, quality 0.9) |
| `fp/000123.jpg` | fingerprint frames: every 5th frame at native resolution (≤ 1280x720), quality 0.95 |
| `frames.jsonl` | `{i, t, capture_time, presented_frames, w, h, file, fp_file?}` |
| `probe.jsonl` | one line per mode-switch step (section 7.3) |
| `pulses.jsonl` | `{pulse_id, kind, source, params, received, applied, painted, ended, ok, sig, shown, error, t_released, t_acked}` (`t_released`/`t_acked`: server monotonic ms; `error`: `late`, `no_ack` or the client's reason): `shown` is what the client painted (light: sRGB 0-255 `{neutral, rgb}` or `{neutral, left, right}`), `error` why `ok` is false |
| `sensors.jsonl` | `{t, rr: [a, b, g], acc: [x, y, z], interval}` |
| `events.jsonl` | the event stream (section 5) |
| `results.json` | check results, families, coverage, continuity, decision |
| `photo.jpg` + `photo.json` | KYC photo and the pulse it was bound to |
| `chain.json` | evidence hash chain |
| `landmarks.jsonl` | cache written by `cli analyze`: `{i, landmarks}` with the normalised positions of the face-mesh points the regions use (`vision/face.py LANDMARKS_USED`), or `null` when no face was found |
| `analysis/checks.json`, `analysis/plots/*.png` | written by `cli analyze`: every registered check's CheckResult, and echo plots with `--plots` |

`t` is the canonical frame time in the `performance.now()` domain. Use `capture_time` if present, else the rVFC `now`, else the VideoFrame timestamp mapped to that domain, else the rAF time. `CameraDetails.clock_source` records which.

### 4.2 Key types (pydantic, mirrored in `packages/types`)

```python
class CameraDetails(BaseModel):
    channel: Literal["mobile_browser", "desktop_browser"]
    browser: str; os: str; ua_mobile: bool | None
    camera_label: str; device_id_hash: str
    settings: dict            # width, height, frameRate, facingMode, aspectRatio, resizeMode
    capabilities: dict        # ranges + exposure/whiteBalance/zoom/torch/focus presence
    native_modes: list[dict]  # filled by the mode-switch probe
    fps_median: float | None; fps_jitter_ms: float | None
    clock_source: Literal["captureTime", "rvfc", "videoframe", "raf"]
    rvfc: bool; resize_mode_supported: bool
    gyro: Literal["available", "granted", "denied", "absent"]
    screen: dict              # w, h, dpr, refresh_hz_estimate
    webgl_renderer: str | None; webdriver: bool
    profile_claimed: str | None; profile_measured: str | None
    noise_curve: dict | None  # slope, intercept, r2, per-channel
    fingerprint_pce: float | None

class CheckResult(BaseModel):
    check_id: str; unit: str
    family: Literal["camera", "optical", "motion", "content", "physiology", "continuity"]
    status: Literal["pending", "running", "pass", "fail", "abstain"]
    score: float | None; threshold: float | None
    threshold_source: Literal["profile", "channel", "pooled", "bootstrap", "rule"] | None
    band: dict | None         # genuine band for display, e.g. {"lo": -10, "hi": 25, "unit": "ms", "n": 18}
    quality: float; features: dict[str, float]
    reason: str               # one plain sentence with real counts
    explainer: str            # key into EXPLAINERS.md, e.g. "check.optical.face_neck"
    plot: dict | None         # {"type": "echo" | "split" | "tilt" | "noise" | "modes" | "continuity", "ref": "..."}
    evidence_frames: list[int] = []

class PlanDecision(BaseModel):
    units: list[dict]         # {unit, reason, effort, duration_s}
    skipped: list[dict]       # {unit, reason}
    coverage_expected: dict[str, list[str]]
    route_hint: str | None
    effort_used: float; effort_cap: float

class SessionDecision(BaseModel):
    route: Literal["PASS", "ADD_CHECKS", "AGENT_CHALLENGE", "ASSISTED_KYC", "HOLD"]
    coverage: dict[str, list[str]]; failed_families: list[str]
    continuity_ok: bool; photo_bound: bool
    reasons: list[str]; needs_human: bool; provisional_thresholds: bool
```

---

## 5. Event stream (what both sites render)

Each event is `{seq, t_server, t_client, type, payload}` (`pulselens.models.Event`; `t_server` in ms, `t_client` is `null` unless the event came from the client), appended to `events.jsonl` and pushed on `/ws/session/{id}` to every subscriber.

| type | payload | Shown as |
|---|---|---|
| `session.created` | mode, scenario, product | header |
| `stage.changed` | stage (`camera`, `coach`, `plan`, `pulses`, `face`, `decide`), status | stepper |
| `camera.details` | CameraDetails (partial updates allowed) | Camera card |
| `probe.step` | requested, accepted, switch_ms, gap_frames, fov_change, delivered | Camera card, modes timeline |
| `camera.summary` | profile claimed and measured, noise curve, fingerprint presence, timing | Camera card |
| `coach.tip` | tip key, round | customer prompt + presenter note |
| `plan.decided` | PlanDecision | Plan card + coverage matrix |
| `pulse.released` | pulse_id, kind, params, source | pulse markers |
| `pulse.acked` | pulse_id, painted, ended, ok | pulse markers |
| `signal.chunk` | kind, pulse_id?, downsampled series | live plots |
| `check.started` | check_id | check card spinner |
| `check.result` | CheckResult | check card |
| `coverage.update` | threat → families with a strong pass | coverage matrix |
| `continuity.update` | lane (`identity`, `camera`), t0, t1, status | continuity strip |
| `photo.taken` | t, pulse_id, bound | continuity strip |
| `decision` | SessionDecision | decision banner |
| `agent.action` | action, note | log |
| `orchestrator.waiting` | next stage (step-through mode) | "Next" button |
| `error` | code, message | toast |

Plot series in `signal.chunk` are downsampled to ≤ 200 points. The full data stays in the bundle for the Lab report.

---

## 6. API and WebSockets

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/sessions` | create `{mode: live|step|superset, product, scenario?, label?}` → `{session_id, pair_code, ws_url}` |
| POST | `/api/pair/{code}` | customer device joins a session → `{session_id, role: "customer"}` (codes are 6 characters and expire in 10 min) |
| POST | `/api/sessions/{id}/details` | CameraDetails from the client |
| POST | `/api/sessions/{id}/probe` | probe.jsonl lines |
| POST | `/api/sessions/{id}/frames` | multipart batch: `meta` = frames.jsonl lines (`FrameMeta`), `frames` = working JPEGs, `fp` = fingerprint JPEGs, each file named as in its meta line |
| POST | `/api/sessions/{id}/sensors` | sensor lines |
| POST | `/api/sessions/{id}/finalize` | end of capture |
| POST | `/api/sessions/{id}/next` | step-through mode: release the stage the orchestrator is waiting at; 409 when it is not waiting (a double-click never skips a stage) or the session is not in step mode |
| POST | `/api/sessions/{id}/agent` | `{action: fire_light|fire_tilt|take_photo|approve|escalate|assisted, note}` (needs `X-Console-Passcode`) |
| GET | `/api/sessions/{id}/events?from=seq` | event catch-up for reconnect and replay: `{events}` with `seq >= from` (default 0), so a client that has seen up to k asks `from=k+1` |
| GET | `/api/sessions/{id}/report` | full results for the Lab report |
| GET | `/api/lab/sessions` | list with filters; set B rows are counts only until `FROZEN` |
| GET | `/api/lab/results` | dashboard data (section 13.5) |
| GET | `/api/sessions/{id}/evidence.zip` | evidence pack |

**WebSocket `/ws/session/{id}?role=customer|presenter|lab[&from=seq]`**
- Customer role receives `prompt`, `pulse`, `stage` and `done` messages, and sends acks and heartbeats.
- Presenter and lab roles receive every event as `{"type": "event", "event": Event}`. A presenter first gets the events from `from` (default 0); the lab role (the Lab's capture device) gets new events only unless it passes `from`.
- One capture device (customer or lab role) per session; a second one is closed with code 4409. Unknown session: 4404; unknown role: 4400. Connecting the capture device starts the orchestrator.
- Customer-facing payloads never include scores, check names or families. The customer sees only prompts and "please try again", "an agent will verify you" or "please visit a branch".
- Pulses are signed with `HMAC_SHA256(secret, pulse_id|kind|params|session_id)` (params as canonical JSON: sorted keys, no spaces), single-use, released just in time, and expire in 300 ms.
- Acks: accepted once, only with the pulse's signature; a repeat, an unknown pulse or a wrong signature is rejected and logged as an `error` event. An ack is **late** (`ok: false`, `error: "late"`) when the client painted more than `expires_in_ms` after receiving the pulse, or when it reaches the server after `release + duration + expires_in_ms + 1500 ms`. Pulses never acked are logged `no_ack` at the end. Every message to a customer is checked against a deny-list (`score`, `check_id`, `family`, …) before it is sent.

**Capture messages** (customer role, and the lab role on the recording device; shapes in `models.py`):

| Direction | `type` | Fields | Client does |
|---|---|---|---|
| server → client | `stage` | `stage`, `prompt?` (explainer key) | shows the stage; for `camera` replies `stage.done` once details are posted; for `coach` runs coaching and replies `stage.done` with `{rounds: [{round, tips, metrics}], face_detector}`; for `pulses` puts up the light overlay |
| server → client | `prompt` | `key` | shows the prompt |
| server → client | `pulse` | `pulse_id`, `kind`, `source`, `params`, `sig` | runs it and replies `ack` |
| server → client | `done` | `key` (`prompt.done`, `prompt.retry`, `prompt.agent`, `prompt.branch`) | flushes frames, posts final details, calls `/finalize` |
| client → server | `ack` | `pulse_id`, `sig`, `received`, `applied`, `painted`, `ended`, `ok`, `error`, `shown` | |
| client → server | `stage.done` | `stage`, `data` | |
| client → server | `heartbeat` | `t` (every 2 s) | |

Light `params` (`LightParams`): `{mode: "colour", hue_deg}`, `{mode: "split", left_hue_deg, right_hue_deg}` or `{mode: "white"}`, plus `duration_ms`. Hues index the isoluminant circle in `packages/capture` (6 colour pulses use hues 0, 60, ..., 300), so the colour maths lives in one place and the ack's `shown` records the exact colours. The client refuses a pulse that would make a 4th flash within 1 s (`ok: false, error: "rate_limit"`). `e2e/support/mock-server.ts` implements this protocol and the M1.2 orchestrator stub; the real server must pass the same e2e tests.

---

## 7. Capture package (`packages/capture`)

### 7.1 Start and camera details
1. Require a secure context. On Android, request fullscreen and a screen wake lock (`navigator.wakeLock.request("screen")`) from the Start tap, then lock to portrait if fullscreen succeeded.
2. Call `getUserMedia({video: {facingMode: "user", width: {ideal: 640}, height: {ideal: 480}, frameRate: {ideal: 30}}, audio: false})`.
3. Collect CameraDetails:
   - `getSettings()`, `getCapabilities?.()` (in try), `track.label`
   - browser and OS (UA-CH where available, else the UA)
   - screen size, DPR, and refresh estimate (median rAF interval over 1 s)
   - WebGL renderer and `navigator.webdriver`
   - `resizeMode` support (`"resizeMode" in getSupportedConstraints()`)
   - rVFC support, and gyro availability (`DeviceMotionEvent` + first event)
   - on iOS, call `DeviceMotionEvent.requestPermission()` from the Start tap
4. POST details, and send updates as later stages measure more.

### 7.2 Frame grabber
- **Preferred:** `video.requestVideoFrameCallback`. Time is `metadata.captureTime ?? now`.
- **Chrome Android and desktop:** may use `MediaStreamTrackProcessor` (VideoFrame) in a worker when available; map `VideoFrame.timestamp` to the `performance.now()` domain once and record `clock_source = "videoframe"`.
- **Fallback:** an rAF loop.
- **Working frames:** draw to a canvas (OffscreenCanvas in a worker where available) at the working size, JPEG 0.9.
- **Fingerprint frames:** every 5th frame, also encode at native size (≤ 1280x720), JPEG 0.95.
- **Upload:** batch every 1 s, bounded queue (90 working frames). Drop and log on overflow. Never block capture.

### 7.3 Stage-1 mode-switch probe (runs once, about 3 s)
On a fresh track:
1. Read `capabilities.width/height/frameRate`.
2. Try up to 3 requests in order with `applyConstraints({width: {exact}, height: {exact}, frameRate: {ideal}, resizeMode: "none"})`:
   - a common native mode (1280x720 @ 30)
   - a second aspect ratio (640x480 @ 30)
   - an unusual mode that real webcams rarely offer (1000x750 @ 24)
3. For each request, log:
   - `apply_start` and `apply_end`
   - `ok` / error name (OverconstrainedError is data, not a failure)
   - `settings_after`
   - the first frame time whose size matches
   - frames missing during the switch (from `presented_frames`)
   - fps over the next 1 s
4. Grab one working frame just before and one 500 ms after each switch, for the field-of-view check.
5. Restore the working mode.

Where `resizeMode` is unsupported (Safari, Firefox), skip the unusual mode and mark it so on the Camera card. The customer prompt says: "Checking your camera. The preview may flicker for a moment."

### 7.4 Pulse executors
- **Light suite** (one planning unit, about 11 s): 10 pulses of 400 ms, gaps of 700 to 1300 ms, never more than 3 flashes in any second.
  - 6 colour pulses from an **equal-luminance set**: `isoluminantColours(Y)` in linear sRGB, relative luminance within ±5% of each other. Unit-tested. Between pulses the overlay shows grey at the same luminance (Y = 0.5, which gives the widest colour circle), so colour pulses change hue, not brightness.
  - 2 split-screen pulses: left half colour A, right half colour B, from the same set.
  - 2 white pulses (`config.pulses.light.white`; 0 disables them) for the noise check.
  - Phones use a full-screen overlay (fullscreen mode). Desktops use a border of 18% of the shorter side; for split pulses the left and right border halves differ.
  - Timing: `received`; set the colour in the next rAF → `applied`; following rAF → `painted`; clear after `duration` → `ended`.
- **Tilt:** prompt "Tilt your phone slightly forward and back, twice" for 2.5 s. Sensors are logged all session.
- **Hand:** prompt "Pass your hand slowly across your face, then turn your head left and right" for 4 s, with an animation.
- **Lens** (only if capabilities list `exposureCompensation`, or a manual `exposureTime`/`colorTemperature`): 3 steps with `applyConstraints({advanced: [...]})`, then restore.
- **KYC photo:** on `take_photo` the server releases a light pulse and asks for a still. The client grabs a native-size frame inside the pulse window and uploads `photo.jpg` with its frame time.

### 7.5 Coaching
- **Measured over 3 s in the browser** (tasks-vision FaceDetector): face size, mean luma, Laplacian blur, face-vs-background luma (backlight).
- **Tips:**
  - Move closer
  - Turn towards a light
  - The light is behind you
  - Hold still or wipe the camera
  - Turn your screen brightness up (always shown once, since browsers can't set brightness)
- **Limit:** up to 2 rounds, then continue. Low quality makes checks abstain later.

### 7.6 Browser and device notes (confirm at gate G1)

| Feature | Chrome Android | Safari iOS | Chrome/Edge desktop | Firefox |
|---|---|---|---|---|
| rVFC | yes | yes (15.4+) | yes | check, rAF fallback |
| `captureTime` | check | check | check | n/a |
| `resizeMode: "none"` | yes | no | yes | no |
| exposure / white balance controls | some devices | no | rarely | no |
| devicemotion | yes, no prompt | yes, after permission | n/a | yes |
| fullscreen + wake lock | yes | partial (no fullscreen on iPhone) | yes | yes |

"check" means record what the device does; the code handles both cases. Budget Android phones may throttle: if measured fps drops below 12, checks abstain and the planner adds an agent challenge.

---

## 8. Device profiles

`profile_key = f"{channel}|{fps_band}"`, with fps bands `lt20`, `20to27`, `ge27` (6 cells). The claimed profile comes from what the device reports; the **measured** profile comes from the frames, and thresholds always use the measured one. Fallback order: profile → channel → pooled.

---

## 9. Checks

Score orientation: **higher is more suspicious**. Every check returns a quality value in 0..1 and abstains below `quality.min` (0.5) with a reason. Every check has an explainer key `check.<check_id>` in `EXPLAINERS.md` and a plot type for the UI.

### 9.1 Shared vision (`vision/`)
- **`linearize.py`:** inverse sRGB to linear light, used by all colour and noise maths.
- **`face.py`:** MediaPipe FaceLandmarker (VIDEO mode). Regions per frame:
  - skin (forehead + cheeks, excluding eyes, brows, lips)
  - left and right cheek
  - **neck**: a box below the chin landmark, 0.6 face widths wide and from 0.05 to 0.45 face heights below the chin, clipped to the frame. Neck or shirt are both fine.
  - background: the frame minus the face box dilated 1.6x and minus a bottom-centre body block
- **`hand.py`:** HandLandmarker, hull mask dilated 15%.
- **`flow.py`:** Lucas-Kanade tracking on background corners.
- **`arcface.py`:** insightface `buffalo_l` on CPU (research-only licence; disclosed).
- **`clip.py`:** open_clip ViT-B-32.
- **`noise.py`:** temporal and spatial noise estimators.
- **`prnu.py`:** fingerprint estimation and PCE.

### 9.2 Camera reality family (stage 1, passive)

| Check | Algorithm | Score |
|---|---|---|
| `camera.modes` | From `probe.jsonl`: share of requests accepted, switch latency, frames missing during the switch, whether delivered frame size matches reported settings, and field-of-view change. FOV change comes from ORB features + RANSAC similarity on the before/after frames: scale and offset when the aspect ratio changed. **Rule part:** settings report a change that the delivered frames don't show → fail. | max robust z of the features vs the genuine profile, plus the rule |
| `camera.noise_curve` | Every 3rd frame pair in linear light; static pixels only (blurred difference below a threshold); temporal noise `(g_t - g_t-1)/√2`. Bin by mean intensity (12 bins, ≥ 200 pixels each) and get per-bin variance by MAD. Fit `var = a·μ + b` per channel. Features: slope `a`, intercept `b`, fit R², noise at mid-grey. **Note:** after the camera's processing the curve is not always rising in raw pixel values, so the test is "matches a real camera of this profile", not "always rises". | max robust z vs genuine profile |
| `camera.fingerprint` | From fingerprint frames: residual `W = I - D(I)`, where D is a wavelet denoiser on the green channel. Estimate `K = ΣW·I / ΣI²` on odd and even frames separately, zero-mean rows and columns, apply a Wiener filter, then take the **PCE** between the two halves (peak vs nearby shifts, so a static scene can't fake it). Needs ≥ 30 fingerprint frames with mean luma between 60 and 200. | `-log(PCE)` vs genuine band |
| `camera.timing` | Frame intervals: median fps, coefficient of variation, share within ±0.5 ms of the median, longest gap. | max robust z |
| `camera.duplicates` | 64-bit dHash; a frame is a duplicate when Hamming distance is 0 and mean absolute difference < 0.5. | duplicate share |
| `camera.claim_mismatch` (rule) | The device claims low quality (fps ≤ 20, or ≤ 480p with a generic label and no controls) but measures high quality: noise below the genuine 2.5th percentile **and** timing CV below the genuine 2.5th percentile, or fps > 1.2x the claim. Sets `force_agent`. | rule |
| `camera.env` (rule, weak) | `webdriver`, a SwiftShader / llvmpipe / emulator renderer, or an emulator UA. | rule |
| `camera.label` (rule, weak) | Label matches known virtual-camera names (OBS, ManyCam, Snap Camera, XSplit, DroidCam, Iriun, e2eSoft, CamTwist, mmhmm). Trivially spoofed. | rule |

### 9.3 Optical family (light suite)
All of these use per-frame mean linear RGB of each region and the pulse log.

**Echo onset (shared helper):**
1. Chromaticity `x = RGB / sum(RGB)`.
2. Expected direction `d_c` = the pulse colour's chromaticity minus neutral.
3. Projection `p(t) = (x(t) - mean_pre) · d_c`, with the baseline over the 300 ms before `painted`.
4. Onset = the first two consecutive frames above `max(4σ_pre, a_min)` within 700 ms, interpolated to the crossing.
5. The pulse colour is the one the client painted (`shown` in pulses.jsonl). `d_c` is normalised, so `p` and `a_min` are in chromaticity units. Interpolating across the exposure ramp makes onsets up to one frame early; the bias is constant per device, so the calibrated centre absorbs it, and it cancels in `face_neck`.

| Check | Algorithm | Score |
|---|---|---|
| `optical.light.delay` | Median onset delay of the face over colour pulses; a pulse with no echo counts as 1000 ms. Needs ≥ 4 valid pulses. | `|median - center|` (centre from calibration) |
| `optical.face_neck` | Onsets for face and neck on the same pulse: `Δ = t_face - t_neck`, plus amplitude ratio `A_face / A_neck`. A neck echo with no face echo is a strong fail. The rolling-shutter row offset is constant for the geometry and absorbed by the genuine centre. Abstains when the neck region is out of frame, saturated, or too weak. | `|median Δ - center| / scale` + ratio deviation |
| `optical.split` | On split pulses: left-cheek minus right-cheek change, projected on the axis between colours A and B, divided by the overall echo amplitude. The expected sign per channel is learned from genuine set A sessions (`split_sign`). Abstains when yaw > 20° or the echo is weak. | `-(sign × contrast)` vs genuine band |
| `optical.noise_pulse` | During pulses, temporal noise of static skin pixels per channel, before vs during. Predicted ratio from this session's own noise curve at the new intensity; measured ratio from the frames. Uses white pulses when present, otherwise the channel the colour pulse raises. Abstains on motion or small intensity change. **Riskiest of the new checks;** decided at gate G2. | `|log(measured / predicted)|` |
| `optical.reflectance` | Face vs background amplitude ratio and colour-direction cosine (a flat screen reacts evenly or not at all). | combined, vs band |
| `optical.lens` | Global luma step after each lens command: direction and delay. Abstains when there are no controls. | vs band |

### 9.4 Motion family
`motion.tilt.corr` and `motion.tilt.lag`:
1. Median LK speed of background features (px/s) vs gyroscope magnitude, resampled to 100 Hz and z-normalised.
2. Cross-correlation over lags of −300 to +300 ms; take `r_max` and the lag at it.
3. Scores: `1 - r_max`, and `|lag - center|`.
4. Abstain when the gyro peak is < 15 deg/s or there are < 30 tracked features.

### 9.5 Face content family

| Check | Algorithm | Score |
|---|---|---|
| `content.hand.response` (rule) | No hand overlap with the face (> 10% of the face box) and no yaw range ≥ 5° between the prompt's `painted` and `ended + 500 ms`. | rule |
| `content.hand.flicker` | High-pass frame difference in face pixels outside the hand mask during overlap, divided by the 1 s baseline before the prompt; take the 95th percentile. | vs band |
| `content.hand.identity` | ArcFace at 10 fps over the window; `1 - p10(cosine to the pre-window reference)`. Abstains when yaw range < 15°. | vs band |
| `content.fingerprint_hole` | Estimate `K_bg` from fingerprint frames using **background pixels only** (face mask weight 0 per frame); pixel positions need enough background samples, which needs some head movement. Then compare the correlation of each frame's residual with `K_bg·I` on face pixels vs an equal-area background ring, summed over frames. The ratio is about 1 for a real face and low for a generated one. A supporting check: PRNU alone is weaker than deep detectors (Lugstein 2021). | `-log(ratio)` vs band |
| `content.clip` | CLIP-feature probe over 16 face crops; mean of the top 25%. Abstains if the model file is missing (datasets not available). | vs band |

### 9.6 Physiology (stretch, `physiology.enabled`)
- `physiology.pos`: POS rPPG over 3 regions, ≥ 10 s, at ≥ 24 fps. Score = `1 - coherence`.
- Never store or return a heart rate or waveform.

### 9.7 Continuity guard (whole call; not a family vote)
- **`continuity.identity`:** ArcFace at 2 Hz. The reference is the median of the first 10 good embeddings. Flag when cosine < τ for ≥ 1.5 s, or a single drop > δ.
- **`continuity.camera`:** in 3 s windows, track noise-curve parameters, fingerprint correlation of the window residual with the session `K`, frame size, fps and gaps. A jump is ≥ 2 of these changing past their thresholds in the same window, or any change in frame size.
- **Photo binding:** `photo_bound = true` only if the photo frame time falls inside a pulse window and both lanes are OK at that time.
- **Guard rule:** any jump → route at least `AGENT_CHALLENGE`, and the photo is retaken.

---

## 10. Calibration (`calibration/`)

1. For each check feature, a per-profile robust z: `(x - median) / (1.4826·MAD)` from set A genuine sessions (fallback order: channel, then pooled).
2. Pool the z-scores across profiles.
3. **Family budget.** All calibrated checks in a family share one z threshold `τ_f`. Choose it as the smallest value whose **leave-one-person-out** family false-fail rate on set A is ≤ `alpha_family` (1%). Report the rate actually achieved and n. If n < 40 genuine sessions, use `τ = 3.0` and mark it `PROVISIONAL`.
4. Centred checks (`*.delay`, `*.lag`, `face_neck`) store their centre. `optical.split` stores `split_sign` per channel.
5. Output `calibration/thresholds.json`: per check `{center?, sign?, tau_f, stats per profile, n}`, plus a hash.
   Until it exists, checks use `calibration/bootstrap.yaml`: physics-based starting values with `threshold_source: "bootstrap"`, always shown as PROVISIONAL.
6. Bands shown on screen are the genuine 2.5% to 97.5% range of the raw feature for that profile, with its n.

---

## 11. Planner (`planner/`)

| Unit | Family | Mode | Needs | Duration (s) | Effort weight | replay | premade | liveswap | emulator |
|---|---|---|---|---|---|---|---|---|---|
| `camera` | camera | passive | always | 3 to 5 | 0 | ○ | ● | ● | ● |
| `clip` | content | passive | model present | 0 | 0 | ○ | ● | ○ | |
| `physiology` | physiology | passive | flag, ≥ 24 fps | 0 | 0 | ○ | ● | ○ | |
| `light` | optical | active, no gesture | screen; not no-flash | 11 | 0.5 | ● | ● | ○ | ○ |
| `tilt` | motion | active | gyro | 3 | 1.0 | ● | ● | ● | ● |
| `hand` | content | active, gesture | always | 4 | 1.5 | ● | ● | ● | ○ |
| `lens` | optical | active | controls | 4 | 0.5 | ○ | ○ | ○ | ○ |

- **Cost** = duration × effort weight. Users barely notice light pulses but do notice gestures.
- **Cap:** effort 20 per round, at most 2 rounds.
- **Algorithm:** passive units first. Then greedily add the active unit with the best (new strong-family coverage) / cost until every threat has 2 strong families, the cap is hit, or nothing helps.
- **Expected plans (pinned in tests):**
  - phone with gyro → `tilt` + `light`
  - desktop → `hand` + `light`, with route hint `AGENT_CHALLENGE` (emulator coverage stays at 1)
  - no-flash → no `light`, and agent challenge
  - claim mismatch → union of plans + `AGENT_CHALLENGE`
- **Ratings:** all are hypotheses, kept in `policy.yaml`. `light` liveswap becomes ● only if gate G2 passes on `optical.face_neck`.
- **For display:** `PlanDecision.units[].reason` and `skipped[].reason` use explainer keys, e.g. `plan.reason.tilt_gyro`, `plan.skip.lens_no_controls`.

---

## 12. Fusion and routing (`fusion.py`, `reasons.py`)

**Family status:**
- fail if any check in the family fails
- pass if any passes (and none fails)
- abstain otherwise

**Coverage per threat:** families that passed and are ● for that threat.

**Routes:**
- **HOLD:** ≥ 2 failed families.
- **One failed family:** `ADD_CHECKS` (if within cap and rounds), else `AGENT_CHALLENGE`.
- **No failures:**
  - `PASS` if every threat is covered twice
  - otherwise `ADD_CHECKS` if possible, else `AGENT_CHALLENGE`
- **Overrides:**
  - `force_agent` or a continuity jump → at least `AGENT_CHALLENGE`
  - still short after the agent challenge, without approval → `ASSISTED_KYC`

**Human sign-off:** `AGENT_CHALLENGE` and `HOLD` become PASS only through a logged agent action with a note.

**Reasons:** one sentence per non-pass check, with real counts and the band ("The face lagged the neck by 120 ms on 7 of 8 pulses; genuine phones like this: -10 to +25 ms, n = 18").

---

## 13. Lab site (`apps/lab`): experiments

Mobile-first; must run on Android Chrome at 360 px wide. Every widget has an "ⓘ What this shows" explainer.

### 13.1 Home
Three buttons: **Device check**, **Record**, **Sessions**, plus a **Results** link. The banner states the honesty labels in use (PROVISIONAL or calibrated).

### 13.2 Device check
Runs stage 1 only, then shows the **Camera card** (every CameraDetails field with an explainer tooltip), the mode-switch timeline, the noise curve plot and fingerprint presence. It has a "Save to device matrix" button (device code + notes). This is how gate G1 is run on each phone.

### 13.3 Record (superset protocol)
1. **Operator form:** person code (dropdown from `eval/people.csv`, which also gives the set), device code, light condition, genuine/attack, attack tool, consent reference.
2. "Hand to volunteer" screen.
3. **Guided session.** Full-screen stages, each with an explainer panel the volunteer can read (what to do, why). Every feasible unit runs in shuffled order, plus 12 s of plain video.
   - Collapsible Camera card.
   - Live mini plots: echo (face/neck) after each pulse, tilt, noise curve after stage 1.
   - A progress bar of units.
4. **End: QC card** (fps, dropped frames, clock source, face visible %, neck visible %, quick status per check) with Keep / Discard and notes.

### 13.4 Sessions and session report
- **List:** id, time, person, device, profile, kind, tool, set, QC, route. Set B rows show counts only until `FROZEN`.
- **Report** (set A, or any set after FROZEN):
  - Camera card
  - Plan and coverage
  - every check card, with its explainer, number vs band (or PROVISIONAL) and its plot
  - evidence frames around each pulse with region overlays (face, neck, cheeks, background boxes)
  - continuity strip, event log, bundle download

### 13.5 Results (experimental results dashboard)
Each section has an explainer on how to read it.
1. **Data collected:** sessions per profile cell and per attack tool, by set (B as counts only).
2. **Device matrix:** per device code: browser, channel, clock source, rVFC, resizeMode, controls, gyro, median fps, mode-probe outcome, noise-curve fit, fingerprint PCE.
3. **Gates G1 to G4:** the measured numbers from `eval/gates.py` plus the decision text entered by a human.
4. **Separation (set A):** per-feature AUC with n per side, and genuine-vs-tool distribution strips, for camera checks vs virtual camera / emulator and optical, content and continuity checks vs live swap.
5. **Calibration:** thresholds per check and profile with n; the leave-one-person-out family false-fail rate.
6. **Final results (only after FROZEN):** Fixed-light vs Fixed-all vs PulseLens on set B:
   - attacks accepted per tool and the worst tool
   - honest users held
   - extra steps for honest users
   - median and p95 time
   - Wilson 95% intervals, with per-profile and per-light breakdowns
   - export PNG and CSV for the deck

---

## 14. Demo site (`apps/demo`): judges

Built for a projector. The presenter view is readable from 3 m: body text ≥ 18 px, nothing denser than the deck.

### 14.1 Presenter home
- **Start a demo session:** choose a scenario (14.4) or Free run.
- **Customer device:** "Phone" (shows a big QR code + pair code) or "This laptop" (opens the desktop combined view).
- **Mode:** `live` or `step` (step-through: the orchestrator waits for **Next** before each stage, so the presenter can explain).
- **Replay a recorded session:** rehearsal sessions marked demo-ready.

### 14.2 Customer view (`/customer?code=`)
Consent and flash notice → camera preview → big prompts with animations → flashes (fullscreen on phones) → "Thanks, the agent will continue". No scores, ever. Language toggle EN/HI is a stretch goal.

### 14.3 Presenter view (`/stage/:id`)
- **Header:** scenario title, **What we expect** (from the scenario) and **What we measured** (filled live). This keeps the demo honest.
- **Stage stepper:** Camera check, Coach, Plan, Pulses, Face integrity, Decide, plus a Continuity lane. The current stage pulses; clicking any stage opens its explainer.
- **Camera card:** channel, browser, camera label, resolution, measured fps, clock source, native modes found, controls, gyro, noise curve (mini plot), fingerprint presence, claimed vs measured profile. Each field has a tooltip.
- **Plan card:** units chosen with their reason, units skipped with theirs, an effort bar, and the **coverage matrix** (attacks × families) filling in as results arrive.
- **Test feed:** a CheckCard per check (pending → running → pass/fail/abstain) with its plain sentence, its number against the genuine band, and an expandable "Why this matters".
- **Live plots:**
  - EchoPlot for the latest pulse (face, neck, pulse marker, band shading)
  - SplitBars (left vs right cheek)
  - TiltPlot (gyro vs video)
  - NoisePlot (predicted vs measured)
- **Continuity strip:** identity and camera lanes over time, pulse diamonds, photo marker.
- **Decision banner** with reasons.
- **Agent panel:** Fire light pulse, Fire tilt, Take KYC photo, Approve, Escalate, Assisted KYC.
- **Footer honesty labels:** `PROVISIONAL THRESHOLDS` or "Thresholds from n genuine sessions", and `ILLUSTRATIVE` on any example data.

### 14.4 Scenarios (`apps/demo/src/scenarios.ts`)

| id | Customer device | Presenter does | What we expect (shown on screen) |
|---|---|---|---|
| `genuine-phone` | team phone, mobile browser | nothing | Camera check passes; tilt and light pulses; PASS in about 15 s |
| `desktop-dim` | laptop, cheap USB webcam, lights low | coaching, then fires one pulse as the agent | Camera passes; light + hand; planner asks for an agent challenge; agent approves |
| `live-swap` | attack laptop: Deep-Live-Cam into a virtual camera posing as a basic webcam (teammate) | fires a pulse | Camera check fails (modes, noise); face lags the neck; HOLD |
| `switch-after-checks` | attack laptop; the teammate switches the swap on after the pulses | takes the KYC photo | Continuity jump on identity and camera; AGENT_CHALLENGE; photo retaken |
| `judge-replay` | laptop; a judge holds up a phone playing a video | nothing | Camera passes (it's real); no light echo; no response to the hand prompt; HOLD |

Expectations are hypotheses. If the measured result differs, the screen shows both, and the presenter explains why.

### 14.5 Desktop combined view (`/desktop`)
On one laptop: the customer area (preview + prompts) sits in the centre with the flash border around the whole window, and a compact presenter column on the right. Use it when no projector second screen is available.

### 14.6 Replay (`/replay/:id`)
The same presenter layout driven by saved events: play, pause, scrub, 0.5x/1x/2x. Clicking a pulse shows its frames with region overlays. This is the fallback if Wi-Fi fails on stage.

### 14.7 Demo data
- Judges' sessions show a consent screen first.
- They are deleted after 1 hour unless "keep for evidence" is ticked.
- They are never used for calibration or evaluation (`mode = live`, no label).

---

## 15. Evidence pack
`chain.json` hashes meta, probe, pulses, sensors, events, results, the photo, and frames around each pulse onset. Each `link = sha256(prev_link + sha256(file))`; the head is stored in SQLite. `scripts/verify_evidence.py` reports the first mismatch.

---

## 16. Evaluation protocol (`eval/`)

**Recordings**
- Superset recordings come from Lab Record (13.3).
- Sets are decided at recording time:
  - genuine: by person, via `people.csv` (about 60/40)
  - attacks: alternating A/B within each tool
  - `liveportrait`: set B only (held out)
- Development and gates use set A only.

**Freeze:** `freeze.py` writes `FROZEN` with hashes of `policy.yaml`, `thresholds.json`, `config.yaml` and `splits.json`. `run.py` refuses set B without it.

**Policies, scored on the same set B sessions:**
- **Fixed-light:** `light` + `clip`, pooled thresholds; HOLD if any check fails.
- **Fixed-all:** every feasible unit, pooled thresholds; HOLD if any check fails; no routing.
- **PulseLens:** planner, per-profile thresholds with family budget, fusion, routing, continuity guard. ADD_CHECKS is simulated from extra recorded units; AGENT_CHALLENGE counts as "routed to a person", never as accepted.

**Metrics:**
- attacks accepted (PASS) per tool and the worst tool
- honest users held
- honest users given extra steps
- abstain rate
- median and p95 time
- all as x of n with Wilson 95% intervals, per profile and per light condition

**Gate scripts:** `eval/gates.py g1|g2|g3|g4` print the numbers each gate needs (BUILD_PLAN), and the Results page reads the same output.

---

## 17. Security and privacy
- HTTPS via tunnel; CORS limited to the tunnel origins.
- Signed single-use pulses; customer payloads never contain scores.
- Agent actions need the console passcode (prototype-level, labelled as such).
- `data/` and `models/` are gitignored; person codes only; no heart rate stored.
- Demo sessions auto-delete after 1 hour.
- `purge_volunteers.py` deletes all sessions whose person code isn't in `TEAM_CODES`.
- Flashes ≤ 3 per second, with a no-flash option that routes to an agent.

---

## 18. `config.yaml` defaults

```yaml
capture:  {desktop_size: [640, 480], mobile_size: [480, 360], jpeg: 0.9, fp_every: 5, fp_max: [1280, 720], fp_jpeg: 0.95, upload_batch_ms: 1000, queue_max: 90}
probe:    {modes: [[1280, 720, 30], [640, 480, 30], [1000, 750, 24]], settle_ms: 1000}
pulses:
  light:  {colour: 6, split: 2, white: 2, duration_ms: 400, gap_ms: [700, 1300], luminance_tolerance: 0.05, desktop_border_frac: 0.18, expires_in_ms: 300}
  tilt:   {duration_ms: 2500, min_peak_dps: 15}
  hand:   {duration_ms: 4000}
  lens:   {steps: 3, ev_delta: 1.0}
  release_jitter_ms: [0, 400]
  agent_fire_delay_ms: [300, 1500]
profiles: {fps_bands: [20, 27]}
planner:  {effort_cap: 20, max_rounds: 2, families_per_threat: 2}
calibration: {alpha_family: 0.01, provisional_tau: 3.0, min_genuine_for_lopo: 40}
continuity: {identity_hz: 2, window_s: 3}
quality:  {min: 0.5, min_face_frac: 0.02, luma_range: [40, 220], min_fps: 12}
physiology: {enabled: false}
demo:     {retention_min: 60, pair_code_ttl_min: 10}
```
