import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The server runs on :8000; the browser only talks to this origin, so the cloudflared tunnel
// (make tunnel) needs one HTTPS URL per site and no CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
    allowedHosts: [".trycloudflare.com"],
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
  test: {
    environment: "jsdom",
  },
});
