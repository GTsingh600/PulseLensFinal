# Status

Ticked = acceptance checks in `docs/BUILD_PLAN.md` pass. Newest notes first in each section.

## Progress

### M1: Engine skeleton, capture, light echo (H0–6)
- [x] **M1.1 [all] Monorepo scaffold** — `make setup`, `make test` (8 passed), `make test-web` (tsc + vitest, 6 workspaces), `make lint` and `make e2e` (3 passed: Lab :5173, Demo :5174, `/api/health` 200 direct and through both proxies). 2026-10-21.
- [x] **M1.2 [C] Server core** — pytest (`test_server_core.py`, 17 tests): events have seq 0..n and `?from=k+1` returns exactly the missed events (also over WS for a reconnecting presenter, and after a server restart); customer-role messages never contain `score`, `check_id` or `family` even with `check.result` events on the bus mid-session; an ack is accepted once, a repeat is rejected (`duplicate_ack`), a late one (server deadline or painted > 300 ms after arrival) is logged `ok:false`; pair codes expire after the 10 min TTL (410). Plus: forged signature and unknown pulse rejected, frame names can't escape the bundle, step mode waits for /next, agent actions need the passcode. e2e: Lab Record against the real server (no mock): 10 of 10 pulses acked, bundle with label written, `cli analyze` runs on it. 2026-10-21.
- [x] **M1.3 [C] Explainer package** — build step (`scripts/build_explainers.ts`, typed keys, staleness vitest) from track A; key coverage: `test_explainer_keys.py` fails when a key used in Python/TS code, the check registry or `policy.yaml` is missing from EXPLAINERS.md (0 missing now), and lists unused keys as a warning (70 now: checks, plan reasons, outcomes and dashboards not built yet). Self-tested on a synthetic tree. `make explainers` rebuilds and prints both lists. 2026-10-21.
- [x] **M1.4 [A] Capture core** — vitest: 39 tests in `packages/capture` (colours within ±5% luminance, ≤ 3 flashes/s, channel detection, uploader, pulse timing, coaching). `make e2e` (Chromium fake camera, mock server): details posted, 371 frames with strictly increasing t (captureTime clock), fingerprint frame on every 5th, 10 pulse acks in order. Runs against `e2e/support/mock-server.ts` until M1.2 lands. 2026-10-21.
- [x] **M1.5 [B] Vision base, light echo and face-vs-neck** — pytest (synthetic): delays 60/100/150/250 ms recovered within ±1 frame at 30 and 24 fps; face lagging the neck by 100 ms fails; neck echo without face echo is a strong (rule) fail; neck out of frame and saturated neck abstain; bad input never throws. `cli analyze --plots` runs on a synthetic bundle (pass, and fail for a synthetic swap) and on a real `make e2e` bundle (no face in Chromium's test pattern, so both checks abstain). Seed sweep: 0 of 600 onsets off by more than a frame at 24–30 fps; genuine face-vs-neck 25/25 pass, 100 ms lag 25/25 fail. 2026-10-21.
- [x] **M1.6 [A] First Lab page: Record (minimal)** — `/record`: operator form → hand-over → camera, coach and light suite with the stage explainer panel, prompt and basic Camera card → labelled bundle. e2e: bundle `meta.json` carries the label, 10 pulses ok, ≥ 100 frames; stage, prompt and Camera card field text equals `docs/EXPLAINERS.md` (parsed independently in the test); no sideways scroll at 360 px. vitest: form validation, ExplainPanel and CameraCard. 2026-10-21.
- [ ] GATE G1 (H6) [HUMAN]

### M2: Every check, UI components, Lab report (H6–18)
- [ ] M2.1 [A] Mode-switch probe and Lab Device check page
- [ ] M2.2 [A] Remaining pulses and superset Record
- [ ] M2.3 [B] Camera reality checks
- [ ] M2.4 [B] Optical, motion and lens
- [ ] M2.5 [B] Face content and continuity
- [ ] M2.6 [B] Calibration
- [ ] M2.7 [C] Shared UI components
- [ ] M2.8 [C] Lab Sessions and Session report
- [ ] M2.9 [C] Evaluation scripts
- [ ] GATE G2 (H14) [HUMAN + C]

### M3: Planner, fusion, orchestrator, Demo site (H18–28)
- [ ] M3.1 [C] Planner
- [ ] M3.2 [C] Fusion, continuity guard and reasons
- [ ] M3.3 [C] Live orchestrator
- [ ] M3.4 [A] Demo customer view and pairing
- [ ] M3.5 [A+C] Demo presenter view
- [ ] M3.6 [A] Desktop combined view
- [ ] M3.7 [C] Replay
- [ ] M3.8 [C] Evidence chain
- [ ] GATE G3 (H24): physiology

### M4: Calibrate, evaluate, Lab Results (H28–38)
- [ ] M4.1 [C] Splits and freeze
- [ ] M4.2 [B] Calibrate on set A
- [ ] M4.3 [C] Evaluate
- [ ] M4.4 [C] Lab Results dashboard
- [ ] GATE G4 (H38)

### M5: Harden, rehearse, fallbacks (H38–48)
- [ ] M5.1 [A+C] Demo hardening
- [ ] M5.2 [HUMAN] Rehearsals
- [ ] M5.3 [C] README
- [ ] M5.4 [C] Purge script

## Needs a human
- **Attack recordings (only the people recorded consent; existing tools only, CLAUDE.md rule 7).** Lab Record → **Attack** → pick the tool. One genuine session on the same device and light first, then each attack below twice. Then `python -m pulselens.cli analyze data/sessions/<id>` and note the statuses. Only the checks marked *now* exist; the rest arrive with M2.3–M2.5 and are listed so the recordings are reusable.

  | Attack (tool in the form) | How to record it | Expected now | Expected later |
  |---|---|---|---|
  | Phone screen replay (`screen_replay`) | play your own earlier session video on a phone held in front of the webcam | `optical.light.delay` fails (no echo) | `camera.noise_curve`, `content.hand` |
  | Virtual camera (`premade_injection`) | OBS Studio → OBS Virtual Camera playing your own video; pick it in the browser | `optical.light.delay` fails | `camera.modes`, `camera.noise_curve`, `camera.label` |
  | Live face swap (`liveswap`) | Deep-Live-Cam into a virtual camera, a consenting teammate's face | `optical.face_neck` fails (face lags neck) | `camera.*`, `content.fingerprint_hole` |
  | Driven portrait (`liveportrait`) | LivePortrait driven by your own face | `optical.light.delay` fails or `face_neck` fails | `content.*` |
  | Emulator (`emulator`) | Android Emulator camera in the emulator's browser | — | `camera.env`, `camera.modes` |

  A glossy phone screen can reflect the laptop's flash, so a screen replay may show a real-looking echo; that is what `face_neck` and the camera checks are for. Record what happens rather than what the table expects. The local replay e2e (`make e2e-brave`, after `python scripts/bundle_to_y4m.py data/sessions/<your genuine id>`) is the same attack without a phone: on session `ed0a0c434e62b495` light delay failed with 0 of 6 echoes and face-vs-neck abstained.
- **Gate G1 (H6): device run of Lab Record.** Everything it needs is on branch `trackC` (it contains tracks A and B too). Merge `trackC` into `main` first (`git switch main && git merge --ff-only trackC`).
  1. On the team laptop: `git pull`, `make setup`, then in three terminals `make server`, `make lab`, `make tunnel`. Note the `https://….trycloudflare.com` URL printed for :5173.
  2. Devices: budget Android (Chrome), mid-range Android (Chrome), iPhone (Safari), laptop (Chrome). Give each a device code (D01–D04) on the paper sheet.
  3. On each device open `<lab tunnel URL>/record`. Operator form: a team person code (e.g. P01), the device code, Light **Normal**, **Genuine**, the consent reference. Tap **Continue**, hand the device over, tap **Start**.
  4. Allow the camera. iPhone: also allow **Motion & Orientation**. Android should go full screen.
  5. Hold the phone about 40 cm away (laptop: sit at arm's length), face the screen, **keep neck and shoulders in view**, stay still during the colour flashes. Wait for **Recording saved**.
  6. Repeat once more on the same device (2 sessions per device, 8 in total).
  7. For each session: `python -m pulselens.cli analyze data/sessions/<session_id> --plots` (session id is on the Recording saved screen).
  8. **Go if:** the Camera card filled on every device; measured fps ≥ 20 or the device maximum; light echo found on ≥ 5 of 6 colour pulses in ≥ 6 of 8 sessions; face-vs-neck computed (neck visible) in ≥ 6 of 8 sessions.
  9. **Record per device** in the device matrix: clock source, `resizeMode` support, camera controls, gyro, median fps (all on the Camera card, and in `meta.json` → `camera_details`).
  10. **No-go fallbacks** (BUILD_PLAN G1): pulses to 600 ms and full screen on desktops; "show your shoulders" coaching tip and the shirt region; `light` becomes ○ for desktops in `policy.yaml`.
  11. Also note on each phone: does the full-screen flash look right (Android), does the page stay awake, is the prompt readable on the coloured overlay. If capture misbehaves, `<lab tunnel URL>/capture-harness.html` shows the raw capture state as JSON.
- **Push to GitHub.** The local repo has the M1.1 commit on `main`; `https://github.com/GTsingh600/PulseLensFinal` is still empty. Review, then: `git remote add origin https://github.com/GTsingh600/PulseLensFinal.git` and `git push -u origin main`. Then each teammate: `git clone`, `make setup`, `git worktree add ../pl-trackA -b trackA` (B, C likewise).
- **Assign track owners** (A, B, C) in `docs/BUILD_PLAN.md` section 1.
- **`.env` secrets.** `make setup` copied `.env.example` to `.env` with `change-me` values; the server logs a warning until they are replaced. Generate a secret with `python -c "import secrets; print(secrets.token_hex(32))"`.
- **`docs/consent_form.md` is missing.** BUILD_PLAN section 5 needs it signed by every volunteer; write it (no personal data in git) and print 20 copies.
- **cloudflared** is not installed on this laptop; `make tunnel` needs it for phones (HTTPS for camera and motion sensors).
- **Heavy models.** `python scripts/fetch_models.py --heavy` downloads buffalo_l (~280 MB) and CLIP ViT-B-32 (~600 MB); run it once on good Wi-Fi before H6. MediaPipe face, hand and BlazeFace files are already fetched by `make setup`.
- **Node 22.12+ and Python 3.11** on every teammate's laptop (vitest 5 needs Node 22.12+). With `uv` installed, `make setup` downloads Python 3.11 itself.

## Decisions
- **Phase 2 (2026-10-21): echo onset.** The robustness matrix (`test_optical_robustness.py`: 12–30 fps, neck 0.3–3x the face, rolling shutter, noise to 0.003) showed the fixed-threshold onset false-failing genuine faces (14 cells) and passing faces redrawn 100 ms late (5 cells), because a weak echo crosses 4σ later on its ramp. The G1 laptop session showed it for real: face and neck rose in the same frame but crossed at 115 vs 54 ms (+61 ms, past the ±60 ms limit). `face_neck` now uses a constant-fraction (half-height) onset, an SNR gate (`min_snr: 2` in bootstrap.yaml) and counts "neck only" only when the face never crossed its threshold. Onsets whose hold amplitude is below threshold no longer count (a noise blip at 360 ms with amplitude −0.0004 was counted as an echo). Both optical checks abstain below `quality.min_fps` (12), which was in config but unused. Matrix: 0 genuine fails, 0 swap passes.
- **G1 laptop D01 (session `ed0a0c434e62b495`, Brave, USB2.0 UVC webcam, border flash, window not full screen):** camera delivered 15.6–21 fps (presented_frames step 1 on 364/365 frames: the camera, not the grabber; intervals of 48/64 ms look like auto-exposure in dim light). Face echo 0.0035–0.0059 vs threshold ~0.003, neck 0.009–0.018. After the fix: `light.delay` fails (2 of 6 echoes), `face_neck` abstains. This is the G1 "echoes fail on desktops" no-go case; see Needs a human.
- **M1.3 (2026-10-21):** Key coverage is a pytest over all sources (Python and TS) rather than a vitest, so server prompt keys and the check registry are covered too. Dotted event and message names (`check.result`, `plan.decided`, `stage.done`) are recognised and skipped. Keys built at run time are not seen in sources; checks are covered through the registry instead.
- **M1.2 (2026-10-21):** `/next` only works while the orchestrator waits (409 otherwise), so a double-click can't skip a stage. Pair codes stay valid for any number of joins within the TTL (the customer page may reload); they are kept in memory, so a server restart drops them. One capture device per session. The orchestrator stub runs camera → coach → light suite (coach added so M1.4 coaching runs; the planner replaces this in M3.3).
- **M1.2:** e2e runs start the server with `PULSE_DATA_DIR=data/e2e`, so test sessions never mix with `data/sessions` (volunteer data).
- **M1.5 (2026-10-21):** No set A data yet, so `optical.light.delay` and `optical.face_neck` use `calibration/bootstrap.yaml` (physics-based, `threshold_source: "bootstrap"`, PROVISIONAL): light delay band 0–300 ms; face-vs-neck centre 0 ms, 20 ms per score unit, tau 3 (fail beyond ±60 ms), amplitude ratio free within 4x. Replace from G1/G2 sessions; record the change here.
- **M1.5:** `cli analyze` caches MediaPipe landmarks in `<bundle>/landmarks.jsonl`; the synthetic bundle ships that cache so the whole pipeline (JPEG → linear → regions → echoes → checks) is tested without a face model. Outputs go to `<bundle>/analysis/`, leaving `results.json` to the server.
- **M1.5:** Python vision deps: `mediapipe` 0.10.35 (same line as the browser's tasks-vision) and its `opencv-contrib-python` as the only cv2; installing `opencv-python-headless` beside it would overwrite the same module. `planner/registry.py` (CheckSpec + register) created here so checks can register; track C extends it for the planner.
- **M1.4 (2026-10-21):** Capture WebSocket protocol defined in `models.py` and SPEC 6 (`stage`/`prompt`/`pulse`/`done` down, `ack`/`stage.done`/`heartbeat` up). Light pulse params carry hues; the client computes the isoluminant colours and reports them in `ack.shown` (new `shown` and `error` fields in pulses.jsonl). Track C: implement the server side to match `e2e/support/mock-server.ts`.
- **M1.4:** Track A's e2e tests use a Playwright mock server (`page.route` + `routeWebSocket`) instead of the Python server, so capture is tested without M1.2. It also writes a SPEC 4.1 bundle under `test-results/` for track B's CLI.
- **M1.4:** Neutral luminance Y = 0.5 for the light suite (widest equal-luminance colour circle). Motion permission is requested only on iOS; desktop Chrome would answer "denied" on laptops without sensors.
- **M1.4:** `config.yaml` is mirrored to `packages/types/src/config.gen.ts` by `make types`, so browser code reads the same numbers as the server.
- **M1.1 (2026-10-21):** Make recipes live in `scripts/dev.py` (works on Windows cmd, PowerShell, macOS, Linux; `python scripts/dev.py <target>` works without make). `scripts/tunnel.sh` from SPEC 3 is replaced by `make tunnel` in the same runner.
- **M1.1:** `packages/types/src/models.gen.ts` is generated from `server/pulselens/models.py` by `make types`; `test_types_mirror.py` fails when it is stale. SPEC 4.2 types and the event envelope are in place now so tracks A, B and C share one contract from H0.
- **M1.1:** Dev tool versions: vitest 5 (vitest 3 and 4 ≤ 4.1.10 have critical tinypool advisories), ESLint 10 (9 is end-of-life), TypeScript 5.9 (typescript-eslint does not support 7 yet), Vite 7, React 19. `npm audit`: 0 vulnerabilities.
- **M1.1:** ESLint forbids `Date.now()` in TS code (CLAUDE.md rule 1); use `now()` from `@pulselens/capture`.

## Blockers
- None.
