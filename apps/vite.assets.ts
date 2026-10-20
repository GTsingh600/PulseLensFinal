// Dev-server plugin shared by both apps: serves the MediaPipe tasks-vision wasm from node_modules at
// /mediapipe/wasm/ and the gitignored models/ folder at /models/, so coaching works offline at the venue.
import { createReadStream, existsSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Plugin } from "vite";

const root = fileURLToPath(new URL("..", import.meta.url));
const MOUNTS: [string, string][] = [
  ["/mediapipe/wasm/", path.join(root, "node_modules/@mediapipe/tasks-vision/wasm")],
  ["/models/", path.join(root, "models")],
];
const TYPES: Record<string, string> = { ".wasm": "application/wasm", ".js": "text/javascript" };

export function pulselensAssets(): Plugin {
  return {
    name: "pulselens-assets",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = decodeURIComponent((req.url ?? "").split("?")[0]!);
        for (const [prefix, dir] of MOUNTS) {
          if (!url.startsWith(prefix)) continue;
          const file = path.resolve(dir, `.${url.slice(prefix.length - 1)}`);
          if (!file.startsWith(dir + path.sep) || !existsSync(file) || !statSync(file).isFile()) break;
          res.setHeader("Content-Type", TYPES[path.extname(file)] ?? "application/octet-stream");
          createReadStream(file).pipe(res);
          return;
        }
        next();
      });
    },
  };
}
