# PulseLens: notes for Claude Code

PulseLens is a camera-first liveness layer for video-KYC (RBI V-CIP). It works in three steps:

1. It proves the video comes from a **real camera**: mode-switch probe, sensor noise curve, sensor fingerprint, frame timing.
2. It makes the face answer **live pulses**: colour and split-screen light, tilt and hand. It scores their **echoes**: delay band, face-vs-neck echo, 3D split, noise that follows the pulse.
3. It keeps the **same face and camera locked** for the whole call (continuity).

A planner picks checks per device. Checks are fused by evidence family. A person (the V-CIP agent) makes the final call.

This repo is the 48-hour prototype for the Amazon AI Cyber Security Hackathon finale (Challenge 03, team Mama Mia). It ships **two websites on one engine**:

- **Lab** (`apps/lab`): the experiments site. It runs on Android Chrome, iPhone Safari and laptops. It records labelled sessions, shows every raw measurement with an explanation, and hosts the experimental results dashboard.
- **Demo** (`apps/demo`): the judges' site. A phone or laptop acts as the customer. A big-screen presenter view explains every step live: camera details, which tests were chosen and why, each result in plain words, the echo charts, continuity and the decision.

The final customer-facing product site is **out of scope**.

Read these before writing code:
- `docs/SPEC.md`: what to build, exact shapes, algorithms, both sites
- `docs/EXPLAINERS.md`: the on-screen explanation text for every stage and test (use it word for word)
- `docs/BUILD_PLAN.md`: order of work, acceptance checks, gates
- `docs/STATUS.md`: progress, blockers, what needs a human

## Commands

| What | Command |
|---|---|
| Setup | `make setup` (Python 3.11 venv + server deps, `npm ci` at the root for all workspaces, `.env` from `.env.example`, `python scripts/fetch_models.py`). Needs Node 22.12+; uses `uv` when installed |
| Without make | `python scripts/dev.py <target>` runs the same recipe (every Makefile target lives in `scripts/dev.py`) |
| Server | `make server` (uvicorn `pulselens.api.main:app` on :8000) |
| Lab site | `make lab` (Vite on :5173, proxies `/api` and `/ws`) |
| Demo site | `make demo` (Vite on :5174, proxies `/api` and `/ws`) |
| HTTPS for phones | `make tunnel` (cloudflared quick tunnels for :5173 and :5174) |
| Tests | `make test` (pytest), `make test-web` (tsc + vitest for every workspace) |
| End-to-end | `make e2e` (Playwright, Chromium with a fake camera, both sites) |
| Lint | `make lint` (ruff, eslint) |
| TS types | `make types` regenerates `packages/types/src/models.gen.ts` (from `server/pulselens/models.py`) and `config.gen.ts` (from `config.yaml`); commit both |
| Explainers | `make explainers` regenerates `packages/explain/src/explainers.gen.ts` from `docs/EXPLAINERS.md`; a vitest fails while it is stale |
| Analyse a session | `python -m pulselens.cli analyze data/sessions/<id> --plots` |
| Evaluation | `python -m eval.run --split eval/splits.json --out eval/out` |

## Rules that always apply

1. **One clock.** Every client timestamp is `performance.now()` in ms, or a frame time in that same domain (`requestVideoFrameCallback` metadata). Never use `Date.now()` in echo maths.
2. **Checks never throw on bad input.** They return a `CheckResult` with `status: "abstain"`, a quality value and a reason. Abstaining is never a failure.
3. **Thresholds come only from genuine sessions in tuning set A.** Never read set B results until `eval/FROZEN` exists; the code enforces this. Development, gates and debugging use set A only.
4. **No invented numbers on screen.** Every number shown on either site comes from a real session, or carries a visible label: `EXAMPLE`, `SYNTHETIC`, `ILLUSTRATIVE` or `PROVISIONAL THRESHOLDS`.
5. **Explain everything.** Every stage, test card, chart and dashboard widget on both sites has an explainer from `docs/EXPLAINERS.md` (via `packages/explain`). Don't ship a widget without its explanation.
6. **Privacy.** Never store heart rate or a pulse waveform. Person codes are pseudonymous (`P01`). Demo sessions are deleted after 1 hour unless the person ticks "keep for evidence". Volunteer data is deleted with `scripts/purge_volunteers.py` after the event.
7. **Attack tooling is out of scope for code.** A human records attack sessions with existing tools (OBS, Deep-Live-Cam, LivePortrait, Android Emulator), only on consenting teammates. Never write code that generates, improves or disguises deepfakes, or that helps evade detection. Detectors, fixtures, labelling and evaluation are in scope.
8. **No secrets or personal data in git.** No real public figures and no real bank data. `.env` holds `PULSE_HMAC_SECRET`, `CONSOLE_PASSCODE` and `TEAM_CODES`.
9. **When a step needs a real phone, a person, a GPU or a decision,** stop. Write exact steps under "Needs a human" in `docs/STATUS.md`, then continue with the next independent task.
10. **A task is done when its acceptance checks in `docs/BUILD_PLAN.md` pass.** Then tick it in `docs/STATUS.md` and commit (`M2.3 noise curve check`). If you change an interface, update `docs/SPEC.md` in the same commit.

## Code conventions

- **Server:** Python 3.11, type hints, pydantic v2. `server/pulselens/models.py` is the source of truth for JSON, mirrored in `packages/types` by `make types` (a pytest fails while the mirror is stale). Analysis code is pure (numpy in, dataclasses out); I/O lives only in `store.py`, `cli.py` and `api/`.
- **Checks:** each check module exposes `run(ctx) -> list[CheckResult]` and registers in `planner/registry.py` with its family, unit, explainer key and plot type.
- **Web:** TypeScript monorepo (npm workspaces).
  - `packages/capture` is framework-free.
  - Both apps use React + Vite, with shared components in `packages/ui`.
  - Live charts use uPlot; static matrices are small SVG components.
- **Tests:** synthetic fixtures (`server/tests/fixtures/synth.py`); no network and no real faces in tests.
- **Mobile first:** every screen must work at 360 px wide on Android Chrome before desktop polish.
