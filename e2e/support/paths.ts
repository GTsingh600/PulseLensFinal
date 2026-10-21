import path from "node:path";

/** Where the server started by Playwright keeps its sessions: away from data/sessions (volunteer data). */
export const E2E_DATA_DIR = path.resolve("data", "e2e");
