# PulseLens

Adaptive, camera-first liveness for Indian video-KYC (RBI V-CIP). A 48-hour prototype for the Amazon AI Cyber Security Hackathon finale, Challenge 03, team Mama Mia (Thapar): Ganeev Singh Tuteja, Yash Vishnoi, Keshav Juneja.

> **Status: prototype, PROVISIONAL THRESHOLDS.** Every number below was measured on about 7 genuine sessions from one person on one laptop webcam, plus a replay and a fake camera. There are no live face-swap recordings yet. Read the claims as hypotheses until the experiments at the end are done.

## The idea

PulseLens asks **two separate questions** on every V-CIP call, not one vague deepfake score:

1. **Is this a real camera, in this session?** (capture and injection integrity). Threats: a pre-recorded replay, a virtual camera, an injected or re-timed stream. Evidence: session binding, frame timing and duplicates, and the response to a fresh challenge.
2. **Is the face itself real?** (live manipulation). Threat: a real person on a real camera, with the face swapped in real time. Evidence: how the face responds to our light compared with the neck and background, consistency through a head turn, and a visual detector.

A clean camera result does not prove a genuine face. A weak sensor signal does not prove injection.

Why question 2 can be answered at all: a live deepfake (Deep-Live-Cam, DeepFaceLive) does not make a fake video. It takes the attacker's real camera frame and **repaints one patch of it**: the face. The neck, hair, background, sensor noise and the light from our screen stay real, so we compare the face with what is around it in the same session.

The evidence comes from **four families**, and none decides alone:

| Family | What it tests | Role |
|---|---|---|
| **A · Pulse coherence** | rPPG (POS or CHROM) on face and neck | Optional. Logged only, outside the vote |
| **B · Sensor & stream integrity** | frame cadence, jitter, dropped and repeated frames, camera mode response, sensor noise; face vs neck vs background noise and sharpness | Core |
| **C · Active light challenge** | a fresh random screen-colour sequence tied to the session; response order, shape and lag on face, neck and background | Core + experiment |
| **D · Visual & motion consistency** | a random left or right head turn with landmark and identity tracking, face-boundary seams, a pretrained SBI detector as one feature | Core + model |

Every check reports its own quality. **Poor capture leads to a retry, never a fraud flag.** The test plan follows the **measured** device (three capture modes), not its name. Each session ends in one of **three outcomes**: PASS, RETRY / STEP-UP, or HUMAN REVIEW. PulseLens recommends; **the bank's V-CIP agent decides**. It never auto-rejects a customer.

Honest positioning: each signal has prior art (Face Flashing, active illumination, self-blended-image detectors). What's ours is the combination: quality-aware fusion and adaptive capture, tested on Indian devices.

## Architecture

![PulseLens architecture](docs/architecture.svg)

> **The diagram is out of date.** `docs/architecture.svg` still shows the earlier layout (four questions, six device tiers). The final architecture is the deck's reference diagram (final deck, slide 17) and `docs/SPEC.md` section 2. The table below is current.

Three columns, as in the final deck: the applicant's device, the PulseLens service (self-hosted in the bank's VPC or on-prem in India; decisions stay server-side), and the bank's existing systems.

| Part | What it does | Built | Planned in `docs/SPEC.md` |
|---|---|---|---|
| **Device: Capture SDK** | frames with monotonic timestamps, face regions, challenge rendered in-session | Browser capture, frame upload, light overlay, exposure lock (`packages/capture`) | Head-turn prompt; Android and iOS SDKs later |
| **Device: quality preflight** | frame rate, dropped frames, blur, brightness, supported camera controls | Mode-switch probe, camera details, coaching | — |
| **1 Session orchestrator & challenge planner** | single-use session; random colour order and timing; expected events logged server-side; capture mode from measurements | Orchestrator stub: signed single-use pulses, shuffled order, random gaps, logged server-side | Planner with the three capture modes; random head-turn direction |
| **2 Ingest, provenance & frame integrity** | session binding, order, duplicates, upload integrity | Frame upload with name checks; acks accepted once, only with the session-bound signature; late and missing acks logged | Near-duplicate runs; protocol errors as their own status |
| **3 Quality gate** | per signal, per window: low quality means abstain, never attack evidence | Every check abstains on low quality, below 12 fps, or with the neck out of view | Shared gate module; `usable / abstain / protocol_error` status |
| **A Pulse coherence** | rPPG face vs neck, logged only | — | `physiology.pos` (flag off) |
| **B Sensor & stream integrity** | see family table | Mode probe, noise curve, sensor fingerprint (PRNU, PCE), frame timing, duplicate frames, claim/env/label rules | Face vs neck vs background noise and sharpness; fingerprint "hole" on the face |
| **C Active light challenge** | see family table | Random colour flash: echo delay, face-vs-neck echo (strength, with safe abstaining) | Split-screen flash, background response, noise that follows the flash, exposure/WB/torch probes |
| **D Visual & motion consistency** | see family table | — | Random head turn with identity tracking, SBI detector, boundary seams, tilt vs gyroscope (phones), optional close/far |
| **4 Evidence fusion** | quality-aware; correlated cues share one vote; interpretable evidence table first | — | Weighted evidence table; calibrated logistic fusion only with enough person-disjoint data |
| **5 Policy outcome** | PASS / RETRY / STEP-UP / HUMAN REVIEW | Provisional thresholds (`server/pulselens/calibration/bootstrap.yaml`), Lab results card with every check's status | Outcomes in code (the code still uses five older route names) |
| **Bank: evidence record** | session, challenge events, per-family results; hash-linked | Session bundle and event log on disk | Hash chain, encryption at rest |
| **Bank: agent review console** | plain reasons; failed vs abstained shown apart; human decides | Agent actions are logged (passcode); session token guards scores | Console in the Demo presenter view |
| **Bank: case / audit workflow** | escalation into the bank's process | — | Mocked for the hackathon |
| **Bank: India readiness & evaluation** | APCER / BPCER, abstention, retry rate, latency, per device / lighting / skin tone | — | `eval/` scripts and the Lab Results page |

### Three outcomes

| Outcome | When | Then |
|---|---|---|
| **PASS** | enough good-quality evidence and low estimated risk at the tested operating point | the call continues |
| **RETRY / STEP-UP** | poor capture or inconclusive evidence, or one family raises risk | a fresh challenge, the no-flash path, agent-led checks, or assisted KYC |
| **HUMAN REVIEW** | two or more reliable, distinct families raise risk, or stream integrity is violated | an agent reviews before activation |

Bank policy sets the bar: permitted actions, retention and the operating point per product (for example stricter for an instant loan than for a savings account).

### Adaptive capture: three modes

The planner measures the device first (frame rate, dropped frames, blur, light, camera controls, claims vs behaviour) and picks a mode. The mode comes from **measurements, not the device name**, it can drop mid-session (for example if the frame rate falls during the light challenge), and it is **never a risk label**. Thresholds are still calibrated per measured cohort (channel and frame-rate band, with lighting kept as metadata), but the cohort never picks the tests.

| Mode | Runs | Typical |
|---|---|---|
| **CAPABLE** | stream integrity; full colour challenge; face / neck region features; head turn; exposure / white-balance probe where supported | Chrome on Android or desktop, steady frame rate, decent light |
| **CONSTRAINED** | stream integrity; simpler, longer colour challenge if viable; head turn; unreliable optical features dropped | budget phone, old webcam, iOS Safari, tube-light flicker |
| **NO-FLASH · ASSISTED** | stream integrity; head turn; agent-led live questions; branch or correspondent route if still short | photosensitivity, bright sunlight, persons with disabilities |

Unsupported camera controls mean unsupported, never failed. Low frame rate, dim light, darker skin, no visible neck and budget devices lower confidence or trigger a retry; they are never a fraud flag on their own. The mode cut-points are provisional (they reuse the 20 fps band edge and the 12 fps floor in `config.yaml`) until device recordings set them. The planner is **not built yet**: today every device gets the camera checks and the light suite, and the light checks abstain below 12 fps.

**Closer / farther** is an optional family D challenge. As the phone (or the person, on a laptop) moves from far to near, three things change together on a real face:

- perspective: the nose grows relative to the face outline and the ears disappear;
- our flash on the face gets much stronger while the background stays the same;
- focus and sensor noise shift.

A screen or replay only scales evenly, and a pasted face has to keep pace with the real neck. FaceTec's commercial 3-D liveness uses a similar close-far motion, so this is not new as an idea; whether live swaps fail it is still to be measured.

**Why is the pulse only logged?** A live swap copies the attacker's own pulse onto the fake face (median r = 0.89 for DeepFaceLive, Fraunhofer HHI 2025), and the attacker's neck and hand are real, so pulses at every site agree. Reading a pulse also needs at least 20 fps and 10–20 s, more than many budget cameras give, and it weakens in dim light and on darker skin. Our flash does the same job better: it is a pulse we control, much stronger, with a known timing. So family A is logged and studied, outside the vote, until it adds measured value. PulseLens never stores a heart rate or a pulse waveform.

**Why prebuilt detectors only as features?** Detectors like SBI are trained on offline, compressed fakes, and their accuracy drops on unseen data (cross-dataset AUC around 0.72–0.89 in reproductions), and further on Indian webcams and faces. They also tend to fail together. SBI enters family D as one feature, scored against genuine sessions and weighted by fusion, never as the only vote. Its weights are research-only, so they need a licence before production. No faces are sent to third-party APIs.

## What changed from the original idea

The original pitch (final deck v6) was "Deepfakes fool faces. PulseLens checks the camera": three questions (real camera, live physics, same camera all call), with **the face lagging the neck** as the star test. The research and our recordings kept the frame but moved where the strength against live swaps comes from. Full reasoning: [`docs/research/deck_review.md`](docs/research/deck_review.md).

| | Original idea | What changed | Why it is better |
|---|---|---|---|
| Core claim against live swaps | The face lags the neck when the screen flashes | The face is a repainted patch of a real frame; test whether it reflects light, shows noise and shades in 3-D like the real neck | Live swaps may copy our flash in the same frame, with no lag; a repaint can't easily fake 3-D shading or sensor noise |
| Structure | 3 questions | First 4 questions; in the final deck, 2 questions answered by 4 evidence families (see below) | Each family targets a different attack, so fusing them means something |
| Face-vs-neck check | Timing (lag) | Echo strength (built), colour direction (planned), safe abstaining | One webcam frame (64–96 ms) is longer than the lag limit, so timing falsely failed genuine users |
| Split-screen flash | One of three echoes | A research item inside the light challenge | The one optical test a colour transfer can't fake (Face Flashing, Gerstner & Farid) |
| Heart rate, multi-site pulse | Stretch goal; "noise follows pulse" | Family A: optional, logged only, outside the vote | A live swap copies the attacker's real pulse (r = 0.89); our cameras are too slow to read one |
| Prebuilt AI models | Not in the plan | SBI as one feature in family D; MiniFASNet optional | They cover blending seams physics can't see, without being the sole judge |
| Challenges | Tilt and hand occlusion | Random left/right head turn with identity tracking; hand occlusion demoted; tilt optional on phones | Pose challenges scored best in the live-swap study; masks now defeat hand occlusion |
| Eye reflection | — | Screen glint in the cornea (idea, not in the final deck) | A swap regenerates the eyes, so the reflection should be lost or wrong |
| Sensor fingerprint | "Missing in generated video" | Supporting evidence only, limit 50 | Chromium's fake camera produced a stable fingerprint (PCE 97) |
| Camera checks | Planned | Built: mode probe, noise curve, fingerprint, timing, duplicates, rules, plus an exposure lock | They catch the fake camera, pass the real one, and line up with CEN/TS 18099 |
| Decisions | Rules with per-device thresholds | Thresholds learned from genuine sessions only; an interpretable evidence table first, logistic fusion only with enough data; error rates per device and skin tone | Fits our data size: few attack samples, and two-class models generalise badly to unseen attacks |
| India claims | "Built for real Indian phones" | A measured-vs-assumed list: budget phones, tube lights, skin tones, languages and live swaps are all untested | Honest, and it gives a concrete test plan |
| Per-device plan | Planner with fps-band profiles (a phone with a gyroscope gets tilt + light; a desktop gets hand + light + agent) | First six named tiers; in the final deck, three capture modes from measurements, which can drop mid-session | Weak devices get a suite they can pass instead of a wall of abstains; the mode never lowers the bar |
| Prior work | Novelty table missing the two closest papers | Gerstner & Farid 2022 and An et al. 2024 cited, with what is different | Keeps "we didn't find, not first" credible |

### Then: the final deck's framing (2026-10-22)

The intermediate README (four questions, six device tiers) was replaced by the final deck's architecture. `docs/SPEC.md` now follows it.

| Intermediate | Final deck |
|---|---|
| 4 questions: real camera, live scene, same surface as the neck, holds up under stress | 2 questions (real camera in this session? real face?) answered by 4 evidence families A–D |
| Six device tiers (good/budget phone, good/bad webcam, suspicious device, no-flash) | 3 capture modes: CAPABLE, CONSTRAINED, NO-FLASH · ASSISTED; a suspicious device keeps its measured mode and gets agent-led checks |
| Five routes: PASS, ADD_CHECKS, AGENT_CHALLENGE, ASSISTED_KYC, HOLD | 3 outcomes: PASS, RETRY / STEP-UP, HUMAN REVIEW |
| Check pass / fail / abstain | Each check also gets a gate status: usable, abstain or protocol error; a protocol violation alone sends the session to HUMAN REVIEW |
| A family fails if any check in it fails | Correlated cues share one vote; an interpretable weighted evidence table decides whether a family raises risk |
| Continuity jump → agent challenge | Continuity jump → HUMAN REVIEW (stream integrity violated) |
| Session API: the prototype's own routes | Deck proposes `POST /sessions`, `GET /challenge`, `POST /frames`, `POST /complete`, `GET /result`; the mapping to the built routes is in SPEC section 6.2 |

**Unchanged, because the research backs it:** camera first, random active light against replays, never auto-reject, abstain on weak devices, the agent in the loop, human review only when two families flag (or integrity breaks), the continuity lock, no pulse stored.

**Still to prove:** none of the swap-specific tests has been run against a real live swap yet. Whether the new framing beats the old one depends on recording Deep-Live-Cam and FaceFusion sessions first.

## Built for India, and what is not measured yet

| Indian reality | How the design handles it | Status |
|---|---|---|
| RBI V-CIP: live, agent-led, liveness, data in India | The agent always decides; self-hosted in the bank's VPC or on-prem; no third-party APIs | Principle built; agent console not built |
| Supreme Court and RBI (2025): liveness may not rely on blinking alone or exclude persons with disabilities | No blink test; a NO-FLASH · ASSISTED mode with agent-led questions and a branch route | Not built |
| DPDP Act: data minimisation, consent | No heart rate or pulse waveform stored; pseudonymous person codes | Built |
| About 95% Android, mostly budget phones | Phones get a full-screen flash; weak devices go to CONSTRAINED mode instead of failing | **No phone tested yet** |
| Dim rooms drop cameras to 10–15 fps | Light checks abstain below 12 fps; the planner moves to a mode without the colour challenge | Abstain built; modes not built; abstain rate on phones unknown |
| Wide range of skin tones | Face is compared with the neck and background of the same person, no absolute colour thresholds | **Not measured**; error rates must be reported per skin tone (Monk scale) |
| Tube lights and LEDs flicker at 50 Hz | Brightness instability lowers confidence; no claim of exact 50 Hz detection (low-fps browsers can't resolve it) | Not built |
| Browsers differ (Chrome on Android exposes exposure and white balance; Safari on iOS very little) | The preflight probes real support live; unsupported means unsupported, never failed | Probe built; per-browser use not built |
| Patchy 4G uploads | Frames uploaded as JPEG | Bandwidth not measured |
| Many languages, low literacy | English and Hindi prompts first, Punjabi next; icon-first coaching steps | Not built |
| Elderly users helped by family (two faces in frame) | Assisted KYC as a step-up | Not built in code |

**Adaptable by design**
- **New check, no rewrite.** Each check is a module registered in `server/pulselens/planner/registry.py`; adding SBI or the split flash adds a file.
- **Thresholds are configuration.** They live in `bootstrap.yaml` and will be recalibrated per measured cohort on a bank's own genuine sessions (M2.6, planned).
- **The plan adapts to the device.** The planner picks one of three capture modes from measurements (planned).
- **Fusion is inspectable, then retrainable.** An interpretable evidence table first; logistic-regression weights per deployment only with enough data, reported as APCER and BPCER (ISO/IEC 30107-3) per attack tool, device, lighting and skin tone, with injection reported separately (CEN/TS 18099) (planned).

## What we have measured

- **Fake camera (Chromium):** accepted an unusual 1000×750 mode and switched in 57–105 ms with no dropped frames. The real webcam refused that mode and passed every camera check.
- **Replay of a genuine session:** every camera check passed it (fingerprint PCE 7542); the light echo answered 0 of 6 flashes and failed. This is exactly why active light is needed.
- **Laptop webcam, bright room:** 15.6 fps, face echo near the noise floor. **Dim room:** echo 3–6× stronger but the camera fell to 10.4 fps, below the 12 fps floor, so the light checks abstained. An exposure lock (when fps < 27, 33 ms exposure) was added and is not yet confirmed on re-recordings.
- **Sensor fingerprint:** genuine sessions as low as PCE 174; Chromium's fake camera produced a stable pattern at PCE 97. The fingerprint is supporting evidence, not proof of a sensor; the limit is 50.
- **Tests:** 444 pytest passed (1 skipped), 131 web tests, lint clean, e2e in headed Brave.

Details and every threshold decision: `docs/STATUS.md`. Research:
- [`docs/research/pulse_and_illumination.md`](docs/research/pulse_and_illumination.md): multi-site pulse, screen illumination, rules vs learning
- [`docs/research/live_swaps_and_detectors.md`](docs/research/live_swaps_and_detectors.md): what a live swap can't fake, prebuilt detectors, active probes, ranked ideas
- [`docs/research/deck_review.md`](docs/research/deck_review.md): the v6 deck and doc checked against the research and our measurements

## Next experiments, in order

1. **Record live-swap sessions** with Deep-Live-Cam and FaceFusion on a consenting teammate, using the tools as-is through the Lab Record page (a human does this; the repo never contains attack tooling).
2. **Face vs neck vs background noise and sharpness** (family B), offline, on existing and new sessions.
3. **Random head turn with identity tracking, and SBI as a feature** (family D).
4. **Split-screen flash** in capture and a check for it (family C, research).
5. **Indian conditions:** 2–3 budget Android phones, a tube-light room, volunteers across skin tones.
6. **Capture modes, quality gate and fusion**, evaluated person-disjoint, with APCER and BPCER per device, lighting and skin tone, abstention and retry rate, and each family alone vs fused.

## Run it

Needs Python 3.11, Node 22.12+, and `make` (or `python scripts/dev.py <target>` without it).

```bash
make setup       # venv, npm ci, .env from .env.example, model files
make server      # API on :8000
make lab         # Lab site on :5173
make demo        # Demo site on :5174
make tunnel      # HTTPS tunnels for testing on phones
make test        # pytest
make test-web    # tsc + vitest
make e2e-brave   # Playwright in the installed Brave, headed
make lint
python -m pulselens.cli analyze data/sessions/<id> --plots
```

## Repo map

| Path | What |
|---|---|
| `apps/lab` | Experiments site: device details, Record, results |
| `apps/demo` | Judges' site: customer view and presenter view (the agent console prototype) |
| `packages/capture` | Framework-free browser capture (the Capture SDK): probe, exposure lock, flashes, frame upload |
| `packages/explain`, `packages/types`, `packages/ui` | On-screen explanations, generated types, shared components |
| `server/pulselens/checks` | One module per check; each maps to a family A–D (SPEC section 9.0) |
| `server/pulselens/vision` | Noise, PRNU, face regions, frame tools |
| `server/pulselens/api` | FastAPI REST and WebSocket |
| `docs` | `SPEC.md`, `BUILD_PLAN.md`, `STATUS.md`, `EXPLAINERS.md`, research notes |

## Privacy and ethics

- No heart rate, pulse waveform, secrets or volunteer data in git; session data lives in the gitignored `data/`.
- The applicant never sees a score: only "please retry" or an assisted route.
- Tests use synthetic fixtures only, with no real faces.
- The code detects; it never generates, improves or disguises deepfakes. Attack sessions are recorded by a person with existing tools, only on consenting teammates.

## Sources

Gerstner & Farid, CVPR-W 2022 (active illumination against real-time deepfakes); An et al., IET Biometrics 2024 (face-vs-neck rPPG); Seibold et al., Frontiers in Imaging 2025 (deepfakes inherit the driver's pulse); Tang et al., NDSS 2018 (Face Flashing); Shiohara & Yamasaki, CVPR 2022 (SBI); Firc et al., "Not All Challenges Are Equal", arXiv 2610.16417; Nowara et al., CVPRW 2020 (skin tone and camera-based PPG); corneal reflection probing, arXiv 2210.14153; SFake, arXiv 2409.10889; CEN/TS 18099:2024; ISO/IEC 30107-3:2023; W3C Image Capture implementation status. Full lists with links in the research notes above and in the final deck's references.
