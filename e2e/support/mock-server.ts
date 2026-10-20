/**
 * A stand-in for the PulseLens server inside Playwright: the REST routes and /ws/session/{id} the capture
 * device uses (SPEC 6), and the M1.2 orchestrator stub (camera stage, coach, then the light suite).
 *
 * It intercepts the page's requests, so tests of the capture device don't depend on the Python server, and
 * it writes what it receives as a SPEC 4.1 session bundle (meta.json, frames/, fp/, frames.jsonl, pulses.jsonl)
 * that the analysis CLI (M1.5) can read. Track C: the real server must accept exactly these messages.
 */
import { createHmac, randomBytes } from "node:crypto";
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import type { Page, WebSocketRoute } from "@playwright/test";
import { config } from "../../packages/types/src/config.gen";
import type {
  CameraDetails, CaptureClientMessage, CaptureServerMessage, FrameMeta, LightParams, PulseAck, PulseMessage,
  SessionCreate, StageDone,
} from "../../packages/types/src/index";

const SECRET = "e2e-test-secret";
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function shuffle<T>(xs: T[]): T[] {
  const a = [...xs];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j]!, a[i]!];
  }
  return a;
}

/** The light suite from config: colour pulses over the isoluminant hues, split pairs, white pulses, shuffled. */
export function lightSuite(): LightParams[] {
  const c = config.pulses.light;
  const hues = Array.from({ length: c.colour }, (_, k) => (360 * k) / c.colour);
  const base = { duration_ms: c.duration_ms, hue_deg: null, left_hue_deg: null, right_hue_deg: null };
  const colour = hues.map((h): LightParams => ({ ...base, mode: "colour", hue_deg: h }));
  const split = Array.from({ length: c.split }, (_, k): LightParams => {
    const left = hues[(2 * k) % hues.length]!;
    return { ...base, mode: "split", left_hue_deg: left, right_hue_deg: (left + 180) % 360 };
  });
  const white = Array.from({ length: c.white }, (): LightParams => ({ ...base, mode: "white" }));
  return shuffle([...colour, ...split, ...white]);
}

export class MockServer {
  sessionId = "";
  bundle = "";
  create: SessionCreate | null = null;
  detailPosts: Partial<CameraDetails>[] = [];
  frames: FrameMeta[] = [];
  workingFiles: string[] = [];
  fpFiles: string[] = [];
  released: PulseMessage[] = [];
  acks: PulseAck[] = [];
  stagesDone: StageDone[] = [];
  heartbeats = 0;
  finalized: Record<string, unknown> | null = null;
  roles: string[] = [];
  private waiters: { pred: (m: CaptureClientMessage) => boolean; resolve: (m: CaptureClientMessage) => void }[] = [];

  constructor(private readonly dir: string) {}

  get details(): Partial<CameraDetails> {
    return Object.assign({}, ...this.detailPosts);
  }

  async install(page: Page): Promise<void> {
    await page.route("**/api/sessions", async (route) => {
      this.create = route.request().postDataJSON() as SessionCreate;
      this.sessionId = `e2e-${randomBytes(4).toString("hex")}`;
      this.bundle = path.join(this.dir, this.sessionId);
      mkdirSync(path.join(this.bundle, "frames"), { recursive: true });
      mkdirSync(path.join(this.bundle, "fp"), { recursive: true });
      await route.fulfill({
        json: { session_id: this.sessionId, pair_code: "ABC123", ws_url: `/ws/session/${this.sessionId}` },
      });
    });
    await page.route("**/api/sessions/*/details", async (route) => {
      this.detailPosts.push(route.request().postDataJSON() as Partial<CameraDetails>);
      await route.fulfill({ status: 204 });
    });
    await page.route("**/api/sessions/*/frames", async (route) => {
      const req = route.request();
      const form = await new Response(req.postDataBuffer(), {
        headers: { "content-type": (await req.headerValue("content-type")) ?? "" },
      }).formData();
      const metas = String(form.get("meta")).trim().split("\n").map((l) => JSON.parse(l) as FrameMeta);
      this.frames.push(...metas);
      appendFileSync(path.join(this.bundle, "frames.jsonl"), metas.map((m) => JSON.stringify(m) + "\n").join(""));
      for (const [field, folder, list] of [["frames", "frames", this.workingFiles], ["fp", "fp", this.fpFiles]] as const) {
        for (const f of form.getAll(field) as File[]) {
          writeFileSync(path.join(this.bundle, folder, f.name), Buffer.from(await f.arrayBuffer()));
          list.push(f.name);
        }
      }
      await route.fulfill({ status: 204 });
    });
    await page.route("**/api/sessions/*/finalize", async (route) => {
      this.finalized = route.request().postDataJSON() as Record<string, unknown>;
      this.writeBundle();
      await route.fulfill({ status: 204 });
    });
    await page.routeWebSocket(/\/ws\/session\//, (ws) => this.orchestrate(ws));
  }

  private waitFor(pred: (m: CaptureClientMessage) => boolean, timeoutMs = 30_000): Promise<CaptureClientMessage> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("mock server: timed out waiting for the client")), timeoutMs);
      this.waiters.push({ pred, resolve: (m) => (clearTimeout(timer), resolve(m)) });
    });
  }

  private orchestrate(ws: WebSocketRoute): void {
    this.roles.push(new URL(ws.url()).searchParams.get("role") ?? "");
    const send = (m: CaptureServerMessage) => ws.send(JSON.stringify(m));
    ws.onMessage((raw) => {
      const m = JSON.parse(String(raw)) as CaptureClientMessage;
      if (m.type === "heartbeat") this.heartbeats++;
      if (m.type === "ack") this.acks.push(m);
      if (m.type === "stage.done") this.stagesDone.push(m);
      this.waiters = this.waiters.filter((w) => (w.pred(m) ? (w.resolve(m), false) : true));
    });
    void (async () => {
      send({ type: "stage", stage: "camera", prompt: null });
      await this.waitFor((m) => m.type === "stage.done" && m.stage === "camera");
      send({ type: "stage", stage: "coach", prompt: null });
      await this.waitFor((m) => m.type === "stage.done" && m.stage === "coach");
      send({ type: "stage", stage: "pulses", prompt: "prompt.light" });
      const [gapLo, gapHi] = config.pulses.light.gap_ms;
      for (const [k, params] of lightSuite().entries()) {
        await sleep(gapLo + Math.random() * (gapHi - gapLo));
        const pulse_id = `${this.sessionId}-L${k}`;
        const sig = createHmac("sha256", SECRET)
          .update(`${pulse_id}|light|${JSON.stringify(params)}|${this.sessionId}`)
          .digest("hex");
        const msg: PulseMessage = { type: "pulse", pulse_id, kind: "light", source: "orchestrator", params: { ...params }, sig };
        this.released.push(msg);
        send(msg);
        await this.waitFor((m) => m.type === "ack" && m.pulse_id === pulse_id);
      }
      send({ type: "done", key: "prompt.done" });
    })().catch((e) => console.error(e));
  }

  /** meta.json and pulses.jsonl (SPEC 4.1); frames and frames.jsonl are written as batches arrive. */
  private writeBundle(): void {
    const meta = {
      session_id: this.sessionId, mode: this.create?.mode, scenario: this.create?.scenario, product: this.create?.product,
      label: this.create?.label ?? null, camera_details: this.details, stages_done: this.stagesDone,
      finalize: this.finalized, source: "e2e mock server",
    };
    writeFileSync(path.join(this.bundle, "meta.json"), JSON.stringify(meta, null, 2));
    const lines = this.released.map((p) => {
      const a = this.acks.find((x) => x.pulse_id === p.pulse_id);
      return JSON.stringify({
        pulse_id: p.pulse_id, kind: p.kind, source: p.source, params: p.params, received: a?.received ?? null,
        applied: a?.applied ?? null, painted: a?.painted ?? null, ended: a?.ended ?? null, ok: a?.ok ?? false,
        sig: p.sig, shown: a?.shown ?? null, error: a?.error ?? null,
      });
    });
    writeFileSync(path.join(this.bundle, "pulses.jsonl"), lines.map((l) => l + "\n").join(""));
  }
}
