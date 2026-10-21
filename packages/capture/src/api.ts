// REST and WebSocket clients for the capture device (SPEC 6).
import type {
  CameraDetails, CaptureClientMessage, CaptureServerMessage, SessionCreate, SessionCreated,
} from "@pulselens/types";
import { now } from "./clock";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export class CaptureApi {
  constructor(private readonly base = "") {}

  private async request<T>(path: string, init: RequestInit): Promise<T> {
    const r = await fetch(`${this.base}${path}`, init);
    if (!r.ok) throw new ApiError(r.status, `${init.method} ${path} → ${r.status} ${await r.text().catch(() => "")}`);
    const text = await r.text();
    return (text ? JSON.parse(text) : undefined) as T;
  }

  private json<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  }

  createSession(body: SessionCreate): Promise<SessionCreated> {
    return this.json("/api/sessions", body);
  }

  /** Full details first, then partial updates as later stages measure more. */
  postDetails(sessionId: string, details: Partial<CameraDetails>): Promise<void> {
    return this.json(`/api/sessions/${sessionId}/details`, details);
  }

  /** probe.jsonl rows (SPEC 7.3), one JSON object per line. */
  postProbe(sessionId: string, rows: object[]): Promise<void> {
    return this.request(`/api/sessions/${sessionId}/probe`, {
      method: "POST",
      headers: { "Content-Type": "application/x-ndjson" },
      body: rows.map((r) => `${JSON.stringify(r)}\n`).join(""),
    });
  }

  postFrames(sessionId: string, body: FormData): Promise<void> {
    return this.request(`/api/sessions/${sessionId}/frames`, { method: "POST", body });
  }

  finalize(sessionId: string, summary: Record<string, unknown>): Promise<void> {
    return this.json(`/api/sessions/${sessionId}/finalize`, summary);
  }
}

export type CaptureRole = "customer" | "lab";

/** The capture device's end of /ws/session/{id}. Heartbeats every 2 s. */
export class CaptureSocket {
  onClose?: () => void;
  private heartbeat: ReturnType<typeof setInterval> | undefined;
  private handler?: (msg: CaptureServerMessage, receivedAt: number) => void;
  /** Messages that arrive before a handler is attached (the server may send right after open). */
  private early: [CaptureServerMessage, number][] = [];

  set onMessage(handler: (msg: CaptureServerMessage, receivedAt: number) => void) {
    this.handler = handler;
    for (const [msg, at] of this.early.splice(0)) handler(msg, at);
  }

  private constructor(private readonly ws: WebSocket) {
    ws.onmessage = (e) => {
      const receivedAt = now(); // pulse `received` time: taken before any parsing
      let msg: CaptureServerMessage;
      try {
        msg = JSON.parse(String(e.data)) as CaptureServerMessage;
      } catch (err) {
        console.warn("Bad server message", err, e.data);
        return;
      }
      if (this.handler) this.handler(msg, receivedAt);
      else this.early.push([msg, receivedAt]);
    };
    ws.onclose = () => {
      clearInterval(this.heartbeat);
      this.onClose?.();
    };
    this.heartbeat = setInterval(() => this.send({ type: "heartbeat", t: now() }), 2000);
  }

  /** `token` (SessionCreated.token) is required for the lab role, which receives every event; customers have none. */
  static connect(wsPath: string, role: CaptureRole, token?: string): Promise<CaptureSocket> {
    const url = new URL(wsPath, location.href);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.searchParams.set("role", role);
    if (token && role === "lab") url.searchParams.set("token", token);
    const ws = new WebSocket(url);
    return new Promise((resolve, reject) => {
      ws.onopen = () => resolve(new CaptureSocket(ws));
      ws.onerror = () => reject(new Error(`WebSocket ${url.pathname} failed to open`));
    });
  }

  send(msg: CaptureClientMessage): void {
    if (this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(msg));
  }

  close(): void {
    clearInterval(this.heartbeat);
    this.ws.close();
  }
}
