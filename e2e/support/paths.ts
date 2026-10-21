import path from "node:path";

/** Where the server started by Playwright keeps its sessions: away from data/sessions (volunteer data). */
export const E2E_DATA_DIR = path.resolve("data", "e2e");

/** The local-only replay video for the brave-replay project (scripts/bundle_to_y4m.py); never committed. */
export const REPLAY_Y4M = path.resolve(process.env.REPLAY_Y4M ?? path.join("data", "local", "replay.y4m"));
