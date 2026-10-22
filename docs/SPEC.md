# PulseLens prototype: technical spec (camera-first, two sites)

This is the contract for the build. `BUILD_PLAN.md` gives the order of work. `EXPLAINERS.md` holds the on-screen text. If code and this spec disagree, fix one of them in the same commit.

The architecture follows the final deck (`PulseLens_Final_Deck_final.pptx`, slides 3–8 and 12–14, and the reference diagram on slide 17). Where this spec describes something the code does not do yet, it says **(planned)**. `docs/STATUS.md` is the record of what is built.

---

## 1. Scope

PulseLens asks two separate questions on every V-CIP call, not one vague deepfake score:

| | Question 1: capture and injection integrity | Question 2: live manipulation |
|---|---|---|
| Asks | Is this a real camera, in this session? | Is the face itself real? |
| Threats | pre-recorded replay, virtual camera, injected or re-timed stream | a real person on a real camera, with the face swapped in real time |
| Evidence | session nonce binding, frame timing and duplicates, response to a fresh challenge | face vs neck vs background response to light, head-turn consistency, a visual detector |

A clean camera result does not prove a genuine face. A weak sensor signal does not prove injection. Poor capture leads to a retry, never a fraud flag. A bank agent makes the final call.

**Built in the 48 hours**
- **One shared engine.** Browser capture (Android Chrome first, iPhone Safari, desktop Chrome and Edge), the five-step service pipeline (section 2), checks in four evidence families A–D plus a continuity guard, a planner that picks one of three capture modes from measured capability, quality-aware fusion into three outcomes, an event stream, and an evidence pack.
- **Lab site (experiments).** Device check, labelled recording on any phone or laptop, session reports with every raw measurement explained, and an experimental results dashboard (separation, calibration, gates, fixed-vs-adaptive results).
- **Demo site (judges).** A customer view on a phone or laptop, plus a big-screen presenter view. The presenter view explains each stage live: camera details, the capture mode and plan and why, every test result in plain words, live response charts, continuity and the outcome. It also has agent controls, step-through mode, the demo scenarios, and replay of recorded sessions.

**Out of scope (say so if asked):**
- the final customer-facing product site
- native Android and iOS SDKs with attestation
- camera-control probes beyond browsers that expose controls
- vendor integrations; the bank's case / audit workflow (mocked for the hackathon)
- linking sessions across customers

---

## 2. Architecture

Three columns, as on deck slides 13 and 17: the applicant's device, the PulseLens service, and the bank's existing systems.

```
 APPLICANT DEVICE (packages/capture)        PULSELENS SERVICE (server, FastAPI)                     BANK SYSTEMS (apps + planned)
 -----------------------------------        -----------------------------------                     -----------------------------
 Capture SDK: frames + monotonic    ─REST─►  1 Session orchestrator & challenge planner              Bank policy & integration
   timestamps, face regions,        ◄─WS──     single-use session, signed JIT challenge steps,          (permitted actions, retention,
   challenge rendered in-session               random colour order/timing, expected events logged       operating point per product)
 Quality preflight: fps, dropped    ─REST─►  2 Ingest, provenance & frame integrity                  Evidence record: session, challenge
   frames, blur, brightness,                   session binding, order, duplicates, ack signatures        events, per-family results;
   supported controls (probe)                3 Quality gate: per signal, per window                      hash-linked (chain.json)
 Adaptive capture mode:                        usable | abstain | protocol_error                     Agent review console: plain reasons,
   CAPABLE / CONSTRAINED / NO-FLASH          A Pulse   B Sensor   C Light   D Visual                   failed vs abstained, human decides
 Privacy boundary: no heart rate,            4 Evidence fusion: quality-aware, correlated            Case / audit workflow (mocked)
   no score shown to the applicant             cues grouped, interpretable evidence table           India readiness & evaluation (eval/)
 Device-local limits: unsupported            5 Policy outcome: PASS | RETRY / STEP-UP |
   means unsupported, never failed             HUMAN REVIEW          event bus ── events.jsonl ── WS /ws/session ─► both sites
```

- **Hosting.** The service is self-hosted in the bank's VPC or on-prem; decisions stay server-side and data stays in India (RBI V-CIP §18). The prototype runs on a team laptop behind an HTTPS tunnel.
- **Data boundary.** Capture features cross over the session channel. Raw pulse waveforms and heart rates are never stored. The applicant never sees a score.

### 2.1 Pipeline steps vs stages vs code

The orchestrator's stages (section 5, `stage.changed`) map onto the deck's session flow (slide 4) and the five service steps:

| Deck step (slide 4) | Service step (slide 13) | Orchestrator stage | Code | Built |
|---|---|---|---|---|
| 1 Preflight (~3 s) | device: quality preflight | `camera`, `coach` | `packages/capture` probe, details, coaching | Built (probe, details, coaching) |
| 2 Plan | 1 Session orchestrator & challenge planner | `plan` | `orchestrator.py`, `pulses.py`; `planner/` | Stub: fixed light suite, shuffled, signed; capture-mode planner **(planned, M3.1)** |
| 3 Capture & ingest | 2 Ingest, provenance & frame integrity | `pulses`, `face` | `api/sessions.py`, `api/ws.py`, `store.py` | Built for the light suite; head turn **(planned)** |
| 4 Gate & check | 3 Quality gate; families A–D | (analysis) | `checks/*`, `cli analyze`, `POST /analyze` | Per-check abstain built; formal gate and status field **(planned)** |
| 5 Fuse & recommend | 4 Evidence fusion; 5 Policy outcome | `decide` | `fusion.py`, `reasons.py` | **(planned, M3.2)** |

Everything both sites show comes from one ordered **event stream** per session (section 5). The same events are saved, so any session can be replayed through the presenter view.

---

## 3. Repo layout

Files listed here that do not exist yet are planned; `docs/STATUS.md` says which are built.

```
CLAUDE.md  Makefile  config.yaml  .env.example  package.json (npm workspaces)  playwright.config.ts  eslint.config.js
docs/ SPEC.md  EXPLAINERS.md  BUILD_PLAN.md  STATUS.md  consent_form.md  architecture.svg
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
    models.py events.py hub.py pulses.py store.py config.py cli.py analyze.py plots.py orchestrator.py pairing.py
    quality.py fusion.py reasons.py evidence.py
    vision/ models.py frames.py modes.py linearize.py face.py hand.py flow.py arcface.py clip.py sbi.py prnu.py noise.py
    checks/ base.py echo.py camera_modes.py camera_noise.py camera_fingerprint.py camera_timing.py camera_rules.py
            camera_regions.py
            optical_light.py optical_face_neck.py optical_split.py optical_noise_pulse.py optical_lens.py
            motion_turn.py motion_tilt.py content_sbi.py content_boundary.py content_hand.py content_hole.py
            content_clip.py physiology_pos.py continuity.py
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
| `pulses.jsonl` | `{pulse_id, kind, source, params, received, applied, painted, ended, ok, sig, shown, error, t_released, t_acked}` (`t_released`/`t_acked`: server monotonic ms; `error`: `late`, `no_ack` or the client's reason): `shown` is what the client painted (light: sRGB 0-255 `{neutral, rgb}` or `{neutral, left, right}`), `error` why `ok` is false. This is the server-side record of the **expected challenge events** that ingest and family C align against. |
| `sensors.jsonl` | `{t, rr: [a, b, g], acc: [x, y, z], interval}` |
| `events.jsonl` | the event stream (section 5) |
| `results.json` | check results, families, coverage, continuity, decision |
| `photo.jpg` + `photo.json` | KYC photo and the pulse it was bound to |
| `chain.json` | evidence hash chain |
| `landmarks.jsonl` | cache written by `cli analyze`: `{i, landmarks}` with the normalised positions of the face-mesh points the regions use (`vision/face.py LANDMARKS_USED`), or `null` when no face was found |
| `analysis/checks.json`, `analysis/plots/*.png` | written by `cli analyze`: every registered check's CheckResult, and echo plots with `--plots` |

`t` is the canonical frame time in the `performance.now()` domain. Use `capture_time` if present, else the rVFC `now`, else the VideoFrame timestamp mapped to that domain, else the rAF time. `CameraDetails.clock_source` records which.

### 4.2 Key types (pydantic, mirrored in `packages/types`)

These are the types in `server/pulselens/models.py` today. Section 4.3 lists the changes the final architecture needs.

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
    profile_claimed: str | None; profile_measured: str | None   # calibration cohort keys (section 8.3)
    noise_curve: dict | None  # slope, intercept, r2, per-channel
    fingerprint_pce: float | None

class CheckResult(BaseModel):
    check_id: str; unit: str
    family: Literal["camera", "optical", "motion", "content", "physiology", "continuity"]  # code family; A–D via 9.0
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

### 4.3 Contract changes for the final architecture (planned)

None of these are in `models.py` yet. Add them with `make types` in one commit, together with the code that fills them.

| Type | Change | Why (deck) |
|---|---|---|
| `CheckSpec` (`planner/registry.py`) | add `group: Literal["A", "B", "C", "D"]` and `vote_group: str` (correlated cues that share one vote, section 12.3) | four evidence families; no double counting |
| `CheckResult` | add `evidence_family: "A" \| "B" \| "C" \| "D"`, `gate: "usable" \| "abstain" \| "protocol_error"`, `uncertainty: float \| None`, `reason_codes: list[str]`, `window_id: str \| None`. Keep `status` (pass/fail/abstain) as the direction for UI and tests: `gate` says whether the evidence counts, `status` says which way it points | slide 7 schema: features, quality, uncertainty, status, reason codes, window id |
| `PlanDecision` | add `capture_mode: "CAPABLE" \| "CONSTRAINED" \| "NO_FLASH"` and `mode_reasons: list[str]` (explainer keys) | three capture modes (section 8) |
| `CameraDetails` | add `capture_mode` (latest; can only move down within a session) | the planner can downgrade mid-session |
| `SessionDecision` | `outcome: "PASS" \| "RETRY_STEP_UP" \| "HUMAN_REVIEW"` plus `step_up: "fresh_challenge" \| "no_flash" \| "agent_checks" \| "assisted_kyc" \| None`; `families: {A..D: {gate, raises_risk, reasons}}`; keep `route` for one release as the internal reason (mapping in 12.5) | three outcomes (slide 4) |

---

## 5. Event stream (what both sites render)

Each event is `{seq, t_server, t_client, type, payload}` (`pulselens.models.Event`; `t_server` in ms, `t_client` is `null` unless the event came from the client), appended to `events.jsonl` and pushed on `/ws/session/{id}` to every subscriber.

| type | payload | Shown as |
|---|---|---|
| `session.created` | mode, scenario, product | header |
| `stage.changed` | stage (`camera`, `coach`, `plan`, `pulses`, `face`, `decide`), status | stepper (deck steps: section 2.1) |
| `camera.details` | CameraDetails (partial updates allowed) | Camera card |
| `probe.step` | requested, accepted, switch_ms, gap_frames, fov_change, delivered | Camera card, modes timeline |
| `camera.summary` | profile claimed and measured, noise curve, fingerprint presence, timing | Camera card |
| `coach.tip` | tip key, round | customer prompt + presenter note |
| `plan.decided` | PlanDecision (with `capture_mode`, planned) | Plan card + coverage matrix |
| `plan.downgraded` **(planned)** | from mode, to mode, reason key | Plan card |
| `pulse.released` | pulse_id, kind, params, source | pulse markers |
| `pulse.acked` | pulse_id, painted, ended, ok | pulse markers |
| `signal.chunk` | kind, pulse_id?, downsampled series | live plots |
| `check.started` | check_id | check card spinner |
| `check.result` | CheckResult | check card (failed and abstained shown separately) |
| `coverage.update` | threat → families with usable, non-raising evidence | coverage matrix |
| `continuity.update` | lane (`identity`, `camera`), t0, t1, status | continuity strip |
| `photo.taken` | t, pulse_id, bound | continuity strip |
| `decision` | SessionDecision | outcome banner |
| `agent.action` | action, note | log |
| `orchestrator.waiting` | next stage (step-through mode) | "Next" button |
| `error` | code, message | toast |

Plot series in `signal.chunk` are downsampled to ≤ 200 points. The full data stays in the bundle for the Lab report.

---

## 6. API and WebSockets

### 6.1 Implemented routes

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/sessions` | create `{mode: live|step|superset, product, scenario?, label?}` → `{session_id, pair_code, ws_url, token}` |
| POST | `/api/pair/{code}` | customer device joins a session → `{session_id, role: "customer"}` (codes are 6 characters and expire in 10 min) |
| POST | `/api/sessions/{id}/details` | CameraDetails from the client |
| POST | `/api/sessions/{id}/probe` | probe.jsonl lines |
| POST | `/api/sessions/{id}/frames` | multipart batch: `meta` = frames.jsonl lines (`FrameMeta`), `frames` = working JPEGs, `fp` = fingerprint JPEGs, each file named as in its meta line |
| POST | `/api/sessions/{id}/sensors` | sensor lines |
| POST | `/api/sessions/{id}/finalize` | end of capture |
| POST | `/api/sessions/{id}/next` | (needs the session token) step-through mode: release the stage the orchestrator is waiting at; 409 when it is not waiting (a double-click never skips a stage) or the session is not in step mode |
| POST | `/api/sessions/{id}/agent` | `{action: fire_light|fire_tilt|take_photo|approve|escalate|assisted, note}` (needs `X-Console-Passcode`); logged only until M3.3 |
| GET | `/api/sessions/{id}/events?from=seq` | (needs the session token: events carry scores) event catch-up for reconnect and replay: `{events}` with `seq >= from` (default 0), so a client that has seen up to k asks `from=k+1` |
| POST | `/api/sessions/{id}/analyze` | (needs the session token) run every check on the saved bundle in a worker thread, as `cli analyze` does; 202 |
| GET | `/api/sessions/{id}/report` | (needs the session token) `{status: none|running|error|done}`; when done, `qc` (fps, frames, dropped, acks, clock, browser, face and neck visible share) and `checks` (CheckResult list), plus `provisional_thresholds` |
| GET | `/api/health` | liveness probe |
| WS | `/ws/session/{id}` | below |

**Planned routes:** `GET /api/lab/sessions` (list with filters; set B rows are counts only until `FROZEN`), `GET /api/lab/results` (dashboard data, section 13.5), `GET /api/sessions/{id}/evidence.zip` (evidence pack).

### 6.2 Deck session API (slide 14) vs the implemented routes

The deck proposes a five-endpoint session API for a bank integration. The prototype keeps its own routes; this is how they correspond.

| Deck endpoint (proposed) | Purpose (deck) | Implemented equivalent | Gap |
|---|---|---|---|
| `POST /sessions` | create session, nonce and capability plan | `POST /api/sessions` (session id, pair code, console token) | No capability plan in the response: the plan is decided after preflight and arrives as `plan.decided` (planner planned, M3.1). There is no separate nonce: the random session id plus per-step HMAC signatures over `pulse_id|kind|params|session_id` bind the challenge to the session. |
| `GET /sessions/{id}/challenge` | single-use challenge schedule | none; each challenge step is released just in time over the WebSocket (`pulse` messages, signed, single-use, 300 ms expiry) | Deliberate: the client never holds the whole sequence in advance, so an injector cannot pre-render it. If this endpoint is built, it should return only the descriptor (number of steps, safety limits), not the colours or timing. **Needs a team decision.** |
| `POST /sessions/{id}/frames` | frame batches and event timestamps, session-bound | `POST /api/sessions/{id}/frames` (frames + meta) and WS `ack` messages (event timestamps) | Same idea, two channels. |
| `POST /sessions/{id}/complete` | finalise capture, run analysis | `POST /api/sessions/{id}/finalize`, then `POST /api/sessions/{id}/analyze` | Two calls today; live analysis in the orchestrator is planned (M3.3). |
| `GET /sessions/{id}/result` | outcome, reasons, quality and abstain states (agent only) | `GET /api/sessions/{id}/report` (per-check results, QC; token-protected) and the `decision` event | No outcome yet (fusion planned, M3.2). Access is by session token, not a role-based reviewer login (planned). |

### 6.3 Session token, WebSocket and capture messages

**Session token.** `POST /api/sessions` returns `token` = HMAC(`PULSE_HMAC_SECRET`, `console|<id>`), truncated to 32 hex. Only the creator (Lab page, presenter) gets it; pairing gives the customer the session id alone. It goes in `X-Session-Token` (or `?token=`) for `/events`, `/next`, `/analyze` and `/report`, and in `?token=` for the presenter and lab sockets (401 / close 4401 without it), so a customer who knows the session id still never sees scores.

**WebSocket `/ws/session/{id}?role=customer|presenter|lab[&from=seq][&token=]`**
- Customer role receives `prompt`, `pulse`, `stage` and `done` messages, and sends acks and heartbeats.
- Presenter and lab roles receive every event as `{"type": "event", "event": Event}`. A presenter first gets the events from `from` (default 0); the lab role (the Lab's capture device) gets new events only unless it passes `from`.
- One capture device (customer or lab role) per session; a second one is closed with code 4409. Unknown session: 4404; unknown role: 4400; presenter or lab without the session token: 4401. Connecting the capture device starts the orchestrator.
- Customer-facing payloads never include scores, check names or families. The customer sees only prompts and "please try again", "an agent will verify you" or "please visit a branch".
- Pulses are signed with `HMAC_SHA256(secret, pulse_id|kind|params|session_id)` (params as canonical JSON: sorted keys, no spaces), single-use, released just in time, and expire in 300 ms.
- Acks: accepted once, only with the pulse's signature; a repeat, an unknown pulse or a wrong signature is rejected and logged as an `error` event. An ack is **late** (`ok: false`, `error: "late"`) when the client painted more than `expires_in_ms` after receiving the pulse, or when it reaches the server after `release + duration + expires_in_ms + 1500 ms`. Pulses never acked are logged `no_ack` at the end. Every message to a customer is checked against a deny-list (`score`, `check_id`, `family`, …) before it is sent. Rejected, repeated and forged acks are **protocol errors** for ingest (section 12.2); late and missing acks make the affected step abstain.

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

Light `params` (`LightParams`): `{mode: "colour", hue_deg}`, `{mode: "split", left_hue_deg, right_hue_deg}` or `{mode: "white"}`, plus `duration_ms`. Hues index the isoluminant circle in `packages/capture` (6 colour pulses use hues 0, 60, ..., 300), so the colour maths lives in one place and the ack's `shown` records the exact colours. The server shuffles the order and randomises the gaps per session (`pulses.light_suite`, `release_jitter_ms`). The client refuses a pulse that would make a 4th flash within 1 s (`ok: false, error: "rate_limit"`). `e2e/support/mock-server.ts` implements this protocol and the M1.2 orchestrator stub; the real server must pass the same e2e tests.

---

## 7. Capture package (`packages/capture`)

This is the deck's **Capture SDK** and **quality preflight** (applicant-device column).

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

### 7.4 Challenge executors
- **Light suite** (family C, one planning unit, about 11 s): 10 pulses of 400 ms, gaps of 700 to 1300 ms, never more than 3 flashes in any second.
  - 6 colour pulses from an **equal-luminance set**: `isoluminantColours(Y)` in linear sRGB, relative luminance within ±5% of each other. Unit-tested. Between pulses the overlay shows grey at the same luminance (Y = 0.5, which gives the widest colour circle), so colour pulses change hue, not brightness.
  - 2 split-screen pulses: left half colour A, right half colour B, from the same set.
  - 2 white pulses (`config.pulses.light.white`; 0 disables them) for the noise check.
  - Phones use a full-screen overlay (fullscreen mode). Desktops use a border of 18% of the shorter side; for split pulses the left and right border halves differ.
  - Timing: `received`; set the colour in the next rAF → `applied`; following rAF → `painted`; clear after `duration` → `ended`.
  - **Safety (deck slide 6):** at most 3 colour changes per second (enforced in the client) and no saturated red flashes (WCAG 2.3.1). The isoluminant set at Y = 0.5 is not yet checked against the saturated-red rule **(to verify)**. A no-flash route exists for photosensitive users (section 8).
  - **Camera lock** (`packages/capture/src/lock.ts`): where capabilities offer them, white balance is frozen at the current temperature and, only when the measured frame rate is below 27 fps (auto exposure stretching frames), exposure at 33 ms (`exposureMode: "manual"`), for the whole suite. The exposureTime a camera reports in continuous mode is not used: at G1 it read 15.6 ms while frames came every 96 ms, and locking at it made the face 10x darker, then set back to continuous. Auto exposure otherwise drops a webcam to ~10 fps in a dim room (G1) and auto white balance can chase the flashes. What was locked goes to `camera_details.camera_lock`; a refused lock is logged there, never an error.
  - **CONSTRAINED mode (planned):** a simpler, longer colour challenge: fewer colours, longer pulses (the G1 fallback is 600 ms), no split pulses.
- **Head turn** (family D, **planned**, replaces the hand prompt as the default gesture): the server picks left or right at random per session and releases it as a signed step like a pulse; prompt "Turn your head to the <side>, then back to the centre", about 4 s, with an animation. The expected direction is logged server-side.
- **Tilt** (family D, optional, phones with a gyroscope): prompt "Tilt your phone slightly forward and back, twice" for 2.5 s. Sensors are logged all session.
- **Hand** (family D, demoted): prompt "Pass your hand slowly across your face, then turn your head left and right" for 4 s, with an animation. Not relied on: a masked swap tool handled hand occlusion (Firc et al. 2026).
- **Close / far** (family D, optional, **planned**): move the phone (or lean, on a laptop) from far to near and back.
- **Camera-control probe** (family C, `lens` unit; only if capabilities list `exposureCompensation`, or a manual `exposureTime`/`colorTemperature`; torch on recent iOS **planned**): 3 steps with `applyConstraints({advanced: [...]})`, then restore. Unsupported means unsupported, never failed.
- **KYC photo:** on `take_photo` the server releases a light pulse and asks for a still. The client grabs a native-size frame inside the pulse window and uploads `photo.jpg` with its frame time.

### 7.5 Coaching (part of the quality preflight)
- **Measured over 3 s in the browser** (tasks-vision FaceDetector): face size, mean luma, Laplacian blur, face-vs-background luma (backlight). Frame rate and dropped frames come from the grabber; supported controls from the probe.
- **Tips:**
  - Move closer
  - Turn towards a light
  - The light is behind you
  - Hold still or wipe the camera
  - Turn your screen brightness up (always shown once, since browsers can't set brightness)
- **Limit:** up to 2 rounds, then continue. Low quality makes checks abstain later.
- **Languages:** English and Hindi prompts first, Punjabi next **(planned)**.

### 7.6 Browser and device notes (confirm at gate G1)

| Feature | Chrome Android | Safari iOS | Chrome/Edge desktop | Firefox |
|---|---|---|---|---|
| rVFC | yes | yes (15.4+) | yes | check, rAF fallback |
| `captureTime` | check | check | check | n/a |
| `resizeMode: "none"` | yes | no | yes | no |
| exposure / white balance controls | some devices (deck: exposure, white balance, ISO, focus, zoom) | no, limited and version-dependent (torch on recent iOS) | rarely (varies by OS and camera) | no (none by default) |
| devicemotion | yes, no prompt | yes, after permission | n/a | yes |
| fullscreen + wake lock | yes | partial (no fullscreen on iPhone) | yes | yes |

"check" means record what the device does; the code handles both cases. The preflight probes real support live; it never assumes it from the device name. Budget Android phones may throttle: if measured fps drops below 12, the optical checks abstain and the planner moves to a mode without the colour challenge (section 8).

---

## 8. Capture modes (adaptive capture)

The plan follows **measured capability, never the device label**. Three modes replace the earlier fps-band profiles and named device tiers. The mode decides which challenges run; it is **never a risk label** and never lowers the bar for raising risk.

### 8.1 The three modes

| Mode | Runs | Typical | Chosen when (measured in preflight) |
|---|---|---|---|
| **CAPABLE** | stream integrity (B); full colour challenge with split pulses (C); face / neck region features; head turn (D); exposure / white-balance probe where supported | Chrome on Android or desktop, steady frame rate, decent light | frame rate steady at or above the CONSTRAINED cut; face and neck in view; light within range after coaching |
| **CONSTRAINED** | stream integrity (B); simpler, longer colour challenge if viable (C); head turn (D); unreliable optical features dropped | budget phone, old webcam, iOS Safari, tube-light flicker | low or unstable frame rate, heavy noise or blur, brightness instability, or no camera controls |
| **NO-FLASH · ASSISTED** | stream integrity (B); head turn (D); agent-led live questions; branch or correspondent route if still short | photosensitivity, bright sunlight, persons with disabilities | the customer's choice, or the light challenge cannot be seen (frame rate below `quality.min_fps`, or ambient light swamps the screen) |

**Cut-points (PROVISIONAL).** Until G1/G2 data sets them, the planner reuses existing config values: the lower fps band edge (20 fps, `profiles.fps_bands`) separates CAPABLE from CONSTRAINED, and `quality.min_fps` (12 fps) is the floor for any colour challenge. They are recorded in `policy.yaml` with the reason, and changed only on evidence, noted in `STATUS.md`.

### 8.2 Rules
- The mode is chosen server-side from the preflight measurements (`CameraDetails`, probe, coaching metrics), not from `profile_claimed`.
- The planner can **downgrade mid-session** (for example when the frame rate falls during the light suite), never upgrade. A downgrade emits `plan.downgraded` **(planned)**.
- **Claimed vs measured.** A device that claims low quality but measures high (`camera.claim_mismatch`) keeps the measured mode and gets agent-led checks added (section 12.4).
- Indoor LED and tube light: brightness instability lowers confidence. Low-fps browsers cannot resolve 50 Hz flicker, so there is no claim of exact 50 Hz detection.
- Status: the planner and mode selection are **planned (M3.1)**. Today the orchestrator stub runs camera → coach → light suite for every device, and the optical checks abstain below 12 fps.

### 8.3 Calibration cohorts (metadata, not planning)
`profile_key = f"{channel}|{fps_band}"`, with fps bands `lt20`, `20to27`, `ge27` (6 cells), stays as the **calibration cohort**: thresholds are calibrated per measured cohort (section 10), with lighting condition and device code kept as metadata for subgroup reporting. The claimed profile comes from what the device reports; the **measured** profile comes from the frames, and thresholds always use the measured one. Fallback order: profile → channel → pooled. A cohort never selects tests; the capture mode does.

---

## 9. Checks

Score orientation: **higher is more suspicious**. Every check returns a quality value in 0..1 and abstains below `quality.min` (0.5) with a reason. Every check has an explainer key `check.<check_id>` in `EXPLAINERS.md` and a plot type for the UI. Check IDs keep their code prefixes (`camera.*`, `optical.*`, …); the evidence family A–D is assigned by the table below.

### 9.0 Evidence families and check map

| Family (deck) | Role | Check IDs | Built |
|---|---|---|---|
| **A · Pulse coherence** | OPTIONAL; logged only, outside the policy vote until it adds measured value | `physiology.pos` | no (flag off) |
| **B · Sensor & lens physics / stream integrity** | CORE; mainly question 1 | `camera.modes`, `camera.noise_curve`, `camera.fingerprint` (supporting only), `camera.timing`, `camera.duplicates`, `camera.claim_mismatch` (rule), `camera.env` (rule, weak), `camera.label` (rule, weak), `content.fingerprint_hole` (supporting only), `camera.regions` (planned) | the 8 `camera.*` checks |
| **C · Active camera / light challenge** | CORE + EXPERIMENT; both questions | `optical.light.delay`, `optical.face_neck`, `optical.split`, `optical.reflectance`, `optical.noise_pulse`, `optical.lens` | `light.delay`, `face_neck` |
| **D · Visual & motion consistency** | CORE + MODEL; mainly question 2 | `motion.turn` (planned), `content.sbi` (planned), `content.boundary` (planned), `motion.tilt.corr`, `motion.tilt.lag`, `motion.close_far` (planned, optional), `content.clip`, `content.minifasnet` (planned, optional), `content.hand.response`, `content.hand.flicker`, `content.hand.identity` (demoted) | none |
| **Continuity guard** | whole call; not a family vote (9.7) | `continuity.identity`, `continuity.camera` | no |

**Why these placements.**
- `camera.modes` is B: it is the camera mode / exposure response the deck puts under sensor physics.
- `content.fingerprint_hole` is B: it is a PRNU comparison of face vs background, i.e. a noise-residual cue, and PRNU is supporting evidence only.
- `optical.noise_pulse` is C: it only exists as a response to our light.
- `optical.lens` is C: the deck's "optional exposure / WB / torch probes" belong to the active challenge.
- Tilt, hand and head turn are D (motion consistency); `content.clip` is D as a detector feature next to SBI.
- **Continuity stays a guard** rather than a D vote: it spans the whole call and protects the KYC photo, and a camera-lane jump is a stream-integrity violation. Its identity lane shares the ArcFace tracker with `motion.turn`.

### 9.1 Shared vision (`vision/`)
- **`linearize.py`:** inverse sRGB to linear light, used by all colour and noise maths.
- **`face.py`:** MediaPipe FaceLandmarker (VIDEO mode). Regions per frame:
  - skin (forehead + cheeks, excluding eyes, brows, lips)
  - left and right cheek
  - **neck**: a box below the chin landmark, 0.6 face widths wide and from 0.05 to 0.45 face heights below the chin, clipped to the frame. Neck or shirt are both fine.
  - background: the frame minus the face box dilated 1.6x and minus a bottom-centre body block
  - five face regions for family A **(planned)**
- **`hand.py`:** HandLandmarker, hull mask dilated 15%.
- **`flow.py`:** Lucas-Kanade tracking on background corners.
- **`arcface.py`:** insightface `buffalo_l` on CPU (research-only licence; disclosed).
- **`clip.py`:** open_clip ViT-B-32.
- **`sbi.py` (planned):** self-blended-image detector, EfficientNet-B4 with research-only weights (licence before production).
- **`noise.py`:** temporal and spatial noise estimators.
- **`prnu.py`:** fingerprint estimation and PCE.

### 9.2 Family B: sensor & lens physics (stage 1, passive)

| Check | Algorithm | Score |
|---|---|---|
| `camera.modes` | From `probe.jsonl`: share of requests accepted, switch latency, frames missing during the switch, whether delivered frame size matches reported settings, and field-of-view change. FOV change comes from ORB features + RANSAC similarity on the before/after frames: scale and offset when the aspect ratio changed. **Rule part:** settings report a change that the delivered frames don't show → fail (a protocol error, section 12.2). | max robust z of the features vs the genuine profile, plus the rule |
| `camera.noise_curve` | Every 3rd frame pair in linear light; static pixels only (blurred difference below a threshold); temporal noise `(g_t - g_t-1)/√2`. Bin by mean intensity (12 bins, ≥ 200 pixels each) and get per-bin variance by MAD. Fit `var = a·μ + b` per channel. Features: slope `a`, intercept `b`, fit R², noise at mid-grey. **Note:** after the camera's processing the curve is not always rising in raw pixel values, so the test is "matches a real camera of this profile", not "always rises". | max robust z vs genuine profile |
| `camera.fingerprint` | From fingerprint frames: residual `W = I - D(I)`, where D is a wavelet denoiser on the green channel. Estimate `K = ΣW·I / ΣI²` on odd and even frames separately, zero-mean rows and columns, apply a Wiener filter, then take the **PCE** between the two halves (peak vs nearby shifts, so a static scene can't fake it). Needs ≥ 30 fingerprint frames with mean luma between 60 and 200. **Supporting evidence only:** Chromium's fake camera produced a stable pattern (PCE 97); compression and browser scaling weaken it. | `-log(PCE)` vs genuine band |
| `camera.timing` | Frame intervals: median fps, coefficient of variation, share within ±0.5 ms of the median, longest gap. | max robust z |
| `camera.duplicates` | 64-bit dHash; a frame is a duplicate when Hamming distance is 0 and mean absolute difference < 0.5. Runs of near-duplicate frames **(planned)**. | duplicate share |
| `camera.claim_mismatch` (rule) | The device claims low quality (fps ≤ 20, or ≤ 480p with a generic label and no controls) but measures high quality: noise below the genuine 2.5th percentile **and** timing CV below the genuine 2.5th percentile, or fps > 1.2x the claim. Sets `force_agent`. | rule |
| `camera.env` (rule, weak) | `webdriver`, a SwiftShader / llvmpipe / emulator renderer, or an emulator UA. | rule |
| `camera.label` (rule, weak) | Label matches known virtual-camera names (OBS, ManyCam, Snap Camera, XSplit, DroidCam, Iriun, e2eSoft, CamTwist, mmhmm). Trivially spoofed. | rule |
| `camera.regions` **(planned)** | Noise residual and sharpness (Laplacian) compared across face, neck and background in the same frames; the repainted face of a live swap should differ from the real neck around it. Challenge-relative: compared within the session, no absolute cut. | robust z of the face-minus-neck difference vs genuine band |
| `content.fingerprint_hole` | see 9.5 (algorithm kept there); counted in B. | |

A hard protocol violation (phantom mode switch, forged or repeated ack, broken session binding) and a weak physical cue (noise slightly off the cohort) get **separate reason codes**.

### 9.3 Family C: active light challenge
All of these use per-frame mean linear RGB of each region and the pulse log (the server's record of expected events). The colour sequence is fresh per session: shuffled order, randomised gaps, each step signed with the session id. Responses are normalised to the session's own pre-pulse baseline.

**Echo onset (shared helper):**
1. Chromaticity `x = RGB / sum(RGB)`.
2. Expected direction `d_c` = the pulse colour's chromaticity minus neutral.
3. Projection `p(t) = (x(t) - mean_pre) · d_c`, with the baseline over the 300 ms before `painted`.
4. Onset = the first two consecutive frames above `max(4σ_pre, a_min)` within 700 ms, interpolated to the crossing.
5. An onset whose hold amplitude (median over 25–75% of the pulse after the crossing) stays at or below the threshold is noise that crossed twice, not an echo.
6. **Constant-fraction onset** (`onset_cf_ms`): the same rising edge timed where it reaches half of its own hold amplitude. `face_neck` compares these, because a fixed threshold is crossed later on a weak echo than a strong one (up to a frame). `face_neck` times a pulse only when both echoes reach `min_snr` (2) times their own threshold; weaker pairs count for neither side.
7. Every optical check abstains below `quality.min_fps` (12 fps, §7.6). Clipping, heavy motion and unstable room light also make it abstain.
8. The pulse colour is the one the client painted (`shown` in pulses.jsonl). `d_c` is normalised, so `p` and `a_min` are in chromaticity units. Interpolating across the exposure ramp makes onsets up to one frame early; the bias is constant per device, so the calibrated centre absorbs it, and it cancels in `face_neck`.

| Check | Algorithm | Score |
|---|---|---|
| `optical.light.delay` | Median onset delay of the face over colour pulses; a pulse with no echo counts as 1000 ms. Needs ≥ 4 valid pulses. Catches replays: a pre-made clip cannot know today's sequence. | `|median - center|` (centre from calibration) |
| `optical.face_neck` | Onsets for face and neck on the same pulse: `Δ = t_face - t_neck`, plus amplitude ratio `A_face / A_neck`. A neck echo with no face echo is a strong fail. The rolling-shutter row offset is constant for the geometry and absorbed by the genuine centre. Abstains when the neck region is out of frame, saturated, or too weak. **A hypothesis we test:** a live swap receives a genuinely lit frame and may keep part of the response. | `|median Δ - center| / scale` + ratio deviation |
| `optical.split` | On split pulses: left-cheek minus right-cheek change, projected on the axis between colours A and B, divided by the overall echo amplitude. The expected sign per channel is learned from genuine set A sessions (`split_sign`). Abstains when yaw > 20° or the echo is weak. Research item for live swaps. | `-(sign × contrast)` vs genuine band |
| `optical.noise_pulse` | During pulses, temporal noise of static skin pixels per channel, before vs during. Predicted ratio from this session's own noise curve at the new intensity; measured ratio from the frames. Uses white pulses when present, otherwise the channel the colour pulse raises. Abstains on motion or small intensity change. **Riskiest of the new checks;** decided at gate G2. | `|log(measured / predicted)|` |
| `optical.reflectance` | Face vs background amplitude ratio and colour-direction cosine (a flat screen reacts evenly or not at all). Background response is part of the deck's "face, neck and background" curve. | combined, vs band |
| `optical.lens` | Global luma step after each camera-control command (exposure, white balance; torch where supported): direction and delay. Abstains when there are no controls; unsupported is recorded as unsupported, not failed. | vs band |

Known limit: weak in bright sunlight (the screen is swamped), which is one reason for the NO-FLASH mode.

### 9.4 Family D: motion consistency

**`motion.turn` (planned, the main D challenge).** Random left or right head turn and return (7.4). Tracks face landmarks for yaw over time and ArcFace identity across the turn.
- Fails when the turn does not follow the requested side within the window (a response-order check, like C's), or identity drops across the profile view.
- Boundary and texture consistency through the turn is scored by `content.boundary` (9.5).
- Abstains when the face is lost for most of the window or the frame rate is below `quality.min_fps`.
- Pose challenges scored best in the 2026 live-swap study, but with confidence intervals that include zero (Firc et al.), so it is measured, not assumed.

`motion.tilt.corr` and `motion.tilt.lag` (optional, phones with a gyroscope):
1. Median LK speed of background features (px/s) vs gyroscope magnitude, resampled to 100 Hz and z-normalised.
2. Cross-correlation over lags of −300 to +300 ms; take `r_max` and the lag at it.
3. Scores: `1 - r_max`, and `|lag - center|`.
4. Abstain when the gyro peak is < 15 deg/s or there are < 30 tracked features.

`motion.close_far` (planned, optional): far-to-near motion; perspective (nose vs face outline), screen-light falloff on the face vs the background, and focus/noise change should move together on a real face. Not relied on alone.

### 9.5 Family D: visual consistency (face content)

| Check | Algorithm | Score |
|---|---|---|
| `content.sbi` **(planned)** | Pretrained self-blended-image detector (Shiohara & Yamasaki 2022) on face crops; output treated as **one feature**, scored against genuine sessions. Benchmark-trained detectors may not transfer to Indian device streams. Research-only weights. | vs band |
| `content.boundary` **(planned)** | Temporal blending, boundary and texture consistency at the face edge (seams), especially through the head turn. | vs band |
| `content.minifasnet` **(planned, optional)** | MiniFASNet (Apache-2.0) screen and print cues, as a feature. | vs band |
| `content.hand.response` (rule, demoted) | No hand overlap with the face (> 10% of the face box) and no yaw range ≥ 5° between the prompt's `painted` and `ended + 500 ms`. | rule |
| `content.hand.flicker` (demoted) | High-pass frame difference in face pixels outside the hand mask during overlap, divided by the 1 s baseline before the prompt; take the 95th percentile. Not a priority: a masked swap tool handled occlusion (Firc et al. 2026). | vs band |
| `content.hand.identity` (demoted; superseded by `motion.turn`) | ArcFace at 10 fps over the window; `1 - p10(cosine to the pre-window reference)`. Abstains when yaw range < 15°. | vs band |
| `content.fingerprint_hole` (**counted in family B**) | Estimate `K_bg` from fingerprint frames using **background pixels only** (face mask weight 0 per frame); pixel positions need enough background samples, which needs some head movement. Then compare the correlation of each frame's residual with `K_bg·I` on face pixels vs an equal-area background ring, summed over frames. The ratio is about 1 for a real face and low for a generated one. A supporting check: PRNU alone is weaker than deep detectors (Lugstein 2021). | `-log(ratio)` vs band |
| `content.clip` | CLIP-feature probe over 16 face crops; mean of the top 25%. Abstains if the model file is missing (datasets not available). | vs band |

### 9.6 Family A: pulse coherence (optional, `physiology.enabled`)
- `physiology.pos`: POS (or CHROM) rPPG from the face regions and the neck, ≥ 10 s, at ≥ 24 fps, only when skin, motion, timing and light allow. Features: face-vs-neck similarity plus signal quality. Score = `1 - coherence`. The code today plans 3 regions; the deck asks for five face regions and the neck **(planned)**.
- **Logged only.** It is outside the policy vote until it adds measured value (ablation, section 16): live swaps can carry the driver's real pulse (Seibold et al. 2025), and low fps, motion, dim light and darker skin weaken it (Nowara et al. 2020).
- Never store or return a heart rate or waveform.

### 9.7 Continuity guard (whole call; not a family vote)
- **`continuity.identity`:** ArcFace at 2 Hz. The reference is the median of the first 10 good embeddings. Flag when cosine < τ for ≥ 1.5 s, or a single drop > δ.
- **`continuity.camera`:** in 3 s windows, track noise-curve parameters, fingerprint correlation of the window residual with the session `K`, frame size, fps and gaps. A jump is ≥ 2 of these changing past their thresholds in the same window, or any change in frame size.
- **Photo binding:** `photo_bound = true` only if the photo frame time falls inside a pulse window and both lanes are OK at that time.
- **Guard rule:** a camera-lane jump is a stream-integrity violation → **HUMAN REVIEW**. An identity jump → **HUMAN REVIEW**, and the photo is retaken. (Earlier rule: at least `AGENT_CHALLENGE`.)

---

## 10. Calibration (`calibration/`)

1. For each check feature, a per-cohort robust z: `(x - median) / (1.4826·MAD)` from set A genuine sessions (cohort = measured profile, section 8.3; fallback order: channel, then pooled).
2. Pool the z-scores across cohorts.
3. **Family budget.** All calibrated checks in a family share one z threshold `τ_f`. Choose it as the smallest value whose **leave-one-person-out** family false-fail rate on set A is ≤ `alpha_family` (1%). Report the rate actually achieved and n. If n < 40 genuine sessions, use `τ = 3.0` and mark it `PROVISIONAL`. Families are A–D (section 9.0); A is calibrated and reported but does not vote.
4. Centred checks (`*.delay`, `*.lag`, `face_neck`) store their centre. `optical.split` stores `split_sign` per channel.
5. Output `calibration/thresholds.json`: per check `{center?, sign?, tau_f, stats per profile, n}`, plus a hash.
   Until it exists, checks use `calibration/bootstrap.yaml`: physics-based starting values with `threshold_source: "bootstrap"`, always shown as PROVISIONAL.
6. Bands shown on screen are the genuine 2.5% to 97.5% range of the raw feature for that cohort, with its n.
7. **Operating point per product** (bank policy; for example stricter for an instant loan than for a savings account) is fit on separate recordings, never on the tuning set.

---

## 11. Planner (`planner/`) — session orchestrator & challenge planner (planned, M3.1)

The planner first picks the capture mode (section 8), then the units allowed in that mode.

| Unit | Family | Mode | Needs | Allowed in | Duration (s) | Effort weight | replay | premade | liveswap | emulator |
|---|---|---|---|---|---|---|---|---|---|---|
| `camera` | B | passive | always | all modes | 3 to 5 | 0 | ○ | ● | ● | ● |
| `light` | C | active, no gesture | screen; not no-flash | CAPABLE (full); CONSTRAINED (simpler, longer, if viable) | 11 | 0.5 | ● | ● | ○ | ○ |
| `lens` | C | active | controls | CAPABLE | 4 | 0.5 | ○ | ○ | ○ | ○ |
| `turn` | D | active, gesture | face landmarks | all modes | 4 | 1.5 | ● | ● | ● | ○ |
| `sbi` | D | passive | model present | all modes | 0 | 0 | ○ | ● | ○ | |
| `clip` | D | passive | model present | all modes | 0 | 0 | ○ | ● | ○ | |
| `tilt` | D | active | gyro | CAPABLE, CONSTRAINED | 3 | 1.0 | ● | ● | ● | ● |
| `close_far` | D | active, gesture | — | optional | — | — | rated after measurement | | | |
| `hand` | D | active, gesture | always | not planned by default (demoted) | 4 | 1.5 | ● | ● | ● | ○ |
| `physiology` | A | passive | flag, ≥ 24 fps | logged only | 0 | 0 | — (no vote) | | | |
| `agent` | — | agent-led live questions | an agent | NO-FLASH, and any step-up | — | — | | | | |

- **Ratings:** all are hypotheses, kept in `policy.yaml`. `turn` starts with the ratings `hand` had; `sbi` with those `clip` had. `light` liveswap becomes ● only if gate G2 passes on `optical.face_neck`. Camera ● for liveswap holds only when the swap is injected through a virtual camera; with a capture card or a hooked phone, only C, D and continuity are left.
- **Cost** = duration × effort weight. Users barely notice light pulses but do notice gestures.
- **Cap:** effort 20 per round, at most 2 rounds.
- **Algorithm:** pick the mode. Passive units first. Then greedily add the allowed active unit with the best (new strong-family coverage) / cost until every threat has 2 strong families, the cap is hit, or nothing helps.
- **Challenge content** is random per session: colour order and gaps (already in `pulses.light_suite`), turn direction. Expected events are logged server-side before release.
- **Expected plans (to pin in `test_planner.py`):**
  - CAPABLE phone → `light` + `turn` (+ `tilt` with a gyroscope)
  - CAPABLE desktop → `light` + `turn` (+ `lens` with controls)
  - CONSTRAINED → simpler `light` if viable + `turn`
  - NO-FLASH → no `light`; `turn` + `agent`
  - claim mismatch → the measured mode's plan + `agent`
- **For display:** `PlanDecision.units[].reason` and `skipped[].reason` use explainer keys, e.g. `plan.reason.tilt_gyro`, `plan.skip.lens_no_controls`, and `capture_mode` has its own reason keys.

---

## 12. Quality gate, evidence fusion and outcomes (`quality.py`, `fusion.py`, `reasons.py`; planned, M3.2)

### 12.1 Quality gate (service step 3)
Per signal, per window (a pulse, the turn window, a continuity window): estimate usable pixels, face and neck visibility, blur, motion, flicker / exposure instability, frame rate and signal confidence. Low quality → that test **abstains**; it is never counted as attack evidence.

Built today, inside each check: `quality` in 0..1, abstain below `quality.min` (0.5), the 12 fps floor (`too_slow`), neck coverage and saturation limits, minimum valid pulses. A shared gate module and per-window ids are planned.

### 12.2 Status per check and per family
Every check (planned schema, 4.3) returns continuous features, quality, uncertainty, a **gate status** and reason codes:

| Gate status | Meaning | Today's equivalent |
|---|---|---|
| `usable` | enough good-quality data; the score counts, in whichever direction | `status` pass or fail |
| `abstain` | not enough good data; recorded, never counted as attack evidence | `status` abstain |
| `protocol_error` | the stream or the challenge protocol was violated: forged, repeated or missing-signature acks, phantom mode switch (`camera.modes` rule), frames outside the session, a camera-lane continuity jump | rule fails and `error` events, not yet separated |

A family is `protocol_error` if any of its checks is; `usable` if at least one check is usable; `abstain` otherwise.

### 12.3 Fusion (service step 4)
1. **Gate.** Only usable checks enter.
2. **Normalise.** Challenge-relative responses (C) and a robust session baseline (median, MAD); scores become robust z against the genuine cohort (section 10). Device and lighting cohort stay as metadata.
3. **Group.** Correlated cues share one vote (`vote_group` in the registry). For example an fps anomaly and duplicate frames are one integrity signal, not two (`camera.timing` + `camera.duplicates`); `camera.fingerprint` and `content.fingerprint_hole` are one PRNU signal. A group's value is its strongest member, not the sum.
4. **Combine (demo).** An interpretable weighted evidence table with every reason visible. A family **raises risk** when its combined, gated evidence passes the family threshold `τ_f`. Weights live in `policy.yaml` and are set at G2, not trained on a few sessions. Family A is shown but never counted.
5. **Calibrate (later).** Regularised logistic fusion only with enough person-disjoint, attack-diverse data; operating point fit on separate recordings.

**Never a fraud flag on their own** (they lower confidence or trigger a retry): unsupported camera controls, low frame rate, dim light, darker skin tone, no visible neck, budget device.

**Coverage per threat:** families (B, C, D) that are usable, did not raise risk, and are ● for that threat.

### 12.4 Outcomes (service step 5)
A recommendation, never an automatic rejection.

| Outcome | When | Then |
|---|---|---|
| **HUMAN REVIEW** | two or more reliable (usable), distinct families raise risk; **or** stream integrity is violated (any B or ingest `protocol_error`, or a continuity jump) | an agent reviews before activation; the applicant sees "an agent will verify you" |
| **RETRY / STEP-UP** | one family raises risk; or no family raises risk but some threat lacks 2 covering families; or poor capture / inconclusive evidence; or `force_agent` (claim mismatch) | in order, within the effort cap and 2 rounds: a fresh challenge → the no-flash path → agent-led checks → assisted KYC (branch or correspondent) |
| **PASS** | no family raises risk, no protocol error, and every threat is covered by 2 families | the call continues; the agent still decides |

**Human sign-off:** HUMAN REVIEW (and any agent-led step-up) becomes PASS only through a logged agent action with a note. The console shows failed and abstained separately, so poor light is never read as an attack.

### 12.5 Old routes → outcomes

| Route (models.py today) | Outcome | Step-up kind |
|---|---|---|
| `PASS` | PASS | — |
| `ADD_CHECKS` | RETRY / STEP-UP | fresh challenge |
| `AGENT_CHALLENGE` | RETRY / STEP-UP | agent-led checks |
| `ASSISTED_KYC` | RETRY / STEP-UP | assisted KYC |
| `HOLD` | HUMAN REVIEW | — |

`HOLD` was "≥ 2 failed families"; HUMAN REVIEW adds stream-integrity violations on their own.

**Reasons:** one sentence per non-pass check, with real counts and the band ("The face lagged the neck by 120 ms on 7 of 8 pulses; genuine phones like this: -10 to +25 ms, n = 18"), plus reason codes. A hard protocol violation and a weak physical cue get different codes.

---

## 13. Lab site (`apps/lab`): experiments

Mobile-first; must run on Android Chrome at 360 px wide. Every widget has an "ⓘ What this shows" explainer.

### 13.1 Home
Three buttons: **Device check**, **Record**, **Sessions**, plus a **Results** link. The banner states the honesty labels in use (PROVISIONAL or calibrated).

### 13.2 Device check
Runs stage 1 only, then shows the **Camera card** (every CameraDetails field with an explainer tooltip), the mode-switch timeline, the noise curve plot and fingerprint presence, and (planned) the capture mode the planner would pick. It has a "Save to device matrix" button (device code + notes). This is how gate G1 is run on each phone.

### 13.3 Record (superset protocol)
1. **Operator form:** person code (dropdown from `eval/people.csv`, which also gives the set), device code, light condition, genuine/attack, attack tool, consent reference.
2. "Hand to volunteer" screen.
3. **Guided session.** Full-screen stages, each with an explainer panel the volunteer can read (what to do, why). Every feasible unit runs in shuffled order, plus 12 s of plain video.
   - Collapsible Camera card.
   - Live mini plots: echo (face/neck) after each pulse, tilt, noise curve after stage 1.
   - A progress bar of units.
4. **End: QC card** (fps, dropped frames, clock source, face visible %, neck visible %, quick status per check grouped by family A–D, failed and abstained apart) with Keep / Discard and notes.

### 13.4 Sessions and session report
- **List:** id, time, person, device, cohort, capture mode, kind, tool, set, QC, outcome. Set B rows show counts only until `FROZEN`.
- **Report** (set A, or any set after FROZEN):
  - Camera card
  - Capture mode, plan and coverage
  - every check card under its family, with its explainer, number vs band (or PROVISIONAL) and its plot
  - evidence frames around each pulse with region overlays (face, neck, cheeks, background boxes)
  - continuity strip, event log, bundle download

### 13.5 Results (experimental results dashboard)
Each section has an explainer on how to read it.
1. **Data collected:** sessions per cohort cell, per capture mode and per attack tool, by set (B as counts only).
2. **Device matrix:** per device code: browser, channel, clock source, rVFC, resizeMode, controls, gyro, median fps, mode-probe outcome, noise-curve fit, fingerprint PCE, capture mode.
3. **Gates G1 to G4:** the measured numbers from `eval/gates.py` plus the decision text entered by a human.
4. **Separation (set A):** per-feature AUC with n per side, and genuine-vs-tool distribution strips, for family B checks vs virtual camera / emulator and families C and D and continuity checks vs live swap.
5. **Calibration:** thresholds per check and cohort with n; the leave-one-person-out family false-fail rate.
6. **Final results (only after FROZEN):** Fixed-light vs Fixed-all vs PulseLens on set B (section 16 metrics), with export PNG and CSV for the deck.

---

## 14. Demo site (`apps/demo`): judges

Built for a projector. The presenter view is readable from 3 m: body text ≥ 18 px, nothing denser than the deck. It doubles as the prototype of the deck's **agent review console** (slide 9).

### 14.1 Presenter home
- **Start a demo session:** choose a scenario (14.4) or Free run.
- **Customer device:** "Phone" (shows a big QR code + pair code) or "This laptop" (opens the desktop combined view).
- **Mode:** `live` or `step` (step-through: the orchestrator waits for **Next** before each stage, so the presenter can explain).
- **Replay a recorded session:** rehearsal sessions marked demo-ready.

### 14.2 Customer view (`/customer?code=`)
Consent and flash notice (with the no-flash choice) → camera preview → big prompts with animations → flashes (fullscreen on phones) → "Thanks, the agent will continue". No scores, ever. The applicant sees only "please retry" or an assisted route. Language toggle EN/HI is a stretch goal.

### 14.3 Presenter view (`/stage/:id`)
- **Header:** scenario title, **What we expect** (from the scenario) and **What we measured** (filled live). This keeps the demo honest.
- **Stage stepper:** Camera check, Coach, Plan, Pulses, Face integrity, Decide, plus a Continuity lane. The current stage pulses; clicking any stage opens its explainer.
- **Camera card:** channel, browser, camera label, resolution, measured fps, clock source, native modes found, controls, gyro, noise curve (mini plot), fingerprint presence, claimed vs measured profile. Each field has a tooltip.
- **Plan card:** capture mode and why, units chosen with their reason, units skipped with theirs, an effort bar, and the **coverage matrix** (attacks × families B–D) filling in as results arrive.
- **Evidence by family:** A–D, each with its gate status (usable, abstained, protocol error) and a CheckCard per check (pending → running → pass/fail/abstain) with its plain sentence, its number against the genuine band, and an expandable "Why this matters". A is labelled experimental.
- **Live plots:**
  - EchoPlot for the latest pulse (face, neck, pulse marker, band shading)
  - SplitBars (left vs right cheek)
  - TiltPlot (gyro vs video)
  - NoisePlot (predicted vs measured)
- **Continuity strip:** identity and camera lanes over time, pulse diamonds, photo marker.
- **Outcome banner** (PASS, RETRY / STEP-UP, HUMAN REVIEW) with reasons.
- **Agent panel:** Fire light pulse, Fire tilt, Take KYC photo, Approve, Re-verify, Escalate, Assisted KYC.
- **Footer honesty labels:** `PROVISIONAL THRESHOLDS` or "Thresholds from n genuine sessions", and `ILLUSTRATIVE` on any example data.

### 14.4 Scenarios (`apps/demo/src/scenarios.ts`)

The first four are the deck's live demo (slide 11).

| id | Customer device | Presenter does | What we expect (shown on screen) |
|---|---|---|---|
| `genuine-phone` | team phone, mobile browser, good light | nothing | CAPABLE mode; B passes; light and head turn; PASS |
| `desktop-dim` | laptop, cheap USB webcam, dim room | coaching, then as needed fires one pulse as the agent | coached; the light check abstains; CONSTRAINED or no-flash path; PASS or RETRY / STEP-UP |
| `virtual-camera` | laptop; pre-recorded clip through the OBS virtual camera | nothing | challenge mismatch (C) and integrity (B); HUMAN REVIEW |
| `live-swap` | attack laptop: Deep-Live-Cam or FaceFusion on a consenting teammate | fires a pulse | shown as measured, including any miss |
| `switch-after-checks` (extra) | attack laptop; the teammate switches the swap on after the pulses | takes the KYC photo | continuity jump on identity and camera; HUMAN REVIEW; photo retaken |
| `judge-replay` (extra) | laptop; a judge holds up a phone playing a video | nothing | B passes (it's a real camera); no light response; HUMAN REVIEW if the turn also fails, else RETRY / STEP-UP |

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

## 15. Evidence pack (evidence record; planned, M3.8)
`chain.json` hashes meta, probe, pulses, sensors, events, results, the photo, and frames around each pulse onset. Each `link = sha256(prev_link + sha256(file))`; the head is stored in SQLite. `scripts/verify_evidence.py` reports the first mismatch. The chain is built **server-side** from server events: hashing a client upload alone does not prove the camera is real. Encryption at rest and role-based access are production items (section 17).

---

## 16. Evaluation protocol (`eval/`) — India readiness & evaluation

**Recordings**
- Superset recordings come from Lab Record (13.3).
- Sets are decided at recording time:
  - genuine: by person, via `people.csv` (about 60/40)
  - attacks: alternating A/B within each tool
  - `liveportrait`: set B only (held out: one attack tool held out when feasible)
- Development and gates use set A only. Splits are person-disjoint.

**Groups to measure (deck slide 12):**

| Group | Conditions | Evidence we expect |
|---|---|---|
| Genuine users | bright and dim rooms, movement, budget and mid-range devices, skin tones | low false holds; safe abstention |
| Replay | old genuine clip, on a screen or fed in, against a fresh challenge | C: response mismatch |
| Injection | virtual camera; duplicated or re-timed frames | B: integrity · C: mismatch |
| Live swap | consented sessions, Deep-Live-Cam and FaceFusion through the normal capture path | C: face vs neck · D: head turn, detector (unvalidated: report misses) |
| Nuisance | LED and tube light, glare, partial neck, compression, network drops | abstain, not flag |
| Ablation | each family alone, then fused | incremental value; redundancy (decides whether A ever votes) |

**Freeze:** `freeze.py` writes `FROZEN` with hashes of `policy.yaml`, `thresholds.json`, `config.yaml` and `splits.json`. `run.py` refuses set B without it.

**Policies, scored on the same set B sessions:**
- **Fixed-light:** `light` + `clip`, pooled thresholds; HUMAN REVIEW if any check fails.
- **Fixed-all:** every feasible unit, pooled thresholds; HUMAN REVIEW if any check fails; no routing.
- **PulseLens:** capture modes and planner, per-cohort thresholds with family budget, quality gate, grouped fusion, outcomes, continuity guard. A fresh-challenge step-up is simulated from extra recorded units; agent-led step-ups and HUMAN REVIEW count as "routed to a person", never as accepted.

**Metrics:**
- APCER and BPCER in ISO/IEC 30107-3 terms: attacks accepted (PASS) per tool and the worst tool; honest users sent to HUMAN REVIEW
- injection results reported separately (CEN/TS 18099)
- honest users given a retry or step-up (retry rate)
- abstain rate and coverage
- median and p95 time (latency)
- all as x of n with Wilson 95% intervals, per device, lighting and skin-tone group, and per capture mode

Small demo samples are feasibility evidence only, never production accuracy.

**Gate scripts:** `eval/gates.py g1|g2|g3|g4` print the numbers each gate needs (BUILD_PLAN), and the Results page reads the same output.

---

## 17. Security and privacy

**Built in the prototype**
- HTTPS via tunnel; CORS limited to the tunnel origins.
- Signed single-use challenge steps (pulses) with expiry and replay protection; acks accepted once; the event sequence is bound to the session.
- Customer payloads never contain scores (deny-list on every customer message).
- Session token for scores and events; agent actions need the console passcode (prototype-level, labelled as such).
- `data/` and `models/` are gitignored; person codes only; no heart rate stored.
- Flashes ≤ 3 per second.

**Planned for the prototype**
- Demo sessions auto-delete after 1 hour.
- `purge_volunteers.py` deletes all sessions whose person code isn't in `TEAM_CODES`.
- No-flash option that routes to an agent.
- Server-side hash-chained evidence events (section 15).

**Production (deck slide 14; not in the prototype)**
- TLS end to end (RBI asks for device-to-host encryption).
- Authorisation on result and evidence endpoints; role-based reviewer access.
- Encryption at rest; retention set by the bank and applicable law.
- Native-app attestation against injection; security audit of the V-CIP stack.
- Licence detector weights (SBI weights are research-only); patent check (challenge-response liveness is heavily patented, e.g. US 12,413,865).

**Data minimisation**
- No heart-rate estimates or raw pulse waveforms stored.
- Temporary computation buffers kept separate from evidence the bank retains.
- No compliance claim just because it runs in India: notice, access and deletion follow the bank's policy.

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
profiles: {fps_bands: [20, 27]}      # calibration cohorts (8.3); 20 is also the provisional CAPABLE / CONSTRAINED cut (8.1)
planner:  {effort_cap: 20, max_rounds: 2, families_per_threat: 2}
calibration: {alpha_family: 0.01, provisional_tau: 3.0, min_genuine_for_lopo: 40}
continuity: {identity_hz: 2, window_s: 3}
quality:  {min: 0.5, min_face_frac: 0.02, luma_range: [40, 220], min_fps: 12}
physiology: {enabled: false}
demo:     {retention_min: 60, pair_code_ttl_min: 10}
```

Planned keys (not in `config.yaml` yet): `pulses.turn` (duration), `pulses.light_constrained` (colour count, duration), and the capture-mode cut-points, which may instead live in `policy.yaml`.
