# Review: final deck (v6) and design doc against the research and our measurements

2026-10-21. This reviews `PulseLens_Final_Deck_v6.pptx` (23 slides) and `finaldoc.pdf` (13 pages), which are kept outside the repo, against:

- research notes `pulse_and_illumination.md` and `live_swaps_and_detectors.md`;
- what we measured on our own sessions (`docs/STATUS.md`).

It lists what still holds and what should change. It changes nothing in the deck itself.

## Bottom line

The frame is sound:

- camera first;
- active pulses;
- continuity;
- per-family false-alarm budgets;
- the agent decides;
- never auto-reject.

It is also written honestly: "hypotheses until measured", "we didn't find, not first". The weak point is that **the headline claim against live face swaps rests on the face lagging the neck**, which the literature suggests may not happen, and the console mock-up and demo are built around it.

## What holds up

| Claim | Where | Evidence |
|---|---|---|
| Camera-first catches virtual cameras and emulators | Slides 5, 7 | Chromium's fake camera accepted 1000×750 and switched in 57–105 ms with no dropped frames; the real webcam refused and passed every camera check. Maps onto CEN/TS 18099 injection-attack testing. |
| Active light defeats replays | Demo #5 | Replay of a genuine session: every camera check passed it (PCE 7542); the light echo answered 0 of 6 and failed. |
| Physiology is a stretch goal; good deepfakes can inherit the driver's pulse | Doc, Stage 5 | Fraunhofer HHI 2025: DeepFaceLive face pulse vs driver pulse, median r = 0.89. |
| False-alarm budget per family | Slide 11 | 1 − 0.975⁸ ≈ 18%, so "about 1 in 5" is right. |
| Abstain, don't fail, on weak devices | Slides 11, 18 | Built: the light checks abstain below 12 fps. |

## What the research and our recordings undercut

1. **"The face lags the neck" (slide 9 notes, "the part we're most excited about"; slide 12 console "face lagged the neck on 7 of 8"; demo #3).**
   - Gerstner & Farid note that DeepFaceLive does a colour transfer from the driver's lighting, so the fake face may carry our flash.
   - Live swaps inherit even the heartbeat colour change.
   - A Deep-Live-Cam frame is processed whole in under about 50 ms, so the face and neck reach the camera output together.
   - So a live swap may answer the flash in the same frame, with no lag.
   - Slide 9's caveat ("a tool that relights the face perfectly in the same frame would pass this echo") is honest. The console and demo, however, present the lag as the expected result.
   - **Change:** lead with echo *strength and colour* vs the neck, and with the split-screen 3-D test; show lag only if recordings show it.
2. **"The face-vs-neck echo cancels device delay" (slide 5).** True as physics, but on our webcam one frame is 64–96 ms, larger than the ±60 ms lag limit. We now compare echo strength and abstain below 12 fps.
3. **Threat table, live face-swap row (slide 17).**
   - Camera gets ● only because the demo routes the swap through a virtual camera, so the camera checks catch the injection path, not the swap.
   - With a capture card or a hooked phone, only face content and continuity are left.
   - **Change:** mark this explicitly; the split-screen pulse is the one optical test a colour transfer can't fake, and it is not built yet.
4. **"Missing in generated video" for the sensor fingerprint (slide 7).** Chromium's fake camera produced a stable pattern at PCE 97; the browser pipeline itself can leave a fixed pattern. **Change:** "supports, does not prove, a real sensor".
5. **"None of these depends on recognising a particular face-swap tool" (slide 4).** True for camera checks. The optical echoes depend on the tool *not* relighting correctly. Add one hedging sentence.
6. **Indian conditions (slide 18): "budget phones and old webcams: 15 to 24 fps"; "in a dim room the screen pulse is relatively stronger".** Our laptop webcam measured both sides of the trade-off:

   | Room | Face echo | Camera fps | Result |
   |---|---|---|---|
   | Bright | at the noise floor (SNR 5) | 15.6 | weak echo |
   | Dim | 3–6× stronger (SNR 15–30) | 10.4 | below the 12 fps floor, so the light checks abstain |

   An exposure lock was added and is not yet confirmed. Today many desktop users would go to an agent challenge. That is acceptable under the routing, but slide 11 should say so.
7. **Slide 18's handling column** (no-flash option, prompts in the customer's language, gesture animations, per-profile thresholds) is design, not code yet.
8. **"Built in 48 hours" (slide 15).** Does not match the code.
   - **Built:** capture, the mode probe, exposure lock, 8 camera checks, the light echo, face vs neck (on echo strength, with safe abstaining), and the Lab results card.
   - **Not built:** split-screen, tilt, hand and head turn, noise-follows-pulse, continuity lock, planner and fusion, agent console, Demo site, fixed-vs-adaptive evaluation.
9. **Gate G2 ("is a swap separable on the same laptop?")** is the crux, and there is no live-swap recording yet. Every optical claim against swaps is untested.

## Missing prior work (novelty table, slide 16)

- **Gerstner & Farid, CVPR-W 2022**, "Detecting Real-Time Deep-Fake Videos Using Active Illumination": screen-colour challenge against real-time deepfakes, with correlation falling with delay and screen size. Closest prior art to the light suite.
- **An et al., IET Biometrics 2024**: face-vs-neck rPPG against deepfakes (AUC 0.91–0.997 on offline fakes). The "face-vs-neck echo" row should cite it and say what is different: active light, not pulse; live, not offline.
- **Corneal reflection probing (arXiv 2210.14153)** and **SFake (vibration, arXiv 2409.10889)**: other active probes against real-time deepfakes.
- **"Not All Challenges Are Equal" (arXiv 2610.16417)**: pose challenges are best against DeepFaceLive and FaceFusion; occlusion is defeated by masks. This bears on the occlusion row (GOTCHA).

## Suggested reframe

- **Lead with what is proven:** camera-first injection detection (CEN/TS 18099) plus active light that defeats replays.
- **Make the live-swap story the 3-D, same-surface question:** "a live deepfake repaints one patch of a real frame; we check whether that patch obeys the same light, noise and geometry as the skin around it". Split flash, face-vs-neck echo strength and colour, and face-vs-neck noise go here.
- **Add "holds up under stress"** (profile turn identity, prebuilt seam detectors as features, Android vibration), scored by fusion.
- **Say plainly** that desktop webcams lean on the camera family plus an agent challenge.
- **Replace "7 of 8 lag"** in the console mock-up and demo #3 with whatever the live-swap recordings actually show.
- **Record Deep-Live-Cam early:** it decides whether optical earns a ● for live swaps.
