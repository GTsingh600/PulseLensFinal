# Status

Ticked = acceptance checks in `docs/BUILD_PLAN.md` pass. Newest notes first in each section.

## Progress

### M1: Engine skeleton, capture, light echo (H0–6)
- [x] **M1.1 [all] Monorepo scaffold** — `make setup`, `make test` (8 passed), `make test-web` (tsc + vitest, 6 workspaces), `make lint` and `make e2e` (3 passed: Lab :5173, Demo :5174, `/api/health` 200 direct and through both proxies). 2026-10-21.
- [ ] M1.2 [C] Server core
- [ ] M1.3 [C] Explainer package — build step done by track A (`make explainers`, typed keys, staleness test); **key-coverage test still open for C**.
- [x] **M1.4 [A] Capture core** — vitest: 39 tests in `packages/capture` (colours within ±5% luminance, ≤ 3 flashes/s, channel detection, uploader, pulse timing, coaching). `make e2e` (Chromium fake camera, mock server): details posted, 371 frames with strictly increasing t (captureTime clock), fingerprint frame on every 5th, 10 pulse acks in order. Runs against `e2e/support/mock-server.ts` until M1.2 lands. 2026-10-21.
- [ ] M1.5 [B] Vision base, light echo and face-vs-neck
- [ ] M1.6 [A] First Lab page: Record (minimal)
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
- **Push to GitHub.** The local repo has the M1.1 commit on `main`; `https://github.com/GTsingh600/PulseLensFinal` is still empty. Review, then: `git remote add origin https://github.com/GTsingh600/PulseLensFinal.git` and `git push -u origin main`. Then each teammate: `git clone`, `make setup`, `git worktree add ../pl-trackA -b trackA` (B, C likewise).
- **Assign track owners** (A, B, C) in `docs/BUILD_PLAN.md` section 1.
- **`.env` secrets.** `make setup` copied `.env.example` to `.env` with `change-me` values; the server logs a warning until they are replaced. Generate a secret with `python -c "import secrets; print(secrets.token_hex(32))"`.
- **`docs/consent_form.md` is missing.** BUILD_PLAN section 5 needs it signed by every volunteer; write it (no personal data in git) and print 20 copies.
- **cloudflared** is not installed on this laptop; `make tunnel` needs it for phones (HTTPS for camera and motion sensors).
- **Heavy models.** `python scripts/fetch_models.py --heavy` downloads buffalo_l (~280 MB) and CLIP ViT-B-32 (~600 MB); run it once on good Wi-Fi before H6. MediaPipe face, hand and BlazeFace files are already fetched by `make setup`.
- **Node 22.12+ and Python 3.11** on every teammate's laptop (vitest 5 needs Node 22.12+). With `uv` installed, `make setup` downloads Python 3.11 itself.

## Decisions
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
