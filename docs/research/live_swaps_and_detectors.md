# Research note 2: live face swaps, prebuilt detectors and active probes

2026-10-21. Follows `pulse_and_illumination.md` (part 1). Part 1 asked whether a multi-site pulse beats our flash; this part asks what a **live** face swap cannot fake, whether prebuilt detectors help, and which new challenges are worth building. Sources are web pages and abstracts unless marked (full). Nothing here is measured on our own data yet.

## How a live swap is built, and why it matters

Deep-Live-Cam (the tool in our attack protocol) runs, per frame:

1. Detect the face in the attacker's **real** camera frame.
2. Swap it with `inswapper`, which works on a **128×128** face crop.
3. Optionally enhance it with GFPGAN.
4. Paste and blend it back; v2.7 claims Poisson blending plus feathering and fewer edge artifacts.
5. Output through a virtual camera.

Everything outside the face mask stays real: neck, hair, background, sensor noise, and the light our screen throws on the room. So the most useful question is not "is this frame AI?" but **"does the face patch obey the same physics as the real skin around it?"**. This reframes PulseLens as four questions (README):

1. Real camera?
2. Live scene?
3. Same surface as the neck?
4. Holds up under stress?

## Evidence

| Source | What it says | What it means for us |
|---|---|---|
| Metaphysic.ai (2022), with Siwei Lyu quoted | DeepFaceLive swaps break when the face turns about 90°. 2-D face-alignment networks give only 50–60% of the frontal landmarks on a profile. | A profile turn is a cheap, strong challenge. |
| Deep-Live-Cam docs and user reports | inswapper is trained on millions of faces, so it handles angles better than per-person DeepFaceLive models. Fast head motion, extreme angles and extreme mouth shapes still glitch. | The turn still helps, less than against DFL. Score identity stability through the turn, not only visible glitches. |
| Reality Defender CEO (2025), via Yahoo Tech | Current models have "fixed" the hand-over-face (three-finger) test. | Matches part 1 (FaceFusion occlusion masks). Hand occlusion is weak; keep it cheap or drop it. |
| Microsoft Digital Defense Report 2025 (as quoted) | Modern deepfakes defeat selfie checks and liveness tests that simulate blinks and head turns. | No single challenge is enough. Supports fusion across families. |
| Shiohara & Yamasaki, CVPR 2022 (SBI) | A detector trained only on self-blended real images (no real deepfakes): 93.18% AUC on Celeb-DF; beats baselines on DFDC/DFDCP by 4.9 and 11.8 points. | Blending seams are what a paste-back leaves. SBI is the best-generalising prebuilt candidate. |
| SBI re-run under the DeepfakeBench FF++ c23 protocol (ACM 2025) | Video AUC 0.886 CDF-v2, 0.827 DFD, 0.717 DFDC, 0.848 DFDCP (mean 0.82). | Expect well below the paper on webcams and Indian faces. Use it as a calibrated feature, never alone. |
| DeepfakeBench (NeurIPS 2023 D&B) | Pretrained weights for many detectors on FF++ c23. Preprocessing changes results a lot (Xception CDF-v2 0.52 → 0.74). | Easy source of weights. Our own face crop and preprocessing must match theirs, or the numbers mean nothing. |
| "Deepfake noise investigation and detection" (2022) | Compare noise traces of the face square with a far background square; a swapped face differs. | Supports a face-vs-neck/background noise check. We already have `vision/noise.py` and `vision/prnu.py`. |
| Region-aware watermarking study (PMC) | Some generators change background statistics too; segmentation-weighted tools keep the background cleaner. | Deep-Live-Cam pastes onto a mask, so the neck and background should stay clean. Verify on recordings. |
| "Camera-noise residuals for face-swap detection: redundant, not complementary" (arXiv 2610.11683) | On FF++, noise residuals add nothing over an RGB detector. The signal is in the face region's residual mean and variance, not in the seam. | Noise is not a new signal *for a learned detector*. For us it is a cheap, explainable physics check that needs no training. Don't expect it to add much on top of SBI. |
| Corneal reflection probing (arXiv 2210.14153) | Show a pattern on screen and check its reflection in the caller's corneas. No special hardware. | A swap that regenerates the eyes should lose or misplace the glint. At 720p and 50 cm the iris is about 20 px, so this works best close up on phones. |
| SFake (arXiv 2409.10889) | Make the phone vibrate and check whether the face follows the induced shake. Self-built real-time dataset; beats six baselines. | Android browsers expose `navigator.vibrate`; iPhone Safari does not. About 95% of Indian phones are Android. |
| "The Deepfakes We Missed" (arXiv 2605.12075, position paper) | Detection research targeted public-figure face swaps. The harms that arrived are voice-clone scam calls, NCII and fraud. | Fair reminder: KYC deepfakes are one threat among many. Camera-injection checks (CEN/TS 18099) cover the most common real-world KYC attack path. |

## On the multi-site pulse idea ("real sites agree, AI is random")

- **True for pre-made fakes.** The fake face carries a different person's pulse; An et al. separate them with AUC 0.91–0.997 (part 1). But a pre-made video also cannot answer a random flash: it already failed 0 of 6 echoes in our replay test.
- **False for live swaps.** The fake face inherits the attacker's own pulse (r = 0.89), and the attacker's neck and hand are real, so all sites agree.
- **What might still differ** is pulse *quality* (Fraunhofer: about 1.4 dB lower SNR) after a 128-px repaint.
- **Our flash is a stronger version of the same test.** It is a pulse we control: much stronger than the heartbeat colour change, with a known time, and usable at 12 fps (pulse needs ≥ 20 fps and 10–20 s).
- **Conclusion:** measure pulse agreement in the Lab only; put the effort into face-vs-neck flash gain and colour.

## On ensembling prebuilt detectors

- **They help where physics can't:** blending seams and repaint texture (SBI), screens and prints held up to the camera (MiniFASNet).
- **Averaging similar detectors adds little,** because they look for the same seams and fail together. The gain comes from combining them with independent families (camera, light).
- **They are trained mostly on Western celebrity and YouTube faces.** Check false-alarm rates on Indian genuine sessions before trusting them.
- **Licences:** many weights are research-only. Fine for a hackathon prototype; state it.
- **No commercial detection APIs.** Sending KYC faces to a third party conflicts with DPDP data minimisation and RBI's data-in-India rule.

## Ranked ideas

| # | Idea | Why a live swap struggles | Cost | Main risk |
|---|---|---|---|---|
| 1 | Face vs neck noise and sharpness | A 128-px face upscaled is too clean and soft next to real neck skin at the same brightness | Hours, offline, reuses `noise.py` | Phone beauty filters smooth faces; GFPGAN adds fake detail; may be redundant with SBI |
| 2 | Split-screen flash: the two cheeks lit differently | Real face is 3-D; a colour transfer applies one change to the whole face | Half a day (capture + check) | Weak with the desktop border flash |
| 3 | Prebuilt detectors as features (SBI, MiniFASNet) | Seams and repaint texture | About a day on CPU | Cross-dataset drop; demographic bias; licences |
| 4 | Identity through a profile turn (OpenCV SFace, Apache-2.0) | Alignment fails past about 60°; the swap glitches or the attacker's identity leaks | Half a day | inswapper copes with angles better than DFL |
| 5 | Screen glint in the cornea | Eyes are regenerated, so the reflection is lost or wrong | 1 day, uncertain | Resolution; glasses |
| 6 | Phone vibration (Android) | The face is re-detected and re-pasted each frame, so it may jitter or stay sharp while the real frame blurs | Half a day | No iOS support |
| 7 | Hand over the face | — | Cheap | Already defeated by occlusion masks |
| 8 | Pulse agreement across sites | Weak for live swaps (inherited pulse) | Lab only | Low fps; darker skin in dim light |

Ideas 1, 3 and 4 need no capture change and can run on existing genuine sessions now.

## What has to be recorded before any of this is trusted

- **Live swaps:** Deep-Live-Cam sessions on a consenting teammate, through the Lab, with the tool used as-is (CLAUDE.md rule 7: no attack tooling in the repo).
- **Genuine sessions:** more people, 2–3 budget Android phones, a tube-light room, a range of skin tones (Monk scale).
- **Reporting:** APCER per attack tool and BPCER per device and skin tone, person-disjoint (ISO/IEC 30107-3).

## Sources

- Metaphysic.ai, "To uncover a deepfake video call, ask the caller to turn sideways" (2022): https://blog.metaphysic.ai/to-uncover-a-deepfake-video-call-ask-the-caller-to-turn-sideways/
- Deep-Live-Cam releases: https://github.com/hacksider/Deep-Live-Cam/releases
- "That viral three-finger deepfake test? Experts say it's already dead": https://tech.yahoo.com/cybersecurity/articles/viral-three-finger-deepfake-test-152126737.html
- Shiohara & Yamasaki, "Detecting Deepfakes with Self-Blended Images", CVPR 2022: https://arxiv.org/abs/2204.08376
- DeepfakeBench: https://github.com/SCLBD/DeepfakeBench
- Hybrid generalizable detector with SBI reproduction (ACM 2025): https://dl.acm.org/doi/10.1145/3709020.3734833
- "Camera-Noise Residuals for Face-Swap Detection: Redundant, Not Complementary, and Why": https://arxiv.org/html/2610.11683
- "Deepfake noise investigation and detection" (2022): https://www.sciencedirect.com/science/article/pii/S2666281722000762
- Region-aware face-swap and watermarking study: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12526903/
- "Detection of Real-time DeepFakes in Video Conferencing with Active Probing and Corneal Reflection": https://arxiv.org/abs/2210.14153
- SFake, "Shaking the Fake": https://arxiv.org/abs/2409.10889
- "The Deepfakes We Missed": https://arxiv.org/abs/2605.12075
