# Research note: multi-site pulse, screen illumination, and rules vs learning

2026-10-21. Written before any change to the decision approach, at the user's request. Papers read in full are marked
(full); the rest from abstracts and summaries. PDFs are kept outside the repo.

## Question

Would asking the person to raise a hand, and measuring the pulse at about 5 face points, 2 neck points and 6 hand
points, be a better liveness signal than what PulseLens does now? And should the decisions stay rule-based, or be
learned?

## What the papers say

| Paper | What they did | Numbers | What it means for us |
|---|---|---|---|
| An et al., IET Biometrics 2024 (full) | rPPG (CHROM, 9 s, 30 fps) on 5 face ROIs vs an 80 px neck box; Euclidean distance after shifting the neck signal up to 1 s; SVM | AUC 0.912 audio-driven, 0.997 FSGAN (KoDF); 0.978 Celeb-DF | Face vs untouched skin works **on offline fakes**, where the fake face carries another person's pulse. Best shifts were 10–18 frames (330–600 ms), far above real face–neck transit (~10 ms), so it matches waveform shape, not physiology. 8:2 split, not person-disjoint. |
| Seibold et al. (Fraunhofer HHI), Frontiers in Imaging 2025 (full summary) | rPPG (POS, 10 s, 25 fps) in genuine videos and face swaps incl. DeepFaceLive (real-time) | DFL deepfake HR vs **driver** HR: median r = 0.89; SNR −1.97 dB genuine vs −3.35 dB fake; HR error 1.80 vs 3.24 bpm | **A live face swap inherits the attacker's real pulse.** In live KYC the driver is the person in front of the camera, so face, neck and hand pulses can all agree. Presence or agreement of a pulse is not evidence against a live swap; only degraded quality or spatial structure might be (they report AUC 0.874 with local blood-flow maps + a CNN). |
| Niu et al., CVPR-W 2023 (full summary) | Full-body rPPG, 90 fps 1080p industrial camera, palm held up 90 s | MAE (POS) face 1.38 bpm, palm 3.88; largest site-to-site transit ≤ 51 ms | The palm is the best non-face site, but even at 90 fps body transit differences are ≤ 51 ms: **below one frame** of a 15–30 fps webcam. Face-to-palm transit time is not measurable on our cameras. |
| Gerstner & Farid, CVPR-W 2022 (full) | Isoluminant hue cycle on screen (yellow–magenta, chosen not to trigger auto white balance), correlate face hue with screen hue | Real 0.93 (13 in light) falling to 0.33 (3 in); no-illumination stand-in 0.09; with 1–4 frames of delay: 0.83, 0.65, 0.37, 0.03 | Closest prior art to our light suite. They note **DeepFaceLive does a colour transfer from the creator's lighting**, so a live swap may carry our flash; then only **delay** or **spatial structure** separates it. They never tested a real swap. Correlation over a continuous pattern, not threshold onsets. |
| Choi et al., CVPR-W 2024 (full) | Learned (ViT + StyleGAN) prediction of monitor content from the face, personalised, 30 min of video per user | ~70% accuracy vs 58% baseline; relighting tools cut it ~15% | A learned model of screen light on faces, with plenty of per-user data, is weak. No real deepfake tool tested. |
| Tang et al., Face Flashing, NDSS 2018 (full, method) | Random colour flashes; timing from the rolling-shutter position of a lit belt (linear regression), shape from ratio images (small CNN) | — | Timing proof needs trusted front-end hardware (known screen refresh and camera row timing), which a browser cannot give. The **shape** idea (ratio of reflected light across the face shows 3-D geometry; a screen or a colour transfer is flat) carries over: it is what `optical.split` measures. |
| Liu et al., LiveScreen, INFOCOM 2020 | Inconspicuous screen challenge frames, chromatic eigenspace features, **anomaly detection** | 94.8% laptop, 97.7% phone, false detection 1–1.6% | Threat was playback through a virtual camera, not live swaps. Decision by anomaly detection (one-class), not a two-class net. |
| "Not All Challenges Are Equal", arXiv 2610.16417 | 108 live sessions, DeepFaceLive and FaceFusion (with occlusion mask) through a virtual camera; randomized gestures | Pose AUC 0.927/0.943 (+0.08 over hold-still); occlusion **hurt** vs FaceFusion (0.840 vs 0.910); session APCER 2.8%, BPCER 11.1% | Real-time swaps are tested here. Head pose challenges help most; hand occlusion is defeated by tools that mask occluders. |
| Gotcha, arXiv 2210.06186 | 47 people, LIA/FSGAN/DFL, 8 challenges | Automated effectiveness: hand occlusion 91.4%, flash illumination 49.1%, head movement 26.5% | Older pipelines without occlusion masks fail on hands; flash alone was weak in their (non-differential) scoring. |
| Rules vs learning: CVPR 2024 one-class FAS; SLIP 2025; Morrison 2021 (logistic-regression fusion); NISTIR 7346 | — | Two-class FAS on unseen attacks: AUC ~0.56–0.72 | With few attack samples, one-class models of genuine data plus logistic-regression fusion (N+1 weights, calibrated likelihood ratios) are the standard; deep two-class models generalise badly. |

## What this means for PulseLens

1. **The face–neck–hand pulse idea is aimed at the wrong attack.** It is strong against offline or pre-made fakes, whose
   face pulse belongs to someone else. Against the live face swap (our `live-swap` scenario) the face inherits the
   attacker's pulse (r = 0.89 for DeepFaceLive), and the attacker's neck and hand are real, so all sites can agree.
   What may still differ is the face signal's **quality** (SNR drops ~1.4 dB) and its **spatial map** across the face.
2. **Transit time between face, neck and hand is not measurable on our cameras.** ≤ 51 ms across the whole body at
   90 fps; our webcams run 10–31 fps (33–100 ms per frame). rPPG itself wants ≥ 20 fps and 8–20 s windows.
3. **Our flash check has the same weakness.** A swap with colour transfer (DeepFaceLive) may reproduce the flash on the
   face with no lag. Two things a colour transfer cannot do, and that we already planned:
   - **Spatial structure** (`optical.split`): a left/right split flash lights the two cheeks differently because the
     face is 3-D; a global colour transfer applies one change to the whole face. This is Face Flashing's "shape" and
     Gerstner & Farid's suggested next step.
   - **Untouched-skin reference** (`optical.face_neck` amplitude and colour direction, and the background): the neck
     and background echo the true flash; the transferred face echo is a statistical copy and should differ in gain
     and hue direction more than lag.
4. **The face-vs-neck lag limit (±60 ms) is untested against a real swap** and the literature suggests lag may not
   appear. It needs live-swap recordings before it is trusted.
5. **Raised hand is more useful as a challenge than as a pulse site,** and even then tools with occluder masks
   (FaceFusion xseg) defeat hand occlusion. Head-pose challenges were the most effective in the one live-swap study.

## Rules vs learning

- Two-class deep models trained on few attack types fail on unseen ones; a learned illumination model with 30 minutes
  of data per person reached ~70%. Our data: 6 genuine sessions, one person, one webcam, no attacks.
- The fit for this data size is what SPEC §10 already describes, with one change of emphasis: physics features →
  **one-class calibration on genuine sessions** (robust z per profile) → **logistic-regression fusion** once attacks
  exist, calibrated to likelihood ratios and reported as APCER per attack tool and BPCER (ISO/IEC 30107-3), with
  injection-attack testing in the sense of CEN/TS 18099.
- Learned components belong where physics has no clean rule: Face Flashing's shape CNN and Fraunhofer's blood-flow map
  CNN are examples, and both need data we do not have yet.

## Recommendation

1. Do not build the 13-point pulse map as a detector now. If built, it is a **Lab measurement only**: forehead, both
   cheeks, neck, palm; coherence, phase and SNR; no BPM or waveform stored (CLAUDE.md rule 6); 15–20 s at ≥ 20 fps.
2. Build **`optical.split`** next: it is the one optical feature the literature says a colour-transfer swap cannot fake.
3. Extend `optical.face_neck` from lag to **gain ratio and colour direction** of the face echo vs neck and background.
4. **Record before modelling:** genuine (several people, devices, rooms; Chrome) and live swaps (DeepFaceLive or
   Deep-Live-Cam through OBS on a consenting teammate), per the attack protocol in STATUS. Without live-swap recordings
   none of the above can be validated.
5. Then calibration (M2.6) and logistic-regression fusion, evaluated person-disjoint with APCER/BPCER.

## Open questions to measure, not assume

- Does Deep-Live-Cam (inswapper + colour correction) transfer our isoluminant flash onto the face? With what gain, hue
  error and lag?
- Does a split flash produce a cheek difference on a live swap?
- How much does face rPPG SNR drop under Deep-Live-Cam compared with the neck, at 30 fps?

## Sources

- An et al. 2024, IET Biometrics, doi:10.1049/bme2/7095412
- Seibold et al. 2025, Frontiers in Imaging, doi:10.3389/fimag.2025.1504551
- Niu et al. 2023, CVPR-W, arXiv:2303.09638
- Gerstner & Farid 2022, CVPR-W, "Detecting Real-Time Deep-Fake Videos Using Active Illumination"
- Choi et al. 2024, CVPR-W, "Building Secure and Engaging Video Communication by Using Monitor Illumination"
- Tang et al. 2018, NDSS, arXiv:1801.01949
- Liu et al. 2020, INFOCOM, LiveScreen
- "Not All Challenges Are Equal", arXiv:2610.16417; Gotcha, arXiv:2210.06186
- Huang et al. CVPR 2024 (one-class FAS); SLIP arXiv:2503.19982; Morrison arXiv:2104.08846; NISTIR 7346
- CEN/TS 18099:2024; ISO/IEC 30107-3
