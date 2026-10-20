# PulseLens final build plan: 48-hour finale

**What we ship:** one engine and two websites.
- **Lab** (experiments): records labelled sessions on Android, iPhone and laptops, explains every raw measurement, and shows the experimental results.
- **Demo** (judges): a phone or laptop is the customer, and a big-screen presenter view explains every step live.

**Not in scope:** the final product website, which we build after the hackathon.

**How to use this file with Claude Code**
- Put `CLAUDE.md` at the repo root. Put `SPEC.md`, `EXPLAINERS.md`, `BUILD_PLAN.md`, `STATUS.md` and `consent_form.md` in `docs/`.
- Start Claude Code in the repo and paste the prompts from section 9, one milestone (or one track) at a time.
- Every task has acceptance checks. Claude Code runs them, fixes failures, ticks the task in `docs/STATUS.md` and commits.
- **[HUMAN]** tasks need a phone, a person, a GPU or a decision. Claude Code writes the exact steps into `STATUS.md` and moves on.

---

## 0. Before the event

Check the rules first. If code before the finale isn't allowed, do only the non-code prep below.

- [ ] **Request dataset access now.** FaceForensics++ and Celeb-DF v2 need forms, and approval can take days. Without them the CLIP detector is cut; everything else still works.
- [ ] **Devices:**
  - one **budget Android** (₹8,000 to 12,000 class) and one mid-range Android, both with Chrome
  - one iPhone with Safari
  - a laptop with a built-in webcam, plus a cheap USB webcam (480p class)
  - a laptop with an NVIDIA GPU for the attack lab
  - a phone stand
  - a projector or second screen for the presenter view, plus an HDMI adapter
  - a phone hotspot as backup Wi-Fi
- [ ] **Attack laptop (human installs and tests once on a teammate):** OBS Studio (virtual camera), Deep-Live-Cam, LivePortrait, Android Studio emulator.
- [ ] **cloudflared:** installed and tested from a phone on mobile data. Phones need HTTPS for the camera and motion sensors.
- [ ] **Models downloaded:** MediaPipe face and hand landmarkers, insightface `buffalo_l`, open_clip ViT-B-32, and the tasks-vision wasm files.
- [ ] **Paperwork:** print 20 consent forms. Prepare the paper code sheet (names to `P01`...); it never goes into the repo.

---

## 1. Team tracks

Do M1.1 together. Then each teammate drives one Claude Code session in its own git worktree (`git worktree add ../pl-trackA -b trackA`). Merge to `main` at every gate.

| Track | Owns | Teammate |
|---|---|---|
| **A: Capture and customer UI** | `packages/capture`, Lab Device check and Record, Demo customer view, desktop combined view | (assign) |
| **B: Analysis** | `server/pulselens/vision`, every check, calibration, CLIP probe | (assign) |
| **C: Engine and screens** | server, events, orchestrator, planner, fusion, `packages/explain`, `packages/ui`, Lab sessions and results, Demo presenter and replay, evaluation | (assign) |

From H18, A helps C on the presenter view. Keep one person recording volunteers from H8 to H36.

---

## 2. Timeline and gates

| Hours | Milestone | Gate at the end |
|---|---|---|
| H0–6 | M1 Engine skeleton, capture, light echo, first Lab page | **G1 (H6):** camera details, light echo and face-vs-neck on real devices |
| H6–18 | M2 Every check, Lab report, UI components; recording starts | **G2 (H14):** camera checks catch virtual cameras? optical/content separate a live swap? |
| H18–28 | M3 Planner, fusion, live orchestrator, Demo site | **G3 (H24):** physiology go/no-go |
| H28–38 | M4 Calibrate, freeze, evaluate, Lab Results | **G4 (H38):** results table filled |
| H38–48 | M5 Harden, rehearse, record fallbacks | **Code freeze H40** |

---

## 3. Milestones and tasks

§ numbers refer to `docs/SPEC.md`.

### M1: Engine skeleton, capture, light echo (H0–6)

**M1.1 [all] Monorepo scaffold (§3).**
- **Build:**
  - npm workspaces (`types`, `capture`, `explain`, `ui`, `apps/lab`, `apps/demo`), FastAPI app
  - Makefile targets, `config.yaml` (§18), `.env.example`, `.gitignore` (data, models, .env)
- **Accept:**
  - `make setup`, `make test`, `make test-web` and `make lint` pass
  - Lab loads on :5173 and Demo on :5174
  - `GET /api/health` returns 200

**M1.2 [C] Server core (§4, §5, §6).**
- **Build:**
  - models, store, session and pairing APIs
  - `/ws/session/{id}` with roles
  - the event bus (append to `events.jsonl`, push, catch-up from `seq`)
  - just-in-time signed pulses
  - an orchestrator stub: camera stage, then the light suite
- **Accept (pytest):**
  - events have strictly increasing `seq`, and catch-up returns exactly the missed events
  - customer-role messages never contain `score`, `check_id` or `family`
  - a pulse ack is accepted once; a repeat is rejected; a late one is logged `ok:false`
  - pair codes expire after the TTL

**M1.3 [C] Explainer package (§3, `EXPLAINERS.md`).**
- **Build:** `scripts/build_explainers.ts` parses `EXPLAINERS.md` into `packages/explain` with `explain(key)`.
- **Accept:** a test fails if any key referenced in code, the check registry or `policy.yaml` is missing from `EXPLAINERS.md`, and the reverse check lists unused keys.

**M1.4 [A] Capture core (§7.1, 7.2, 7.4 light suite, 7.5).**
- **Build:**
  - secure-context guard, fullscreen + wake lock on Android, CameraDetails collection
  - the grabber (rVFC, VideoFrame, rAF) with working and fingerprint frames and batched upload
  - the light suite (equal-luminance colours, split, white)
  - coaching
- **Accept:**
  - `make e2e` (Chromium fake camera): details posted, ≥ 200 frames with increasing `t`, a fingerprint frame every 5th frame, 10 pulse acks in order
  - vitest: colours are within ±5% luminance, ≤ 3 flashes per second, channel detection works

**M1.5 [B] Vision base, light echo and face-vs-neck (§9.1, §9.3).**
- **Build:**
  - `linearize.py`; `face.py` regions including the neck box
  - the echo onset helper; `optical.light.delay` and `optical.face_neck`
  - `cli analyze --plots`
- **Accept (synthetic):**
  - delays of 60, 100, 150 and 250 ms are recovered within ±1 frame
  - a face lagging the neck by 100 ms is detected
  - a neck echo with no face echo is a strong fail
  - the neck box out of frame abstains
  - the CLI runs on a synthetic bundle and on an e2e bundle without crashing

**M1.6 [A] First Lab page: Record (minimal).**
- **Build:** operator form, then camera + light suite with the stage explainer panel and a basic Camera card; uploads a labelled bundle.
- **Accept:** e2e records a labelled bundle, and the explainer text matches `EXPLAINERS.md`.

**GATE G1 (H6) [HUMAN]**
- **Test:** budget Android, mid Android, iPhone and laptop. Run Lab Record twice on each in normal light, then `cli analyze`.
- **Go:**
  - Camera card fills on every device
  - ≥ 20 fps or the device maximum
  - light echo found on ≥ 5 of 6 colour pulses in ≥ 6 of 8 sessions
  - face-vs-neck computed (neck visible) in ≥ 6 of 8 sessions
- **Record:** clock source, `resizeMode`, controls and gyro for each device in the device matrix.
- **No-go fallbacks:**
  - pulses to 600 ms; full screen on desktops
  - neck rarely in frame → add the coaching tip "show your shoulders" and use the shirt region
  - echoes fail on desktops → `light` becomes ○ for desktops in `policy.yaml`

### M2: Every check, UI components, Lab report (H6–18)

**M2.1 [A] Mode-switch probe (§7.3) and Lab Device check page (§13.2).**
- **Accept:**
  - `probe.jsonl` is written with every field
  - on Safari/Firefox the unusual mode is skipped and labelled
  - the Device check page shows the Camera card, modes timeline and "Save to device matrix"

**M2.2 [A] Remaining pulses and superset Record (§7.4, §13.3).**
- **Build:**
  - tilt (sensors, iOS permission in the Start tap), hand with animation, lens, KYC photo
  - full superset protocol with shuffled units + 12 s of plain video
  - set taken from `people.csv`, with attacks alternating
  - live mini plots and the QC card
- **Accept:**
  - vitest covers the permission state machine and set assignment
  - **[HUMAN]** Android and iPhone `sensors.jsonl` has ≥ 40 Hz during the tilt

**M2.3 [B] Camera reality checks (§9.2).**
- **Accept (synthetic):**
  - a fixed pattern + noise gives high PCE, no pattern gives low PCE, and a static scene with no pattern stays low (shift test)
  - the noise-curve slope is recovered on Poisson-Gaussian frames in linear light
  - modes: reported change with unchanged frames fails; ORB FOV estimates a known crop within 5%
  - duplicate count is exact; truth tables for the rules

**M2.4 [B] Optical, motion and lens (§9.3, §9.4).**
- **Build:** split, noise_pulse, reflectance, lens, tilt corr/lag.
- **Accept (synthetic):**
  - a split with the correct sign passes and the wrong sign fails
  - a noise ratio matching the predicted curve passes, and a flat one fails
  - gyro-driven background shift with lag recovers the lag within ±20 ms, and unrelated motion gives `r_max` < 0.4
  - abstain rules hold

**M2.5 [B] Face content and continuity (§9.5, §9.7).**
- **Build:** hand response/flicker/identity, fingerprint hole, CLIP (only if datasets are on disk by H6, else mark CUT), continuity identity/camera, photo binding.
- **Accept:**
  - a synthetic identity switch at time t is flagged within 1.5 s
  - a synthetic camera switch (noise and size change) is flagged
  - a photo outside a pulse window gives `photo_bound = false`
  - a face region with the pattern removed gives a hole ratio < 0.5

**M2.6 [B] Calibration (§10).**
- **Accept:** tests with fake score tables cover robust z, pooled thresholds, LOPO family false-fail ≤ target, `PROVISIONAL` below 40 sessions, bands with n, and `split_sign` learned.

**M2.7 [C] Shared UI components (`packages/ui`, §13, §14).**
- **Build:** CameraCard, PlanCard, CoverageMatrix, CheckCard, EchoPlot, SplitBars, TiltPlot, NoisePlot, ModesTimeline, ContinuityStrip, DecisionBanner, ExplainPanel, HonestyLabel, plus a gallery page `/ui-gallery` in Lab with SYNTHETIC fixtures.
- **Accept:**
  - every component requires an explainer key prop (a type error if missing)
  - the gallery renders at 360 px and 1920 px with no element where `scrollWidth > clientWidth` (Playwright check)
  - fixtures show the SYNTHETIC label

**M2.8 [C] Lab Sessions and Session report (§13.4).**
- **Accept:** the report shows every check with its explainer, band (or PROVISIONAL) and plot; evidence frames have region overlays; set B rows are counts only (test).

**M2.9 [C] Evaluation scripts.**
- **Build:** `people.csv`, label sync, `separation.py`, `gates.py g1 g2`.
- **Accept:** they run on synthetic bundles, print AUC with n per side, and refuse set B (test).

**[HUMAN] Recording:** genuine sessions from H8, attacks from H10 (section 5).

**GATE G2 (H14, set A only) [HUMAN + C]**
- **G2a, camera vs virtual cameras:** any of `camera.modes`, `camera.noise_curve`, `camera.fingerprint` or `camera.timing` reaches AUC ≥ 0.8 for OBS/Deep-Live-Cam/emulator vs genuine on the same laptop (≥ 5 attack, ≥ 10 genuine).
- **G2b, live swap:** any of `optical.face_neck`, `optical.split`, `optical.noise_pulse`, `optical.light.delay`, `content.hand.flicker`, `content.hand.identity` or `content.fingerprint_hole` reaches AUC ≥ 0.8 vs Deep-Live-Cam.
- **Decisions, per check:**
  - ≥ 0.8 → voting
  - 0.65 to 0.8 → voting but its family stays ○ for that attack
  - < 0.65 → shown on screen as "measured, not voting"
- `light` liveswap becomes ● only if `face_neck` passes.
- Record every decision in `STATUS.md` and tell the deck owner.

### M3: Planner, fusion, orchestrator, Demo site (H18–28)

**M3.1 [C] Planner (§11, `policy.yaml`).**
- **Accept (`test_planner.py`):**
  - phone with gyro → `tilt` + `light`
  - desktop → `hand` + `light` + `AGENT_CHALLENGE`
  - no-flash → no light, plus an agent challenge
  - mismatch → union + agent challenge
  - effort cap respected
  - round 2 re-plans after abstentions
  - every reason has an explainer key

**M3.2 [C] Fusion, continuity guard and reasons (§12).**
- **Accept:** table-driven tests for every route rule, family de-duplication, `force_agent`, continuity jump, photo binding, the human-signoff rule, and reasons carrying real counts and bands.

**M3.3 [C] Live orchestrator (§5, §6).**
- **Build:** modes `live`, `step` and `superset`; incremental analysis in a process pool; every event type emitted; agent actions.
- **Accept:**
  - e2e live session with the fake camera reaches `decision` in < 60 s, with the event sequence `stage.changed` → `camera.details` → `probe.step` → `plan.decided` → `check.result`… → `decision`
  - step mode waits on `/next`
  - `fire_light` produces a `source: "agent"` pulse

**M3.4 [A] Demo customer view and pairing (§14.2).**
- **Accept:** e2e with two browser contexts: the presenter creates a session and the customer joins by code; consent and the no-flash path work; customer payloads contain no scores.

**M3.5 [A+C] Demo presenter view (§14.1, 14.3, 14.4).**
- **Build:** home, scenarios, stepper, Camera card, Plan card + coverage, test feed, live plots, continuity strip, decision, agent panel, expected-vs-measured header, honesty footer, step-through controls.
- **Accept (Playwright, 1920x1080 and 1366x768, fake camera customer):**
  - events render in order
  - every card shows its explainer on click
  - no text overflow (scrollWidth check)
  - body text ≥ 18 px
  - a screenshot per scenario is saved to `apps/demo/test-results/`

**M3.6 [A] Desktop combined view (§14.5).**
- **Accept:** the flash border surrounds the whole window, and the presenter column stays readable at 1366x768.

**M3.7 [C] Replay (§14.6).**
- **Accept:** a recorded session replays with play, pause, scrub and speeds; a pulse click shows frames with overlays; replay works with the network disconnected (data cached on load).

**M3.8 [C] Evidence chain (§15).**
- **Accept:** changing one byte makes `verify_evidence.py` name the file.

**GATE G3 (H24): physiology.** Turn it on only if set A genuine vs pre-made injection reaches AUC ≥ 0.75 with < 50% abstain on phones. Otherwise it stays on the roadmap.

### M4: Calibrate, evaluate, Lab Results (H28–38)

**M4.1 [C] Splits and freeze.** Run `split.py` checks (no person in both sets; LivePortrait only in B), then `freeze.py`.

**M4.2 [B] Calibrate on set A.** Write `thresholds.json`; the PROVISIONAL label disappears where n ≥ 40.

**M4.3 [C] Evaluate.** Run `run.py` (three policies on set B) and `report.py`.
- **Accept:** `run.py` refuses without FROZEN or after any config change (test).

**M4.4 [C] Lab Results dashboard (§13.5).**
- **Build:** data collected, device matrix, gates (numbers from `gates.py` plus decision text), separation, calibration, final results with Wilson intervals, PNG and CSV export.
- **Accept:** every widget has its explainer; every number prints as "x of n"; it renders at 360 px.

**GATE G4 (H38):** results table filled. The numbers go into the deck exactly as measured. If PulseLens doesn't keep attack acceptance at or below both baselines, the Results page shows which family or rule let attacks through.

### M5: Harden, rehearse, fallbacks (H38–48)

**M5.1 [A+C] Demo hardening.**
- **Build:** WebSocket reconnect with catch-up from `seq`; timeouts with clear messages; auto-delete of demo sessions after 1 hour; a projector check at both resolutions.
- **Accept:** killing the server for 5 s mid-session recovers without losing events.

**M5.2 [HUMAN] Rehearsals.**
- Run each scenario 5 times: the first in step-through mode, the rest live.
- Run the judge replay 20 times. Keep it in the demo only if ≥ 18 are held and the genuine control passes every time.
- Mark 2 good sessions per scenario as "demo-ready" for the replay fallback.
- Record a fallback screen video by H44.

**M5.3 [C] README** with a "How to read the screens" section generated from `EXPLAINERS.md`.

**M5.4 [C] Purge script** tested on a copy of `data/`.

**H40: code freeze.** After this, only fixes for demo bugs.

**[HUMAN] Deck v6 updates after G4:**
- replace the slide 13 results table with measured numbers
- replace the illustrative echo charts with real EchoPlot screenshots (label MEASURED)
- swap the console mock-up for a real presenter screenshot, or keep the EXAMPLE label

---

## 4. Cut list (cut from the top when behind)

1. Physiology
2. Lens pulse
3. CLIP detector (if datasets are late)
4. `optical.noise_pulse` and `content.fingerprint_hole` as voting checks (keep them visible in the Lab as "measured, not voting")
5. Desktop combined view (use two windows instead)
6. Frame overlays in replay (keep plain replay)
7. Hindi prompts

**Never cut:**
- camera check (modes, noise curve, fingerprint presence, timing)
- light suite with face-vs-neck and split
- tilt and hand
- continuity identity
- planner and fusion
- presenter view with explanations
- Lab Record and the final results table

---

## 5. Data collection protocol [HUMAN]

**Consent first:** every volunteer signs `docs/consent_form.md`. Use codes only. Volunteer faces are never used in attacks. Each volunteer is assigned set A or B in `eval/people.csv` at enrolment (about 60/40, balancing phones and laptops).

**Genuine sessions** (target ≥ 100, ≥ 10 per profile cell where possible):
- 10 to 15 volunteers
- each records on their own phone, the team laptop webcam, the USB webcam and the budget Android
- normal and dim light, 2 repeats each
- about 1 minute each, from two stations in parallel

**Attack sessions** (consenting teammates only, swapping teammates' faces):

| Attack | How (human-operated) | Channel | Target | Set |
|---|---|---|---|---|
| Screen replay | teammate video played on a phone held to the camera | desktop and mobile | 10 | A and B |
| Pre-made injection | OBS virtual camera playing a recorded teammate video | desktop | 10 | A and B |
| Single-photo fake | LivePortrait output through the OBS virtual camera | desktop | 8 | B only (held out) |
| Live face-swap | Deep-Live-Cam into the OBS virtual camera | desktop | 10 | A and B |
| Source switch | real face during pulses, Deep-Live-Cam switched on before the photo | desktop | 6 | A and B |
| Emulator injection | Android Studio emulator with the virtual camera as webcam, Chrome inside | mobile (emulated) | 6 | A and B |

Attackers follow the prompts the way a real attacker would. Log tool versions in `STATUS.md`. Data stays on the team laptop and is purged after the event.

Demo-ready rehearsal sessions are `mode = live`, unlabelled, and never used for calibration or evaluation.

---

## 6. Demo script (about 7 minutes)

1. **Genuine phone, in step-through mode (2 min).** Walk the judges through each stage on the presenter view: the Camera card, why the plan picked tilt + light, each echo, continuity, PASS.
2. **Desktop, cheap webcam, dim room (1.5 min).** Coaching appears. The plan explains why an agent challenge is needed. Fire one pulse and approve.
3. **Live face-swap through a virtual camera posing as a basic webcam (1.5 min).** The camera check flags the modes and noise, the face lags the neck, HOLD.
4. **Swap switched on after the checks (1 min).** Take the KYC photo; the continuity lock shows the jump.
5. **Judge's replay (1 min).** A judge holds up their phone: no echo, no response to the hand prompt, HOLD. Include only if M5.2 passed.

**Rule for the presenter:** read the "What we expect" line before each run and point at "What we measured" after. If they differ, say why.

---

## 7. Traceability: deck v6 → code → proof on screen

| Deck claim | Code | Where judges see it |
|---|---|---|
| Camera first: modes, noise curve, fingerprint | `checks/camera_*.py`, `capture/probe` | Camera card, ModesTimeline, NoisePlot |
| Physics echoes: face-vs-neck, split, noise follows pulse | `checks/optical_*.py` | EchoPlot, SplitBars, NoisePlot |
| Continuity lock, photo during a pulse | `checks/continuity.py`, agent `take_photo` | ContinuityStrip |
| Fair on any device: plan per device, never a lower bar | `planner/`, `policy.yaml` | Plan card with reasons and coverage matrix |
| Agent in the loop, two families to hold | `fusion.py`, agent panel | Decision banner, agent actions log |
| Measured, not assumed | `eval/`, Lab Results | Results page, deck slide 13 |

---

## 8. Risks to watch

| Risk | Early sign | Response |
|---|---|---|
| Neck not visible on phones held close | G1 face-vs-neck below 6 of 8 | Coach "show your shoulders"; use the shirt region |
| Camera noise flattened by phone processing | `noise_curve` AUC < 0.65 at G2 | Measured, not voting; rely on modes, fingerprint, timing |
| Fingerprint too weak at browser resolution | PCE overlaps genuine vs OBS | Keep presence only on desktops; hole check goes Lab-only |
| `resizeMode` missing (Safari, Firefox) | Camera card shows unsupported | Modes check abstains there; other camera checks carry it |
| Venue Wi-Fi fails | WebSocket drops | Phone hotspot; replay demo-ready sessions; fallback video |
| Bright venue lighting weakens echoes | Low echo amplitude | Shade the demo corner; desk lamp off; coach brightness up |

---

## 9. Prompts for Claude Code

Paste one at a time, in a fresh session at the repo root.

**M1.1 (together)**
```
Read CLAUDE.md, docs/SPEC.md, docs/EXPLAINERS.md and docs/BUILD_PLAN.md completely before writing code.
Do task M1.1 only. Run its acceptance checks, fix failures, tick it in docs/STATUS.md and commit.
Then summarise what exists and what each of tracks A, B and C should start with.
```

**Track A, M1**
```
Read CLAUDE.md, docs/SPEC.md sections 4, 6 and 7, docs/EXPLAINERS.md and docs/BUILD_PLAN.md (M1.4, M1.6).
Build the capture package and the minimal Lab Record page exactly as specified, with explainer text from
packages/explain. Write the tests from each acceptance check first. Run make e2e and make test-web until they pass.
Tick each task in docs/STATUS.md, commit after each, then write the gate G1 device steps under "Needs a human".
```

**Track B, M1**
```
Read CLAUDE.md, docs/SPEC.md sections 4, 9.1 and 9.3, and docs/BUILD_PLAN.md (M1.5).
Write the synthetic tests first, then linearize.py, the face and neck regions, the echo onset helper,
optical.light.delay, optical.face_neck and the analysis CLI with plots. Keep estimators pure functions of
region means and the pulse log. Tick M1.5 in docs/STATUS.md and commit.
```

**Track C, M1**
```
Read CLAUDE.md, docs/SPEC.md sections 4, 5, 6 and 17, docs/EXPLAINERS.md and docs/BUILD_PLAN.md (M1.2, M1.3).
Build the server core with the event bus, pairing and signed just-in-time pulses, then the explainer package and
its key-coverage test. Write every acceptance check as a test first, including "customer payloads never contain
scores". Tick both tasks in docs/STATUS.md and commit after each.
```

**Any later milestone (per track)**
```
Read CLAUDE.md, docs/STATUS.md, and the sections of docs/SPEC.md and docs/EXPLAINERS.md referenced by tasks <IDs>
in docs/BUILD_PLAN.md. Do tasks <IDs> in order. For each: write tests from its acceptance checks first, implement
until they pass, tick it in docs/STATUS.md, commit. Every new screen element must show its explainer from
packages/explain. If a task needs a device, a person or data we don't have, write exact steps under "Needs a human"
and continue. Do not change thresholds, policy.yaml ratings or splits unless the task says so. Stop at the next gate
and summarise the numbers the humans need to decide on.
```

**After a gate (paste the numbers back)**
```
Here are the gate <G#> results: <paste gates.py output and device notes>.
Read gate <G#> in docs/BUILD_PLAN.md. Apply the go/no-go rules exactly: update policy.yaml or config.yaml only as
the gate says, mark checks as voting or "measured, not voting", record the decision in docs/STATUS.md under
"Decisions", make the Lab Results gates widget show it, and commit.
```

**Before code freeze (H39)**
```
Review the repo against docs/SPEC.md, docs/EXPLAINERS.md and CLAUDE.md. Find any place where: a number is shown
without a source or an honesty label, a screen element has no explainer, a customer payload could leak a score,
set B could be read before FROZEN, a heart rate could be stored, a check can throw instead of abstaining, or text
overflows at 360 px or 1366x768. Fix each with a test and commit.
```
